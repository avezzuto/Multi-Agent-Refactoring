import re
import shutil
from pathlib import Path
from dataclasses import dataclass

from src.utils.logger import logger
from src.config import PROJECT_ROOT, BENCH_NAME, USE_DUMMY

@dataclass
class BenchmarkJob:
    repository_name: str
    task_name: str
    instruction: str
    test_path: Path
    repository_path: Path
    relevant_files: list[Path]
    execution_paths: set[Path]


def cleanup_repo_test_folders(generated: bool = False, repo_tests: bool = False) -> None:
    """Delete generated_tests and/or tests folders inside all benchmark repositories."""
    repos_path = PROJECT_ROOT / BENCH_NAME / "repositories"
    for repo_dir in repos_path.iterdir():
        if not repo_dir.is_dir():
            continue
        if generated:
            folder = repo_dir / "generated_tests"
            if folder.exists():
                shutil.rmtree(folder)
                logger.info(f"[Cleanup] Deleted generated_tests in {repo_dir.name}")
        if repo_tests:
            folder = repo_dir / "tests"
            if folder.exists():
                shutil.rmtree(folder)
                logger.info(f"[Cleanup] Deleted tests in {repo_dir.name}")

def load_allowed_tasks(mapping_file: Path) -> set[str]:

    allowed = set()

    for line in mapping_file.read_text().splitlines():

        line = line.strip()

        if (
                not line
                or line.startswith("---")
        ):
            continue

        task_name = (
            line.split(",")[0]
            .strip()
        )

        allowed.add(task_name)

    return allowed

def load_benchmark_jobs(file_mapping) -> list[BenchmarkJob]:
    jobs = []
    allowed_tasks = load_allowed_tasks(PROJECT_ROOT/"RefactorBenchFilteredProblems"/"mapping.txt")

    for test_rel_path, task_rel_path in file_mapping.items():

        task_name = Path(task_rel_path).name

        if not USE_DUMMY and task_name not in allowed_tasks:
            continue

        repository_name = test_rel_path.split("/")[2]

        task_path = PROJECT_ROOT / BENCH_NAME / task_rel_path[3:]
        test_path = PROJECT_ROOT / BENCH_NAME / test_rel_path[3:]

        repository_path = (
            PROJECT_ROOT
            / BENCH_NAME
            / "repositories"
            / repository_name
        )

        instruction = task_path.read_text().strip()
        test_code = test_path.read_text()

        matches = re.findall(
            r"file_path = '(\.\./[^']+)'",
            test_code,
        )

        if not matches:
            logger.info(
                f"Could not find file_path in {test_path}"
            )
            continue

        relevant_files = set([
            repository_path / path[3:]
            for path in matches
        ])
        logger.info(f"Relevant files: {relevant_files}")

        execution_paths = [
            repository_path / path[3:].split("/")[0]
            for path in matches
        ]

        jobs.append(
            BenchmarkJob(
                repository_name=repository_name,
                task_name=task_name,
                instruction=instruction,
                test_path=test_path,
                repository_path=repository_path,
                relevant_files=relevant_files,
                execution_paths=execution_paths,
            )
        )

    return jobs

def backup_repository_state(jobs: list[BenchmarkJob]):
    originals = {}
    test_originals = {}

    for job in jobs:

        for file_path in job.relevant_files:

            if (file_path.exists() and file_path not in originals):
                originals[file_path] = file_path.read_text()

        tests_dir = job.repository_path / "tests"

        if tests_dir.exists():

            for test_file in tests_dir.rglob("*.py"):

                if test_file not in test_originals:
                    test_originals[test_file] = test_file.read_text()

    return originals, test_originals

def restore_repository_state(originals, test_originals):
    for file_path, content in originals.items():
        file_path.write_text(content)

    for file_path, content in test_originals.items():
        file_path.write_text(content)

    logger.info("All changes reverted")