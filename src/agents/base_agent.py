from abc import ABC, abstractmethod
from typing import Dict, Any, Optional


class BaseAgent(ABC):
    """
    Abstract base class for all agents.
    """

    def __init__(self):
        pass

    @abstractmethod
    def run(
            self,
            instruction: str,
            context: str,
    ) -> str:
        """
        Execute the agent.

        Args:
            instruction: Refactoring instruction/task.
            context: Retrieved code context.

        Returns:
            str containing output of the agent.
        """
        pass