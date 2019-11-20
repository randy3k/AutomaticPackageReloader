import sys
from importlib.machinery import PathFinder


loader = PathFinder.find_module("AutomaticPackageReloader")
mod = loader.load_module("AutomaticPackageReloader")
sys.modules["AutomaticPackageReloader"] = mod

from AutomaticPackageReloader.package_reloader import PackageReloaderReloadCommand  # noqa


class PackageReloader33ReloadCommand(PackageReloaderReloadCommand):
    pass
