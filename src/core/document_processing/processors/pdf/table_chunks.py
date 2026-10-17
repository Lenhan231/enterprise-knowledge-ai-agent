"""Create retrieval chunks from extracted PDF table rows."""

from __future__ import annotations

import re
import unicodedata
from collections import Counter, defaultdict
from typing import Any, Dict, List, Tuple

from core.document_processing.chunking.chunk_builder import (
    build_text_chunk,
    build_text_chunks,
)


class PDFTableChunker:
    """Format structured rows and reconcile them with text chunks."""

    def __init__(self, config: dict[str, Any], chunking):
        self.config = config
        self.chunking = chunking

    def replace_flat_table_chunks(self, chunks: List[Dict[str, Any]], tables: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Use row/column-aware table text when it safely matches a same-page chunk.
        Unmatched table fragments are added without deleting source text. This
        keeps uncertain parser output searchable while avoiding a lossy swap.
        """
        threshold = float(self.config["table_chunk_replacement_threshold"])
        replacements: Dict[int, Dict[str, Any]] = {}
        additions: Dict[int, List[Dict[str, Any]]] = defaultdict(list)
        claimed_chunks = set()
        for table in tables:
            page_number = int(table.get("page_number") or 0)
            table_context = table.get("context") or {}
            table_title = str(table_context.get("table_title") or "").strip()
            fragments = self._structured_table_fragments(
                table, self.chunking, table_title=table_title,
            )
            for fragment_index, fragment in enumerate(fragments):
                best = None
                for chunk_index, chunk in enumerate(chunks):
                    if chunk_index in claimed_chunks:
                        continue
                    if int(chunk.get("metadata", {}).get("page_number") or 0) != page_number:
                        continue
                    chunk_coverage, table_coverage = self._table_match_coverage(
                        chunk.get("text", ""), fragment["match_text"],
                    )
                    score = min(chunk_coverage, table_coverage)
                    if best is None or score > best[0]:
                        best = (score, chunk_coverage, table_coverage, chunk_index)
                matched_chunk_index = None
                chunk_coverage = table_coverage = 0.0
                best_chunk_index = None
                if best:
                    _, chunk_coverage, table_coverage, best_chunk_index = best
                if best and chunk_coverage >= threshold and table_coverage >= threshold:
                    matched_chunk_index = best_chunk_index
                    claimed_chunks.add(matched_chunk_index)
                context_chunk_index = matched_chunk_index if matched_chunk_index is not None else best_chunk_index
                source_metadata = (
                    chunks[context_chunk_index].get("metadata", {})
                    if context_chunk_index is not None
                    else next((
                        chunk.get("metadata", {}) for chunk in chunks
                        if int(chunk.get("metadata", {}).get("page_number") or 0) == page_number
                    ), chunks[0].get("metadata", {}) if chunks else {})
                )
                metadata = {
                    **source_metadata,
                    **table.get("metadata", {}),
                    "page_number": page_number,
                    "chunk_strategy": source_metadata.get("chunk_strategy", "sentence"),
                    "layout_type": "table",
                    "element_type": "table",
                    "table_index": table.get("table_index"),
                    "table_fragment_index": fragment_index,
                    "table_fragment_count": len(fragments),
                    **({"table_title": table_title} if table_title else {}),
                    "table_extraction_method": table.get("metadata", {}).get("table_extraction_method"),
                    "parser": "pymupdf.structured_table_chunk",
                    "table_chunk_match_threshold": threshold,
                    "table_chunk_match": {
                        "matched_source_chunk": matched_chunk_index is not None,
                        "chunk_token_coverage": round(chunk_coverage, 4),
                        "table_token_coverage": round(table_coverage, 4),
                        "best_candidate_chunk_index": (
                            chunks[best_chunk_index].get("metadata", {}).get("chunk_index")
                            if best_chunk_index is not None else None
                        ),
                        "matched_source_chunk_index": (
                            chunks[matched_chunk_index].get("metadata", {}).get("chunk_index")
                            if matched_chunk_index is not None else None
                        ),
                    },
                }
                table_chunk = build_text_chunk(
                    fragment["text"], metadata, self.chunking, index=fragment_index
                )
                if matched_chunk_index is not None:
                    replacements[matched_chunk_index] = table_chunk
                else:
                    additions[page_number].append(table_chunk)
        by_page: Dict[int, List[Dict[str, Any]]] = defaultdict(list)
        unpaged = []
        for index, chunk in enumerate(chunks):
            page_number = int(chunk.get("metadata", {}).get("page_number") or 0)
            if page_number:
                by_page[page_number].append(replacements.get(index, chunk))
            else:
                unpaged.append(replacements.get(index, chunk))
        result = []
        for page_number in sorted(set(by_page) | set(additions)):
            result.extend(by_page.get(page_number, []))
            result.extend(additions.get(page_number, []))
        result.extend(unpaged)
        for index, chunk in enumerate(result):
            chunk["metadata"]["chunk_index"] = index
        return result

    @staticmethod

    def _structured_table_fragments(
        table: Dict[str, Any], chunking, *, table_title: str = "",
    ) -> List[Dict[str, str]]:
        columns = [str(column or f"column_{index + 1}").strip() for index, column in enumerate(table.get("columns", []))]
        rows = table.get("rows", [])
        if not columns and rows:
            columns = list(dict.fromkeys(str(key) for row in rows for key in row))
        if not columns:
            return []
        column_line = "Columns: " + " | ".join(columns)
        title_line = f"Table: {table_title}" if table_title else ""
        row_lines = []
        for row_index, row in enumerate(rows, start=1):
            cells = [str(row.get(column) if row.get(column) is not None else "").strip() for column in columns]
            if any(cells):
                row_lines.append(f"Row {row_index}: " + " | ".join(
                    f"{column}: {value}" for column, value in zip(columns, cells)
                ))
        if not row_lines:
            return []
        table_text = "\n".join(part for part in (
            title_line, column_line, *row_lines,
        ) if part)
        return [
            {
                "text": chunk["text"],
                "match_text": chunk["text"],
            }
            for chunk in build_text_chunks(table_text, {}, chunking)
        ]

    @staticmethod

    def _table_match_coverage(chunk_text: str, table_text: str) -> Tuple[float, float]:

        def tokens(value: str) -> Counter:
            normalized = unicodedata.normalize("NFKD", value).casefold()
            normalized = "".join(char for char in normalized if unicodedata.category(char) != "Mn")
            return Counter(re.findall(r"[\w]+", normalized, flags=re.UNICODE))
        chunk_tokens = tokens(chunk_text)
        table_tokens = tokens(table_text)
        if not chunk_tokens or not table_tokens:
            return 0.0, 0.0
        matched = sum((chunk_tokens & table_tokens).values())
        return matched / sum(chunk_tokens.values()), matched / sum(table_tokens.values())
