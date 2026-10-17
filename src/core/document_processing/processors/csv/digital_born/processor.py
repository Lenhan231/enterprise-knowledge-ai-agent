"""Parse CSV rows into a structured table and searchable parser chunks."""

from __future__ import annotations

import csv
import io
from typing import Any

from core.document_processing.chunking.chunk_builder import build_text_chunk
from core.document_processing.chunking.config import ChunkingConfig


class CSVProcessor:
    def __init__(self, config: dict[str, Any] | None = None):
        self.chunking = ChunkingConfig.from_config(config or {})

    def process_file(self, content: bytes, metadata: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
        try:
            text = content.decode("utf-8-sig")
        except UnicodeDecodeError as error:
            raise ValueError("CSV files must use UTF-8 encoding") from error

        sample = text[:8192]
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
        except csv.Error:
            dialect = csv.excel

        rows = [
            [value for value in row]
            for row in csv.reader(io.StringIO(text, newline=""), dialect)
            if any(value.strip() for value in row)
        ]
        if not rows:
            raise ValueError("CSV file must contain a header row")

        width = max(map(len, rows))
        columns = self._unique_columns(rows[0], width)
        records = [
            dict(zip(columns, row + [""] * (width - len(row))))
            for row in rows[1:]
        ]
        table_index = 0
        table = {
            # Structured-table storage requires a 1-based location; a CSV's
            # single table is its first logical section.
            "page_number": 1,
            "table_index": table_index,
            "columns": columns,
            "rows": records,
            "metadata": {
                "parser": "python-csv",
                "delimiter": dialect.delimiter,
            },
        }
        chunk_metadata = {
            **metadata,
            "parser": "python-csv",
            "element_type": "table",
            "layout_type": "table",
            "table_index": table_index,
        }
        chunks = self._build_row_chunks(columns, records, chunk_metadata)
        return {"chunks": chunks, "tables": [table]}

    def _build_row_chunks(
        self,
        columns: list[str],
        records: list[dict[str, str]],
        metadata: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """Group whole CSV rows and repeat the column header in every chunk."""
        header = "Columns: " + " | ".join(columns)
        lines = [header]
        row_start: int | None = None
        row_end: int | None = None
        chunks = []

        def flush() -> None:
            if not lines:
                return
            chunk = build_text_chunk(
                "\n".join(lines), metadata, self.chunking, index=len(chunks),
            )
            chunk["metadata"].update({
                "chunking_method": "csv_row_groups",
                "chunk_overlap_chars": 0,
                "table_row_start": row_start,
                "table_row_end": row_end,
            })
            chunks.append(chunk)

        for row_number, record in enumerate(records, start=1):
            row_text = f"Row {row_number}: " + " | ".join(
                f"{column}: {record[column]}" for column in columns
            )
            candidate = "\n".join([*lines, row_text])
            if row_start is not None and len(candidate) > self.chunking.size:
                flush()
                lines = [header]
                row_start = row_end = None

            lines.append(row_text)
            row_start = row_number if row_start is None else row_start
            row_end = row_number

            # Keep a single oversized row intact; the downstream token chunker
            # remains responsible for enforcing the embedding model limit.
            if len(lines) == 2 and len("\n".join(lines)) > self.chunking.size:
                flush()
                lines = [header]
                row_start = row_end = None

        if row_start is not None or not records:
            flush()
        return chunks

    @staticmethod
    def _unique_columns(header: list[str], width: int) -> list[str]:
        columns = []
        seen: set[str] = set()
        for index in range(width):
            name = header[index].strip() if index < len(header) else ""
            name = name or f"column_{index + 1}"
            base = name
            suffix = 2
            while name in seen:
                name = f"{base}_{suffix}"
                suffix += 1
            seen.add(name)
            columns.append(name)
        return columns
