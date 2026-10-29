"""Routes review chat prompts to existing source-draft specialists."""

from __future__ import annotations

import json
from typing import Literal

from pydantic import BaseModel

from agents.codex_cli import run_codex_json

INTENT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["intent", "reply", "actions"],
    "properties": {
        "intent": {"type": "string", "enum": ["execute", "clarify"]},
        "reply": {"type": "string"},
        "actions": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["area", "instruction"],
                "properties": {
                    "area": {"type": "string", "enum": ["bbox", "transcript", "table"]},
                    "instruction": {"type": "string"},
                },
            },
        },
    },
}


class ReviewAction(BaseModel):
    area: Literal["bbox", "transcript", "table"]
    instruction: str


class ReviewIntent(BaseModel):
    intent: Literal["execute", "clarify"]
    reply: str
    actions: list[ReviewAction]


def run_review_intent_agent(
    message: str, page_context: dict, history: list[dict] | None = None
) -> tuple[ReviewIntent, str]:
    prompt = (
        "Route the user's request to one or more existing source-review draft areas. "
        "Use bbox for region geometry, transcript for full-page OCR text, and table for table grids. "
        "If the user asks to fix multiple areas, create one action per area in actions and do not ask them to split the work. "
        "Choose clarify only when the target or requested change is genuinely unclear, or an area is unavailable. "
        "A request about a missing or incorrect table value, cell, row, or named table column is table; do not clarify "
        "only because a row coordinate was omitted when one table is available. "
        "Treat short confirmations such as 'yes', 'đúng rồi', or 'that one' as answers to the previous assistant question and "
        "continue all confirmed tasks. Keep reply concise and in the user's language. Each action instruction must combine "
        "the current message with relevant prior turns, so each specialist can act without chat history. For clarify, use "
        "intent clarify and an empty actions list; otherwise use execute and include every needed action.\n\n"
        f"Available page draft areas:\n{json.dumps(page_context, ensure_ascii=False)}\n\n"
        f"Recent conversation:\n{json.dumps(history or [], ensure_ascii=False)}\n\n"
        f"User request:\n{message}\n\n"
        "Return only the schema object."
    )
    return run_codex_json(
        [], prompt, INTENT_SCHEMA, "codex-review-intent-", "intent.json", ReviewIntent,
    )
