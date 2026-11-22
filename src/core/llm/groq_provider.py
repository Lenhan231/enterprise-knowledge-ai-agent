import os
import re
import threading
import time
from types import SimpleNamespace

from dotenv import load_dotenv
from openai import InternalServerError, OpenAI, RateLimitError

from core.llm.llm_interface import LLMInterface
from core.agents.runtime import remaining
from core.prompts.examples import GROQ_SMOKE_PROMPT


load_dotenv()


# Per-call timeout; eval raises it for slower self-hosted serving (quality runs, not latency runs).
CALL_TIMEOUT = float(os.getenv('LLM_CALL_TIMEOUT', '60'))

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
        # Evaluation only: GROQ_BASE_URL points the same calls at a self-hosted copy of the model (vLLM).
        self._self_hosted = bool(os.getenv('GROQ_BASE_URL'))
        self._clients = [OpenAI(api_key=key, base_url=os.getenv('GROQ_BASE_URL') or 'https://api.groq.com/openai/v1')
                         for key in keys]
        self.client = self._clients[0]
        self._active = 0
        self._cooldowns = [0.0] * len(keys)
        self._lock = threading.Lock()
        self._last_rate_error = None

    def generate(self, prompt: str, *, max_output_tokens: int = 1000, response_schema: dict | None = None) -> str:
        if not 1 <= max_output_tokens <= 4096:
            raise ValueError("Output token budget must be between 1 and 4096")
        self.last_usage = None
        with self._lock:
            order = [(self._active + offset) % len(self._clients) for offset in range(len(self._clients))]
        response = None
        last_rate_error = self._last_rate_error
        last_rate_index = None
        rate_limited_this_call = False
        for index in order:
            remaining(CALL_TIMEOUT)
            with self._lock:
                cooling = self._cooldowns[index] > time.monotonic()
            if cooling:
                continue
            try:
                response = self._create(index, prompt, max_output_tokens, **({'response_schema': response_schema} if response_schema else {}))
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
                last_rate_error = error
                last_rate_index = index
                rate_limited_this_call = True
        if response is None and rate_limited_this_call and last_rate_error is not None:
            message = str(last_rate_error).casefold()
            if 'tokens per minute' in message:
                retry_after = last_rate_error.response.headers.get('retry-after')
                try:
                    delay = float(retry_after)
                except (TypeError, ValueError):
                    match = re.search(r'try again in ([\d.]+)s', message)
                    delay = float(match.group(1)) if match else None
                if delay is not None and 0 <= delay <= 10 and remaining(CALL_TIMEOUT) > delay + 1:
                    time.sleep(delay + 1)
                    response = self._create(last_rate_index, prompt, max_output_tokens, **({'response_schema': response_schema} if response_schema else {}))
                    with self._lock:
                        self._active = last_rate_index
        if response is None:
            raise last_rate_error or RuntimeError('No Groq key is currently available')

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

    def _create(self, index, prompt, max_output_tokens, *, response_schema=None):
        for attempt in range(2):
            client = self._clients[index].with_options(timeout=remaining(CALL_TIMEOUT), max_retries=0)
            try:
                if response_schema:
                    schema = response_schema.copy()
                    instruction = schema.pop('description', 'Return only a response matching the supplied JSON schema.')
                    result = client.chat.completions.create(
                        model=self.model_name, messages=[{'role': 'system', 'content': instruction},
                            {'role': 'user', 'content': prompt}],
                        temperature=self.temperature, **(self._self_hosted_reasoning() if self._self_hosted else {'reasoning_effort': self.reasoning_effort}),
                        max_completion_tokens=max_output_tokens,
                        response_format={'type': 'json_schema', 'json_schema': {
                            'name': 'dashboard_response', 'strict': True, 'schema': schema}},
                    )
                    usage = result.usage
                    return SimpleNamespace(output_text=result.choices[0].message.content or '',
                        usage=None if usage is None else SimpleNamespace(
                            input_tokens=usage.prompt_tokens, output_tokens=usage.completion_tokens,
                            total_tokens=usage.total_tokens))
                if self._self_hosted:  # vLLM: chat completions; Qwen's thinking off matches Groq's reasoning effort "none"
                    result = client.chat.completions.create(
                        model=self.model_name, messages=[{'role': 'user', 'content': prompt}],
                        temperature=self.temperature, max_tokens=max_output_tokens,
                        **self._self_hosted_reasoning())
                    usage = result.usage
                    return SimpleNamespace(output_text=result.choices[0].message.content or '',
                        usage=None if usage is None else SimpleNamespace(
                            input_tokens=usage.prompt_tokens, output_tokens=usage.completion_tokens,
                            total_tokens=usage.total_tokens))
                return client.responses.create(
                    model=self.model_name, input=prompt, temperature=self.temperature,
                    reasoning={"effort": self.reasoning_effort}, max_output_tokens=max_output_tokens,
                )
            except InternalServerError as error:
                # 503 "over capacity" is model-wide, so another key does not help; one short retry often does.
                if attempt or error.status_code != 503:
                    raise
                time.sleep(min(1.0, remaining(CALL_TIMEOUT)))

    def _self_hosted_reasoning(self):
        # vLLM: Qwen's thinking is a chat-template switch (off = Groq's "none"); gpt-oss takes reasoning_effort as Groq does.
        if self.model_name.startswith('qwen/'):
            return {'extra_body': {'chat_template_kwargs': {'enable_thinking': False}}}
        return {'reasoning_effort': self.reasoning_effort}

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
