import sublime_plugin
import sublime
import os
import sys
import shutil
from threading import Thread, Lock

from .reloader import reload_package, load_dummy
from .utils import ProgressBar, read_config, has_package, package_of, package_python_version


try:
    reload_lock  # Preserve same lock across reloads
except NameError:
    reload_lock = Lock()


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

    def run(self, package=None, pkg_name=None, extra_pkgs=[], verbose=None):
        if package is None and pkg_name is not None:
            print("`pkg_name` is an deprecated option, use `package`.")
            package = pkg_name

        if package == "<prompt>":
            self.prompt_package(lambda x: self.run(package=x))
            return

        if package is None:
            package = self.current_package_name
            if package is None:
                print("Cannot detect package name.")
                return

        if not has_package(package):
            raise RuntimeError("{} is not installed.".format(package))

        if sys.version_info >= (3, 8) and package_python_version(package) == "3.3":
            print("run reloader in python 3.3")
            self.window.run_command(
                "package_reloader33_reload", {"package": package, "extra_pkgs": extra_pkgs})
            return

        Thread(
            name="AutomaticPackageReloader",
            target=self.run_async,
            args=(package, extra_pkgs, verbose)
        ).start()

    def run_async(self, package, extra_pkgs=[], verbose=None):
        lock = reload_lock  # In case we're reloading AutoPackageReloader
        if not lock.acquire(blocking=False):
            print("Reloader is running.")
            return

        pr_settings = sublime.load_settings("package_reloader.sublime-settings")
        open_console = pr_settings.get("open_console")
        open_console_on_failure = pr_settings.get("open_console_on_failure")
        close_console_on_success = pr_settings.get("close_console_on_success")

        progress_bar = ProgressBar("Reloading %s" % package)
        progress_bar.start()

        console_opened = self.window.active_panel() == "console"
        if not console_opened and open_console:
            self.window.run_command("show_panel", {"panel": "console"})
        dependencies = read_config(package, "dependencies", [])
        if verbose is None:
            verbose = pr_settings.get('verbose')
        try:
            reload_package(package, dependencies=dependencies, verbose=verbose)
            if close_console_on_success:
                self.window.run_command("hide_panel", {"panel": "console"})

            sublime.status_message("{} reloaded.".format(package))
        except Exception:
            if open_console_on_failure:
                self.window.run_command("show_panel", {"panel": "console"})
            sublime.status_message("Fail to reload {}.".format(package))
            raise
        finally:
            progress_bar.stop()
            lock.release()

        extra_pkgs = read_config(package, "siblings", []) + extra_pkgs
        if extra_pkgs:
            next_package = extra_pkgs.pop(0)
            if not has_package(next_package):
                print("{} is not installed.".format(next_package))
                return
            sublime.set_timeout(lambda: sublime.active_window().run_command(
                "package_reloader_reload",
                {"package": next_package, "extra_pkgs": extra_pkgs, "verbose": verbose}))


def plugin_loaded():
    if sys.version_info >= (3, 8):
        APR33 = os.path.join(sublime.packages_path(), "AutomaticPackageReloader33")
        if not os.path.exists(APR33):
            os.makedirs(APR33)
        data = sublime.load_resource("Packages/AutomaticPackageReloader/py33/package_reloader.py")
        with open(os.path.join(APR33, "package_reloader.py"), 'w') as f:
            f.write(data.replace("\r\n", "\n"))
        with open(os.path.join(APR33, ".package_reloader.json"), 'w') as f:
            f.write("{\"dependencies\" : [\"AutomaticPackageReloader\"]}")


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
            finally:
                lock.release()
