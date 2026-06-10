from abc import ABC

from langchain_core.messages import SystemMessage, HumanMessage

from src.utils.google_client import create_model
from src.agents.base_agent import BaseAgent
from src.prompts import (
    GENERAL_REFACTORING_SYSTEM_PROMPT,
    VARIABLE_REFACTORING_SYSTEM_PROMPT,
    FUNCTION_REFACTORING_SYSTEM_PROMPT,
)


class BaseRefactoringAgent(BaseAgent, ABC):
    """
    Abstract base for all refactoring agents.

    Subclasses must define AGENT_NAME and SYSTEM_PROMPT class attributes.
    """

    AGENT_NAME: str = "BaseRefactoringAgent"
    SYSTEM_PROMPT: str = ""

    def __init__(self, model_name: str):
        super().__init__()
        self.model = create_model(model_name)

    def build_prompt(self, instruction: str, context: str, refactoring_str: str | None = None) -> str:
        refactoring_section = ""
        if refactoring_str:
            refactoring_section = \
                f"""
            ### Identifiers to Refactor
            {refactoring_str}
            """

        return f"""
        ### Refactoring Instruction
        {instruction}
        {refactoring_section}
        ### Code Context
        {context}

        ### Task
        Apply the refactoring and return the updated code.
        """

    def build_refactoring_str(self, refactorings: list[dict[str, str]]) -> str:
        lines = []
        for i, r in enumerate(refactorings, 1):
            lines.append(f"{i}. `{r['identifier']}`")
        return "\n".join(lines)

    def run(
            self,
            instruction: str,
            context: str,
            refactorings: list[dict[str, str]] | None = None,
    ) -> str:

        refactorings_str = None

        if refactorings and len(refactorings) > 0:
            refactorings_str = self.build_refactoring_str(refactorings)

        prompt = self.build_prompt(instruction, context, refactorings_str)

        response = self.model.invoke([SystemMessage(content=self.SYSTEM_PROMPT), HumanMessage(content=prompt)])

        content = response.content.strip()

        if content.startswith("```"):
            lines = content.splitlines()

            # remove opening fence
            lines = lines[1:]

            # remove closing fence
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]

            content = "\n".join(lines)

        return content


class GeneralRefactoringAgent(BaseRefactoringAgent):
    """
    Simple single-agent baseline.
    """

    AGENT_NAME = "GeneralRefactoringAgent"
    SYSTEM_PROMPT = GENERAL_REFACTORING_SYSTEM_PROMPT


class VariableRefactoringAgent(BaseRefactoringAgent):
    """
    Specialised agent for local variable refactoring tasks.

    Refactors a variable at every occurrence within its local scope (e.g. a
    function or method body) without affecting other scopes or files.
    """

    AGENT_NAME = "VariableRefactoringAgent"
    SYSTEM_PROMPT = VARIABLE_REFACTORING_SYSTEM_PROMPT


class FunctionRefactoringAgent(BaseRefactoringAgent):
    """
    Specialised agent for cross-file function refactoring tasks.

    Refactors a function across the entire repository: its definition, every
    import statement that references it, and every call site across all
    affected files.
    """

    AGENT_NAME = "FunctionRefactoringAgent"
    SYSTEM_PROMPT = FUNCTION_REFACTORING_SYSTEM_PROMPT
