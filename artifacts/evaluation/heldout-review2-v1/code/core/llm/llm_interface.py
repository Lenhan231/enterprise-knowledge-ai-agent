# src/core/llm/llm_interface.py
from abc import ABC, abstractmethod
from pydantic import BaseModel


class EmptyLLMResponseError(RuntimeError):
    """A provider completed a request without returning usable text."""


class LLMInterface(ABC):

    @abstractmethod
    def generate(self, prompt: str, *, instructions: str | None = None) -> str:
        pass
    
    # @abstractmethod
    # def generate_json(
    #     self,
    #     prompt: str,
    #     schema: type[BaseModel],
    # ) -> BaseModel:
    #     pass
