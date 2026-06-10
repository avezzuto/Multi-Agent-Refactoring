from pathlib import Path

from langchain_core.messages import (
    SystemMessage,
    HumanMessage,
)

from src.agents.base_agent import BaseAgent

from src.prompts import TESTER_SUMMARY_PROMPT

from src.testing.test_runner import TestRunner
from src.utils.google_client import create_model

from src.utils.logger import logger


class TestValidatorAgent(BaseAgent):
    """
    Runtime validation agent.

    Responsibilities:
    - run validation tests
    - summarize failures
    """

    def __init__(
            self,
            model_name: str,
    ):
        super().__init__()

        self.model = create_model(model_name)

    def summarize_failure(
            self,
            instruction: str,
            original_code: str,
            candidate_code: str,
            output: str,
    ) -> str:

        prompt = f"""
Refactoring instruction:
{instruction}

Original implementation:
{original_code}

Current candidate implementation:
{candidate_code}

Validation/test output:
{output}

Analyze the failure.

Determine whether the issue is primarily:
- missing/incomplete refactoring
- incorrect behavior in the candidate
- test synchronization/import issues
- infrastructure/runtime issues

IMPORTANT:
New symbols, renamed methods, renamed variables,
or moved functionality may be expected if they
match the requested refactoring instruction.

Do not treat newly introduced symbols as errors
if they correspond to the requested refactoring.

Focus first on whether the requested
refactoring was actually applied correctly.

Return:
- what likely broke
- what should be repaired
- affected symbols/files

Keep response concise.
"""

        response = self.model.invoke(
            [
                SystemMessage(
                    content=TESTER_SUMMARY_PROMPT
                ),
                HumanMessage(content=prompt),
            ]
        )

        return response.content

    def validate(
            self,
            repo_path: str | Path,
            validation_tests: list[Path],
            original_code: str,
            candidate_code: str,
            instruction: str,
    ) -> dict:

        repo_path = Path(repo_path)

        logger.debug(f"Repo path: {repo_path}")
        logger.debug(f"Repo name: {repo_path.name}")

        runner = TestRunner(repo_path)

        result = {
            "success": True,
            "stdout": "",
            "stderr": "",
        }

        if validation_tests:
            test_paths = []
            for test in validation_tests:
                # logger.debug(f"Test path: {test}")
                test_paths.append(str(Path(test).resolve()))

            result = runner.run_pytest(
                test_paths,
                repo_path,
            )

        combined_output = (
                result["stdout"] +
                "\n" +
                result["stderr"]
        )

        overall_success = result["success"]

        feedback = None

        if not overall_success:

            feedback = self.summarize_failure(
                instruction=instruction,
                original_code=original_code,
                candidate_code=candidate_code,
                output=combined_output,
            )

        logger.debug(f"Test output: {combined_output}")

        tests_run = [
            str(Path(test).resolve())
            for test in validation_tests
        ]

        return {
            "success": overall_success,
            "feedback": feedback,
            "stdout": combined_output,
            "stderr": "",
            "tests_run": tests_run,
        }

    def run(self, *args, **kwargs):
        return self.validate(*args, **kwargs)