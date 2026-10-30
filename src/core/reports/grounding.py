"""Conservative citation and numeric support checks, not semantic verification."""

import re
from decimal import Decimal, InvalidOperation

CITATION = re.compile(r"\[S(\d+)\]")
NUMBER = re.compile(r"(?<!\w)[+-]?\d+(?:[.,]\d+)*(?:\s*%)?(?!\w)")
VERIFICATION_SCOPE = (
    "Checks cover citation existence and numeric matching only. They do not prove semantic "
    "entailment, arithmetic correctness, accounting scope or exhaustive source coverage."
)
UNAVAILABLE = "Unavailable in source data; section verification failed."


def numeric_value(token):
    token = token.strip()
    percent = token.endswith("%")
    token = token.rstrip("%").strip()
    # A single separator followed by three digits is ambiguous across locales.
    if re.fullmatch(r"[+-]?\d{1,3}[.,]\d{3}", token):
        return None
    if "," in token and "." in token:
        if token.rfind(".") < token.rfind(","):
            token = token.replace(".", "").replace(",", ".")
        else:
            token = token.replace(",", "")
    elif token.count(",") > 1 or token.count(".") > 1:
        separator = "," if "," in token else "."
        if not re.fullmatch(r"[+-]?\d{1,3}(?:[.,]\d{3})+", token):
            return None
        token = token.replace(separator, "")
    else:
        token = token.replace(",", ".")
    try:
        return (Decimal(token), percent)
    except InvalidOperation:
        return None


def validate_claim(text, evidence):
    """Every paragraph/row must cite supplied evidence or explicitly abstain."""
    if text.strip() == UNAVAILABLE:
        return
    identifiers = CITATION.findall(text)
    sources = {item.citation_id: item.content or "" for item in evidence}
    if not identifiers:
        raise ValueError("missing_citation")
    if any(f"S{identifier}" not in sources for identifier in identifiers):
        raise ValueError("unknown_citation")
    supported = {
        numeric_value(token) for identifier in identifiers
        for token in NUMBER.findall(sources[f"S{identifier}"])
    } - {None}
    claim = CITATION.sub("", text)
    if re.search(r"\d", NUMBER.sub("", claim)):
        raise ValueError("unsupported_numeric_notation")
    for token in NUMBER.findall(claim):
        value = numeric_value(token)
        if value is None or value not in supported:
            raise ValueError("unsupported_or_ambiguous_number")


def validate_section(draft, heading, headers, evidence):
    if not isinstance(draft, dict) or not isinstance(draft.get("sections"), dict):
        raise ValueError("invalid_sections")
    if set(draft["sections"]) != {heading}:
        raise ValueError("incorrect_headings")
    body = draft["sections"][heading]
    if not isinstance(body, str) or not body.strip() or len(body.split()) > 600:
        raise ValueError("invalid_section_length")
    tables = draft.get("tables")
    if not isinstance(tables, list) or len(tables) != len(headers):
        raise ValueError("incorrect_table_count")
    for paragraph in body.splitlines():
        if paragraph.strip():
            validate_claim(paragraph, evidence)
    for table, columns in zip(tables, headers):
        if not isinstance(table, dict) or not isinstance(table.get("rows"), list) or len(table["rows"]) > 100:
            raise ValueError("invalid_table_rows")
        for row in table["rows"]:
            if (not isinstance(row, list) or len(row) != len(columns)
                    or any(not isinstance(cell, str) or len(cell) > 2000 for cell in row)):
                raise ValueError("invalid_table_columns")
            validate_claim(" ".join(row), evidence)
    return body, [table["rows"] for table in tables]
