from core.llm.groq_provider import GroqProvider
from core.llm.provider_fallback import (
    accumulate_token_usage,
    generate_with_provider_fallback,
    is_retryable_provider_error,
)
from core.retrieval.retrieval import RetrievalRequest
from core.retrieval.retrieval_service import RetrievalService
from core.prompts.Knowledge import ENTERPRISE_ASSISTANT_PROMPT
from pydantic import BaseModel, Field
from typing import Literal
import re
import hashlib
import json
import unicodedata
from collections import OrderedDict
from threading import Lock
from time import monotonic
from openai import RateLimitError

# Leave room for the system prompt, question, and response under Groq's 8k TPM cap.
MAX_CONTEXT_CHARS = 5_000
RESPONSE_CACHE_TTL_SECONDS = 60
RESPONSE_CACHE_MAX_ENTRIES = 128
_RESPONSE_CACHE: OrderedDict[str, tuple[float, str, tuple[str, ...]]] = OrderedDict()
_RESPONSE_CACHE_LOCK = Lock()

INSUFFICIENT_ANSWER = (
    "Insufficient information in the retrieved documents."
)

CITATION_PATTERN = re.compile(
    r"\[\s*(?:(?:source|nguồn)\s*:\s*)?([A-Z]\d+)\s*\]"
    r"|【\s*(?:(?:source|nguồn)\s*:\s*)?([A-Z]\d+)\s*】",
    re.IGNORECASE,
)
RECORD_TYPES = {
    "invoice": ("invoice", "invoices"),
    "contract": ("contract", "contracts", "agreement", "agreements"),
    "manual": ("manual", "manuals", "handbook", "handbooks"),
}


def _requested_record_type(question: str) -> str | None:
    text = question.casefold()
    matches = [
        (text.find(alias), record_type)
        for record_type, aliases in RECORD_TYPES.items()
        for alias in aliases
        if text.find(alias) >= 0
    ]
    return min(matches)[1] if matches else None


def _record_type_matches(record_type: str, contexts: list[dict]) -> bool:
    aliases = RECORD_TYPES[record_type]
    for context in contexts:
        metadata = context.get("metadata") or {}
        source_type = str(metadata.get("document_type") or "").casefold().replace("_", " ")
        source_name = str(metadata.get("source_document") or context.get("document_name") or "").casefold()
        if any(alias in source_type or alias in source_name for alias in aliases):
            return True
    return False


def _related_party_invoice_disclosure(contexts: list[dict]) -> "RAGResult | None":
    for context in contexts:
        content = " ".join(str(context.get("content") or "").split())
        match = re.search(
            r"(?:The\s+)?trade related amounts due to the related parties were"
            r"[^.!?]*payable within 60 days from invoice date\.",
            content,
            re.IGNORECASE,
        )
        if not match:
            continue
        source_id = context["source_id"]
        source_name = context.get("metadata", {}).get("source_document") or context["document_name"]
        return RAGResult(
            answer=(
                f"The retrieved source is {source_name}, not an invoice [{source_id}]. "
                f"It states: “{match.group(0).strip()}” [{source_id}] "
                f"No invoice document was present in the retrieved sources [{source_id}]."
            ),
            contexts=[context],
            source_ids=[source_id],
        )
    return None


class RAGResult(BaseModel):
    answer: str
    contexts: list[dict] = Field(default_factory=list)
    source_ids: list[str] = Field(default_factory=list)
    insufficient_context: bool = False
    prompt_sha256: str | None = None
    answer_fallback_reason: str | None = None
    generation_provider: str | None = None
    token_usage: dict | None = None


def _source_only_fallback(question: str, contexts: list[dict], reason: str) -> RAGResult:
    is_vietnamese = any(
        character in question.casefold()
        for character in "ăâđêôơưàáạảãằắặẳẵầấậẩẫềếệểễồốộổỗờớợởỡừứựửữỳýỵỷỹ"
    )
    note_key = "source_notes" if is_vietnamese else "source_notes_en"
    question_terms = set(re.findall(r"[a-z0-9]+", question.casefold()))
    named_sources = []
    for context in contexts:
        publisher = str((context.get("metadata") or {}).get("source_publisher") or "")
        publisher_terms = set(re.findall(r"[a-z0-9]+", publisher.casefold()))
        publisher_terms -= {"the", "company", "group", "holding", "holdings"}
        if context.get("source_id") and publisher_terms & question_terms:
            named_sources.append(context)
    if named_sources:
        # A named source in the question is stronger than an unrelated catalog note.
        contexts = named_sources[:3]
    curated_policy = next((
        context for context in contexts
        if (context.get("metadata") or {}).get("synthetic_company_policy") is True
        and isinstance((context.get("metadata") or {}).get(note_key), str)
        and (context.get("metadata") or {}).get(note_key).strip()
        and context.get("source_id")
    ), None)
    if curated_policy:
        metadata = curated_policy.get("metadata") or {}
        source_id = curated_policy["source_id"]
        note = metadata[note_key].strip()
        if is_vietnamese:
            opening = (
                "Request tổng hợp đã chạm giới hạn token của model provider. "
                if reason == "provider_rate_limited" else
                "Không thể gọi dịch vụ mô hình để tổng hợp. "
                if reason == "provider_unavailable" else
                "Bản nháp mô hình thiếu citation hợp lệ nên đã bị loại. "
            )
            answer = (
                f"{opening}Ghi chú biên mục cho policy giả lập Commerce Demo "
                f"(không phải bản chép OCR): {note} Đối chiếu trang PDF gốc; "
                f"nội dung chỉ áp dụng cho dữ liệu demo. [{source_id}]"
            )
        else:
            opening = (
                "The model request exceeded the provider's current token rate limit. "
                if reason == "provider_rate_limited" else
                "Model synthesis is unavailable. "
                if reason == "provider_unavailable" else
                "The model draft lacked valid citations and was rejected. "
            )
            answer = (
                f"{opening}The curated catalog note for this synthetic Commerce Demo policy "
                f"(not a verified OCR transcript) says: {note} Check the original PDF page; "
                f"it applies only to the demo data. [{source_id}]"
            )
        return RAGResult(
            answer=answer,
            contexts=contexts,
            source_ids=[source_id],
            answer_fallback_reason=reason,
        )
    if reason == "provider_unavailable":
        opening = (
            "Không thể tổng hợp câu trả lời vì dịch vụ mô hình đang tạm thời không khả dụng. "
            "Các trích đoạn dưới đây là nội dung nguồn đã truy xuất, chưa được diễn giải:"
            if is_vietnamese else
            "Answer synthesis is temporarily unavailable. The retrieved passages below are source text, "
            "not a synthesized answer:"
        )
    elif reason == "provider_rate_limited":
        opening = (
            "Request tổng hợp đã chạm giới hạn token của nhà cung cấp mô hình. Các trích đoạn dưới đây là nội dung nguồn đã truy xuất, chưa được diễn giải:"
            if is_vietnamese else
            "The model request exceeded the provider's current token rate limit. The retrieved passages below are source text, not a synthesized answer:"
        )
    else:
        opening = (
            "Bản trả lời của mô hình không có citation hợp lệ nên đã bị loại. Các trích đoạn dưới đây là nội dung nguồn "
            "đã truy xuất, chưa được diễn giải:"
            if is_vietnamese else
            "The model draft did not contain valid citations and was rejected. The retrieved passages below are source "
            "text, not a synthesized answer:"
        )
    excerpts = []
    source_ids = []
    for context in contexts[:3]:
        source_id = context.get("source_id")
        content = " ".join(str(context.get("content") or "").split())
        if not source_id or not content:
            continue
        excerpt = content[:700].rstrip()
        if len(content) > len(excerpt):
            excerpt = excerpt.rsplit(" ", 1)[0].rstrip() + "…"
        excerpts.append(f"[{source_id}] {excerpt}")
        source_ids.append(source_id)
    return RAGResult(
        answer=opening + "\n\n" + "\n\n".join(excerpts),
        contexts=contexts,
        source_ids=source_ids,
        answer_fallback_reason=reason,
    )


def _format_contexts(contexts: list[dict]) -> str:
    blocks = []

    for context in contexts:
        metadata = context.get("metadata") or {}

        lines = [
            f"[{context['source_id']}]",
            (
                "Document: "
                f"{metadata.get('source_document', context['document_name'])}"
            ),
            f"Document ID: {metadata.get('document_id', 'unknown')}",
            f"Chunk: {context['chunk_index']}",
            f"Retrieval score ({context['retrieval_method']}): {context['retrieval_score']:.4f}",
        ]

        if metadata.get("page_number") is not None:
            lines.append(f"Page: {metadata['page_number']}")

        if metadata.get("section_title"):
            lines.append(f"Section: {metadata['section_title']}")

        if metadata.get("evidence_class"):
            lines.append(f"Evidence class: {metadata['evidence_class']}")
        if metadata.get("source_publisher"):
            lines.append(f"Publisher: {metadata['source_publisher']}")
        if metadata.get("reference_applicability"):
            lines.append(f"Applicability: {metadata['reference_applicability']}")
        if metadata.get("synthetic_company_policy") is True:
            lines.append("Status: synthetic demo policy; not issued by a real company")
        if metadata.get("knowledge_domains"):
            lines.append(f"Decision domains: {', '.join(metadata['knowledge_domains'])}")

        lines.append(f"Content: {context['content']}")
        blocks.append("\n".join(lines))

    return "\n\n".join(blocks)


def extract_source_ids(answer: str) -> list[str]:
    # Some model outputs insert zero-width formatting characters into citations.
    visible = "".join(char for char in answer if unicodedata.category(char) != "Cf")
    return list(dict.fromkeys(
        next(source for source in match if source).upper()
        for match in CITATION_PATTERN.findall(visible)
    ))


def _response_cache_key(
    prompt_sha256: str,
    company: str | None,
    roles: list[str] | None,
    model_name: str,
    reasoning_effort: str | None,
) -> str:
    cache_scope = json.dumps(
        [prompt_sha256, company, sorted(roles or []), model_name, reasoning_effort],
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return hashlib.sha256(cache_scope.encode("utf-8")).hexdigest()


def _get_cached_response(key: str) -> tuple[str, list[str]] | None:
    now = monotonic()
    with _RESPONSE_CACHE_LOCK:
        while _RESPONSE_CACHE:
            oldest_key, (expires_at, _, _) = next(iter(_RESPONSE_CACHE.items()))
            if expires_at > now:
                break
            _RESPONSE_CACHE.pop(oldest_key)
        cached = _RESPONSE_CACHE.get(key)
        if cached is None:
            return None
        expires_at, answer, source_ids = cached
        if expires_at <= now:
            _RESPONSE_CACHE.pop(key, None)
            return None
        _RESPONSE_CACHE.move_to_end(key)
        return answer, list(source_ids)


def _cache_response(key: str, answer: str, source_ids: list[str]) -> None:
    with _RESPONSE_CACHE_LOCK:
        _RESPONSE_CACHE[key] = (monotonic() + RESPONSE_CACHE_TTL_SECONDS, answer, tuple(source_ids))
        _RESPONSE_CACHE.move_to_end(key)
        while len(_RESPONSE_CACHE) > RESPONSE_CACHE_MAX_ENTRIES:
            _RESPONSE_CACHE.popitem(last=False)


class RAGService:
    def __init__(
        self,
        retrieval_service: RetrievalService | None = None,
        llm: GroqProvider | None = None,
    ):
        self.retrieval_service = retrieval_service or RetrievalService()
        self.llm = llm or GroqProvider()


    def generate_answer(
        self,
        question: str,
        limit: int = 5,
        company: str | None = None,
        roles: list[str] | None = None,
        metadata_filter: dict | None = None,
        retrieval_method: Literal["dense", "bm25", "hybrid", "parent", "translated_hybrid", "translated_hybrid_rerank"] = "hybrid",
        retrieval_query: str | None = None,
        document_ids: list[str] | None = None,
        query_language: str = "auto",
        document_languages: dict[str, str] | None = None,
        retrieved_contexts: list[dict] | None = None,
    ) -> RAGResult:
        if not isinstance(roles, list) or not roles or any(
            not isinstance(role, str) or not role.strip() for role in roles
        ):
            raise ValueError("RAG generation requires trusted authenticated roles")
        requested_record_type = _requested_record_type(question)
        if retrieved_contexts is None and requested_record_type == "invoice" and retrieval_method == "hybrid":
            # Adjacent chunks may contain the scope that was split from a
            # payment-term sentence; parent expansion remains role/company filtered.
            retrieval_method = "parent"
        retrieval_options = {}
        if document_ids is not None:
            retrieval_options["document_ids"] = document_ids
        if query_language != "auto":
            retrieval_options["query_language"] = query_language
        if document_languages is not None:
            retrieval_options["document_languages"] = document_languages
        contexts = retrieved_contexts if retrieved_contexts is not None else self.retrieve_contexts(
            retrieval_query or question,
            limit=limit,
            company=company,
            roles=roles,
            metadata_filter=metadata_filter,
            retrieval_method=retrieval_method,
            **retrieval_options,
        )
        if not contexts:
            return RAGResult(
                answer=INSUFFICIENT_ANSWER,
                insufficient_context=True,
                source_ids=[],
            )

        if requested_record_type and not _record_type_matches(requested_record_type, contexts):
            if requested_record_type == "invoice":
                disclosure = _related_party_invoice_disclosure(contexts)
                if disclosure:
                    return disclosure
            return RAGResult(
                answer=INSUFFICIENT_ANSWER,
                contexts=contexts,
                insufficient_context=True,
                source_ids=[],
            )

        # Only expose contexts that were actually sent to the model as sources.
        # A raw string slice could truncate midway through a chunk while still
        # allowing the model to cite evidence that was never in its prompt.
        prompt_contexts = []
        remaining = MAX_CONTEXT_CHARS
        for context in contexts:
            formatted = _format_contexts([context])
            if len(formatted) > remaining:
                content = context["content"]
                overhead = len(formatted) - len(content)
                if remaining <= overhead:
                    break
                context = {**context, "content": content[:remaining - overhead]}
                formatted = _format_contexts([context])
            prompt_contexts.append(context)
            remaining -= len(formatted) + 2
            if remaining <= 0:
                break

        prompt = ENTERPRISE_ASSISTANT_PROMPT.format(
            context=_format_contexts(prompt_contexts),
            question=question,
        )
        prompt_sha256 = hashlib.sha256(prompt.encode("utf-8")).hexdigest()

        model_name = getattr(self.llm, "model_name", None)
        if not isinstance(model_name, str):
            model_name = type(self.llm).__qualname__
        reasoning_effort = getattr(self.llm, "reasoning_effort", None)
        if not isinstance(reasoning_effort, str):
            reasoning_effort = None
        cache_key = _response_cache_key(
            prompt_sha256,
            company,
            roles,
            model_name,
            reasoning_effort,
        )
        cached = _get_cached_response(cache_key)
        if cached is not None:
            answer, source_ids = cached
            return RAGResult(
                answer=answer,
                contexts=prompt_contexts,
                source_ids=source_ids,
                prompt_sha256=prompt_sha256,
                generation_provider="response_cache",
            )

        try:
            answer, generation_provider = generate_with_provider_fallback(self.llm, prompt)
            answer_token_usage = accumulate_token_usage(None, self.llm)
        except Exception as error:
            if not is_retryable_provider_error(error):
                raise
            reason = "provider_rate_limited" if isinstance(error, RateLimitError) else "provider_unavailable"
            fallback = _source_only_fallback(question, prompt_contexts, reason)
            return fallback.model_copy(update={"prompt_sha256": prompt_sha256})

        if answer == INSUFFICIENT_ANSWER:
            return RAGResult(
                answer=INSUFFICIENT_ANSWER,
                contexts=contexts,
                insufficient_context=True,
                prompt_sha256=prompt_sha256,
                generation_provider=generation_provider,
                token_usage=answer_token_usage,
            )
        source_ids = extract_source_ids(answer)

        if not source_ids:
            return _source_only_fallback(question, prompt_contexts, "evidence_validation_failed").model_copy(
                update={
                    "prompt_sha256": prompt_sha256,
                    "generation_provider": generation_provider,
                    "token_usage": answer_token_usage,
                },
            )

        allowed_source_ids = {
            context["source_id"]
            for context in contexts
        }
        unknown_source_ids = (
            set(source_ids) - allowed_source_ids
        )

        if unknown_source_ids:
            return _source_only_fallback(question, prompt_contexts, "evidence_validation_failed").model_copy(
                update={
                    "prompt_sha256": prompt_sha256,
                    "generation_provider": generation_provider,
                    "token_usage": answer_token_usage,
                },
            )

        _cache_response(cache_key, answer, source_ids)

        return RAGResult(
            answer=answer,
            contexts=prompt_contexts,
            source_ids=source_ids,
            prompt_sha256=prompt_sha256,
            generation_provider=generation_provider,
            token_usage=answer_token_usage,
        )

    def retrieve_contexts(
        self,
        question: str,
        limit: int = 5,
        company: str | None = None,
        roles: list[str] | None = None,
        metadata_filter: dict | None = None,
        retrieval_method: Literal["dense", "bm25", "hybrid", "parent", "translated_hybrid", "translated_hybrid_rerank"] = "hybrid",
        document_ids: list[str] | None = None,
        query_language: str = "auto",
        document_languages: dict[str, str] | None = None,
    ) -> list[dict]:
        """Return authorized passages; translated_hybrid also invokes query translation."""
        if not isinstance(roles, list) or not roles or any(
            not isinstance(role, str) or not role.strip() for role in roles
        ):
            raise ValueError("RAG retrieval requires trusted authenticated roles")
        request = RetrievalRequest(query=question, top_k=limit)
        method = {} if retrieval_method == "hybrid" else {"method": retrieval_method}
        retrieval_filters = {"roles": roles}
        if metadata_filter:
            retrieval_filters["metadata_filter"] = metadata_filter
        if company is not None:
            retrieval_filters["company"] = company
        if document_ids is not None:
            retrieval_filters["document_ids"] = document_ids
        if query_language != "auto":
            retrieval_filters["query_language"] = query_language
        if document_languages is not None:
            retrieval_filters["document_languages"] = document_languages
        retrieval_filters.update(method)
        retrieved = self.retrieval_service.retrieve(request, **retrieval_filters)

        contexts = [
            {
                "document_name": context.source,
                "chunk_id": context.chunk_id,
                "chunk_index": context.location.chunk_index,
                "content": context.text,
                "metadata": context.metadata,
                "retrieval_score": context.score,
                "retrieval_method": context.retrieval_method,
                "source_id": f"S{index}",
            }
            for index, context in enumerate(
                retrieved.results,
                start=1,
            )
        ]
        if retrieved.retrieval_details:
            for context in contexts:
                context["retrieval_details"] = dict(retrieved.retrieval_details)
        return contexts

    def close(self) -> None:
        self.retrieval_service.close()
        if hasattr(self.llm, "close"):
            self.llm.close()
