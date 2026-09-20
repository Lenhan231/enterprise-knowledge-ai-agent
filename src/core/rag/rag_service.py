# src/core/rag/rag_service.py
from core.llm.groq_provider import GroqProvider
from core.retrieval import RetrievalService
from core.llm.llm_interface import LLMInterface
from core.prompts.Knowledge import ENTERPRISE_ASSISTANT_PROMPT
from pydantic import BaseModel, Field
import re

INSUFFICIENT_ANSWER = (
    "Insufficient information in the retrieved documents."
)

CITATION_PATTERN = re.compile(r"\[(S\d+)\]")


class RAGResult(BaseModel):
    answer: str
    contexts: list[dict] = Field(default_factory=list)
    source_ids: list[str] = Field(default_factory=list)
    insufficient_context: bool = False


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
            f"Similarity: {context['similarity_score']:.4f}",
        ]

        if metadata.get("page_number") is not None:
            lines.append(f"Page: {metadata['page_number']}")

        if metadata.get("section_title"):
            lines.append(f"Section: {metadata['section_title']}")

        lines.append(f"Content: {context['content']}")
        blocks.append("\n".join(lines))

    return "\n\n".join(blocks)


def _extract_source_ids(answer: str) -> list[str]:
    return list(dict.fromkeys(CITATION_PATTERN.findall(answer)))


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
        limit: int = 5
    ) -> RAGResult:
        retrieved = self.retrieval_service.retrieve(
            question,
            limit,
        )

        contexts = [
            {
                **context,
                "source_id": f"S{index}",
            }
            for index, context in enumerate(
                retrieved["contexts"],
                start=1,
            )
        ]

        if not contexts:
            return RAGResult(
                answer=INSUFFICIENT_ANSWER,
                insufficient_context=True,
                source_ids=[],
            )

        prompt = ENTERPRISE_ASSISTANT_PROMPT.format(
            context=_format_contexts(contexts),
            question=question,
        )

        answer = self.llm.generate(prompt).strip()

        if answer == INSUFFICIENT_ANSWER:
            return RAGResult(
                answer=INSUFFICIENT_ANSWER,
                contexts=contexts,
                insufficient_context=True,
            )
        source_ids=_extract_source_ids(answer)
        
        if not source_ids:
            raise ValueError(
                "Generated answer contains no source citations"
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
            contexts=contexts,
            source_ids=source_ids,
        )
    
    def close(self) -> None:
        self.retrieval_service.close()
        
    # def generate_answer(self, question: str, limit: int = 5) -> str:
    #     retrieved = self.retrieval_service.retrieve(question, limit)
    #     contexts = retrieved["contexts"]

    #     context = "\n\n".join(item["content"] for item in contexts)
    #     print(context)

    #     prompt = ENTERPRISE_ASSISTANT_PROMPT.format(context=context, question=question)

    #     return self.llm.generate(prompt)


