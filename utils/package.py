import sublime

import os
import sys
import re
from glob import glob


if sys.platform.startswith("win"):
    def realpath(path):
        # path on Windows may not be properly cased
        # https://github.com/randy3k/AutomaticPackageReloader/issues/10
        r = glob(re.sub(r'([^:/\\])(?=[/\\]|$)', r'[\1]', os.path.realpath(path)))
        return r and r[0] or path
else:
    def realpath(path):
        return os.path.realpath(path)


def package_of(path):
    spp = sublime.packages_path()
    spp_real = realpath(spp)
    for p in {path, realpath(path)}:
        for sp in {spp, spp_real}:
            if p.startswith(sp + os.sep):
                return p[len(sp):].split(os.sep)[1]

    if not sys.platform.startswith("win"):
        # we try to follow symlink if the real file is not located in spp
        for d in os.listdir(spp):
            subdir = os.path.join(spp, d)
            subdir_real = realpath(subdir)
            if not (os.path.islink(subdir) and os.path.isdir(subdir)):
                continue
            for sd in {subdir, subdir_real}:
                for p in {path, realpath(path)}:
                    if p.startswith(sd + os.sep):
                        return d

    return None


def has_package(package):
    zipped_file = os.path.join(
        sublime.installed_packages_path(), "{}.sublime-package".format(package))
    unzipped_folder = os.path.join(sublime.packages_path(), package)
    if not os.path.exists(zipped_file) and not os.path.exists(unzipped_folder):
        return False
    preferences = sublime.load_settings("Preferences.sublime-settings")
    if package in preferences.get("ignored_packages", []):
        return False
    return True


def package_python_version(package):
    try:
        version = sublime.load_resource("Packages/{}/.python-version".format(package))
    except (FileNotFoundError, IOError):
        version = "3.3"
    return version


def package_python_matched(package):
    ver = package_python_version(package)
    if sys.version_info >= (3, 8) and ver == "3.8":
        return True
    if sys.version_info >= (3, 3) and ver == "3.3":
        return True
    return False
