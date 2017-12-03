import sublime_plugin
import sublime
import os
from .reloader import reload_package, ProgressBar
from glob import glob


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

    def is_enabled(self):
        return self.current_package_name is not None

    @property
    def current_package_name(self):
        view = self.window.active_view()
        spp = os.path.realpath(sublime.packages_path())
        if view and view.file_name():
            file_path = os.path.realpath(view.file_name())
            if file_path.endswith(".py") and file_path.startswith(spp):

                def get_actual_filename(name):
                    """
                        In Python, how can I get the correctly-cased path for a file?
                        https://stackoverflow.com/questions/3692261/in-python-how-can-i-get-the-correctly-cased-path-for-a-file
                    """
                    sep = os.path.sep
                    parts = os.path.normpath(name).split(sep)
                    dirs = parts[0:-1]
                    filename = parts[-1]
                    if dirs[0] == os.path.splitdrive(name)[0]:
                        test_name = [dirs[0].upper()]
                    else:
                        test_name = [sep + dirs[0]]
                    for d in dirs[1:]:
                        test_name += ["%s[%s]" % (d[:-1], d[-1])]
                    path = glob(sep.join(test_name))[0]
                    res = glob(sep.join((path, filename)))
                    if not res:
                        #File not found
                        return None
                    return res[0]

                # https://github.com/randy3k/AutomaticPackageReloader/issues/10
                file_path = get_actual_filename(file_path)
                return file_path[len(spp):].split(os.sep)[1]

        folders = self.window.folders()
        if folders and len(folders) > 0:
            first_folder = os.path.realpath(folders[0])
            if first_folder.startswith(spp):
                return os.path.basename(first_folder)

        return None

    def run(self, pkg_name=None):
        sublime.set_timeout_async(lambda: self.run_async(pkg_name))

    def run_async(self, pkg_name=None):
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
            except:
                sublime.status_message("Fail to reload {}.".format(pkg_name))
                if open_console_on_failure:
                    self.window.run_command("show_panel", {"panel": "console"})
                raise
            finally:
                progress_bar.stop()

            if close_console_on_success:
                self.window.run_command("hide_panel", {"panel": "console"})

            sublime.status_message("{} reloaded.".format(pkg_name))
