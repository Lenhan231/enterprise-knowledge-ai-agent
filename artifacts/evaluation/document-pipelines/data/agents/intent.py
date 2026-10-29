"""Routes review chat prompts to one existing source-draft specialist."""

from __future__ import annotations

import json
from typing import Literal

from pydantic import BaseModel

from agents.codex_cli import run_codex_json

INTENT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["intent", "reply", "instruction"],
    "properties": {
        "intent": {"type": "string", "enum": ["bbox", "transcript", "table", "clarify"]},
        "reply": {"type": "string"},
        "instruction": {"type": "string"},
    },
}


class ReviewIntent(BaseModel):
    intent: Literal["bbox", "transcript", "table", "clarify"]
    reply: str
    instruction: str


def run_review_intent_agent(
    message: str, page_context: dict, history: list[dict] | None = None
) -> tuple[ReviewIntent, str]:
    prompt = (
        "Route the user's request to exactly one existing source-review draft area. "
        "Use bbox for region geometry, transcript for full-page OCR text, and table for table grids. "
        "Choose clarify when the request is ambiguous, asks to change labels/reading order, needs multiple areas, "
        "or the requested area is unavailable. A request about a missing or incorrect table value, cell, row, or named "
        "table column is table intent; do not clarify only because a row coordinate was omitted when one table is available. "
        "Treat short confirmations such as 'yes', 'đúng rồi', or 'that one' as answers to the previous assistant question and "
        "continue the confirmed task. Keep reply concise and in the user's language. Return instruction as one actionable "
        "request that combines the current message with relevant prior turns, so the specialist can act without chat history.\n\n"
        f"Available page draft areas:\n{json.dumps(page_context, ensure_ascii=False)}\n\n"
        f"Recent conversation:\n{json.dumps(history or [], ensure_ascii=False)}\n\n"
        f"User request:\n{message}\n\n"
        "Return only the schema object."
    )
    return run_codex_json(
        [], prompt, INTENT_SCHEMA, "codex-review-intent-", "intent.json", ReviewIntent,
    )
