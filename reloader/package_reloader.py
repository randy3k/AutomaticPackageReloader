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


def dprint(*args, fill=None, fill_width=60, **kwargs):
    if fill is not None:
        sep = str(kwargs.get('sep', ' '))
        caption = sep.join(args)
        args = "{0:{fill}<{width}}".format(caption and caption + sep,
                                           fill=fill, width=fill_width),
    print("[Package Reloader]", *args, **kwargs)


# check the link for comments
# https://github.com/divmain/GitSavvy/blob/599ba3cdb539875568a96a53fafb033b01708a67/common/util/reload.py
def reload_package(pkg_name):
    if pkg_name not in sys.modules:
        dprint("error:", pkg_name, "is not loaded.")
        return

    main = sys.modules[pkg_name]

    dprint("begin", fill='=')

    modules = {name: module for name, module in sys.modules.items()
               if name.startswith(pkg_name + ".")}
    try:
        reload_modules(main, modules)
    except:
        dprint("reload failed.", fill='-')
        sublime.set_timeout(
            lambda: sublime.status_message("Fail to reload {}.".format(pkg_name)), 500)
        raise

    check_missing(modules)
    finalize_reload(main)


def finalize_reload(main):
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


def check_missing(modules):
    missing_modules = {name: module for name, module in modules.items()
                       if name not in sys.modules}
    if missing_modules:
        for name in missing_modules:
            dprint("note:", name, "is not reloaded.")


def reload_plugin(pkg_name):
    pkg_path = os.path.join(os.path.realpath(sublime.packages_path()), pkg_name)
    plugins = [pkg_name + "." + os.path.splitext(f)[0]
               for f in os.listdir(pkg_path) if f.endswith(".py")]
    for plugin in plugins:
        sublime_plugin.reload_plugin(plugin)


def reload_modules(main, modules):

    sublime_plugin.unload_module(main)
    for m in modules:
        if m in sys.modules:
            sublime_plugin.unload_module(modules[m])

    loaded_modules = dict(sys.modules)
    for name in loaded_modules:
        if name in modules:
            del sys.modules[name]

    with intercepting_imports(modules), \
            importing_fromlist_aggresively(modules):

        reload_plugin(main.__name__)


@contextmanager
def intercepting_imports(modules):
    finder = FilterFinder(modules)
    sys.meta_path.insert(0, finder)
    try:
        yield
    finally:
        if finder in sys.meta_path:
            sys.meta_path.remove(finder)


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


class FilterFinder:
    def __init__(self, modules):
        self._modules = modules
        self._stack_meter = StackMeter()

    def find_module(self, name, path=None):
        if name in self._modules:
            return self

    def load_module(self, name):
        module = self._modules[name]
        sys.modules[name] = module  # restore the module back
        with self._stack_meter as depth:
            dprint("reloading", ('| '*depth) + '|--', name)
            try:
                return module.__loader__.load_module(name)
            except:
                if name in sys.modules:
                    del sys.modules[name]  # to indicate an error
                raise
