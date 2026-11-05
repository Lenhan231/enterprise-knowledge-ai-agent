"""Experimental semantic audit; evidence-ID/coverage checks do not prove entailment."""

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

# Groq reserves the full output cap against per-minute output quota; audits use ~40-70 tokens.
AUDIT_MAX_OUTPUT_TOKENS = 768
VERIFICATION_UNAVAILABLE_ANSWER = (
    "Chưa thể kiểm chứng đầy đủ câu trả lời với các nguồn được trích dẫn. "
    "Vui lòng thử lại hoặc hỏi rõ hơn."
)


EvidenceId = Annotated[str, StringConstraints(pattern=r"^S\d+\.\d+$")]


class ClaimReview(BaseModel):
    model_config = ConfigDict(extra="forbid")
    claim_id: str = Field(pattern=r"^C[1-9]\d*$")
    verdict: Literal["supported", "contradicted", "insufficient"]
    evidence: list[EvidenceId] = Field(max_length=10)


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
    gap = _is_source_gap_note(tail)
    if (tail.strip(" \t\r\n|*_`)]}") and not gap) or not blocks or len(blocks) > 16:
        raise ValueError("uncited_or_oversized_draft")
    if not gap:
        blocks[-1]["text"] += tail
    return blocks


# Prompt rule 4 lets a partial answer close by saying what the sources do not cover; that is not a policy claim.
_SOURCE_GAP = re.compile(r"(?:tài liệu|nguồn)[^.!?\n]*(?:chưa đủ|chưa (?:nêu|đề cập|có)|không (?:nêu|đề cập|có thông tin|quy định))",
                         re.IGNORECASE)


def _is_source_gap_note(tail):
    """Every sentence must be a number-free 'the sources do not cover ...' note, so no claim escapes the audit."""
    sentences = [s.strip(" \t\r\n|*_`)]}.,;:") for s in re.split(r"(?<=[.!?])\s+|\n+", tail)]
    sentences = [s for s in sentences if s]
    return bool(sentences) and not re.search(r"\d", tail) and all(_SOURCE_GAP.search(s) for s in sentences)


def evidence_units(content):
    """Split a source per line, then at . ! ? followed by whitespace; numbers like 1.5 stay whole."""
    return [part for line in content.splitlines() for part in re.split(r"(?<=[.!?])\s+", line.strip()) if part]


def parse_review(raw):
    fenced = re.fullmatch(r"\s*```(?:json)?\s*\n(.*?)\n```\s*", raw, flags=re.DOTALL | re.IGNORECASE)
    return AnswerReview.model_validate_json(fenced.group(1) if fenced else raw)


def validate_review(answer: str, contexts: list[dict], review: AnswerReview) -> VerificationOutcome:
    blocks = {block["claim_id"]: block for block in claim_blocks(answer)}
    identifiers = [c.claim_id for c in review.claims]
    if len(set(identifiers)) != len(identifiers) or set(identifiers) != set(blocks):
        raise ValueError("incomplete_claim_coverage")
    sources = {c["source_id"] for c in contexts}
    units = {f"{c['source_id']}.{i}" for c in contexts for i, _ in enumerate(evidence_units(c["content"]), 1)}
    for claim in review.claims:
        cited = set(blocks[claim.claim_id]["source_ids"])
        if not cited or not cited.issubset(sources):
            raise ValueError("invalid_claim_citations")
        if claim.verdict != "supported":
            return VerificationOutcome(status="rejected", reason=claim.verdict, claim_count=len(review.claims))
        if {e.rsplit(".", 1)[0] for e in claim.evidence} != cited:
            raise ValueError("missing_cited_source_evidence")
        if not units.issuperset(claim.evidence):
            raise ValueError("unknown_evidence_id")
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
         "section": (c.get("metadata") or {}).get("section_title"),
         "units": [{"id": f"{c['source_id']}.{i}", "text": text}
                   for i, text in enumerate(evidence_units(c["content"]), 1)]}
        for c in contexts
    ]}, ensure_ascii=False)
    if len(payload) > 40000:
        return VerificationOutcome(status="unavailable", reason="verification_input_budget", arithmetic_checked=checked)
    token = None
    try:
        token = deadline.set(time.monotonic() + remaining(15))
        for attempt in range(2):
            raw = llm.generate(CLAIM_VERIFICATION_PROMPT + payload, max_output_tokens=AUDIT_MAX_OUTPUT_TOKENS)
            try:
                outcome = validate_review(answer, contexts, parse_review(raw))
                break
            except ValueError:
                # A malformed or incomplete audit gets one more try; a second failure still fails closed below.
                if attempt or remaining(15) < 5:
                    raise
        return outcome.model_copy(update={"arithmetic_checked": checked})
    except (APIError, ValueError, RuntimeError, TimeoutError) as error:
        return VerificationOutcome(status="unavailable", reason=type(error).__name__, arithmetic_checked=checked)
    finally:
        if token is not None:
            deadline.reset(token)
