from pathlib import Path
from langgraph.graph import StateGraph

from src.agents.vanilla_agent import VanillaAgent
from src.utils.logger import logger
from src.utils.preparation_utils import cleanup_repo_test_folders, load_benchmark_jobs, backup_repository_state, restore_repository_state, BenchmarkJob
from src.utils.testing_utils import run_benchmark_tests, run_tests_without_refactoring
from src.graph import build_graph
from src.config import USE_DUMMY, MODEL, BENCH_NAME, USE_SPECIALISED, USE_VANILLA

if USE_DUMMY:
    from DummyBench.scripts.base_mapping import file_mapping
else:
    from RefactorBench.scripts.base_mapping import file_mapping


def _run_graph_job(graph: StateGraph, job: BenchmarkJob):

    result = graph.invoke(
        {
            "instruction": job.instruction,
            "repository_path": str(job.repository_path),
            "relevant_files": job.relevant_files,
            "task_name": job.task_name,
            "file_plans": [],
            "visible_tests": [],
            "generated_tests": [],
            "refactored_code": {},
            "compile_error": None,
            "compile_attempts": 0,
            "test_error": None,
            "test_attempts": 0,
            "tests_generated": 0,
            "test_coverage": 0.0,
            "success": False,
        }
    )

    refactored = result.get(
        "refactored_code",
        {},
    )

    if (
        result.get("success")
        and isinstance(refactored, dict)
    ):
        for file_path, code in refactored.items():
            Path(file_path).write_text(code)

    return result

def _run_vanilla_job(agent: VanillaAgent, job: BenchmarkJob):

    refactored_files = agent.run(
        instruction=job.instruction,
        repository_path=job.repository_path,
    )

    for file_path, code in refactored_files.items():
        Path(file_path).write_text(code)

    return {
        "success": True,
        "compile_attempts": 0,
        "test_attempts": 0,
        "tests_generated": 0,
        "test_coverage": 0.0,
        "file_plans": [],
        "refactored_code": refactored_files,
    }

# Generic evaluation pipeline
def _evaluate(run_job):

    jobs = load_benchmark_jobs(file_mapping=file_mapping)
    logger.info(jobs)

    if not USE_DUMMY:
        run_tests_without_refactoring(jobs)

    originals, test_originals = (backup_repository_state(jobs))

    cleanup_repo_test_folders(generated=True)

    results = []

    logger.info("-" * 25 + "STARTING REFACTORING" + "-" * 25)

    try:

        for job in jobs:

            try:
                result = run_job(job)

            except Exception as error:
                logger.error(error)
                result = {
                    "success": False,
                    "compile_attempts": 0,
                    "test_attempts": 0,
                    "tests_generated": 0,
                    "test_coverage": 0.0,
                    "file_plans": [],
                    "refactored_code": {},
                }

            results.append(result)

        cleanup_repo_test_folders(generated=True)

        logger.info(
            "[REFACTORING COMPLETE] "
            "Running tests..."
        )

        run_benchmark_tests(results, jobs)

    finally:
        restore_repository_state(originals, test_originals)


# Specialised evaluation
def evaluate_graph():
    graph = build_graph()
    _evaluate(lambda job: _run_graph_job(graph, job))


def evaluate_vanilla_agent():
    agent = VanillaAgent(MODEL)
    _evaluate(lambda job: _run_vanilla_job(agent, job))


if __name__ == "__main__":

    logger.info("=" * 50)
    logger.info("[Config] Running refactoring evaluation with:")
    logger.info(f"  MODEL:          {MODEL}")
    logger.info(f"  BENCH:          {BENCH_NAME}")
    logger.info(f"  USE_SPECIALISED:{USE_SPECIALISED}")
    logger.info(f"  USE_VANILLA:    {USE_VANILLA}")
    logger.info("=" * 50)

    if USE_VANILLA:
        evaluate_vanilla_agent()
    else:
        evaluate_graph()
