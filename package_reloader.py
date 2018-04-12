import sublime_plugin
import sublime
import os
from glob import glob
import re

from .reloader import reload_package, ProgressBar


def casedpath(path):
    # path on Windows may not be properly cased
    # https://github.com/randy3k/AutomaticPackageReloader/issues/10
    r = glob(re.sub(r'([^:/\\])(?=[/\\]|$)', r'[\1]', path))
    return r and r[0] or path


def relative_to_spp(path):
    spp = sublime.packages_path()
    spp_real = casedpath(os.path.realpath(spp))
    for p in [path, casedpath(os.path.realpath(path))]:
        for sp in [spp, spp_real]:
            if p.startswith(sp + os.sep):
                return p[len(sp):]
    return None


class PackageReloaderListener(sublime_plugin.EventListener):

    def on_post_save(self, view):
        if view.is_scratch() or view.settings().get('is_widget'):
            return
        file_name = view.file_name()

        if file_name and file_name.endswith(".py") and relative_to_spp(file_name):
            package_reloader_settings = sublime.load_settings("package_reloader.sublime-settings")
            if package_reloader_settings.get("reload_on_save"):
                sublime.set_timeout_async(view.window().run_command("package_reloader_reload"))


class PackageReloaderToggleReloadOnSaveCommand(sublime_plugin.WindowCommand):

    def run(self):
        package_reloader_settings = sublime.load_settings("package_reloader.sublime-settings")
        reload_on_save = not package_reloader_settings.get("reload_on_save")
        package_reloader_settings.set("reload_on_save", reload_on_save)
        onoff = "on" if reload_on_save else "off"
        sublime.status_message("Package Reloader: Reload on Save is %s." % onoff)


class PackageReloaderReloadCommand(sublime_plugin.WindowCommand):

    def is_enabled(self):
        return self.current_package_name is not None

    @property
    def current_package_name(self):
        view = self.window.active_view()
        if view and view.file_name():
            file_path = relative_to_spp(view.file_name())
            if file_path and file_path.endswith(".py"):
                return file_path.split(os.sep)[1]

        folders = self.window.folders()
        if folders and len(folders) > 0:
            first_folder = relative_to_spp(folders[0])
            if first_folder:
                return os.path.basename(first_folder)

        return None

    def run(self, pkg_name=None):
        sublime.set_timeout_async(lambda: self.run_async(pkg_name))

    def run_async(self, pkg_name=None):
        if not pkg_name:
            pkg_name = self.current_package_name

        if pkg_name:
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
            except Exception:
                sublime.status_message("Fail to reload {}.".format(pkg_name))
                if open_console_on_failure:
                    self.window.run_command("show_panel", {"panel": "console"})
                raise
            finally:
                progress_bar.stop()

            if close_console_on_success:
                self.window.run_command("hide_panel", {"panel": "console"})

            sublime.status_message("{} reloaded.".format(pkg_name))
