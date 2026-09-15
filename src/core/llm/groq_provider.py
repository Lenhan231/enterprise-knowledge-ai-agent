# src/core/llm/groq_provider.py
from openai import OpenAI
import os
from dotenv import load_dotenv
load_dotenv()

from core.llm.llm_interface import LLMInterface


class GroqProvider(LLMInterface):
    def __init__(self):
        self.groq_api_key = os.getenv("GROQ_API_KEY")
        if self.groq_api_key is None:
            raise ValueError("GROQ_API_KEY is not set")
        self.client = OpenAI(
                    api_key=self.groq_api_key,
                    base_url="https://api.groq.com/openai/v1",
                )
        
    def generate(self, prompt: str) -> str:
        response = self.client.responses.create(
            model="openai/gpt-oss-20b",
            input=prompt,
            max_output_tokens=500,
        )

        return response.output_text
    
if __name__ == "__main__":
    response = GroqProvider()
    print(response.generate("What is RAG? Answer in one sentence."))