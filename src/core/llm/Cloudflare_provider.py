"""Cloudflare Workers AI chat completions provider."""

from __future__ import annotations

import json
import os
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from dotenv import load_dotenv

from core.llm.llm_interface import LLMInterface


load_dotenv()


class CloudflareProvider(LLMInterface):
    """Call a Cloudflare Workers AI model through its OpenAI-compatible API."""

    DEFAULT_MODEL = "@cf/meta/llama-3.1-8b-instruct-fp8-fast"

    def __init__(self, model: str | None = None, temperature: float = 0, max_tokens: int | None = None) -> None:
        self.account_id = os.getenv("CLOUDFLARE_ACCOUNT_ID")
        self.api_token = os.getenv("CLOUDFLARE_API_TOKEN") or os.getenv("CLOUDFLARE_WORKERS_API")
        if not self.account_id:
            raise ValueError("CLOUDFLARE_ACCOUNT_ID is not set")
        if not self.api_token:
            raise ValueError("CLOUDFLARE_API_TOKEN or CLOUDFLARE_WORKERS_API is not set")

        self.model_name = model or os.getenv("CLOUDFLARE_MODEL", self.DEFAULT_MODEL)
        self.model = self.model_name
        self.temperature = temperature
        self.max_tokens = max_tokens if max_tokens is not None else (
            2048 if self.model_name.startswith('@cf/openai/gpt-oss-') else 1000)
        self.last_usage = None
        self.endpoint = (
            "https://api.cloudflare.com/client/v4/accounts/"
            f"{self.account_id}/ai/v1/chat/completions"
        )

    def generate(self, prompt: str) -> str:
        if not prompt or not prompt.strip():
            raise ValueError("prompt must not be empty")

        payload = json.dumps({
            "model": self.model_name,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "chat_template_kwargs": {"enable_thinking": False},
            **({'reasoning_effort': 'low'} if self.model_name.startswith('@cf/openai/gpt-oss-') else {}),
        }).encode("utf-8")
        request = Request(
            self.endpoint,
            data=payload,
            headers={
                "Authorization": f"Bearer {self.api_token}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=30) as response:
                result = json.loads(response.read().decode("utf-8"))
        except HTTPError as error:
            details = error.read().decode("utf-8", errors="replace")
            raise RuntimeError(
                f"Cloudflare Workers AI request failed (HTTP {error.code}): {details}"
            ) from error
        except (URLError, TimeoutError) as error:
            raise RuntimeError(f"Cloudflare Workers AI request failed: {error}") from error
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise RuntimeError("Cloudflare Workers AI returned invalid JSON") from error

        try:
            choice = result["choices"][0]
            message = choice["message"]
            answer = message.get("content")
        except (KeyError, IndexError, TypeError) as error:
            raise RuntimeError("Cloudflare Workers AI response did not contain a chat completion") from error
        if not isinstance(answer, str) or not answer.strip():
            raise RuntimeError(
                "Cloudflare Workers AI returned empty output "
                f"(finish_reason={choice.get('finish_reason')!r}, "
                f"message_fields={sorted(message)})"
            )
        self.last_usage = result.get("usage")
        return answer.strip()
