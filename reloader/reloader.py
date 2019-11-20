import sublime
import sublime_plugin
import os
import os.path
import threading
import sys

from .dprint import dprint
from .importer import ReloadingImporter
from .resolver import resolve_dependencies


def get_package_modules(package_names):
    package_path_bases = [
        p
        for pkg_name in package_names
        for p in (
            os.path.join(
                sublime.installed_packages_path(),
                pkg_name + '.sublime-package'
            ),
            os.path.join(sublime.packages_path(), pkg_name),
        )
    ]

    def module_paths(module):
        try:
            yield module.__file__
        except AttributeError:
            pass

        try:
            yield from module.__path__
        except AttributeError:
            pass

    for module in sys.modules.values():
        try:
            base, path = next(
                (base, path)
                for path in module_paths(module)
                for base in package_path_bases
                if path and (path == base or path.startswith(base + os.sep))
            )
        except StopIteration:
            continue
        else:
            is_plugin = (os.path.dirname(path) == base)
            yield module, is_plugin


def reload_package(pkg_name, dummy=True, verbose=True):
    if pkg_name not in sys.modules:
        dprint("error:", pkg_name, "is not loaded.")
        return

    if verbose:
        dprint("begin", fill='=')

    packages = resolve_dependencies(pkg_name)
    modules = list(get_package_modules(packages))

    sorted_modules = sorted(
        [module for module, is_plugin in modules],
        key=lambda module: module.__name__.split('.')
    )

    plugins = [
        module
        for module, is_plugin in modules
        if is_plugin
    ]

    # Tell Sublime to unload plugins
    for module in plugins:
        sublime_plugin.unload_module(module)

    with ReloadingImporter(sorted_modules, verbose) as reload:
        for module in sorted_modules:
            reload(module)

    for module in plugins:
        sublime_plugin.load_module(module)

    if dummy:
        load_dummy(verbose)

    if verbose:
        dprint("end", fill='-')


def load_dummy(verbose):
    """
    Hack to trigger automatic "reloading plugins".

    This is needed to ensure TextCommand's and WindowCommand's are ready.
    """
    if verbose:
        dprint("installing dummy package")

    if sys.version_info >= (3, 8):
        # in ST 4, User package is always loaded in python 3.8
        dummy_name = "User._dummy"
        dummy_py = os.path.join(sublime.packages_path(), "User", "_dummy.py")
    else:
        # in ST 4, packages under Packages are always loaded in python 3.3
        dummy_name = "_dummy"
        dummy_py = os.path.join(sublime.packages_path(), "_dummy.py")

    with open(dummy_py, "w"):
        pass

    def remove_dummy(trial=0):
        if dummy_name in sys.modules:
            if verbose:
                dprint("removing dummy package")
            try:
                os.unlink(dummy_py)
            except FileNotFoundError:
                pass
            after_remove_dummy()
        elif trial < 300:
            threading.Timer(0.1, lambda: remove_dummy(trial + 1)).start()
        else:
            try:
                os.unlink(dummy_py)
            except FileNotFoundError:
                pass

    condition = threading.Condition()

    def after_remove_dummy(trial=0):
        if dummy_name not in sys.modules:
            condition.acquire()
            condition.notify()
            condition.release()
        elif trial < 300:
            threading.Timer(0.1, lambda: after_remove_dummy(trial + 1)).start()

    threading.Timer(0.1, remove_dummy).start()
    condition.acquire()
    condition.wait(30)  # 30 seconds should be enough for all regular usages
    condition.release()
