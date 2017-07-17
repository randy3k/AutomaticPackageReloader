import sublime_plugin
import sublime
import os
from .reloader import reload_package, ProgressBar


class PackageReloaderListener(sublime_plugin.EventListener):

    def on_post_save(self, view):
        if view.is_scratch() or view.settings().get('is_widget'):
            return
        file_name = view.file_name()
        if not file_name:
            return

        file_name = os.path.realpath(file_name)
        spp = os.path.realpath(sublime.packages_path())
        if file_name and file_name.endswith(".py") and spp in file_name:
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

    def run(self, pkg_name=None):
        sublime.set_timeout_async(lambda: self.run_async(pkg_name))

    def run_async(self, pkg_name=None):
        if not pkg_name:
            view = self.window.active_view()
            pkg_name = self.extract_from_file_name(view.file_name())

        if not pkg_name:
            folders = sublime.active_window().folders()
            if folders and len(folders) > 0:
                pkg_name = os.path.basename(os.path.realpath(folders[0]))
            else:
                project_file_name = sublime.active_window().project_file_name()
                pkg_name = os.path.splitext(os.path.basename(project_file_name))[0]

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
                reload_package(pkg_name)
            except:
                sublime.status_message("Fail to reload {}.".format(pkg_name))
                if open_console_on_failure:
                    self.window.run_command("show_panel", {"panel": "console"})
                raise
            finally:
                progress_bar.stop()

            if not console_opened and close_console_on_success:
                self.window.run_command("hide_panel", {"panel": "console"})

            sublime.status_message("{} reloaded.".format(pkg_name))

    def extract_from_file_name(self, file_name):
        if not file_name:
            return None

        spp = sublime.packages_path()
        real_spp = os.path.realpath(spp)
        real_file_name = os.path.realpath(file_name)

        for d in (real_spp, spp):
            for f in (real_file_name, file_name):
                if f.endswith(".py") and d in f:
                    return f.replace(d, "").split(os.sep)[1]

        return None
