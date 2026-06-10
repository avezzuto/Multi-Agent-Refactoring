# src/agents/fixer_agent.py

from langchain_core.messages import HumanMessage, SystemMessage

from src.agents.base_agent import BaseAgent
from src.prompts import FIXER_SYSTEM_PROMPT
from src.utils.google_client import create_model
from src.utils.logger import logger


class FixerAgent(BaseAgent):
    """
    Fixes syntax or behavioral errors in refactored code.
    Works on the refactored code, not the original.
    Supports fixing multiple files (dict of {file: code}).
    """

    def __init__(self, model_name: str):
        super().__init__()
        self.model = create_model(model_name)

    def build_prompt(
            self,
            instruction: str,
            refactored_code: str,
            error: str,
            error_type: str,
    ) -> str:
        return f"""### Original Refactoring Instruction
{instruction}

### Refactored Code (has {error_type} error)
{refactored_code}

### Error Description and fix instructions
{error}

### Task
Fix the {error_type} error. Keep the refactoring intact. Return the fixed code."""

    def run(self, instruction: str, context: str) -> str:
        """Required by BaseAgent."""
        return self.fix(
            instruction=instruction,
            refactored_code={"context": context},
            error="unknown error",
            error_type="unknown",
        )

    def _fix_single(
            self,
            instruction: str,
            refactored_code: str,
            error: str,
            error_type: str,
    ) -> str:
        messages = [
            SystemMessage(content=FIXER_SYSTEM_PROMPT),
            HumanMessage(content=self.build_prompt(
                instruction=instruction,
                refactored_code=refactored_code,
                error=error,
                error_type=error_type,
            )),
        ]
        # logger.info(messages)
        response = self.model.invoke(messages)
        return response.content

    def fix(
            self,
            instruction: str,
            refactored_code: dict[str, str],
            error: str,
            error_type: str = "syntax",
    ) -> dict[str, str]:
        """
        Fix errors in all refactored files.
        Calls LLM once per file.
        """
        fixed = {}
        for file_path, code in refactored_code.items():
            logger.info(f"[Fixer] Fixing file: {file_path}")
            fixed[file_path] = self._fix_single(
                instruction=instruction,
                refactored_code=code,
                error=error,
                error_type=error_type,
            )
        return fixed
