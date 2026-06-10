import ast
import os
import subprocess
import uuid
from pathlib import Path

from src.utils.logger import logger


class TestRunner:
    """
    Executes pytest suites.
    """

    def __init__(
            self,
            repo_path: Path,
    ):
        self.repo_path = Path(repo_path)

    def run_pytest(
            self,
            test_files: list[str],
            repo_path: Path,
            coverage: bool = False,
            coverage_target: str | None = None,
    ) -> dict:

        if not test_files:
            return {
                "success": False,
                "returncode": -1,
                "stdout": "",
                "stderr": "No test files were provided.",
                "command": None,
                "coverage": 0.0,
            }

        results = []
        stdout = ""
        stderr = ""
        commands = []
        success = True
        coverage_percent = 0.0

        venv_python = repo_path / "venv" / "bin" / "python3"
        dotenv_python = repo_path / ".venv" / "bin" / "python3"
        python_executable = (
            str(venv_python) if venv_python.exists()
            else str(dotenv_python) if dotenv_python.exists()
            else "python3"
        )
        logger.debug(f"venv python exists? {venv_python.exists()}")
        logger.debug(f"dotenv python exists? {dotenv_python.exists()}")

        for test_file in test_files:
            execution_cwd = repo_path

            if not execution_cwd:
                continue

            cmd = [
                python_executable,
                "-m",
                "pytest",
                "-W",
                "ignore::PendingDeprecationWarning",
                str(test_file),
            ]

            if coverage:
                target = coverage_target or "."
                cmd.extend(
                    [
                        f"--cov={target}",
                        "--cov-report=term",
                        "--cov-config=/dev/null",
                    ]
                )

            env = self._build_env(execution_cwd)

            result = subprocess.run(
                cmd,
                cwd=execution_cwd,
                capture_output=True,
                text=True,
                env=env,
                timeout=30,
            )

            results.append(result)
            commands.append(cmd)

            stdout += result.stdout + "\n"
            stderr += result.stderr + "\n"

            if result.returncode != 0:
                success = False

            if coverage:
                coverage_percent = max(
                    coverage_percent,
                    self._parse_coverage(
                        result.stdout + "\n" + result.stderr
                    ),
                )

        return {
            "success": success,
            "returncode": 0 if success else 1,
            "stdout": stdout,
            "stderr": stderr,
            "command": commands,
            "coverage": coverage_percent,
        }

    def _build_env(
            self,
            execution_cwd: Path,
    ) -> dict:

        env = os.environ.copy()

        existing = env.get(
            "PYTHONPATH",
            "",
        )

        env["PYTHONPATH"] = (
            f"{execution_cwd}:{existing}"
        )

        project_root = (
            Path(__file__)
            .resolve()
            .parents[2]
        )

        coverage_dir = (
                project_root /
                "logs" /
                "coverage"
        )

        coverage_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

        coverage_file = (
                coverage_dir /
                f".coverage_{uuid.uuid4().hex}"
        )

        env["COVERAGE_FILE"] = str(
            coverage_file
        )

        return env

    def _parse_coverage(
            self,
            output: str,
    ) -> float:

        for line in output.splitlines():

            if "TOTAL" in line:
                parts = line.split()

                try:
                    return (
                            float(
                                parts[-1].replace("%", "")
                            ) / 100.0
                    )

                except Exception:
                    pass

        return 0.0

    def _resolve_execution_cwd(
            self,
            test_file: str,
    ) -> Path:

        imports = set()

        try:

            tree = ast.parse(
                Path(test_file).read_text(
                    encoding="utf-8"
                )
            )

        except Exception:

            logger.warning(
                f"Failed to parse test file: "
                f"{test_file}"
            )

            return self.repo_path

        for node in ast.walk(tree):

            if isinstance(node, ast.Import):

                for alias in node.names:

                    imports.add(
                        alias.name
                    )

            elif isinstance(
                    node,
                    ast.ImportFrom,
            ):

                if node.module:

                    imports.add(
                        node.module
                    )

        for module in imports:

            module_parts = module.split(".")

            candidate_files = [
                Path(*module_parts).with_suffix(
                    ".py"
                ),
                Path(*module_parts) /
                "__init__.py",
                ]

            for source_file in self.repo_path.rglob(
                    "*.py"
            ):

                relative = source_file.relative_to(
                    self.repo_path
                )

                if relative not in candidate_files:
                    continue

                module_depth = len(
                    module_parts
                )

                execution_cwd = source_file

                for _ in range(
                        module_depth
                ):
                    execution_cwd = (
                        execution_cwd.parent
                    )

                env = os.environ.copy()

                existing = env.get(
                    "PYTHONPATH",
                    "",
                )

                env["PYTHONPATH"] = (
                    f"{execution_cwd}:"
                    f"{existing}"
                )

                result = subprocess.run(
                    [
                        "python",
                        "-c",
                        (
                            "import importlib;"
                            f"importlib.import_module("
                            f"'{module}')"
                        ),
                    ],
                    cwd=execution_cwd,
                    capture_output=True,
                    text=True,
                    env=env,
                )

                if result.returncode == 0:

                    return execution_cwd

        logger.warning(
            f"Could not determine execution "
            f"directory for {test_file}. "
        )

        return None