# tools/ingestion/ingest_documents.py

from core.chunking.text.strategies.semantic import SemanticDocumentChunker
from core.chunking.text.router import split_text
from core.embeddings import EmbeddingService
from core.embeddings.embedding_service import EMBEDDING_MAX_SEQUENCE_LENGTH
from core.models.document import ChunkMetadata
from uuid import uuid4
from dataclasses import asdict
from core.tokenization.token_counter import TokenCounter

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
        self._sections: list[tuple[str | None, list[str]]] = [(None, [])]
        self._heading_tag: str | None = None
        self._heading_parts: list[str] = []
        self.ignored_depth = 0
        self.anchor_menu_depth = 0

    def _append(self, text: str) -> None:
        self.parts.append(text)
        self._sections[-1][1].append(text)

    def handle_starttag(self, tag: str, attrs) -> None:
        attributes = dict(attrs)
        if self.anchor_menu_depth:
            if tag == "div":
                self.anchor_menu_depth += 1
            return
        if tag == "div" and attributes.get("id") == "anchor-menu":
            self.anchor_menu_depth = 1
            return
        if tag in self._ignored:
            self.ignored_depth += 1
        elif not self.ignored_depth and tag in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            self.parts.append("\n")
            self._heading_tag = tag
            self._heading_parts = []
        elif not self.ignored_depth and tag in self._breaks:
            self._append("\n")

    def handle_endtag(self, tag: str) -> None:
        if self.anchor_menu_depth:
            if tag == "div":
                self.anchor_menu_depth -= 1
            return
        if tag in self._ignored and self.ignored_depth:
            self.ignored_depth -= 1
        elif not self.ignored_depth and tag == self._heading_tag:
            heading = " ".join(" ".join(self._heading_parts).split())
            if heading:
                self.parts.append(f"{heading}\n")
                self._sections.append((heading, []))
            self._heading_tag = None
            self._heading_parts = []
        elif not self.ignored_depth and tag in self._breaks:
            self._append("\n")

    def handle_data(self, data: str) -> None:
        if not self.ignored_depth and not self.anchor_menu_depth and data.strip() and data.strip().casefold() not in {
            "skip to content", "skip to navigate",
        }:
            if self._heading_tag:
                self._heading_parts.append(data.strip())
            else:
                self._append(f" {data.strip()} ")

    def blocks(self) -> list[dict]:
        blocks = []
        for heading, parts in self._sections:
            body = self._normalize("".join(parts))
            if heading and not body:
                continue
            text = "\n".join(value for value in (heading, body) if value)
            if text:
                blocks.append({"heading": heading, "text": text})
        return blocks

    @staticmethod
    def _normalize(text: str) -> str:
        text = re.sub(r"[ \t\xa0]+", " ", text)
        text = re.sub(r" *\n *", "\n", text)
        return re.sub(r"\n{3,}", "\n\n", text).strip()

    def text(self) -> str:
        return self._normalize("".join(self.parts))

class Ingestion:
    def __init__(
        self,
        embedding_service: EmbeddingService | None = None,
        chunking_strategy: str = "sentence",
        extract_tables: bool = True,
        chunk_size_chars: int = 1200,
        chunk_overlap_chars: int = 150,
    ):
        self.embedding_service = embedding_service or EmbeddingService()
        self.token_counter = TokenCounter(self.embedding_service.model_name)
        if chunking_strategy not in {"fixed", "sentence", "semantic"}:
            raise ValueError(
                "chunking_strategy must be 'fixed', 'sentence', or 'semantic'"
            )
        self.chunking_strategy = chunking_strategy
        self.splitter = (
            SemanticDocumentChunker(self.embedding_service)
            if chunking_strategy == "semantic"
            else None
        )
        self.extract_tables = extract_tables
        self.chunk_size_chars = chunk_size_chars
        self.chunk_overlap_chars = chunk_overlap_chars


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

        document_metadata = {
            key: value for key, value in (extra_metadata or {}).items()
            if key != "title"
        }

        if file_type == ".pdf":
            # Seed corpus ingestion follows the same page-aware parser as uploads.
            # Keep bulk parsing bounded while OCRing sparse scans and mixed pages
            # dominated by raster images. Preserve detected tables for persistence.
            from document_processing.document_processor import DocumentProcessor
            from core.chunking.processor import ChunkingProcessor

            processor_config = {
                "paddle_layout": False,
                "parser_engine": "docling",
                "ocr_fallback": True,
                "ocr_language": "vie+eng",
                "extract_tables": self.extract_tables,
                "chunking_strategy": self.chunking_strategy,
                "chunk_size": self.chunk_size_chars,
                "chunk_overlap": self.chunk_overlap_chars,
            }
            parsed = DocumentProcessor(processor_config).process(
                input_path.name, input_path.read_bytes(), document_metadata,
            )
            processed = ChunkingProcessor(processor_config).process(parsed)
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
            markdown_content = [
                {"metadata": {"page_number": None, "section_title": block["heading"]}, "text": block["text"]}
                for block in parser.blocks()
            ]
            Path(output_dir).mkdir(parents=True, exist_ok=True)
            (Path(output_dir) / f"{input_path.stem}.md").write_text(
                parser.text(), encoding="utf-8"
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

            # PDF parser chunks already use the shared strategy. HTML follows the
            # configured strategy so sentence/fixed chunking does not embed text
            # once for boundaries and again for the final stored vectors.
            if file_type == ".pdf":
                if self.chunking_strategy == "semantic":
                    raise ValueError(
                        "Semantic chunking is currently supported for HTML seed documents only"
                    )
                page_chunks = [Document(page_content=page_text, metadata={})]
            elif self.chunking_strategy == "semantic":
                assert self.splitter is not None
                page_chunks = self.splitter.chunk_text(page_text)
            else:
                chunking_text = re.sub(r"\n{2,}", "\n", page_text)
                page_chunks = [
                    Document(page_content=text, metadata={})
                    for text in split_text(
                        chunking_text,
                        size=self.chunk_size_chars,
                        overlap=self.chunk_overlap_chars,
                        strategy=self.chunking_strategy,
                    )
                ]
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
                        section_title=page_metadata.get("section_title"),
                        parent_id=None,
                        token_count=0,
                        document_id=document_id,
                    )
                    bounded_chunk = Document(page_content=bounded_text, metadata=asdict(metadata))
                    bounded_chunk.metadata.update(page_metadata)
                    bounded_chunk.metadata.update(document_metadata)
                    bounded_chunk.metadata["chunk_index"] = chunk_index
                    bounded_chunk.metadata["token_count"] = self.token_counter.count(bounded_text)
                    all_chunks.append(bounded_chunk)
                    chunk_index += 1


        return (all_chunks, extracted_tables) if include_tables else all_chunks
