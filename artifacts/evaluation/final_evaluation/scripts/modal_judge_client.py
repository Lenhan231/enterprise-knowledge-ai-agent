"""Standalone GPT-OSS judge for local evaluations."""

import os
from pathlib import Path
from urllib.parse import urlsplit

from dotenv import load_dotenv
from openai import OpenAI


class ModalJudge:
    def __init__(self) -> None:
        load_dotenv(Path(__file__).resolve().parents[1] / ".env")
        base_url = os.getenv("MODAL_JUDGE_BASE_URL", "")
        api_key = os.getenv("MODAL_JUDGE_API_KEY", "")
        if not base_url or not api_key:
            raise ValueError("Set MODAL_JUDGE_BASE_URL and MODAL_JUDGE_API_KEY in .env")

        endpoint = urlsplit(base_url)
        if (
            endpoint.scheme != "https"
            or not (endpoint.hostname or "").endswith(".modal.run")
            or endpoint.netloc != endpoint.hostname
            or endpoint.path.rstrip("/") != "/v1"
            or endpoint.query
            or endpoint.fragment
        ):
            raise ValueError("MODAL_JUDGE_BASE_URL must be an HTTPS Modal endpoint ending in /v1")

        self.client = OpenAI(base_url=base_url, api_key=api_key, max_retries=6, timeout=300)

    def generate(self, prompt: str) -> str:
        response = self.client.chat.completions.create(
            model="openai/gpt-oss-120b",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.01,
            max_completion_tokens=4000,
        )
        answer = (response.choices[0].message.content or "").strip()
        if not answer:
            raise RuntimeError("The Modal judge returned an empty answer")
        return answer

    def close(self) -> None:
        self.client.close()
