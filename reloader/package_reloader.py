import sublime
import sublime_plugin
import os
import builtins
import functools
import importlib
import sys
import types
from contextlib import contextmanager
from .stack_meter import StackMeter


def trace(*args, tag="debug", fill=None, fill_width=60, **kwargs):
    if fill is not None:
        sep = str(kwargs.get('sep', ' '))
        caption = sep.join(args)
        args = "{0:{fill}<{width}}".format(caption and caption + sep,
                                           fill=fill, width=fill_width),
    print("[{}]".format(tag), *args, **kwargs)


dprint = functools.partial(trace, tag="Package Reloader")


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
        sublime.set_timeout(
            lambda: sublime.status_message("Fail to reload {}.".format(pkg_name)), 500)
        raise
    finally:
        ensure_loaded(main, modules)

    # a hack to trigger automatic "reloading plugins"
    # this is needed to ensure TextCommand's and WindowCommand's are ready.
    dprint("installing dummy package")
    dummy = "_dummy_package"
    dummy_py = os.path.join(sublime.packages_path(), "%s.py" % dummy)
    open(dummy_py, "w").close()

    def remove_dummy():
        if dummy in sys.modules:
            dprint("removing dummy package")
            if os.path.exists(dummy_py):
                os.unlink(dummy_py)
            after_remove_dummy()
        else:
            sublime.set_timeout_async(remove_dummy, 100)

    def after_remove_dummy():
        if dummy not in sys.modules:
            sublime.status_message("{} reloaded.".format(main.__name__))
            dprint("end", fill='-')
        else:
            sublime.set_timeout_async(after_remove_dummy, 100)

    sublime.set_timeout_async(remove_dummy, 100)


def ensure_loaded(main, modules):
    missing_modules = {name: module for name, module in modules.items()
                       if name not in sys.modules}
    if missing_modules:
        for name, module in missing_modules:
            sys.modules[name] = modules
            dprint("Error:", "Bug!", "restored", name)
        reload_plugin(main.__name__)


def reload_plugin(pkg_name):
    pkg_path = os.path.join(os.path.realpath(sublime.packages_path()), pkg_name)
    plugins = [pkg_name + "." + os.path.splitext(f)[0]
               for f in os.listdir(pkg_path) if f.endswith(".py")]
    for plugin in plugins:
        sublime_plugin.reload_plugin(plugin)


def reload_modules(main, modules, perform_reload=True):

    if perform_reload:
        sublime_plugin.unload_module(main)
        for m in modules:
            if m in sys.modules:
                sublime_plugin.unload_module(modules[m])

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
        module_names = sorted(name for name in modules)
        for name in module_names:
            importlib.import_module(name)


@contextmanager
def intercepting_imports(hook):
    sys.meta_path.insert(0, hook)
    try:
        yield
    finally:
        if hook in sys.meta_path:
            sys.meta_path.remove(hook)


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
