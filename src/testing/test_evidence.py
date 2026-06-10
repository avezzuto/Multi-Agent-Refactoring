import ast
from pathlib import Path


class TestDependencyVisitor(
    ast.NodeVisitor
):
    def __init__(self):
        self.dependencies = []

    def visit_Call(self, node):

        if isinstance(
                node.func,
                ast.Attribute,
        ):
            self.dependencies.append(
                node.func.attr
            )

        elif isinstance(
                node.func,
                ast.Name,
        ):
            self.dependencies.append(
                node.func.id
            )

        self.generic_visit(node)


def extract_test_dependencies(
        test_file: Path,
) -> list[str]:

    source = test_file.read_text(
        encoding="utf-8"
    )

    tree = ast.parse(source)

    visitor = (
        TestDependencyVisitor()
    )

    visitor.visit(tree)

    return sorted(
        set(visitor.dependencies)
    )