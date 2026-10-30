# src/core/llm/llm_interface.py
from abc import ABC, abstractmethod
from pydantic import BaseModel


class LLMInterface(ABC):

    @abstractmethod
    def generate(self, prompt: str) -> str:
        pass
    
    # @abstractmethod
    # def generate_json(
    #     self,
    #     prompt: str,
    #     schema: type[BaseModel],
    # ) -> BaseModel:
    #     pass