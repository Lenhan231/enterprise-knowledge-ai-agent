import hashlib
import inspect
import json
import logging
import re
import time
import unicodedata
from itertools import zip_longest
from typing import Annotated

from openai import APIError
from pydantic import BaseModel, Field, StringConstraints, field_validator

from core.llm.groq_provider import GroqProvider
from core.rag.claim_verification import VerificationOutcome, VERIFICATION_UNAVAILABLE_ANSWER, verify_answer
from core.latency import measure
from core.agents.runtime import deadline, remaining
from core.prompts.knowledge_search import SEARCH_PLAN_PROMPT
from core.prompts.Knowledge import ENTERPRISE_ASSISTANT_PROMPT, INSUFFICIENT_ANSWER, NO_MATCHING_DOCUMENTS_ANSWER
from core.retrieval.retrieval import RetrievalRequest
from core.retrieval.retrieval_service import RetrievalService


MAX_CONTEXT_CHARS = 24_000
_log = logging.getLogger(__name__)


class SearchPlan(BaseModel):
    model_config = {"extra": "forbid"}
    questions: list[Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=4000)]] = Field(min_length=1, max_length=2)

    @field_validator("questions")
    @classmethod
    def distinct_questions(cls, questions):
        if len({q.casefold() for q in questions}) != len(questions):
            raise ValueError("Search questions must be distinct")
        return questions


def _context_key(context: dict):
    return context.get("chunk_id") or (context["metadata"]["document_id"], context["chunk_index"])


def _merge_contexts(groups: list[list[dict]]) -> list[dict]:
    """Interleave branches, deduplicate and keep complete chunks within budget."""
    merged, seen = [], set()
    for row in zip_longest(*groups):
        for context in row:
            if context is None:
                continue
            key = _context_key(context)
            if key in seen:
                continue
            candidate = {**context, "source_id": f"S{len(merged) + 1}"}
            if len(_format_contexts([*merged, candidate])) > MAX_CONTEXT_CHARS:
                continue
            merged.append(candidate)
            seen.add(key)
            if len(merged) == 10:
                return merged
    return merged
CITATION_PATTERN = re.compile(
    r"\[\s*(?:(?:source|nguồn)\s*:\s*)?([A-Z]\d+)\s*\]"
    r"|【\s*(?:(?:source|nguồn)\s*:\s*)?([A-Z]\d+)\s*】",
    re.IGNORECASE,
)


def _normalize_source_citations(answer: str) -> str:
    visible = "".join(char for char in answer if unicodedata.category(char) != "Cf")
    return CITATION_PATTERN.sub(
        lambda match: f"[{next(source for source in match.groups() if source).upper()}]",
        visible,
    )


def extract_source_ids(answer: str) -> list[str]:
    normalized = _normalize_source_citations(answer)
    return list(dict.fromkeys(
        next(source for source in match if source).upper()
        for match in CITATION_PATTERN.findall(normalized)
    ))


class RAGResult(BaseModel):
    answer: str
    contexts: list[dict] = Field(default_factory=list)
    source_ids: list[str] = Field(default_factory=list)
    insufficient_context: bool = False
    prompt_sha256: str | None = None
    verification: VerificationOutcome | None = None


def _format_contexts(contexts: list[dict]) -> str:
    blocks = []
    for context in contexts:
        metadata = context.get("metadata") or {}
        score = context.get("retrieval_score", context.get("similarity_score", 0.0))
        lines = [
            f"[{context['source_id']}]",
            f"Tài liệu: {metadata.get('source_document', context['document_name'])}",
            f"Mã tài liệu: {metadata.get('document_id', 'không rõ')}",
            f"Đoạn: {context['chunk_index']}",
            f"Độ tương đồng: {score:.4f}",
        ]
        if metadata.get("page_number") is not None:
            lines.append(f"Trang: {metadata['page_number']}")
        if metadata.get("section_title"):
            lines.append(f"Mục: {metadata['section_title']}")
        lines.append(f"Nội dung: {context['content']}")
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)


class RAGService:
    def __init__(
        self,
        retrieval_service: RetrievalService | None = None,
        llm: GroqProvider | None = None,
    ):
        self.retrieval_service = retrieval_service or RetrievalService()
        self.llm = llm or GroqProvider()

    def retrieve_contexts(
        self,
        question: str,
        limit: int = 5,
        company: str | None = None,
        roles: list[str] | None = None,
        retrieval_method: str = "translated_hybrid_rerank",
        metadata_filter: dict | None = None,
        document_ids: list[str] | None = None,
        query_language: str = "auto",
        document_languages: dict[str, str] | None = None,
    ) -> list[dict]:
        request = RetrievalRequest(query=question, top_k=limit)
        parameters = inspect.signature(self.retrieval_service.retrieve).parameters
        options = {}
        if roles is not None and "roles" not in parameters:
            raise ValueError("The configured retrieval backend cannot enforce role-scoped retrieval")
        if company is not None and "company" not in parameters:
            raise ValueError("The configured retrieval backend cannot enforce company-scoped retrieval")
        if "company" in parameters:
            options["company"] = company
        if "roles" in parameters:
            options["roles"] = roles
        if "method" in parameters:
            options["method"] = retrieval_method
        for name, value in (
            ("metadata_filter", metadata_filter),
            ("document_ids", document_ids),
            ("query_language", query_language),
            ("document_languages", document_languages),
        ):
            if name in parameters and value is not None:
                options[name] = value
        retrieved = self.retrieval_service.retrieve(request, **options)

        return [
            {
                "document_name": context.source,
                "chunk_id": getattr(context, "chunk_id", None),
                "chunk_index": context.location.chunk_index,
                "content": context.text,
                "metadata": context.metadata,
                # Preserve the benchmark's existing key while exposing main's
                # evaluation contract alongside it.
                "similarity_score": context.score,
                "retrieval_score": context.score,
                "retrieval_method": getattr(context, "retrieval_method", retrieved.method),
                "retrieval_details": getattr(retrieved, "retrieval_details", {}),
                "source_id": f"S{index}",
            }
            for index, context in enumerate(retrieved.results, start=1)
        ]

    def generate_answer(
        self,
        question: str,
        limit: int = 5,
        company: str | None = None,
        roles: list[str] | None = None,
        retrieval_method: str = "translated_hybrid_rerank",
        metadata_filter: dict | None = None,
        document_ids: list[str] | None = None,
        query_language: str = "auto",
        document_languages: dict[str, str] | None = None,
        decompose: bool = False,
        verify_claims: bool = False,
    ) -> RAGResult:
        if decompose:
            questions = self._search_questions(question)
            groups = []
            for query in questions:
                remaining()
                groups.append(self.retrieve_contexts(
                    query, limit=min(limit, 5), company=company, roles=roles,
                    retrieval_method=retrieval_method, metadata_filter=metadata_filter,
                    document_ids=document_ids, query_language=query_language,
                    document_languages=document_languages,
                ))
            contexts = _merge_contexts(groups)
            selected = {_context_key(item) for item in contexts}
            missing_branch = len(questions) == 2 and any(
                not selected.intersection(_context_key(item) for item in group) for group in groups
            )
            if any(groups) and (not contexts or missing_branch):
                return RAGResult(answer=INSUFFICIENT_ANSWER, contexts=contexts, insufficient_context=True)
            remaining()
            return self.generate_from_contexts(question, contexts, verify_claims=verify_claims)
        contexts = self.retrieve_contexts(
            question,
            limit=limit,
            company=company,
            roles=roles,
            retrieval_method=retrieval_method,
            metadata_filter=metadata_filter,
            document_ids=document_ids,
            query_language=query_language,
            document_languages=document_languages,
        )
        return self.generate_from_contexts(question, contexts, verify_claims=verify_claims)

    def _search_questions(self, question: str) -> list[str]:
        token = deadline.set(time.monotonic() + remaining(15))
        try:
            with measure("knowledge_search_planning"):
                raw = self.llm.generate(
                    SEARCH_PLAN_PROMPT.format(question=json.dumps(question, ensure_ascii=False)),
                    max_output_tokens=256,
                )
            plan = SearchPlan.model_validate_json(raw)
            return plan.questions if len(plan.questions) == 2 else [question]
        except (APIError, ValueError, RuntimeError) as error:
            _log.warning("Knowledge search plan fallback: %s", type(error).__name__)
            return [question]
        finally:
            deadline.reset(token)

    def generate_from_contexts(self, question: str, contexts: list[dict], *, verify_claims: bool = False) -> RAGResult:
        if not contexts:
            return RAGResult(answer=NO_MATCHING_DOCUMENTS_ANSWER, insufficient_context=True)

        prompt = ENTERPRISE_ASSISTANT_PROMPT.format(
            context=_format_contexts(contexts)[:MAX_CONTEXT_CHARS],
            question=question,
        )
        prompt_sha256 = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
        with measure("answer_generation"):
            answer = _normalize_source_citations(self.llm.generate(prompt).strip())

        if answer == INSUFFICIENT_ANSWER:
            return RAGResult(
                answer=INSUFFICIENT_ANSWER,
                contexts=contexts,
                insufficient_context=True,
                prompt_sha256=prompt_sha256,
            )

        source_ids = extract_source_ids(answer)
        if not source_ids:
            raise ValueError(f"Generated answer contains no source citations. Answer: {answer}")

        allowed_source_ids = {context["source_id"] for context in contexts}
        unknown_source_ids = set(source_ids) - allowed_source_ids
        if unknown_source_ids:
            raise ValueError(
                "Generated answer contains unknown citations: "
                f"{sorted(unknown_source_ids)}"
            )

        verification = None
        if verify_claims:
            cited_contexts = [c for c in contexts if c["source_id"] in source_ids]
            verification = verify_answer(self.llm, question, answer, cited_contexts)
            if verification.status != "supported":
                return RAGResult(answer=VERIFICATION_UNAVAILABLE_ANSWER, contexts=contexts,
                                 prompt_sha256=prompt_sha256, verification=verification)

        return RAGResult(
            answer=answer,
            contexts=contexts,
            source_ids=source_ids,
            prompt_sha256=prompt_sha256,
            verification=verification,
        )

    def close(self) -> None:
        self.retrieval_service.close()
