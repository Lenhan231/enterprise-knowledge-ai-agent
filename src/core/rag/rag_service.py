from core.llm.groq_provider import GroqProvider
from core.retrieval.retrieval import RetrievalRequest
from core.retrieval.retrieval_service import RetrievalService
from core.retrieval.retrieval import RetrievalRequest
from core.prompts.Knowledge import ENTERPRISE_ASSISTANT_PROMPT
from pydantic import BaseModel, Field
from typing import Literal
import re
import hashlib
import unicodedata

# Groq's on-demand tier can reject prompts close to its 8k TPM request limit.
# Keep the retrieved evidence smaller so the prompt and generated answer fit.
MAX_CONTEXT_CHARS = 16_000

INSUFFICIENT_ANSWER = (
    "Insufficient information in the retrieved documents."
)

CITATION_PATTERN = re.compile(
    r"\[\s*(?:(?:source|nguồn)\s*:\s*)?([A-Z]\d+)\s*\]"
    r"|【\s*(?:(?:source|nguồn)\s*:\s*)?([A-Z]\d+)\s*】",
    re.IGNORECASE,
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
        retrieval_method: Literal["dense", "bm25", "hybrid", "parent"] = "hybrid",
    ) -> RAGResult:
        contexts = self.retrieve_contexts(
            question,
            limit=limit,
            company=company,
            roles=roles,
            retrieval_method=retrieval_method,
        )
        if not contexts:
            return RAGResult(
                answer=INSUFFICIENT_ANSWER,
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
        retrieval_method: Literal["dense", "bm25", "hybrid", "parent"] = "hybrid",
    ) -> list[dict]:
        """Return authorized ranked passages without invoking the language model."""
        request = RetrievalRequest(query=question, top_k=limit)
        method = {} if retrieval_method == "hybrid" else {"method": retrieval_method}
        if company is None and roles is None:
            retrieved = self.retrieval_service.retrieve(request, **method)
        else:
            retrieval_filters = {"roles": roles}
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
