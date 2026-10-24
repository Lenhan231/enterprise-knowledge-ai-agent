from abc import ABC, abstractmethod

from core.models.agents import AgentRequest, AgentResult


class BaseAgent(ABC):
    @abstractmethod
    async def run(self, request: AgentRequest) -> AgentResult:
        pass

    @abstractmethod
    async def close(self) -> None:
        pass
