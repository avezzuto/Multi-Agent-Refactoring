import ast
import json
from pathlib import Path
from typing import Any

from langgraph.graph import StateGraph, END

from src.agents import FixerAgent
from src.agents import VariableRefactoringAgent, FunctionRefactoringAgent, GeneralRefactoringAgent
from src.agents.compiler_agent import CompilerAgent
from src.agents.planner_agent import PlannerAgent
from src.agents.test_validator_agent import TestValidatorAgent
from src.state import RefactoringState
from src.utils.logger import logger

MAX_COMPILE_ATTEMPTS = 5
MAX_TEST_ATTEMPTS = 5


def _count_test_functions(test_paths: list[str]) -> int:
    count = 0
    for path in test_paths:
        try:
            tree = ast.parse(Path(path).read_text(encoding="utf-8"))
            count += sum(
                1 for node in ast.walk(tree)
                if isinstance(node, ast.FunctionDef)
                and node.name.startswith("test_")
            )
        except Exception:
            pass
    return count


def build_graph(model_name: str, use_specialised_refactoring_agents: bool = False) -> StateGraph:
    planner = PlannerAgent(model_name)
    compiler = CompilerAgent()
    test_validator = TestValidatorAgent(model_name)
    fixer = FixerAgent(model_name)

    if use_specialised_refactoring_agents:
        variable_refactoring_agent = VariableRefactoringAgent(model_name)
        function_refactoring_agent = FunctionRefactoringAgent(model_name)
    else:
        general_refactoring_agent = GeneralRefactoringAgent(model_name)

    # --- Nodes ---

    def planner_node(state: RefactoringState) -> RefactoringState:
        """Creates a refactoring plan.
        Planner output structure (the intended return from the LLM):

        {
           "file_plans": [
             {
               "file": "path/to/file.py",
               "refactoring_entity": "refactoring_entity",
               "refactorings": [
                 {
                   "refactoring_entity": "refactoring_entity",
                   "identifier": "identifier_to_refactor"
                 }
               ],
               "plan": "Step-by-step natural language plan for this file."
             }
           ]
        }
        """
        repo_name = Path(state["repository_path"]).name
        instruction = state.get("instruction", "")
        logger.info(f"[Task] Repository: {repo_name}")
        logger.info(f"[Task] Instruction: {instruction}")
        logger.info("[Planner] Running...")

        plan_json, validation_tests, test_coverage = planner.run(
            instruction=state.get("instruction"),
            repository_path=Path(state["repository_path"]),
        )

        planner_output = json.loads(plan_json)

        return {
            **state,
            "file_plans": planner_output.get("file_plans", []),
            "validation_tests": [
                str(path)
                for path in validation_tests
            ],
            "tests_generated": _count_test_functions([str(p) for p in validation_tests]),
            "test_coverage": test_coverage
        }

    def refactoring_node(state: RefactoringState) -> RefactoringState:
        """
        Calls the General Refactoring Agent when the graph gets initialised with this flag set, otherwise
        it uses the Variable/Function Renaming Agent depending on which refactoring type has been passed down
        by the planner agent. It does this for each file plan and returns a dictionary with the file name as the key and
        the refactored code as values.
        """
        logger.info("[Refactoring] Running...")

        file_plans: list[dict[str, Any]] = state['file_plans']
        res = dict()

        for file_plan in file_plans:
            instruction: str = file_plan['plan']
            refactorings: list[dict[str, str]] = file_plan['refactorings']

            file: str = file_plan['file']
            original_code = Path(file).read_text()

            refactored = None
            if use_specialised_refactoring_agents:
                refactoring_entity = file_plan['refactoring_entity']
                if refactoring_entity == 'variable':
                    refactored = variable_refactoring_agent.run(
                        instruction=instruction,
                        context=original_code,
                        refactorings=refactorings
                    )
                elif refactoring_entity == 'method':
                    refactored = function_refactoring_agent.run(
                        instruction=instruction,
                        context=original_code,
                        refactorings=refactorings
                    )
                else:
                    logger.error("Refactoring type not supported")
            else:
                refactored = general_refactoring_agent.run(
                    instruction=instruction,
                    context=original_code,
                    refactorings=refactorings
                )

            res[file] = refactored

        logger.debug(res)

        return {
            **state,
            "refactored_code": res,
            "compile_error": None,
            "compile_attempts": 0,
            "test_error": None,
            "test_attempts": 0,
        }

    def compiler_node(state: RefactoringState) -> RefactoringState:
        """Checks syntax. Sets compile_error if invalid."""
        logger.info("[Compiler] Checking syntax...")

        is_valid, error = compiler.check_syntax(
            state["refactored_code"]
        )

        logger.info(
            f"[Compiler] "
            f"{'Valid' if is_valid else f'Invalid: {error}'}"
        )

        return {
            **state,
            "compile_error": None if is_valid else error,
            "compile_attempts": (
                    state["compile_attempts"] + 1
            ),
            "success": is_valid,
        }

    def tester_node(state: RefactoringState) -> RefactoringState:
        logger.info("[Tester] Running...")

        file_plans: list[dict[str, Any]] = state['file_plans']

        logger.debug(file_plans)

        # Save originals and write all refactored files first
        originals = {}
        for file_plan in file_plans:
            target_file_path = file_plan['file']
            logger.debug(f"Target file path: {target_file_path}")
            target_file = Path(target_file_path)
            originals[target_file_path] = target_file.read_text()
            target_file.write_text(state["refactored_code"][target_file_path])

        result = {"success": True, "feedback": None}

        try:
            for file_plan in file_plans:
                instruction: str = file_plan['plan']
                target_file_path = file_plan['file']
                refactorings: list[dict[str, str]] = file_plan['refactorings']
                candidate_code = state["refactored_code"][target_file_path]

                for refactoring in refactorings:
                    result = test_validator.validate(
                        repo_path=state["repository_path"],
                        validation_tests=[
                            Path(path)
                            for path in state["validation_tests"]
                        ],
                        original_code=originals[target_file_path],
                        candidate_code=candidate_code,
                        instruction=instruction,
                    )
                    if not result["success"]:
                        break
                if not result["success"]:
                    break

        finally:
            # Always revert all files
            for file_path, content in originals.items():
                Path(file_path).write_text(content)

        return {
            **state,
            "test_error": None if result["success"] else result["feedback"],
            "test_attempts": state["test_attempts"] + 1,
            "success": result["success"],
        }

    def fixer_node(state: RefactoringState) -> RefactoringState:
        """Fixes syntax or test errors in refactored code."""
        logger.info("[Fixer] Running...")

        is_compile_fix = bool(state.get("compile_error"))
        error = state.get("compile_error") or state.get("test_error") or ""
        error_type = "syntax" if is_compile_fix else "test"

        logger.info(f"[Fixer] Error type: {error_type}, error: {error}")

        fixed = fixer.fix(
            instruction=state.get("instruction", ""),
            refactored_code=state["refactored_code"],
            error=error,
            error_type=error_type,
        )
        # logger.debug(fixed)
        return {
            **state,
            "refactored_code": fixed,
            "compile_error": None,
            "test_error": None,
        }

    # --- Routing ---

    def after_compiler(state: RefactoringState) -> str:
        if state["compile_error"]:
            if state["compile_attempts"] < MAX_COMPILE_ATTEMPTS:
                logger.info(
                    f"[Router] Compile failed "
                    f"(attempt {state['compile_attempts']}/{MAX_COMPILE_ATTEMPTS}), "
                    f"sending to fixer..."
                )
                return "fixer"
            logger.info("[Router] Max compile attempts reached, giving up")
            return END
        if not state["validation_tests"]:
            logger.info("[Router] No tests found, skipping tester...")
            return END
        logger.info("[Router] Compile passed!")
        return "tester"

    def after_tester(state: RefactoringState) -> str:
        if state["test_error"]:
            if state["test_attempts"] < MAX_TEST_ATTEMPTS:
                logger.info(
                    f"[Router] Tests failed "
                    f"(attempt {state['test_attempts']}/{MAX_TEST_ATTEMPTS}), "
                    f"sending to fixer..."
                )
                return "fixer"
            logger.info("[Router] Max test attempts reached, giving up")
            return END
        logger.info("[Router] Validation passed!")
        return END

    # --- Build graph ---

    graph = StateGraph(RefactoringState)

    graph.add_node("planner", planner_node)
    graph.add_node("refactoring", refactoring_node)
    graph.add_node("compiler", compiler_node)
    graph.add_node("tester", tester_node)
    graph.add_node("fixer", fixer_node)

    graph.set_entry_point("planner")
    graph.add_edge("planner", "refactoring")
    graph.add_edge("refactoring", "compiler")
    graph.add_conditional_edges("compiler", after_compiler)
    graph.add_conditional_edges("tester", after_tester)
    graph.add_edge("fixer", "compiler")

    return graph.compile()