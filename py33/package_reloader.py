import sys
from importlib.machinery import PathFinder


loader = PathFinder.find_module("AutomaticPackageReloader")
mod = loader.load_module("AutomaticPackageReloader")
sys.modules["AutomaticPackageReloader"] = mod

from AutomaticPackageReloader import package_reloader as package_reloader38  # noqa


class PackageReloader33ReloadCommand(package_reloader38.PackageReloaderReloadCommand):
    pass
