from abc import ABC, abstractmethod

from core.models.agents import AgentRequest, AgentResult


class BaseAgent(ABC):
    @abstractmethod
    def run(self, request: AgentRequest) -> AgentResult:
        ...