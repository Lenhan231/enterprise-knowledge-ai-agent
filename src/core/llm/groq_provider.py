import os

from dotenv import load_dotenv
from openai import OpenAI

from core.llm.llm_interface import LLMInterface


load_dotenv()


class GroqProvider(LLMInterface):
    """OpenAI-compatible Groq provider with benchmark-safe model overrides."""

    def __init__(self, model: str | None = None, temperature: float = 0):
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            raise ValueError("GROQ_API_KEY is not set")

        self.model_name = model or os.getenv("GROQ_MODEL", "openai/gpt-oss-20b")
        # Keep the historical attribute for existing benchmark callers.
        self.model = self.model_name
        self.temperature = temperature
        self.reasoning_effort = "none" if self.model_name.startswith("qwen/") else "low"
        self.last_usage: dict[str, int | None] | None = None
        self.client = OpenAI(
            api_key=api_key,
            base_url="https://api.groq.com/openai/v1",
        )

    def generate(self, prompt: str) -> str:
        response = self.client.responses.create(
            model=self.model_name,
            input=prompt,
            temperature=self.temperature,
            reasoning={"effort": self.reasoning_effort},
            max_output_tokens=1000,
        )

        answer = response.output_text.strip()
        usage = getattr(response, "usage", None)
        self.last_usage = None if usage is None else {
            "input_tokens": self._token_count(usage, "input_tokens"),
            "output_tokens": self._token_count(usage, "output_tokens"),
            "total_tokens": self._token_count(usage, "total_tokens"),
        }
        if not answer:
            raise RuntimeError(
                "Groq returned empty output "
                f"(status={getattr(response, 'status', None)}, "
                f"incomplete={getattr(response, 'incomplete_details', None)})"
            )
        return answer

    @staticmethod
    def _token_count(usage, field: str) -> int | None:
        value = getattr(usage, field, None)
        return value if isinstance(value, int) else None

    def close(self) -> None:
        self.client.close()


if __name__ == "__main__":
    provider = GroqProvider()
    try:
        print(provider.generate("RAG là gì? Trả lời bằng một câu tiếng Việt."))
    finally:
        provider.close()
