"""Hugging Face Inference Providers fallback for decision suggestions."""

import os

from openai import OpenAI

from core.llm.llm_interface import EmptyLLMResponseError, LLMInterface


class HuggingFaceProvider(LLMInterface):
    def __init__(self):
        self.api_key = os.getenv("HUGGINGFACE_API_KEY")
        if not self.api_key:
            raise ValueError("HUGGINGFACE_API_KEY is not set")
        self.model_name = os.getenv("HUGGINGFACE_LLM_MODEL", "openai/gpt-oss-20b:cheapest")
        self.last_usage = None
        self.client = OpenAI(
            api_key=self.api_key,
            base_url="https://router.huggingface.co/v1",
            max_retries=0,
            timeout=45,
        )

    def generate(self, prompt: str, *, instructions: str | None = None) -> str:
        self.last_usage = None
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
        usage = getattr(response, "usage", None)
        if usage is not None:
            self.last_usage = {
                "input_tokens": getattr(usage, "prompt_tokens", None),
                "output_tokens": getattr(usage, "completion_tokens", None),
                "total_tokens": getattr(usage, "total_tokens", None),
            }
        choice = response.choices[0]
        answer = (choice.message.content or "").strip()
        if not answer:
            raise EmptyLLMResponseError(
                "Hugging Face Inference Providers returned empty output "
                f"(model={response.model}, finish_reason={choice.finish_reason})"
            )
        return answer

    def close(self) -> None:
        self.client.close()
