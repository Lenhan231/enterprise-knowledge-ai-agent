import time

from dotenv import load_dotenv
from openai import OpenAI, RateLimitError

from core.llm.llm_interface import LLMInterface


load_dotenv()


class OpenAICompatibleProvider(LLMInterface):
    def __init__(
        self,
        model: str,
        base_url: str,
        api_key: str,
        temperature: float = 0,
    ) -> None:
        self.model = model
        self.temperature = temperature
        self.client = OpenAI(api_key=api_key, base_url=base_url)

    def generate(self, prompt: str) -> str:
        for attempt in range(2):
            try:
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=self.temperature,
                    max_tokens=1000,
                )
                break
            except RateLimitError as error:
                if attempt:
                    raise
                retry_after = error.response.headers.get("retry-after")
                if retry_after is None:
                    raise
                time.sleep(float(retry_after))

        answer = response.choices[0].message.content or ""
        if not answer.strip():
            raise RuntimeError(f"{self.model} returned empty output")
        return answer.strip()