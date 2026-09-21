# src/core/llm/groq_provider.py
from openai import OpenAI
import os
from dotenv import load_dotenv
load_dotenv()

# from pydantic import BaseModel
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
            temperature=0,
            reasoning={"effort": "low"},
            max_output_tokens=1000,
        )

         answer = response.output_text.strip()

        if not answer:
            raise RuntimeError(
                "Groq returned empty output "
                f"(status={getattr(response, 'status', None)}, "
                f"incomplete={getattr(response, 'incomplete_details', None)})"
            )

        return answer
    
    # def generate_json(
    #     self,
    #     prompt: str,
    #     schema: type[BaseModel],
    # ) -> BaseModel:
    #     schema_json = schema.model_json_schema()
    #     system_prompt = f"Output valid JSON that matches the following schema:\n{schema_json}"
        
    #     response = self.client.chat.completions.create(
    #         model="openai/gpt-oss-20b",
    #         messages=[
    #             {"role": "system", "content": system_prompt},
    #             {"role": "user", "content": prompt}
    #         ],
    #         response_format={"type": "json_object"},
    #         temperature=0,
    #         max_tokens=1000,
    #     )

    #     return schema.model_validate_json(response.choices[0].message.content)

if __name__ == "__main__":
    response = GroqProvider()
    print(response.generate("What is RAG? Answer in one sentence."))