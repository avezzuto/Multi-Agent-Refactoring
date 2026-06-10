# src/agents/compiler_agent.py
import os
import py_compile
import tempfile

from src.agents.base_agent import BaseAgent


class CompilerAgent(BaseAgent):
    """
    Checks whether refactored code is syntactically valid Python.
    Does NOT fix the code — just validates and returns the error.
    The graph routes back to RefactoringAgent if compilation fails.
    """

    def __init__(self):
        super().__init__()

    def check_syntax(self, code_dict: dict[str, str]) -> tuple[bool, str]:
        """
        Returns (True, "") if valid, (False, error_msg) if not.
        """
        errors = []

        for file, code in code_dict.items():
            with tempfile.NamedTemporaryFile(
                mode="w",
                suffix=".py",
                delete=False,
            ) as f:
                f.write(code)
                tmp_path = f.name

            try:
                py_compile.compile(tmp_path, doraise=True)
            except py_compile.PyCompileError as e:
                errors.append(f'{file}: {e}')
            finally:
                os.unlink(tmp_path)

        if errors:
            return False, "\n".join(errors)
        else:
            return True, ""


    def run(self, instruction: str, context: str) -> str:
        dummy_dict = dict()
        dummy_dict['dummy_file'] = context
        is_valid, error = self.check_syntax(dummy_dict)
        return "" if is_valid else error