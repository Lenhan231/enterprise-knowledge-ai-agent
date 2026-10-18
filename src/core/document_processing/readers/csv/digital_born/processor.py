"""Parse CSV rows into a structured table and searchable parser chunks."""

from __future__ import annotations

import csv
import io
from typing import Any

from core.document_processing.chunking.config import ChunkingConfig
from core.document_processing.chunking.router import build_chunks


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
        chunks = build_chunks(table, self.chunking, kind="table", metadata=chunk_metadata)
        return {"chunks": chunks, "tables": [table]}

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
