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
        reload(modules[pkg_name])
