import sublime_plugin
import sublime
import os
import sys
import shutil
from glob import glob
import re
from threading import Thread, Lock

from .reloader import reload_package
from .utils import ProgressBar


try:
    reload_lock  # Preserve same lock across reloads
except NameError:
    reload_lock = Lock()


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


class PackageReloaderListener(sublime_plugin.EventListener):

    def on_post_save(self, view):
        if view.is_scratch() or view.settings().get('is_widget'):
            return
        file_name = view.file_name()

        if file_name and file_name.endswith(".py") and package_of(file_name):
            package_reloader_settings = sublime.load_settings("package_reloader.sublime-settings")
            if package_reloader_settings.get("reload_on_save"):
                view.window().run_command("package_reloader_reload")


class PackageReloaderToggleReloadOnSaveCommand(sublime_plugin.WindowCommand):

    def run(self):
        package_reloader_settings = sublime.load_settings("package_reloader.sublime-settings")
        reload_on_save = not package_reloader_settings.get("reload_on_save")
        package_reloader_settings.set("reload_on_save", reload_on_save)
        onoff = "on" if reload_on_save else "off"
        sublime.status_message("Package Reloader: Reload on Save is %s." % onoff)


class PackageReloaderReloadCommand(sublime_plugin.WindowCommand):
    @property
    def current_package_name(self):
        view = self.window.active_view()
        if view and view.file_name():
            file_path = view.file_name()
            package = package_of(file_path)
            if package and file_path.endswith(".py"):
                return package

        folders = self.window.folders()
        if folders and len(folders) > 0:
            package = package_of(folders[0])
            if package:
                return package

        return None

    def prompt_package(self, callback):
        package = self.current_package_name
        if not package:
            package = ""
        view = sublime.active_window().show_input_panel(
            'Package:', package, callback, None, None)
        view.run_command("select_all")

    def package_python_version(self, pkg_name):
        try:
            version = sublime.load_resource("Packages/{}/.python-version".format(pkg_name))
        except FileNotFoundError:
            version = "3.3"
        return version

    def run(self, pkg_name=None):
        if pkg_name == "<prompt>":
            self.prompt_package(lambda x: self.run(pkg_name=x))
            return

        if pkg_name is None:
            pkg_name = self.current_package_name
            if pkg_name is None:
                print("Cannot detect package name.")
                return

        if sys.version_info >= (3, 8) and self.package_python_version(pkg_name) == "3.3":
            print("run reloader in python 3.3")
            self.window.run_command("package_reloader33_reload", {"pkg_name": pkg_name})
            return

        Thread(
            name="AutomaticPackageReloader",
            target=self.run_async,
            args=(pkg_name,)
        ).start()

    def run_async(self, pkg_name):
        lock = reload_lock  # In case we're reloading AutoPackageReloader
        if not lock.acquire(blocking=False):
            print("Reloader is running.")
            return

        pr_settings = sublime.load_settings("package_reloader.sublime-settings")
        open_console = pr_settings.get("open_console")
        open_console_on_failure = pr_settings.get("open_console_on_failure")
        close_console_on_success = pr_settings.get("close_console_on_success")

        progress_bar = ProgressBar("Reloading %s" % pkg_name)
        progress_bar.start()

        console_opened = self.window.active_panel() == "console"
        if not console_opened and open_console:
            self.window.run_command("show_panel", {"panel": "console"})
        try:
            reload_package(pkg_name, verbose=pr_settings.get('verbose'))
            if close_console_on_success:
                self.window.run_command("hide_panel", {"panel": "console"})

            sublime.status_message("{} reloaded.".format(pkg_name))
        except Exception:
            if open_console_on_failure:
                self.window.run_command("show_panel", {"panel": "console"})
            sublime.status_message("Fail to reload {}.".format(pkg_name))
            raise
        finally:
            progress_bar.stop()
            lock.release()

        # helper to reload ourself
        if sys.version_info >= (3, 8) and pkg_name == "AutomaticPackageReloader":
            sublime.set_timeout(lambda: sublime.active_window().run_command(
                "package_reloader33_reload", {"pkg_name": "AutomaticPackageReloader33"}))


def plugin_loaded():
    if sys.version_info >= (3, 8):
        APR33 = os.path.join(sublime.packages_path(), "AutomaticPackageReloader33")
        if not os.path.exists(APR33):
            os.makedirs(APR33)
        data = sublime.load_resource("Packages/AutomaticPackageReloader/py33/package_reloader.py")
        with open(os.path.join(APR33, "package_reloader.py"), 'w') as f:
            f.write(data.replace("\r\n", "\n"))
        with open(os.path.join(APR33, ".package-reloader"), 'w') as f:
            f.write("AutomaticPackageReloader")


def plugin_unloaded():
    if sys.version_info >= (3, 8):
        APR33 = os.path.join(sublime.packages_path(), "AutomaticPackageReloader33")
        lock = reload_lock
        # do not remove AutomaticPackageReloader33 if it is being reloaded by APR
        if os.path.exists(APR33) and lock.acquire(blocking=False):
            try:
                shutil.rmtree(APR33)
            except Exception:
                pass
