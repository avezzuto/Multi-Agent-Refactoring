import ast
from pathlib import Path


class TestIndexer:
    """
    Discovers repository tests and extracts lightweight metadata.

    Responsibilities:
    - find test files
    - extract imported modules
    - build searchable test index
    """

    TEST_PATTERNS = [
        "*test*.py",
    ]

    def __init__(self, repo_path: Path):
        self.repo_path = Path(repo_path)

    def find_test_files(self) -> list[Path]:

        test_files = []

        for pattern in self.TEST_PATTERNS:
            test_files.extend(
                self.repo_path.rglob(pattern)
            )

        return sorted(set(test_files))

    def extract_imports(
            self,
            file_path: Path,
    ) -> set[str]:

        imports = set()

        try:
            source = file_path.read_text(
                encoding="utf-8"
            )

            tree = ast.parse(source)

        except Exception:
            return imports

        for node in ast.walk(tree):

            if isinstance(node, ast.Import):

                for alias in node.names:
                    imports.add(
                        alias.name.split(".")[0]
                    )

            elif isinstance(node, ast.ImportFrom):

                if node.module:
                    imports.add(
                        node.module.split(".")[0]
                    )

        return imports

    def build_index(self) -> dict[str, dict]:

        index = {}

        for test_file in self.find_test_files():

            relative_path = str(
                test_file.relative_to(
                    self.repo_path
                )
            )

            try:
                content = test_file.read_text(
                    encoding="utf-8"
                )

            except Exception:
                content = ""

            index[relative_path] = {
                "path": test_file,
                "imports": self.extract_imports(
                    test_file
                ),
                "content": content,
            }

        return index