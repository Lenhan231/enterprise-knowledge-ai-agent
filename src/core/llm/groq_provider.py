import os
import re
import threading
import time

from dotenv import load_dotenv
from openai import OpenAI, RateLimitError

from core.llm.llm_interface import LLMInterface
from core.agents.runtime import remaining
from core.prompts.examples import GROQ_SMOKE_PROMPT


load_dotenv()


class GroqProvider(LLMInterface):
    """OpenAI-compatible Groq provider with benchmark-safe model overrides."""

    def __init__(self, model: str | None = None, temperature: float = 0, api_key: str | None = None,
                 *, api_keys: list[str] | None = None):
        keys = api_keys if api_keys is not None else ([api_key] if api_key is not None else [
            os.getenv('GROQ_API_KEY'), *(os.environ[name] for name in sorted(os.environ)
                                       if re.fullmatch(r'GROQ_API_KEY_\d+', name))])
        keys = list(dict.fromkeys(key for key in keys if key))
        if not keys:
            raise ValueError("GROQ_API_KEY is not set")

        self.model_name = model or os.getenv("GROQ_MODEL", "qwen/qwen3.8-27b")
        # Keep the historical attribute for existing benchmark callers.
        self.model = self.model_name
        self.temperature = temperature
        self.reasoning_effort = "none" if self.model_name.startswith("qwen/") else "low"
        self.last_usage: dict[str, int | None] | None = None
        self._clients = [OpenAI(api_key=key, base_url='https://api.groq.com/openai/v1') for key in keys]
        self.client = self._clients[0]
        self._active = 0
        self._cooldowns = [0.0] * len(keys)
        self._lock = threading.Lock()
        self._last_rate_error = None

    def generate(self, prompt: str, *, max_output_tokens: int = 1000) -> str:
        if not 1 <= max_output_tokens <= 4096:
            raise ValueError("Output token budget must be between 1 and 4096")
        with self._lock:
            order = [(self._active + offset) % len(self._clients) for offset in range(len(self._clients))]
        response = None
        for index in order:
            remaining(60)
            with self._lock:
                cooling = self._cooldowns[index] > time.monotonic()
            if cooling:
                continue
            try:
                client = self._clients[index].with_options(timeout=remaining(60), max_retries=0)
                response = client.responses.create(
                    model=self.model_name, input=prompt, temperature=self.temperature,
                    reasoning={"effort": self.reasoning_effort}, max_output_tokens=max_output_tokens,
                )
                with self._lock:
                    self._active = index
                break
            except RateLimitError as error:
                try:
                    cooldown = max(1, float(error.response.headers.get('retry-after', 60)))
                except (ValueError, TypeError):
                    cooldown = 60
                with self._lock:
                    self._cooldowns[index] = time.monotonic() + min(cooldown, 3600)
                    self._last_rate_error = error
        if response is None:
            raise self._last_rate_error or RuntimeError('No Groq key is currently available')

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
        for client in self._clients:
            client.close()


if __name__ == "__main__":
    provider = GroqProvider()
    try:
        print(provider.generate(GROQ_SMOKE_PROMPT))
    finally:
        provider.close()
