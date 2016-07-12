import sublime
import sublime_plugin
import os
from sys import modules


class ModuleReloader(sublime_plugin.EventListener):

    def on_post_save(self, view):
        if view.is_scratch() or view.settings().get('is_widget'):
            return False

        file_name = view.file_name()
        if not file_name.endswith(".py"):
            return

        if sublime.packages_path() not in file_name:
            return

        try:
            pkg_name = file_name.replace(sublime.packages_path(), "").split(os.sep)[1]
        except:
            return

        sublime.set_timeout_async(lambda: self.reload_package(pkg_name), 0)

    def reload_package(self, pkg_name):
        # disable and re-enabling the package
        psettings = sublime.load_settings("Preferences.sublime-settings")
        ignored_packages = psettings.get("ignored_packages", [])
        ignored_packages.append(pkg_name)
        psettings.set("ignored_packages", ignored_packages)

        mods = list(modules.keys()).copy()
        for mod in mods:
            if mod.startswith(pkg_name + "."):
                del modules[mod]
        del modules[pkg_name]

        ignored_packages.pop(-1)
        psettings.set("ignored_packages", ignored_packages)
