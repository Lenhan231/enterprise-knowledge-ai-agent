# src/core/document_processing/ingest_documents.py

from core.chunking.semantic_chunker import SemanticDocumentChunker
from core.document_processing.processors.pdf_processor import PDFProcessor
from core.embeddings import EmbeddingService
from core.embeddings.embedding_service import EMBEDDING_MAX_SEQUENCE_LENGTH
from core.models.document import ChunkMetadata
from uuid import uuid4
from dataclasses import asdict
from core.utils.token_counter import TokenCounter

from pathlib import Path
from html.parser import HTMLParser
import re
from langchain_core.documents import Document


class _HTMLTextExtractor(HTMLParser):
    """Keep readable article text while skipping non-content elements."""

    _ignored = {
        "button", "footer", "form", "header", "head", "nav", "noscript",
        "script", "style", "svg",
    }
    _breaks = {"article", "br", "div", "h1", "h2", "h3", "h4", "li", "p", "section"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.ignored_depth = 0

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag in self._ignored:
            self.ignored_depth += 1
        elif not self.ignored_depth and tag in self._breaks:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in self._ignored and self.ignored_depth:
            self.ignored_depth -= 1
        elif not self.ignored_depth and tag in self._breaks:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self.ignored_depth and data.strip():
            self.parts.append(f" {data.strip()} ")

    def text(self) -> str:
        text = "".join(self.parts)
        text = re.sub(r"[ \t\xa0]+", " ", text)
        text = re.sub(r" *\n *", "\n", text)
        return re.sub(r"\n{3,}", "\n\n", text).strip()

class Ingestion:
    def __init__(
        self,
        embedding_service: EmbeddingService | None = None,
        chunking_strategy: str = "sentence",
        extract_tables: bool = True,
    ):
        self.embedding_service = embedding_service or EmbeddingService()
        self.token_counter = TokenCounter(self.embedding_service.model_name)
        self.splitter = SemanticDocumentChunker(self.embedding_service)
        if chunking_strategy not in {"fixed", "sentence", "semantic"}:
            raise ValueError("chunking_strategy must be 'fixed' or 'sentence'")
        self.chunking_strategy = chunking_strategy
        self.extract_tables = extract_tables

        
    def ingestion(
        self,
        input_path: Path,
        output_dir: Path,
        extra_metadata: dict | None = None,
        document_id: str | None = None,
        include_tables: bool = False,
    ):

        if not input_path.exists():
            raise FileNotFoundError(f"File does not exist: {input_path}")

        file_type = input_path.suffix.lower()
        extracted_tables = []

        if file_type == ".pdf":
            # Seed corpus ingestion follows the same page-aware parser as uploads.
            # Keep bulk parsing bounded while OCRing sparse scans and mixed pages
            # dominated by raster images. Preserve detected tables for persistence.
            processed = PDFProcessor({
                "paddle_layout": False,
                "ocr_fallback": True,
                "ocr_language": "vie+eng",
                "extract_tables": self.extract_tables,
                "chunking_strategy": self.chunking_strategy,
                "chunk_size": 1200,
                "chunk_overlap": 150,
            }).process({
                "metadata": {"filepath": str(input_path)},
                "content": input_path.read_bytes(),
            })
            extracted_tables = processed["tables"]
            markdown_content = [
                {"metadata": chunk["metadata"], "text": chunk["text"]}
                for chunk in processed["chunks"]
            ]
            output_path = Path(output_dir)
            output_path.mkdir(parents=True, exist_ok=True)
            (output_path / f"{input_path.stem}.md").write_text(
                "\n\n".join(page["text"] for page in markdown_content),
                encoding="utf-8",
            )
        elif file_type in {".html", ".htm"}:
            parser = _HTMLTextExtractor()
            parser.feed(input_path.read_text(encoding="utf-8", errors="replace"))
            markdown_content = [{
                "metadata": {"page_number": None},
                "text": parser.text(),
            }]
            Path(output_dir).mkdir(parents=True, exist_ok=True)
            (Path(output_dir) / f"{input_path.stem}.md").write_text(
                markdown_content[0]["text"], encoding="utf-8"
            )
        else:
            raise NotImplementedError(f"Unsupported document type: {file_type}")
        document_id = document_id or str(uuid4())
        chunk_index = 0
        all_chunks = []

        for page in markdown_content:
            page_metadata = page["metadata"]
            page_number = page_metadata.get("page_number")
            page_text = page["text"]

            # PDFProcessor has already page-aware chunked PDFs; splitting each
            # chunk again with SemanticChunker embeds every sentence repeatedly.
            # Keep its bounded chunks and provenance, then embed them in one batch.
            page_chunks = (
                [Document(page_content=page_text, metadata={})]
                if file_type == ".pdf"
                else self.splitter.chunk_text(page_text)
            )
            for chunk in page_chunks:
                bounded_texts = self.token_counter.split_text(
                    chunk.page_content,
                    max_sequence_tokens=getattr(
                        self.embedding_service,
                        "max_sequence_length",
                        EMBEDDING_MAX_SEQUENCE_LENGTH,
                    ),
                )
                for bounded_text in bounded_texts:
                    metadata = ChunkMetadata(
                        source_document=input_path.name,
                        document_type=file_type.lstrip("."),
                        page_number=page_number,
                        chunk_index=chunk_index,
                        section_title=None,
                        parent_id=None,
                        token_count=0,
                        document_id=document_id,
                    )
                    bounded_chunk = Document(page_content=bounded_text, metadata=asdict(metadata))
                    bounded_chunk.metadata.update(page_metadata)
                    bounded_chunk.metadata.update(extra_metadata or {})
                    bounded_chunk.metadata["chunk_index"] = chunk_index
                    bounded_chunk.metadata["token_count"] = self.token_counter.count(bounded_text)
                    all_chunks.append(bounded_chunk)
                    chunk_index += 1
                

        return (all_chunks, extracted_tables) if include_tables else all_chunks
