"""Experimental semantic audit; quote/coverage checks do not prove entailment."""

import json
import re
import time
from typing import Annotated, Literal

from openai import APIError
from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from core.agents.runtime import deadline, remaining
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
    text: Text
    verdict: Literal["supported", "contradicted", "insufficient"]
    quotes: list[SupportingQuote] = Field(max_length=10)


class AnswerReview(BaseModel):
    model_config = ConfigDict(extra="forbid")
    claims: list[ClaimReview] = Field(min_length=1, max_length=16)


class VerificationOutcome(BaseModel):
    status: Literal["supported", "rejected", "unavailable"]
    reason: str
    claim_count: int = 0


def validate_review(answer: str, contexts: list[dict], review: AnswerReview) -> VerificationOutcome:
    if "".join(answer.split()) != "".join("".join(c.text.split()) for c in review.claims):
        raise ValueError("incomplete_draft_coverage")
    sources = {c["source_id"]: " ".join(c["content"].split()) for c in contexts}
    for claim in review.claims:
        cited = set(re.findall(r"\[(S\d+)\]", claim.text))
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
    payload = json.dumps({"question": question, "draft": answer, "sources": [
        {"source_id": c["source_id"], "document": c["document_name"],
         "section": (c.get("metadata") or {}).get("section_title"), "content": c["content"]}
        for c in contexts
    ]}, ensure_ascii=False)
    if len(answer) > 6000 or len(payload) > 40000:
        return VerificationOutcome(status="unavailable", reason="verification_input_budget")
    token = None
    try:
        token = deadline.set(time.monotonic() + remaining(15))
        raw = llm.generate(CLAIM_VERIFICATION_PROMPT + payload, max_output_tokens=3072)
        fenced = re.fullmatch(r"\s*```(?:json)?\s*\n(.*?)\n```\s*", raw, flags=re.DOTALL | re.IGNORECASE)
        if fenced:
            raw = fenced.group(1)
        return validate_review(answer, contexts, AnswerReview.model_validate_json(raw))
    except (APIError, ValueError, RuntimeError, TimeoutError) as error:
        return VerificationOutcome(status="unavailable", reason=type(error).__name__)
    finally:
        if token is not None:
            deadline.reset(token)
