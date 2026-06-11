import ast
import re
import subprocess
from pathlib import Path

from src.utils.logger import logger

from src.config import MODEL, BENCH_NAME

def _count_subtests(test_path: Path) -> int:
    tree = ast.parse(test_path.read_text())

    total = 0

    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if (
                        isinstance(target, ast.Name)
                        and target.id == "files_to_check"
                        and isinstance(node.value, ast.List)
                ):
                    total += len(node.value.elts)

    return total


def _count_failed_subtests(output: str) -> int:
    return len(
        re.findall(
            r"^(?:FAIL|ERROR): .*?\(file='[^']+'\)",
            output,
            re.MULTILINE,
        )
    )


def _parse_test_output(output: str, test_path: Path) -> tuple[int, int]:
    total_subtests = _count_subtests(test_path)

    if total_subtests > 0:
        failed = _count_failed_subtests(output)
        return total_subtests - failed, total_subtests

    # fallback for normal unittest tests
    ran_match = re.search(r"Ran (\d+) tests?", output)
    if not ran_match:
        return 0, 0

    total = int(ran_match.group(1))

    failures = int(m.group(1)) if (m := re.search(r"failures=(\d+)", output)) else 0
    errors = int(m.group(1)) if (m := re.search(r"errors=(\d+)", output)) else 0

    return max(0, total - failures - errors), total


def _run_test(test_path: Path, execution_path: Path, repository_name: str, task_name: str) -> tuple[int, int]:
    """Runs a single test file and returns (passes, total)."""
    cmd = ["python", f"../../../tests/{test_path.parent.name}/{test_path.name}"]
    result = subprocess.run(cmd, cwd=execution_path, capture_output=True, text=True)
    output = result.stdout + result.stderr
    logger.debug(output)

    passes, total = _parse_test_output(output, test_path)
    if total == 0:
        logger.info("Could not parse test results")
    else:
        logger.info(f"[{repository_name}] {task_name}: {passes}/{total}")

    return passes, total


def run_tests_without_refactoring(jobs):

    Path("results").mkdir(exist_ok=True)

    results = [
        {
            "success": True,
            "compile_attempts": 0,
            "test_attempts": 0,
            "tests_generated": 0,
            "test_coverage": 0.0,
            "file_plans": [],
            "refactored_code": {},
        }
        for _ in jobs
    ]

    run_benchmark_tests(results, jobs)


def run_benchmark_tests(results, jobs):

    total_passes = 0
    total_tests = 0
    total_files_refactored = 0

    with open(
        f"results/{BENCH_NAME}_results.csv",
        "w",
    ) as f:

        f.write(
            "repository,task,model,"
            "refactoring_entity,"
            "files_refactored,"
            "tests_generated,"
            "test_coverage,"
            "test_attempts,"
            "success,"
            "tests_passed,"
            "total_tests,"
            "passing_rate\n"
        )

        for job, result in zip(jobs, results):

            file_plans = result.get("file_plans", [])

            files_refactored = len(
                {
                    fp["file"]
                    for fp in file_plans
                }
            )

            total_files_refactored += files_refactored

            refactoring_entities = set()

            for fp in file_plans:

                for r in fp.get("refactorings", []):

                    entity = r.get("refactoring_entity")

                    if entity:
                        refactoring_entities.add(entity)

            entities = (
                ";".join(
                    sorted(refactoring_entities)
                )
                if refactoring_entities
                else "unknown"
            )

            passes = total = 0

            p, t = _run_test(
                job.test_path,
                job.execution_paths[0],
                job.repository_name,
                job.task_name,
            )

            passes += p
            total += t

            total_passes += passes
            total_tests += total

            rate = (
                passes / total
                if total
                else 0.0
            )

            f.write(
                f"{job.repository_name},"
                f"{job.task_name},"
                f"{MODEL},"
                f"{entities},"
                f"{files_refactored},"
                f"{result.get('tests_generated', 0)},"
                f"{result.get('test_coverage', 0.0):.2f},"
                f"{result.get('test_attempts', 0)},"
                f"{result.get('success', False)},"
                f"{passes},"
                f"{total},"
                f"{rate:.2f}\n"
            )

    if total_files_refactored == 0:
        logger.info(
            f"[Before Refactoring] Overall: {total_passes}/{total_tests}"
        )
    else:
        logger.info(
            f"[After Refactoring] Overall: {total_passes}/{total_tests}"
        )
