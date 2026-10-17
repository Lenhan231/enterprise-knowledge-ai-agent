"""Small shared parsers for table markup returned by document engines."""

from __future__ import annotations

from html.parser import HTMLParser


class _HTMLTableParser(HTMLParser):
    """Read HTML table cells, expanding row and column spans into a grid."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.rows: list[list[tuple[str, int, int]]] = []
        self._row: list[tuple[str, int, int]] | None = None
        self._cell: list[str] | None = None
        self._rowspan = 1
        self._colspan = 1
        self._table_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if tag == "table":
            self._table_depth += 1
        elif self._table_depth == 1 and tag == "tr":
            self._row = []
        elif self._table_depth == 1 and tag in {"td", "th"} and self._row is not None:
            self._cell = []
            self._rowspan = max(1, int(attributes.get("rowspan") or 1))
            self._colspan = max(1, int(attributes.get("colspan") or 1))
        elif self._cell is not None and tag == "br":
            self._cell.append(" ")

    def handle_data(self, data: str) -> None:
        if self._cell is not None:
            self._cell.append(data)

    def handle_endtag(self, tag: str) -> None:
        if self._table_depth == 1 and tag in {"td", "th"} and self._cell is not None:
            value = " ".join("".join(self._cell).split())
            if self._row is not None:
                self._row.append((value, self._rowspan, self._colspan))
            self._cell = None
        elif self._table_depth == 1 and tag == "tr" and self._row is not None:
            if self._row:
                self.rows.append(self._row)
            self._row = None
        elif tag == "table" and self._table_depth:
            self._table_depth -= 1


def parse_html_table(content: str) -> list[list[str]]:
    """Return a rectangular cell grid; repeated cells preserve row/column spans."""
    parser = _HTMLTableParser()
    parser.feed(content)
    grid: list[list[str]] = []
    spans: dict[int, tuple[int, str]] = {}

    for row_index, cells in enumerate(parser.rows):
        row: list[str] = []
        for column, (end_row, value) in spans.items():
            if end_row > row_index:
                while len(row) <= column:
                    row.append("")
                row[column] = value

        column = 0
        for value, rowspan, colspan in cells:
            while column < len(row) and row[column]:
                column += 1
            for offset in range(colspan):
                target = column + offset
                while len(row) <= target:
                    row.append("")
                row[target] = value
                if rowspan > 1:
                    spans[target] = (row_index + rowspan, value)
            column += colspan
        grid.append(row)

    width = max((len(row) for row in grid), default=0)
    return [row + [""] * (width - len(row)) for row in grid]
