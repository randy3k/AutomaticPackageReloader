try:
    from package_control.package_manager import PackageManager

except ImportError:
    def resolve_parents(root_name):
        return {root_name}

else:
    def resolve_parents(root_name):
        """Given the name of a dependency, return all dependencies and packages
        that require that dependency, directly or indirectly.
        """
        manager = PackageManager()
        packages = manager.list_packages()
        dependencies = map(lambda lib: lib.name, manager.list_libraries())
        everything = list(packages) + list(dependencies)        

        recursive_dependencies = set()

        dependency_relationships = {
            name: manager.get_libraries(name) for name in everything
        }

        def rec(name):
            if name in recursive_dependencies:
                return

            recursive_dependencies.add(name)

            for pkg_name in everything:
                if name in dependency_relationships[pkg_name]:
                    rec(pkg_name)

        rec(root_name)

        recursive_dependencies.remove(root_name)

        return recursive_dependencies
