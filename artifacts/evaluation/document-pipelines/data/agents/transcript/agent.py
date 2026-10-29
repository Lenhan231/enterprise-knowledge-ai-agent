"""Full-page OCR transcript specialist."""

from __future__ import annotations

from pathlib import Path
from string import Template

from pydantic import BaseModel

from agents.codex_cli import run_codex_json

TRANSCRIPT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["ocr_text", "uncertain_items"],
    "properties": {
        "ocr_text": {"type": "string"},
        "uncertain_items": {"type": "array", "items": {"type": "string"}},
    },
}


class GeneratedTranscriptDraft(BaseModel):
    ocr_text: str
    uncertain_items: list[str]


def run_transcript_agent(image_bytes: bytes, instruction: str = "") -> tuple[GeneratedTranscriptDraft, str]:
    prompt = Template(Path(__file__).with_name("system_prompt.md").read_text(encoding="utf-8")).substitute(
        user_instruction=instruction or "Transcribe the full page in reading order.",
    )
    draft, model = run_codex_json(
        [("source-page.jpg", image_bytes)], prompt, TRANSCRIPT_SCHEMA,
        "codex-transcript-draft-", "transcript.json", GeneratedTranscriptDraft,
    )
    if not draft.ocr_text.strip():
        raise ValueError("Codex returned an empty transcript")
    return draft, model
