# src/core/llm/llm_interface.py
from abc import ABC, abstractmethod


class LLMInterface(ABC):

    @abstractmethod
    def generate(self, prompt: str) -> str:
        pass