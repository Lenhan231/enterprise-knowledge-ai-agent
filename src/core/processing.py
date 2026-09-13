from typing import List

class DocumentProcessor:
    """Stub for document parsing and OCR pipeline."""

    def parse(self, path: str) -> dict:
        """Parse a document and return extracted content and metadata."""
        # TODO: implement PDF, DOCX, Excel, image parsing and OCR
        return {"text": "", "metadata": {}}


class Retriever:
    """Stub for embedding generation and vector retrieval."""

    def embed(self, texts: List[str]):
        # TODO: integrate embedding model
        return []

    def search(self, query: str):
        # TODO: implement hybrid BM25 + vector search
        return []


class AgentRouter:
    """Dispatches requests to specialized AI agents."""

    def route(self, intent: str, context: dict):
        # TODO: implement intent routing to QA, SQL, Report agents
        return {"agent": "qa", "response": ""}
