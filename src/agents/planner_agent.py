import ast
import json
import re
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Optional
from langchain_core.messages import SystemMessage, HumanMessage

from src.utils.google_client import create_model
from src.agents.base_agent import BaseAgent
from src.prompts import (
    PLANNER_SYSTEM_PROMPT,
    PARSE_MULTIPLE_REFACTORINGS_PROMPT,
    FILE_LEVEL_PLAN_PROMPT,
)
from src.testing.test_creator import TestCreator, logger


@dataclass
class Location:
    """
    Stores a place in the code where something was found.
    """
    file: str
    line: int
    column: int
    context: str


@dataclass
class RefactoringRequest:
    refactoring_entity: str
    identifier: str


@dataclass
class RefactoringEvidence:
    refactoring_entity: str
    identifier: str
    definitions: list[Location]
    usages: list[Location]
    affected_files: list[str]
    risk_notes: list[str]

@dataclass
class RefactoringTarget:
    identifiers: list[str]

class PlannerAgent(BaseAgent):
    """
    Planner agent for Python refactoring tasks.

    It:
    - receives an optional instruction;
    - if instruction exists, parses one or more refactorings;
    - if no instruction exists, asks the LLM to discover refactorings;
    - scans the repository using AST tools;
    - creates evidence for each refactoring;
    - asks the LLM once to create per-file plans.
    """

    def __init__(self, model_name: str | None = None):
        super().__init__()

        if not model_name:
            raise ValueError("PlannerAgent requires a model_name.")

        self.model = create_model(model_name)

        self.test_creator = TestCreator(model_name)



    def run(
            self,
            instruction: Optional[str],
            repository_path: Path,
            context: str | None = None,
    ) -> tuple[str, list[str], float]:
        """
        Main planner entry point.

        Args:
            instruction: Optional user/benchmark instruction.
            repository_path: Path to the repository that should be analyzed.

        Returns:
            JSON with file-level natural-language plans.
        """

        if not repository_path.exists():
            raise FileNotFoundError(f"Repository path does not exist: {repository_path}")

        files = self._read_python_files(repository_path)

        target = (
            self._extract_target_identifiers(
                instruction
            )
        )

        logger.debug(f"Extracted target identifiers with instruction \"{instruction}\": {target}\n")

        refactorings = []

        for identifier in target.identifiers:

            entity_type = (
                self._resolve_identifier_type(
                    identifier=identifier,
                    files=files,
                )
            )

            refactorings.append(
                RefactoringRequest(
                    refactoring_entity=entity_type,
                    identifier=identifier,
                )
            )

        all_evidence = []

        for request in refactorings:
            if request.refactoring_entity == "variable":
                evidence = self._collect_variable_evidence(
                    request=request,
                    files=files,
                )
            elif request.refactoring_entity == "method":
                evidence = self._collect_method_evidence(
                    request=request,
                    files=files,
                )
            else:
                raise ValueError(f"Unsupported refactoring entity: {request.refactoring_entity}")

            all_evidence.append(evidence)

        logger.info("[Planner Debug] Refactorings:")
        logger.info([asdict(r) for r in refactorings])

        logger.info("[Planner Debug] Evidence affected files:")
        logger.info([e.affected_files for e in all_evidence])

        try:
            test_evidence, test_paths, test_coverage = (
                self._test_preparation(
                    repository_path=repository_path,
                    evidence=all_evidence,
                    refactorings=refactorings,
                )
            )
        except Exception:
            logger.exception("[Planner] Test preparation failed; continuing without generated tests.")
            test_evidence = []
            test_paths = []
            test_coverage = 0.0

        all_evidence.extend(test_evidence)

        return self._generate_file_level_plan_with_llm(all_evidence, instruction), test_paths, test_coverage

    # ------------------------------------------------------------------
    # Test Preparation
    # ------------------------------------------------------------------

    def _test_preparation(
            self,
            repository_path: Path,
            evidence: list[RefactoringEvidence],
            refactorings: list[RefactoringRequest],
    ) -> tuple[list[RefactoringEvidence], list[str], float]:

        affected_files = set()

        for item in evidence:
            affected_files.update(
                item.affected_files
            )

        test_context = (
            self.test_creator.prepare_test_context(
                repo_path=repository_path,
                generated_tests_root=(
                        repository_path /
                        "generated_tests"
                ),
                changed_files=[
                    Path(path)
                    for path in affected_files
                ],
            )
        )
        test_coverage = test_context.get("test_coverage", 0.0)

        existing_tests = (
            test_context["visible_tests"]
        )

        generated_tests = (
            test_context["hidden_generated_tests"]
        )

        test_files = {}

        for test_file in [
            *generated_tests,
        ]:

            test_path = Path(test_file)

            try:
                test_files[str(test_path)] = (
                    test_path.read_text(
                        encoding="utf-8"
                    )
                )

            except Exception:
                continue

        test_evidence = []

        for request in refactorings:
            if (request.refactoring_entity == "variable"):
                test_evidence.append(
                    self._collect_variable_evidence(
                        request=request,
                        files=test_files,
                    )
                )

            elif (request.refactoring_entity == "method"):
                test_evidence.append(
                    self._collect_method_evidence(
                        request=request,
                        files=test_files,
                    )
                )

        return test_evidence, generated_tests + existing_tests, test_coverage
    # ------------------------------------------------------------------
    # Repository reading
    # ------------------------------------------------------------------

    def _read_python_files(self, repository_path: Path) -> dict[str, str]:
        files = {}

        for path in repository_path.rglob("*.py"):
            if "venv" in path.parts or ".venv" in path.parts or "build" in path.parts:
                continue

            try:
                files[str(path)] = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            except OSError:
                continue

        return files

    # ------------------------------------------------------------------
    # Refactoring request parsing / discovery
    # ------------------------------------------------------------------

    def _extract_target_identifiers(
            self,
            instruction: str,
    ) -> RefactoringTarget:

        prompt = PARSE_MULTIPLE_REFACTORINGS_PROMPT.format(instruction=instruction)
        parsed = self._invoke_json(prompt)

        return RefactoringTarget(
            identifiers=parsed["identifiers"]
        )

    def _resolve_identifier_type(
            self,
            identifier: str,
            files: dict[str, str],
    ) -> str:

        method_hits = 0
        variable_hits = 0

        for filename, code in files.items():

            if code.find(identifier) != -1:

                try:
                    tree = ast.parse(code)

                except SyntaxError:
                    continue

                for node in ast.walk(tree):

                    if (isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == identifier):
                        method_hits += 1

                    elif (isinstance(node, ast.Name) and isinstance(node.ctx, (ast.Store)) and node.id == identifier):
                        variable_hits += 1

        if not method_hits and not variable_hits:
            raise ValueError(
                f"Could not determine type for "
                f"'{identifier}'"
            )

        if (method_hits and not variable_hits) or method_hits >= variable_hits:
            return "method"

        return "variable"



    # ------------------------------------------------------------------
    # Evidence collection
    # ------------------------------------------------------------------

    def _collect_variable_evidence(
        self,
        request: RefactoringRequest,
        files: dict[str, str],
    ) -> RefactoringEvidence:

        definitions: list[Location] = []
        usages: list[Location] = []
        affected_files = set()
        risk_notes = []

        for file_path, code in files.items():
            try:
                tree = ast.parse(code)
            except SyntaxError:
                risk_notes.append(f"Could not parse {file_path} with AST.")
                continue

            visitor = VariableUsageVisitor(
                identifier=request.identifier,
                source_code=code,
                file_path=file_path,
            )
            visitor.visit(tree)

            if visitor.definitions or visitor.usages:
                affected_files.add(file_path)
                definitions.extend(visitor.definitions)
                usages.extend(visitor.usages)

        if not definitions:
            risk_notes.append(
                f"No variable definition named '{request.identifier}' was found."
            )

        if len(definitions) > 1:
            risk_notes.append(
                f"Multiple variable definitions named '{request.identifier}' were found. "
                "The refactoring agent must avoid renaming unrelated variables in different scopes."
            )

        return RefactoringEvidence(
            refactoring_entity=request.refactoring_entity,
            identifier=request.identifier,
            definitions=definitions,
            usages=usages,
            affected_files=sorted(affected_files),
            risk_notes=risk_notes,
        )

    def _collect_method_evidence(
        self,
        request: RefactoringRequest,
        files: dict[str, str],
    ) -> RefactoringEvidence:

        definitions: list[Location] = []
        usages: list[Location] = []
        affected_files = set()
        risk_notes = []

        for file_path, code in files.items():
            try:
                tree = ast.parse(code)
            except SyntaxError:
                risk_notes.append(f"Could not parse {file_path} with AST.")
                continue

            visitor = MethodUsageVisitor(
                identifier=request.identifier,
                source_code=code,
                file_path=file_path,
            )
            visitor.visit(tree)

            if visitor.definitions or visitor.usages:
                affected_files.add(file_path)
                definitions.extend(visitor.definitions)
                usages.extend(visitor.usages)

        if not definitions:
            risk_notes.append(
                f"No method/function definition named '{request.identifier}' was found."
            )

        return RefactoringEvidence(
            refactoring_entity=request.refactoring_entity,
            identifier=request.identifier,
            definitions=definitions,
            usages=usages,
            affected_files=sorted(affected_files),
            risk_notes=risk_notes,
        )

    # ------------------------------------------------------------------
    # Final per-file plan generation
    # ------------------------------------------------------------------
    # Expected planner output format:
    #
    # {
    #   "file_plans": [
    #     {
    #       "file": "path/to/file.py",
    #       "refactoring_entity": "method",
    #       "refactorings": [
    #         {
    #           "refactoring_entity": "method",
    #           "identifier": "fetch_data",
    #         }
    #       ],
    #       "plan": "Step-by-step natural language plan for this file."
    #     }
    #   ]
    # }
    #

    def _generate_file_level_plan_with_llm(
        self,
        evidence: list[RefactoringEvidence],
        instruction: Optional[str],
    ) -> str:

        refactorings_payload = [
            {
                "refactoring_entity": item.refactoring_entity,
                "identifier": item.identifier,
            }
            for item in evidence
        ]

        evidence_payload = [asdict(item) for item in evidence]

        prompt = FILE_LEVEL_PLAN_PROMPT.format(
            instruction=instruction or "No specific instruction provided. Discover refactorings autonomously based on the evidence.",
            refactorings=json.dumps(refactorings_payload, indent=2),
            tool_evidence=json.dumps(evidence_payload, indent=2),
        )

        parsed = self._invoke_json(prompt)

        logger.debug(f"Generated file-level plan:\n{json.dumps(parsed, indent=2)}\n")

        return json.dumps(parsed, indent=2)

    # ------------------------------------------------------------------
    # LLM helpers
    # ------------------------------------------------------------------

    def _invoke_json(self, prompt: str) -> dict:
        response = self.model.invoke([SystemMessage(content=PLANNER_SYSTEM_PROMPT), HumanMessage(content=prompt)])

        raw_output = response.content.strip()
        cleaned = self._strip_code_fences(raw_output)

        return json.loads(cleaned)

    def _strip_code_fences(self, text: str) -> str:
        text = text.strip()

        if text.startswith("```"):
            lines = text.splitlines()

            if lines[0].startswith("```"):
                lines = lines[1:]

            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]

            text = "\n".join(lines).strip()

        return text

    def _name_exists_in_code(self, name: str, code: str) -> bool:
        """
        Checks whether the given name (e.g. new variable name or method name) is already present in the context
        :param name:    The name to check
        :param code:    The code
        :return:        A boolean whether the name is present
        """
        return re.search(rf"\b{re.escape(name)}\b", code) is not None


class VariableUsageVisitor(ast.NodeVisitor):
    """
    AST visitor for variable definitions and usages.

    Should find appearances like:
    - x = ...
    - for x in ...
    - with ... as x
    - function parameters named x
    - usages of x
    """

    def __init__(self, identifier: str, source_code: str, file_path: str):
        self.identifier = identifier
        self.source_code = source_code
        self.file_path = file_path
        self.definitions: list[Location] = []
        self.usages: list[Location] = []

    def visit_Name(self, node: ast.Name) -> Any:
        if node.id == self.identifier:
            location = self._to_location(node)

            if isinstance(node.ctx, ast.Store):
                self.definitions.append(location)
            elif isinstance(node.ctx, ast.Load):
                self.usages.append(location)

        self.generic_visit(node)

    def visit_arg(self, node: ast.arg) -> Any:
        if node.arg == self.identifier:
            self.definitions.append(self._to_location(node))

        self.generic_visit(node)

    def _to_location(self, node: ast.AST) -> Location:
        line = getattr(node, "lineno", -1)
        column = getattr(node, "col_offset", -1)
        context = self.source_code.splitlines()[line - 1].strip() if line > 0 else ""

        return Location(
            file=self.file_path,
            line=line,
            column=column,
            context=context,
        )


class MethodUsageVisitor(ast.NodeVisitor):
    """
    AST visitor for method/function definitions and calls.

    Finds:
    - def identifier(...)
    - obj.identifier(...)
    - identifier(...)
    """

    def __init__(self, identifier: str, source_code: str, file_path: str):
        self.identifier = identifier
        self.source_code = source_code
        self.file_path = file_path
        self.definitions: list[Location] = []
        self.usages: list[Location] = []

    def visit_FunctionDef(self, node: ast.FunctionDef) -> Any:
        if node.name == self.identifier:
            self.definitions.append(self._to_location(node))

        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> Any:
        if node.name == self.identifier:
            self.definitions.append(self._to_location(node))

        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> Any:
        if isinstance(node.func, ast.Attribute):
            if node.func.attr == self.identifier:
                self.usages.append(self._to_location(node))

        elif isinstance(node.func, ast.Name):
            if node.func.id == self.identifier:
                self.usages.append(self._to_location(node))

        self.generic_visit(node)

    def _to_location(self, node: ast.AST) -> Location:
        line = getattr(node, "lineno", -1)
        column = getattr(node, "col_offset", -1)
        context = self.source_code.splitlines()[line - 1].strip() if line > 0 else ""

        return Location(
            file=self.file_path,
            line=line,
            column=column,
            context=context,
        )
