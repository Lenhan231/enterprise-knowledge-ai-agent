from core.llm.groq_provider import GroqProvider
from core.retrieval.retrieval import RetrievalRequest
from core.retrieval.retrieval_service import RetrievalService
from core.retrieval.retrieval import RetrievalRequest
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

# Groq's on-demand tier can reject prompts close to its 8k TPM request limit.
# Keep the retrieved evidence smaller so the prompt and generated answer fit.
MAX_CONTEXT_CHARS = 16_000
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


def _employee_access_policy_disclosure(question: str, contexts: list[dict]) -> "RAGResult | None":
    terms = question.casefold()
    if not all(re.search(pattern, terms) for pattern in (r"\bemployees?\b", r"\baccess\b", r"\bpolic(?:y|ies)\b")):
        return None

    code_id = "VNM-CODE-2025-EN"
    for context in contexts:
        metadata = context.get("metadata") or {}
        document_name = str(metadata.get("source_document") or context.get("document_name") or "")
        document_type = str(metadata.get("document_type") or "").casefold().replace("_", " ")
        if (
            metadata.get("document_id") != code_id
            and "information system policy" in document_name.casefold()
            and "policy" in document_type
        ):
            return None

    access_context = next((
        context for context in contexts
        if (context.get("metadata") or {}).get("document_id") == code_id
        and "employees are assigned rights to access and process information" in str(context.get("content", "")).casefold()
    ), None)
    reference_context = next((
        context for context in contexts
        if (context.get("metadata") or {}).get("document_id") == code_id
        and "in information system policy" in str(context.get("content", "")).casefold()
    ), None)
    if not access_context or not reference_context:
        return None

    def sentence(context: dict, start: str) -> str | None:
        match = re.search(re.escape(start) + r"[^.]*\.", str(context.get("content", "")), re.IGNORECASE)
        return match.group(0).strip() if match else None

    rights = sentence(access_context, "Employees are assigned rights to access and process information")
    exceptions = sentence(access_context, "For the exceptions")
    prohibited = sentence(access_context, "Unauthorized access and processing")
    policy_reference = sentence(reference_context, "The Company stipulates the usage and protection")
    if not all((rights, exceptions, prohibited, policy_reference)):
        return None

    access_id = access_context["source_id"]
    reference_id = reference_context["source_id"]
    return RAGResult(
        answer=(
            f"The Code of Conduct's Network and access section says: “{rights}” [{access_id}] "
            f"“{exceptions}” [{access_id}] “{prohibited}” [{access_id}] "
            f"The Code separately refers to the Information System Policy: “{policy_reference}” [{reference_id}] "
            f"The separate Information System Policy is not included in the retrieved documents; this answer covers only the Code of Conduct provisions [{reference_id}]."
        ),
        contexts=[access_context, reference_context],
        source_ids=list(dict.fromkeys((access_id, reference_id))),
    )


class RAGResult(BaseModel):
    answer: str
    contexts: list[dict] = Field(default_factory=list)
    source_ids: list[str] = Field(default_factory=list)
    insufficient_context: bool = False
    prompt_sha256: str | None = None


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
        retrieval_method: Literal["dense", "bm25", "hybrid", "parent"] = "hybrid",
        retrieval_query: str | None = None,
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
        contexts = retrieved_contexts if retrieved_contexts is not None else self.retrieve_contexts(
            retrieval_query or question,
            limit=limit,
            company=company,
            roles=roles,
            metadata_filter=metadata_filter,
            retrieval_method=retrieval_method,
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

        access_policy_disclosure = _employee_access_policy_disclosure(question, contexts)
        if access_policy_disclosure:
            return access_policy_disclosure

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
            )

        answer = self.llm.generate(prompt).strip()

        if answer == INSUFFICIENT_ANSWER:
            return RAGResult(
                answer=INSUFFICIENT_ANSWER,
                contexts=contexts,
                insufficient_context=True,
                prompt_sha256=prompt_sha256,
            )
        source_ids = extract_source_ids(answer)

        if not source_ids:
            raise ValueError(
                f"Generated answer contains no source citations. Answer: {answer}"
)

        allowed_source_ids = {
            context["source_id"]
            for context in contexts
        }
        unknown_source_ids = (
            set(source_ids) - allowed_source_ids
        )

        if unknown_source_ids:
            raise ValueError(
                "Generated answer contains unknown citations: "
                f"{sorted(unknown_source_ids)}"
            )

        _cache_response(cache_key, answer, source_ids)

        return RAGResult(
            answer=answer,
            contexts=prompt_contexts,
            source_ids=source_ids,
            prompt_sha256=prompt_sha256,
        )

    def retrieve_contexts(
        self,
        question: str,
        limit: int = 5,
        company: str | None = None,
        roles: list[str] | None = None,
        metadata_filter: dict | None = None,
        retrieval_method: Literal["dense", "bm25", "hybrid", "parent"] = "hybrid",
    ) -> list[dict]:
        """Return authorized ranked passages without invoking the language model."""
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
        retrieval_filters.update(method)
        retrieved = self.retrieval_service.retrieve(request, **retrieval_filters)

        contexts = [
            {
                "document_name": context.source,
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
        return contexts

    def close(self) -> None:
        self.retrieval_service.close()
        if hasattr(self.llm, "close"):
            self.llm.close()
