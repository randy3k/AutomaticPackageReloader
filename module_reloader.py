import sublime_plugin
import sublime
import builtins
import functools
import importlib
import sys
import types
from contextlib import contextmanager
import os


def trace(*args, tag="debug", fill=None, fill_width=60, **kwargs):
    """
    Lightweight logging facility. Provides simple print-like interface with
    filtering by tags and pretty-printed captions for delimiting output
    sections.

    See the "dev_trace" setting for possible values of the "tag" keyword.
    """

    if fill is not None:
        sep = str(kwargs.get('sep', ' '))
        caption = sep.join(args)
        args = "{0:{fill}<{width}}".format(caption and caption + sep,
                                           fill=fill, width=fill_width),
    print("[{}]".format(tag), *args, **kwargs)


dprint = functools.partial(trace, tag="Module Reloader")


def expand_folder(folder, project_file):
    if project_file:
        root = os.path.dirname(project_file)
        if not os.path.isabs(folder):
            folder = os.path.abspath(os.path.join(root, folder))
    return folder


class ModuleReloaderListener(sublime_plugin.EventListener):

    def on_post_save(self, view):
        if view.is_scratch() or view.settings().get('is_widget'):
            return False
        module_reloader_settings = sublime.load_settings("module_reloader.sulime-settings")
        if module_reloader_settings.get("reload_on_save"):
            sublime.set_timeout_async(view.window().run_command("module_reloader_reload"))


class ModuleReloaderToggleReloadOnSaveCommand(sublime_plugin.WindowCommand):

    def run(self):
        module_reloader_settings = sublime.load_settings("module_reloader.sulime-settings")
        reload_on_save = not module_reloader_settings.get("reload_on_save", False)
        module_reloader_settings.set("reload_on_save", reload_on_save)
        onoff = "on" if reload_on_save else "off"
        sublime.status_message("Module Reloader: Reload On Save is %s." % onoff)


class ModuleReloaderReloadCommand(sublime_plugin.WindowCommand):

    def run(self, pkg_name=None):
        spp = os.path.realpath(sublime.packages_path())

        if not pkg_name:
            view = self.window.active_view()
            file_name = view.file_name()
            if file_name:
                file_name = os.path.realpath(file_name)
                if file_name and file_name.endswith(".py") and spp in file_name:
                    pkg_name = file_name.replace(spp, "").split(os.sep)[1]

        if not pkg_name:
            pd = self.window.project_data()
            if pd and "folders" in pd and pd["folders"]:
                folder = pd["folders"][0].get("path", "")
                path = expand_folder(folder, self.window.project_file_name())
                pkg_name = path.replace(spp, "").split(os.sep)[1]

        if pkg_name:
            sublime.set_timeout_async(lambda: reload_package(pkg_name))


# https://github.com/divmain/GitSavvy/blob/599ba3cdb539875568a96a53fafb033b01708a67/common/util/reload.py

def reload_package(pkg_name):
    if pkg_name not in sys.modules:
        dprint("ERROR", pkg_name, "is not loaded.")
        return

    # we need to disable and reenable the package enable to make sure
    # the TextCommand's and WindowCommand's would be loaded.
    psettings = sublime.load_settings("Preferences.sublime-settings")
    ignored_packages = psettings.get("ignored_packages", [])
    ignored_packages.append(pkg_name)
    psettings.set("ignored_packages", ignored_packages)

    main = sys.modules[pkg_name]
    dprint("begin", fill='=')

    modules = {name: module for name, module in sys.modules.items()
               if name.startswith(pkg_name + ".")}
    try:
        reload_modules(main, modules)
    except:
        dprint("ERROR", fill='-')
        reload_modules(main, modules, perform_reload=False)
        raise
    finally:
        ensure_loaded(main, modules)

    dprint("end", fill='-')

    ignored_packages.pop(-1)
    psettings.set("ignored_packages", ignored_packages)

    sublime.set_timeout(lambda: sublime.status_message("Module Reloaded."), 500)


def ensure_loaded(main, modules):
    # More simple (comparing to reload_modules(perform_reload=False)) and dumb
    # approach to ensure all modules are back. Quite useful when debugging the
    # "reload" module itself, i.e. for cases when reloading might fail due to
    # bugs in reload_modules().
    missing_modules = {name: module for name, module in modules.items()
                       if name not in sys.modules}
    if missing_modules:
        for name, module in missing_modules:
            sys.modules[name] = modules
            dprint("Error", "Bug!", "restored", name)
        sublime_plugin.reload_plugin(main.__name__)


def reload_modules(main, modules, perform_reload=True):
    """Implements the machinery for reloading a given plugin module."""
    #
    # Here's the approach in general:
    #
    #   - Hide GitSavvy modules from the sys.modules temporarily;
    #
    #   - Install a special import hook onto sys.meta_path;
    #
    #   - Call sublime_plugin.reload_plugin(), which imports the main
    #     "git_savvy" module under the hood, triggering the hook;
    #
    #   - The hook, instead of creating a new module object, peeks the saved
    #     one and reloads it. Once the module encounters an import statement
    #     requesting another module, not yet reloaded, the hook reenters and
    #     processes that new module recursively, then get back to the previous
    #     one, and so on.
    #
    # This makes the modules reload in the very same order as they were loaded
    # initially, as if they were imported from scratch.
    #
    if perform_reload:
        sublime_plugin.unload_module(main)

    # Insert the main "git_savvy" module at the beginning to make the reload
    # order be as close to the order of the "natural" import as possible.
    module_names = [main.__name__] + sorted(name for name in modules
                                            if name != main.__name__)

    # First, remove all the loaded modules from the sys.modules cache,
    # otherwise the reloading hook won't be called.
    loaded_modules = dict(sys.modules)
    for name in loaded_modules:
        if name in modules:
            del sys.modules[name]

    stack_meter = StackMeter()

    @FilteringImportHook.when(condition=lambda name: name in modules)
    def module_reloader(name):
        module = modules[name]
        sys.modules[name] = module  # restore the module back

        if perform_reload:
            with stack_meter as depth:
                dprint("reloading", ('| '*depth) + '|--', name)
                try:
                    return module.__loader__.load_module(name)
                except:
                    if name in sys.modules:
                        del sys.modules[name]  # to indicate an error
                    raise
        else:
            if name not in loaded_modules:
                dprint("NO RELOAD", '---', name)
            return module

    with intercepting_imports(module_reloader), importing_fromlist_aggresively(modules):
        # Now, import all the modules back, in order, starting with the main
        # module. This will reload all the modules directly or indirectly
        # referenced by the main one, i.e. usually most of our modules.
        sublime_plugin.reload_plugin(main.__name__)

        # Be sure to bring back *all* the modules that used to be loaded, not
        # only these imported through the main one. Otherwise, some of them
        # might end up being created from scratch as new module objects in
        # case of being imported after detaching the hook. In general, most of
        # the imports below (if not all) are no-ops though.
        for name in module_names:
            importlib.import_module(name)


@contextmanager
def importing_fromlist_aggresively(modules):
    orig___import__ = builtins.__import__

    @functools.wraps(orig___import__)
    def __import__(name, globals=None, locals=None, fromlist=(), level=0):
        # Given an import statement like this:
        #
        #     from .some.module import something
        #
        # The original __import__ performs roughly the following steps:
        #
        #   - Import ".some.module", just like the importlib.import_module()
        #     function would do, i.e. resolve packages, calculate the absolute
        #     name, check sys.modules for that module, invoke import hooks and
        #     so on...
        #
        #   - For each name specified in the "fromlist" (a "something" in our
        #     case), ensure the module have that name in its namespace. This
        #     could be:
        #
        #       - a regular name defined within that module, like a function
        #         named "something", and in this case we're done;
        #
        #       - or, in case the module is missing that attribute, there's a
        #         chance that the requested name refers to a submodule of that
        #         module, ".some.module.something", and we need to import it.
        #         Once imported it will take care to register itself within
        #         the parent's namespace.
        #
        # This looks natural and it is indeed in case of loading a module for
        # the first time. But things start to behave slightly different once
        # you try to reload a module.
        #
        # The main difference is that during the reload the module code is
        # executed with its dictionary retained. And this has an undesired
        # effect on handling the "fromlist" as described above: the second
        # part (involving import of a submodule) is only executed when the
        # module dictionary is missing the submodule name, which is not the
        # case during the reload.
        #
        # This is generally not a problem: the name refers to the submodule
        # imported earlier anyway. But we need to import it in order to force
        # the necessary hook to reload that submodule too.

        module = orig___import__(name, globals, locals, fromlist, level)
        if fromlist and module.__name__ in modules:
            # Refer to _handle_fromlist() from "importlib/_bootstrap.py"
            if '*' in fromlist:
                fromlist = list(fromlist)
                fromlist.remove('*')
                fromlist.extend(getattr(module, '__all__', []))
            for x in fromlist:
                # Here's an altered part of logic.
                #
                # The original __import__ doesn't even try to import a
                # submodule if its name is already in the module namespace,
                # but we do that for certain set of the known submodule.
                if isinstance(getattr(module, x, None), types.ModuleType):
                    from_name = '{}.{}'.format(module.__name__, x)
                    if from_name in modules:
                        importlib.import_module(from_name)
        return module

    builtins.__import__ = __import__
    try:
        yield
    finally:
        builtins.__import__ = orig___import__


@contextmanager
def intercepting_imports(hook):
    sys.meta_path.insert(0, hook)
    try:
        yield hook
    finally:
        if hook in sys.meta_path:
            sys.meta_path.remove(hook)


class FilteringImportHook:
    """
    PEP-302 importer that delegates loading of given modules to a function.
    """

    def __init__(self, condition, load_module):
        super().__init__()
        self.condition = condition
        self.load_module = load_module

    @classmethod
    def when(cls, condition):
        """A handy loader function decorator."""
        return lambda load_module: cls(condition, load_module)

    def find_module(self, name, path=None):
        if self.condition(name):
            return self


class StackMeter:
    """Reentrant context manager counting the reentrancy depth."""

    def __init__(self, depth=0):
        super().__init__()
        self.depth = depth

    def __enter__(self):
        depth = self.depth
        self.depth += 1
        return depth

    def __exit__(self, *exc_info):
        self.depth -= 1
