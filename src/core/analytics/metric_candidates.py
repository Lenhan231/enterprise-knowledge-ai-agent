"""Extract source-located financial metric candidates for admin review."""

from __future__ import annotations

import hashlib
import math
import re

from core.analytics.metric_ontology import METRIC_ONTOLOGY

NUMBER = re.compile(r"(?<![\w.])(?:\(?\d[\d,.]*\)?)(?!\w)")
MAX_VALUE_DISTANCE = 80
VALUE_CONNECTORS = {"năm"}
ROW_QUALIFIERS = {"net", "consolidated", "total", "current", "gross"}
NON_VALUE_ROW_TERMS = {"ratio", "margin", "turnover", "per share", "percentage", "%"}
METRICS = {name: definition["source_labels"] for name, definition in METRIC_ONTOLOGY.items()}


def _label_matches(text: str) -> list[tuple[int, int, str, str]]:
    matches = []
    for key, labels in METRICS.items():
        for label in labels:
            matches.extend(
                (match.start(), match.end(), label, key)
                for match in re.finditer(rf"(?<!\w){re.escape(label)}(?!\w)", text, re.IGNORECASE)
            )
    return [
        item for item in matches
        if not (
            item[3] == "net_revenue"
            and re.search(r"\b(?:domestic|trong nước)\b", text[max(0, item[0] - 50):item[1] + 50], re.IGNORECASE)
        )
        if not any(
            other[0] <= item[0] and other[1] >= item[1]
            and len(other[2]) > len(item[2])
            for other in matches
        )
    ]


def candidates(
    pages: list[dict],
    document: dict,
    tables: list[dict] | None = None,
    visual_pages: list[dict] | None = None,
) -> list[dict]:
    """Find source-located metric evidence; leave figure/year interpretation for review."""
    found = []
    seen = set()

    def add_candidate(key: str, page_number: int, values: list[str], quote: str) -> None:
        found.append({
            "company": document["company"],
            "fiscal_year": int(document["fiscal_year"]),
            "metric_name": key,
            "metric_label": METRIC_ONTOLOGY[key]["label"],
            "candidate_values": values,
            "document_id": document["document_id"],
            "page_number": page_number,
            "source_quote": quote,
            "source_quote_hash": hashlib.sha256(quote.encode()).hexdigest(),
            "source_url": document["official_url"],
            "allowed_roles": document["rbac"]["allowed_roles"],
            "status": "needs_review",
        })
        seen.add(key)

    # KPI cards often store their large figure before or beside the label in
    # PDF reading order. Pair only prominent numeric spans with nearby labels.
    for page in visual_pages or []:
        labels = []
        numbers = []
        for span in page.get("spans", []):
            text = str(span.get("text", "")).strip()
            bbox = span.get("bbox")
            if not text or not bbox or len(bbox) != 4:
                continue
            if float(span.get("font_size", 0)) >= 28:
                if NUMBER.fullmatch(text) and not (text.isdigit() and 1900 <= int(text) <= 2100):
                    numbers.append((text, tuple(map(float, bbox))))
            else:
                labels.extend((key, text, tuple(map(float, bbox)))
                              for _, _, _, key in _label_matches(text))
        possible = []
        for key, label_text, label_box in labels:
            if key in seen:
                continue
            for value, value_box in numbers:
                dx = max(label_box[0] - value_box[2], value_box[0] - label_box[2], 0)
                dy = max(label_box[1] - value_box[3], value_box[1] - label_box[3], 0)
                distance = math.hypot(dx, dy)
                if distance <= 36:
                    possible.append((distance, key, label_text, value, value_box))
        used_numbers = set()
        for _, key, label_text, value, value_box in sorted(possible):
            number_key = (value, value_box)
            if key in seen or number_key in used_numbers:
                continue
            quote = f"{label_text} | {value}"
            add_candidate(key, int(page["page_number"]), [value], quote)
            used_numbers.add(number_key)

    for table in tables or []:
        page_number = table.get("page_number")
        if not page_number:
            continue
        for row in table.get("rows", []):
            cells = [str(value or "").strip() for value in row.values()]
            if len(cells) < 2:
                continue
            label_cell = cells[0]
            folded_label = label_cell.casefold()
            if "/" in label_cell or any(term in folded_label for term in NON_VALUE_ROW_TERMS):
                continue
            matched = set()
            for key, labels in METRICS.items():
                for label in labels:
                    match = re.search(rf"(?<!\w){re.escape(label)}(?!\w)", label_cell, re.IGNORECASE)
                    if not match:
                        continue
                    prefix = label_cell[:match.start()]
                    qualifiers = re.findall(r"[\wÀ-ỹ]+", prefix.casefold())
                    if all(word in ROW_QUALIFIERS for word in qualifiers):
                        suffix = label_cell[match.end():]
                        suffix = re.sub(r"\([^)]*\)", " ", suffix)
                        suffix = re.sub(r"\b(?:V|VI)\.?\d+(?:\.\d+)*\b", " ", suffix, flags=re.IGNORECASE)
                        suffix = re.sub(r"\b\d{1,3}\b", " ", suffix)
                        suffix_words = re.findall(r"[\wÀ-ỹ]+", suffix.casefold())
                        if not suffix_words:
                            matched.add(key)
            if len(matched) != 1:
                continue
            key = next(iter(matched))
            if key in seen:
                continue
            formula_context = " ".join(cells[:3])
            formula = re.search(r"\(([^)]*=[^)]*)\)", formula_context)
            formula_codes = set(re.findall(r"\d+", formula.group(1))) if formula else set()
            values = []
            for index, cell in enumerate(cells[1:], start=1):
                if "=" in cell:
                    continue
                for number in NUMBER.findall(cell):
                    plain_number = number.strip("()")
                    digits = re.sub(r"\D", "", plain_number)
                    if key != "employees" and digits and len(digits) <= 3:
                        continue
                    if plain_number in formula_codes:
                        continue
                    if plain_number.isdigit() and len(plain_number) <= 3 and (
                        re.fullmatch(r"(?:V|VI)\.?\d+(?:\.\d+)*", cell, re.IGNORECASE)
                        or re.search(rf"\b{re.escape(plain_number)}\s+(?:V|VI)\.?\d", cell, re.IGNORECASE)
                        or (index + 1 < len(cells) and re.fullmatch(
                            r"(?:V|VI)\.?\d+(?:\.\d+)*", cells[index + 1], re.IGNORECASE
                        ))
                    ):
                        continue
                    values.append(number)
            if values:
                add_candidate(key, int(page_number), values, " | ".join(cells)[:500])

    page_texts = {}
    for page in pages:
        page_number = page.get("metadata", {}).get("page_number")
        if page_number:
            page_texts.setdefault(int(page_number), []).append(page.get("text", ""))

    for page_number, page_chunks in sorted(page_texts.items()):
        text = " ".join(page_chunks)
        for key in METRICS:
            if key in seen:
                continue
            matches = []
            matches.extend((start, end) for start, end, _, matched_key in _label_matches(text)
                           if matched_key == key)
            for start, end in sorted(matches):
                value_window = text[end:end + MAX_VALUE_DISTANCE]
                formula = re.search(r"\(([^)]*=[^)]*)\)", value_window)
                formula_codes = set(re.findall(r"\d+", formula.group(1))) if formula else set()
                number = None
                for candidate_number in NUMBER.finditer(value_window):
                    value = candidate_number.group()
                    digits = re.sub(r"\D", "", value.strip("()"))
                    if key != "employees" and digits and len(digits) <= 3:
                        continue
                    if value.strip("()") in formula_codes:
                        continue
                    if value.isdigit() and 1900 <= int(value) <= 2100:
                        continue
                    if value.isdigit() and int(value) == page_number:
                        continue
                    if value.isdigit() and len(value) <= 3 and re.match(
                        r"\s*(?:V|VI)\.?\d", value_window[candidate_number.end():], re.IGNORECASE
                    ):
                        continue
                    if re.match(r"\s*(?:years?|năm)\b", value_window[candidate_number.end():], re.IGNORECASE):
                        continue
                    if value_window[candidate_number.end():].lstrip().startswith("%"):
                        continue
                    between = value_window[:candidate_number.start()]
                    between = re.sub(r"\([^)]*=[^)]*\)", " ", between)
                    between = re.sub(r"\b(?:V|VI)\.?\d+(?:\.\d+)*\b", " ", between, flags=re.IGNORECASE)
                    between = re.sub(r"\b\d{1,3}\b", " ", between)
                    words = re.findall(r"[\wÀ-ỹ]+", between.casefold())
                    if all(word in VALUE_CONNECTORS for word in words):
                        prior_numbers = list(NUMBER.finditer(text[:start]))
                        context_start = prior_numbers[-1].end() if prior_numbers else max(0, start - 80)
                        preceding = text[max(context_start, start - 80):start]
                        context = preceding.casefold()
                        if (
                            "/" in preceding
                            or "%" in preceding
                            or any(term in context for term in (
                                "vòng quay", "inventory turnover", "change in", "merchandise",
                                "raw material", "finished goods", "allowance for", "margin",
                                "xuất khẩu", "export",
                            ))
                        ):
                            continue
                        number = candidate_number
                        break
                if not number:
                    continue
                value = number.group()
                quote_start = max(0, start - 80)
                quote_end = min(len(text), end + number.end() + 100)
                quote = " ".join(text[quote_start:quote_end].split())[:500]
                # A label and nearby number are evidence only; comparative years,
                # table-column alignment, sign, and units still need admin review.
                add_candidate(key, page_number, [value], quote)
                break
    return found
