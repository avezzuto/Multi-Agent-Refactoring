from pathlib import Path

from langchain_core.messages import SystemMessage, HumanMessage

from src.agents.base_agent import BaseAgent
from src.agents.planner_agent import (
    PlannerAgent,
    RefactoringRequest,
)
from src.prompts import (
    VANILLA_REFACTORING_SYSTEM_PROMPT,
    VANILLA_REFACTORING_HUMAN_PROMPT,
)
from src.utils.google_client import create_model
from src.utils.logger import logger


class VanillaAgent(BaseAgent):

    def __init__(self, model_name: str):
        super().__init__()

        self.model = create_model(model_name)
        self.planner = PlannerAgent(model_name)

    def run(
            self,
            instruction: str,
            repository_path: Path,
    ) -> dict[str, str]:

        logger.info("[Vanilla] Running...")
        logger.info(
            f"[Vanilla] Instruction: {instruction}"
        )

        files = self.planner._read_python_files(
            repository_path
        )

        targets = self.planner._extract_target_identifiers(
            instruction
        )

        logger.info(
            f"[Vanilla] Identifiers: "
            f"{targets.identifiers}"
        )

        affected_files = set()

        for identifier in targets.identifiers:

            logger.info(
                f"[Vanilla] Resolving "
                f"'{identifier}'..."
            )

            entity_type = (
                self.planner._resolve_identifier_type(
                    identifier=identifier,
                    files=files,
                )
            )

            logger.info(
                f"[Vanilla] "
                f"{identifier} -> {entity_type}"
            )

            request = RefactoringRequest(
                refactoring_entity=entity_type,
                identifier=identifier,
            )

            if entity_type == "variable":

                evidence = (
                    self.planner._collect_variable_evidence(
                        request=request,
                        files=files,
                    )
                )

            elif entity_type == "method":

                evidence = (
                    self.planner._collect_method_evidence(
                        request=request,
                        files=files,
                    )
                )

            else:

                logger.warning(
                    f"[Vanilla] Unsupported "
                    f"entity type: {entity_type}"
                )

                continue

            logger.debug(
                f"[Vanilla] Evidence for "
                f"{identifier}: "
                f"{len(evidence.definitions)} definitions, "
                f"{len(evidence.usages)} usages"
            )

            affected_files.update(
                evidence.affected_files
            )

        logger.info(
            f"[Vanilla] Found "
            f"{len(affected_files)} affected files"
        )

        logger.debug(
            "[Vanilla] Affected files:\n" +
            "\n".join(sorted(affected_files))
        )

        refactored_files = {}

        for file_path in sorted(affected_files):

            logger.info(
                f"[Vanilla] Refactoring "
                f"{file_path}"
            )

            source_code = files[file_path]

            response = self.model.invoke(
                [
                    SystemMessage(
                        content=(
                            VANILLA_REFACTORING_SYSTEM_PROMPT
                        )
                    ),
                    HumanMessage(
                        content=(
                            VANILLA_REFACTORING_HUMAN_PROMPT.format(
                                instruction=instruction,
                                file_path=file_path,
                                source_code=source_code,
                            )
                        )
                    ),
                ]
            )

            result = response.content.strip()

            logger.debug(
                f"[Vanilla] Generated "
                f"{len(result)} chars for "
                f"{Path(file_path).name}"
            )

            if not result:

                logger.warning(
                    f"[Vanilla] Empty response "
                    f"for {file_path}"
                )

                continue

            refactored_files[file_path] = result

        logger.info(
            f"[Vanilla] Refactored "
            f"{len(refactored_files)} files"
        )

        logger.debug(
            list(refactored_files.keys())
        )

        return refactored_files

