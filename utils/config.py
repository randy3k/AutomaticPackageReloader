import sublime


def read_config(package, key, default=None):
    try:
        context = sublime.load_resource(
            "Packages/{}/.package_reloader.json".format(package))
        value = sublime.decode_value(context).get(key, default)
    except Exception:
        value = default

    return value
