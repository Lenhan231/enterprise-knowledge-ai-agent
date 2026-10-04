"""Hugging Face Inference Providers fallback for decision suggestions."""

import os

from openai import OpenAI

from core.llm.llm_interface import LLMInterface


class HuggingFaceProvider(LLMInterface):
    def __init__(self):
        self.api_key = os.getenv("HUGGINGFACE_API_KEY")
        if not self.api_key:
            raise ValueError("HUGGINGFACE_API_KEY is not set")
        self.model_name = os.getenv("HUGGINGFACE_LLM_MODEL", "openai/gpt-oss-20b:cheapest")
        self.client = OpenAI(
            api_key=self.api_key,
            base_url="https://router.huggingface.co/v1",
            max_retries=0,
            timeout=45,
        )

    def generate(self, prompt: str, *, instructions: str | None = None) -> str:
        messages = []
        if instructions:
            messages.append({"role": "system", "content": instructions})
        messages.append({"role": "user", "content": prompt})
        response = self.client.chat.completions.create(
            model=self.model_name,
            messages=messages,
            temperature=0,
            reasoning_effort="low",
            max_completion_tokens=1600,
        )
        choice = response.choices[0]
        answer = (choice.message.content or "").strip()
        if not answer:
            raise RuntimeError(
                "Hugging Face Inference Providers returned empty output "
                f"(model={response.model}, finish_reason={choice.finish_reason})"
            )
        return answer

    def close(self) -> None:
        self.client.close()
