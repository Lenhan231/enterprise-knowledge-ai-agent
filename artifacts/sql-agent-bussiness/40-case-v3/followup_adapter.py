"""Build leak-checked context-conditioned SQL requests for v3 follow-ups."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any


ADAPTER_VERSION = "context-conditioned-sql.v1"
EVALUATION_MODE = "context-conditioned SQL; not conversational-memory evaluation"
ALLOWED_CONTEXT_KEYS = {
    "metric",
    "formula",
    "source",
    "date_field",
    "start",
    "end_exclusive",
    "snapshot_date",
    "grouping",
    "population",
    "ranking",
}
FORBIDDEN_CONTEXT_KEYS = {
    "answer",
    "assistant_output",
    "gold",
    "gold_sql",
    "gold_result",
    "parameters",
    "result",
    "results",
    "rows",
    "sql",
}


def canonical_sha256(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _check_context_keys(value: Any) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            normalized = str(key).casefold()
            if normalized in FORBIDDEN_CONTEXT_KEYS:
                raise ValueError(f"follow-up context contains forbidden field: {key}")
            if normalized not in ALLOWED_CONTEXT_KEYS:
                raise ValueError(f"follow-up context contains unapproved field: {key}")
            _check_context_keys(child)
    elif isinstance(value, list):
        for child in value:
            _check_context_keys(child)


@dataclass(frozen=True)
class AdaptedFollowup:
    case_id: str
    question: str
    context_sha256: str
    prior_question_sha256: str
    adapter_version: str = ADAPTER_VERSION
    evaluation_mode: str = EVALUATION_MODE

    def to_chat_request(self):
        """Return the normal SQL-mode ChatRequest without hidden metadata."""
        from core.agents.main import ChatRequest

        return ChatRequest(question=self.question, agent_mode="sql")


def adapt_followup_case(case: dict[str, Any]) -> AdaptedFollowup:
    """Package only the frozen prior user turn and its approved typed state."""
    if case.get("category") != "sql_followup_context":
        raise ValueError("the v3 context adapter accepts follow-up cases only")
    setup = case.get("conversation_setup")
    if not isinstance(setup, dict):
        raise ValueError("follow-up case is missing conversation_setup")
    if setup.get("mode") != "frozen_context_injection":
        raise ValueError("follow-up setup mode is not frozen_context_injection")
    if setup.get("adapter_version") != ADAPTER_VERSION:
        raise ValueError("follow-up adapter version mismatch")
    if setup.get("assistant_output_injected") is not False:
        raise ValueError("assistant output must not be injected")
    prior = setup.get("prior_user_question")
    context = setup.get("semantic_context")
    if not isinstance(prior, str) or not prior.strip() or not isinstance(context, dict):
        raise ValueError("follow-up needs a prior user question and structured context")
    context_hash = canonical_sha256(context)
    if setup.get("semantic_context_sha256") != context_hash:
        raise ValueError("follow-up semantic context hash mismatch")
    _check_context_keys(context)
    current = case.get("question")
    if not isinstance(current, str) or not current.strip():
        raise ValueError("follow-up question is required")

    serialized_context = json.dumps(context, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    question = (
        "Earlier user request (frozen context):\n"
        f"{prior.strip()}\n"
        "Approved semantic context from that user request (JSON):\n"
        f"{serialized_context}\n"
        "Current user follow-up:\n"
        f"{current.strip()}\n"
        "Apply the follow-up to the earlier user request. Preserve inherited metric, source, time scope, "
        "population, grouping, and ranking unless the follow-up changes them. No prior assistant answer "
        "or query result is available."
    )
    request = AdaptedFollowup(
        case_id=str(case.get("id", "")),
        question=question,
        context_sha256=context_hash,
        prior_question_sha256=hashlib.sha256(prior.strip().encode("utf-8")).hexdigest(),
    )
    # Validate the exact public request contract and its 2,000-character limit.
    request.to_chat_request()
    return request
