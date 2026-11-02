"""Experimental semantic audit; quote/coverage checks do not prove entailment."""

import json
import re
import time
from typing import Annotated, Literal

from openai import APIError
from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from core.agents.runtime import deadline, remaining
from core.rag.arithmetic import check_equalities
from core.latency import measure
from core.prompts.knowledge_verification import CLAIM_VERIFICATION_PROMPT

VERIFICATION_UNAVAILABLE_ANSWER = (
    "Chưa thể kiểm chứng đầy đủ câu trả lời với các nguồn được trích dẫn. "
    "Vui lòng thử lại hoặc hỏi rõ hơn."
)
Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=6000)]


class SupportingQuote(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_id: str = Field(pattern=r"^S\d+$")
    text: Text


class ClaimReview(BaseModel):
    model_config = ConfigDict(extra="forbid")
    claim_id: str = Field(pattern=r"^C[1-9]\d*$")
    verdict: Literal["supported", "contradicted", "insufficient"]
    quotes: list[SupportingQuote] = Field(max_length=10)


class AnswerReview(BaseModel):
    model_config = ConfigDict(extra="forbid")
    claims: list[ClaimReview] = Field(min_length=1, max_length=16)


class VerificationOutcome(BaseModel):
    status: Literal["supported", "rejected", "unavailable"]
    reason: str
    claim_count: int = 0
    arithmetic_checked: int = 0


def claim_blocks(answer):
    blocks, start = [], 0
    for match in re.finditer(r"(?:\[S\d+\][\s.,;:!?]*)+", answer):
        text = answer[start:match.end()].strip()
        blocks.append({"claim_id": f"C{len(blocks) + 1}", "text": text,
                       "source_ids": list(dict.fromkeys(re.findall(r"\[(S\d+)\]", text)))})
        start = match.end()
    tail = answer[start:]
    if tail.strip(" \t\r\n|*_`)]}") or not blocks or len(blocks) > 16:
        raise ValueError("uncited_or_oversized_draft")
    blocks[-1]["text"] += tail
    return blocks


def parse_review(raw):
    fenced = re.fullmatch(r"\s*```(?:json)?\s*\n(.*?)\n```\s*", raw, flags=re.DOTALL | re.IGNORECASE)
    return AnswerReview.model_validate_json(fenced.group(1) if fenced else raw)


def validate_review(answer: str, contexts: list[dict], review: AnswerReview) -> VerificationOutcome:
    blocks = {block["claim_id"]: block for block in claim_blocks(answer)}
    identifiers = [c.claim_id for c in review.claims]
    if len(set(identifiers)) != len(identifiers) or set(identifiers) != set(blocks):
        raise ValueError("incomplete_claim_coverage")
    sources = {c["source_id"]: " ".join(c["content"].split()) for c in contexts}
    for claim in review.claims:
        cited = set(blocks[claim.claim_id]["source_ids"])
        if not cited or not cited.issubset(sources):
            raise ValueError("invalid_claim_citations")
        if claim.verdict != "supported":
            return VerificationOutcome(status="rejected", reason=claim.verdict, claim_count=len(review.claims))
        if {q.source_id for q in claim.quotes} != cited:
            raise ValueError("missing_cited_source_quotes")
        if any(" ".join(q.text.split()) not in sources[q.source_id] for q in claim.quotes):
            raise ValueError("fabricated_source_quote")
    return VerificationOutcome(status="supported", reason="all_claims_supported", claim_count=len(review.claims))


@measure("claim_verification")
def verify_answer(llm, question: str, answer: str, contexts: list[dict]) -> VerificationOutcome:
    if len(answer) > 6000:
        return VerificationOutcome(status="unavailable", reason="verification_input_budget")
    checked, issue = check_equalities(answer)
    if issue:
        status = "rejected" if issue in {"arithmetic_mismatch", "invalid_arithmetic"} else "unavailable"
        return VerificationOutcome(status=status, reason=issue, arithmetic_checked=checked)
    try:
        blocks = claim_blocks(answer)
    except ValueError:
        return VerificationOutcome(status="unavailable", reason="uncited_or_oversized_draft", arithmetic_checked=checked)
    payload = json.dumps({"question": question, "claims": blocks, "sources": [
        {"source_id": c["source_id"], "document": c["document_name"],
         "section": (c.get("metadata") or {}).get("section_title"), "content": c["content"]}
        for c in contexts
    ]}, ensure_ascii=False)
    if len(payload) > 40000:
        return VerificationOutcome(status="unavailable", reason="verification_input_budget", arithmetic_checked=checked)
    token = None
    try:
        token = deadline.set(time.monotonic() + remaining(15))
        raw = llm.generate(CLAIM_VERIFICATION_PROMPT + payload, max_output_tokens=3072)
        outcome = validate_review(answer, contexts, parse_review(raw))
        return outcome.model_copy(update={"arithmetic_checked": checked})
    except (APIError, ValueError, RuntimeError, TimeoutError) as error:
        return VerificationOutcome(status="unavailable", reason=type(error).__name__, arithmetic_checked=checked)
    finally:
        if token is not None:
            deadline.reset(token)
