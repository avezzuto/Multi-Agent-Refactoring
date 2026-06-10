from pathlib import Path


class TestDiscovery:
    """
    Finds tests related to changed files using:
    - import overlap
    - module overlap
    - file path references
    """

    def __init__(
            self,
            repo_path: Path,
            test_index: dict[str, dict],
    ):
        self.repo_path = Path(repo_path)
        self.test_index = test_index

    def _module_name_from_file(
            self,
            file_path: Path,
    ) -> str:

        rel = file_path.relative_to(
            self.repo_path
        )

        return (
            rel.with_suffix("")
            .as_posix()
            .replace("/", ".")
        )

    def _top_level_module(
            self,
            file_path: Path,
    ) -> str:

        rel = file_path.relative_to(
            self.repo_path
        )

        return rel.parts[0]

    def find_related_tests(
            self,
            changed_files: list[Path],
    ) -> list[Path]:
        
        return []

        # related = set()

        # changed_modules = set()
        # top_level_modules = set()

        # for file_path in changed_files:

        #     changed_modules.add(
        #         self._module_name_from_file(
        #             file_path
        #         )
        #     )

        #     top_level_modules.add(
        #         self._top_level_module(
        #             file_path
        #         )
        #     )

        # for item in self.test_index.values():

        #     imports = item["imports"]
        #     content = item["content"]

        #     # direct import overlap
        #     if imports & top_level_modules:
        #         related.add(item["path"])
        #         continue

        #     # module prefix overlap
        #     for module in changed_modules:

        #         if any(
        #                 module.startswith(imported)
        #                 for imported in imports
        #         ):
        #             related.add(item["path"])
        #             break

        #     # textual file reference overlap
        #     for changed_file in changed_files:

        #         if changed_file.name in content:
        #             related.add(item["path"])
        #             break

        # return sorted(related)