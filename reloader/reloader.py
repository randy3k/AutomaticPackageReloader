import functools
import os
import posixpath
import sys

import sublime
import sublime_plugin

from .dprint import dprint
from .importer import ReloadingImporter
from .resolver import resolve_parents
from ..utils.package import package_python_matched


def get_package_modules(package_names):
    package_names = set(package_names)
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

    @functools.lru_cache(1024)
    def _package_python_matched(package):
        return package_python_matched(package)

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
            pkg_name = module.__name__.split(".")[0]
            is_plugin = (os.path.dirname(path) == base) and _package_python_matched(pkg_name)
            yield module.__name__, is_plugin

    # get all the top level plugins in case they were removed from sys.modules
    for path in sublime.find_resources("*.py"):
        for pkg_name in package_names:
            if not _package_python_matched(pkg_name):
                continue
            if posixpath.dirname(path) == 'Packages/'+pkg_name:
                yield pkg_name + '.' + posixpath.basename(posixpath.splitext(path)[0]), True


def reload_package(package, dependencies=[], extra_modules=[], verbose=True):
    if verbose:
        dprint("begin", fill='=')

    packages = [package] + dependencies
    parents = set()
    for package in packages:
        for parent in resolve_parents(package):
            parents.add(parent)
    parents = list(parents)

    modules = sorted(
        list(set(get_package_modules(packages + parents))),
        key=lambda x: x[0].split('.')
    )

    plugins = [m for m, is_plugin in modules if is_plugin]
    # Tell Sublime to unload plugin_modules
    for plugin in plugins:
        if plugin in sys.modules:
            sublime_plugin.unload_module(sys.modules[plugin])

    # these are modules marked to be reloaded, they are not necessarily reloaded
    modules_to_reload = [sys.modules[m] for m, is_plugin in modules if m in sys.modules]
    extra_modules_to_reload = [sys.modules[m] for m in extra_modules if m in sys.modules]

    with ReloadingImporter(modules_to_reload + extra_modules_to_reload, verbose) as importer:
        if plugins:
            # we only reload top level plugin_modules to mimic Sublime Text natural order
            for plugin in plugins:
                if plugin in sys.modules:
                    module = sys.modules[plugin]
                    importer.reload(module)

            for plugin in plugins:
                if plugin in sys.modules:
                    module = sys.modules[plugin]
                    sublime_plugin.load_module(module)
                else:
                    # in case we missed something
                    sublime_plugin.reload_plugin(plugin)
        else:
            # it is possibly a dependency but no packages use it
            for module in modules_to_reload:
                importer.reload(module)

        for module in extra_modules_to_reload:
            importer.reload(module)

    if verbose:
        dprint("end", fill='-')
