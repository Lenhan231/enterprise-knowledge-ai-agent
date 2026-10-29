import json
from functools import lru_cache
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field
from core.llm.llm_interface import LLMInterface
from core.prompts.translation import AUTO_TRANSLATION_PROMPT, TRANSLATION_PROMPT

class Translation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    translation: str = Field(min_length=1, max_length=4000)


class DetectedTranslation(Translation):
    source_lang: Literal["en", "vn"]
    
class QueryTranslator:
    def __init__(self, llm: LLMInterface):
        self.llm = llm

    @lru_cache(maxsize=256)
    def translate(self, question: str, source_lang: str = "auto") -> dict[str, str]:
        if not isinstance(question, str) or not question.strip() or len(question) > 4000:
            raise ValueError("Question must contain 1–4000 characters of text")
        if source_lang == "auto":
            raw = self.llm.generate(
                AUTO_TRANSLATION_PROMPT.format(question=json.dumps(question, ensure_ascii=False))
            )
            result = DetectedTranslation.model_validate_json(raw)
            translated = result.translation.strip()
            if not translated:
                raise ValueError("Translation failed")
            target = "vn" if result.source_lang == "en" else "en"
            return {result.source_lang: question, target: translated}
        if source_lang not in {"en", "vn"}:
            raise ValueError("Unsupported query language")
        
        target = "vn" if source_lang == "en" else "en"
        target_name = "Vietnamese" if target == "vn" else "English"
        
        raw = self.llm.generate(
            TRANSLATION_PROMPT.format(target_language=target_name, question=json.dumps(question, ensure_ascii=False))
        )
        translated = Translation.model_validate_json(raw).translation.strip()
        if not translated:
            raise ValueError("Translation failed")
        return {source_lang: question, target: translated}
