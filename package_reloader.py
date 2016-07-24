import sublime_plugin
import sublime
import os
from .reloader import reload_package, ProgressBar


class PackageReloaderListener(sublime_plugin.EventListener):

    def on_post_save(self, view):
        if view.is_scratch() or view.settings().get('is_widget'):
            return False
        package_reloader_settings = sublime.load_settings("package_reloader.sulime-settings")
        if package_reloader_settings.get("reload_on_save"):
            sublime.set_timeout_async(view.window().run_command("package_reloader_reload"))


class PackageReloaderToggleReloadOnSaveCommand(sublime_plugin.WindowCommand):

    def run(self):
        package_reloader_settings = sublime.load_settings("package_reloader.sulime-settings")
        reload_on_save = not package_reloader_settings.get("reload_on_save")
        package_reloader_settings.set("reload_on_save", reload_on_save)
        onoff = "on" if reload_on_save else "off"
        sublime.status_message("Package Reloader: Reload on Save is %s." % onoff)


class PackageReloaderReloadCommand(sublime_plugin.WindowCommand):

    def run(self, pkg_name=None):
        sublime.set_timeout_async(lambda: self.run_async(pkg_name))

    def run_async(self, pkg_name=None):
        spp = os.path.realpath(sublime.packages_path())

        if not pkg_name:
            view = self.window.active_view()
            file_name = view.file_name()
            if file_name:
                file_name = os.path.realpath(file_name)
                if file_name and file_name.endswith(".py") and spp in file_name:
                    pkg_name = file_name.replace(spp, "").split(os.sep)[1]

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
                raise
            finally:
                progress_bar.stop()

            if not console_opened and close_console_on_success:
                self.window.run_command("hide_panel", {"panel": "console"})

            sublime.status_message("{} reloaded.".format(pkg_name))
