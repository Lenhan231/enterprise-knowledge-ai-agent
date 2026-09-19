# src/core/models/document.py

from dataclasses import dataclass

@dataclass
class ChunkMetadata:
    source_document: str      # e.g. "2024_Apple.pdf" original name
    document_type: str        # e.g. "pdf", "docx", "xlsx", "image"
    page_number: int | None   # None when the format has no stable page concept
    chunk_index: int          # index within one source document
    section_title: str | None # nearest structural heading/section
    parent_id: str | None     # parent structural unit / parent chunk id
    token_count: int | None   # token count for this chunk
    document_id: str          # UUID or deterministic document identifier

