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


# check the link for comments
# https://github.com/divmain/GitSavvy/blob/599ba3cdb539875568a96a53fafb033b01708a67/common/util/reload.py

def reload_package(pkg_name):
    if pkg_name not in sys.modules:
        dprint("ERROR:", pkg_name, "is not loaded.")
        return

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

    # a hack to trigger automatic "reloading plugins"
    # this is needed to ensure TextCommand's and WindowCommand's are ready.
    dummy = os.path.join(sublime.packages_path(), "_moduler_reloader.py")
    open(dummy, "w").close()
    sublime.set_timeout(lambda: os.path.exists(dummy) and os.unlink(dummy), 100)
    sublime.set_timeout(lambda: sublime.status_message("Module Reloaded."), 500)


def ensure_loaded(main, modules):
    missing_modules = {name: module for name, module in modules.items()
                       if name not in sys.modules}
    if missing_modules:
        for name, module in missing_modules:
            sys.modules[name] = modules
            dprint("Error:", "Bug!", "restored", name)
        reload_plugin(main.__name__)


def reload_modules(main, modules, perform_reload=True):

    if perform_reload:
        sublime_plugin.unload_module(main)

    module_names = [main.__name__] + sorted(name for name in modules
                                            if name != main.__name__)

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
                dprint("No Reload", '---', name)
            return module

    with intercepting_imports(module_reloader), importing_fromlist_aggresively(modules):
        reload_plugin(main.__name__)
        for name in module_names:
            importlib.import_module(name)


def reload_plugin(pkg_name):
    pkg_path = os.path.join(os.path.realpath(sublime.packages_path()), pkg_name)
    if os.path.exists(os.path.join(pkg_path, "__init__.py")):
        sublime_plugin.reload_plugin(pkg_name)
    else:
        plugins = [pkg_name + "." + os.path.splitext(f)[0]
                   for f in os.listdir(pkg_path) if f.endswith(".py")]
        for plugin in plugins:
            sublime_plugin.reload_plugin(plugin)


@contextmanager
def importing_fromlist_aggresively(modules):
    orig___import__ = builtins.__import__

    @functools.wraps(orig___import__)
    def __import__(name, globals=None, locals=None, fromlist=(), level=0):
        module = orig___import__(name, globals, locals, fromlist, level)
        if fromlist and module.__name__ in modules:
            if '*' in fromlist:
                fromlist = list(fromlist)
                fromlist.remove('*')
                fromlist.extend(getattr(module, '__all__', []))
            for x in fromlist:
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
