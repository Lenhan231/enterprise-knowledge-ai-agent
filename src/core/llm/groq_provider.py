# src/core/llm/groq_provider.py
import base64
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
        self.model_name = os.getenv("GROQ_MODEL", "openai/gpt-oss-20b")
        self.vision_model_name = os.getenv("GROQ_VISION_MODEL", "qwen/qwen3.8-27b")
        self.reasoning_effort = "none" if self.model_name.startswith("qwen/") else "low"
        self.last_usage = None
        self.client = OpenAI(
                    api_key=self.groq_api_key,
                    base_url="https://api.groq.com/openai/v1",
                )
        
    def generate(self, prompt: str) -> str:
        response = self.client.responses.create(
            model=self.model_name,
            input=prompt,
            temperature=0,
            reasoning={"effort": self.reasoning_effort},
            max_output_tokens=1000,
        )

        answer = response.output_text.strip()
        usage = getattr(response, "usage", None)
        token_count = lambda field: (
            getattr(usage, field, None) if isinstance(getattr(usage, field, None), int) else None
        )
        self.last_usage = {
            "input_tokens": token_count("input_tokens"),
            "output_tokens": token_count("output_tokens"),
            "total_tokens": token_count("total_tokens"),
        } if usage is not None else None

        if not answer:
            raise RuntimeError(
                "Groq returned empty output "
                f"(status={getattr(response, 'status', None)}, "
                f"incomplete={getattr(response, 'incomplete_details', None)})"
            )

        return answer

    def caption_image(self, image: bytes, mime_type: str) -> str:
        """Create a short visual description using Groq's vision-capable model."""
        if len(image) > 14 * 1024 * 1024:
            raise ValueError("Image is too large for the bounded base64 vision request")
        if mime_type not in {"image/png", "image/jpeg", "image/webp"}:
            raise ValueError("Vision captions require PNG, JPEG, or WebP image data")

        data_url = f"data:{mime_type};base64,{base64.b64encode(image).decode('ascii')}"
        response = self.client.responses.create(
            model=self.vision_model_name,
            input=[{
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": (
                            "Describe only the visible content of this business document image "
                            "in one concise sentence. Preserve readable labels and values; "
                            "do not infer causes or conclusions."
                        ),
                    },
                    {"type": "input_image", "detail": "auto", "image_url": data_url},
                ],
            }],
            max_output_tokens=160,
        )
        answer = response.output_text.strip()
        if not answer:
            raise RuntimeError("Groq returned an empty image caption")
        return answer

    def close(self) -> None:
        self.client.close()
    
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
