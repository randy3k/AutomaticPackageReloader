import sublime
import sublime_plugin
import os
from imp import reload
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

        pd = view.window().project_data()
        if not pd:
            return

        try:
            pkg_name = os.path.basename(pd["folders"][0]["path"])
        except:
            return

        mods = list(modules.keys()).copy()
        for mod in mods:
            if mod.startswith(pkg_name + "."):
                del modules[mod]

        del modules[pkg_name]

        # disable and re-enabling the package
        psettings = sublime.load_settings("Preferences.sublime-settings")
        ignored_packages = psettings.get("ignored_packages", [])
        ignored_packages.append(pkg_name)
        psettings.set("ignored_packages", ignored_packages)
        ignored_packages.pop(-1)
        psettings.set("ignored_packages", ignored_packages)
