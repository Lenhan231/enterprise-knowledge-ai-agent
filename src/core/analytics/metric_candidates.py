"""Extract source-located financial metric candidates for admin review."""

from __future__ import annotations

import hashlib
import math
import re

from core.analytics.metric_ontology import METRIC_ONTOLOGY

NUMBER = re.compile(r"(?<![\w.])(?:\(?\d[\d,.]*\)?)(?!\w)")
PERIOD_HEADER = re.compile(
    r"\b(20\d{2})\s+(?:(?:triệu|tỷ)\s+)?(?:vnd|đồng)\s+"
    r"(20\d{2})\s+(?:(?:triệu|tỷ)\s+)?(?:vnd|đồng)\b",
    re.IGNORECASE,
)
MAX_VALUE_DISTANCE = 80
VALUE_CONNECTORS = {"năm"}
ROW_QUALIFIERS = {"net", "consolidated", "total", "current", "gross"}
NON_VALUE_ROW_TERMS = {"ratio", "margin", "turnover", "per share", "percentage", "%"}
SEGMENT_SCOPE_TERMS = (
    "thị trường nội địa", "thị trường nước ngoài", "domestic market", "overseas market",
    "export market", "xuất khẩu",
)
UNIT_HINTS = (
    ("million VND", re.compile(r"(?:million\s+vnd|vnd\s+million)", re.IGNORECASE)),
    ("billion VND", re.compile(r"(?:billion\s+vnd|vnd\s+billion)", re.IGNORECASE)),
    ("triệu VND", re.compile(r"(?:triệu\s+(?:vnd|đồng)|(?:vnd|đồng)\s+triệu)", re.IGNORECASE)),
    ("tỷ đồng", re.compile(r"(?:tỷ\s+đồng|đồng\s+tỷ)", re.IGNORECASE)),
    ("VND", re.compile(r"\bvnd\b", re.IGNORECASE)),
)
METRICS = {name: definition["source_labels"] for name, definition in METRIC_ONTOLOGY.items()}


def _label_matches(text: str) -> list[tuple[int, int, str, str]]:
    matches = []
    for key, labels in METRICS.items():
        for label in labels:
            label_pattern = r"\s+".join(re.escape(part) for part in label.split())
            matches.extend(
                (match.start(), match.end(), label, key)
                for match in re.finditer(rf"(?<!\w){label_pattern}(?!\w)", text, re.IGNORECASE)
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


def _unit_hint(text: str) -> str | None:
    for unit, pattern in UNIT_HINTS[:-1]:
        if pattern.search(text):
            return unit
    if re.search(r"\bbillion\b", text, re.IGNORECASE) and re.search(r"\bvnd\b", text, re.IGNORECASE):
        return "billion VND"
    if re.search(r"\bmillion\b", text, re.IGNORECASE) and re.search(r"\bvnd\b", text, re.IGNORECASE):
        return "million VND"
    if UNIT_HINTS[-1][1].search(text):
        return UNIT_HINTS[-1][0]
    return None


def candidates(
    pages: list[dict],
    document: dict,
    tables: list[dict] | None = None,
    visual_pages: list[dict] | None = None,
    text_evidence_page_numbers: set[int] | None = None,
) -> list[dict]:
    """Find source-located metric evidence; leave figure/year interpretation for review."""
    found = []
    seen = set()
    page_texts = {}
    page_table_units = {}
    for page in pages:
        if page.get("metadata", {}).get("is_model_generated"):
            continue
        page_number = page.get("metadata", {}).get("page_number")
        if page_number:
            page_texts.setdefault(int(page_number), []).append(page.get("text", ""))
    for page in visual_pages or []:
        page_number = page.get("page_number")
        if page_number:
            page_texts.setdefault(int(page_number), []).append(" ".join(
                str(span.get("text", "")) for span in page.get("spans", [])
            ))
    for table in tables or []:
        page_number = table.get("page_number")
        if page_number:
            values = [str(value or "") for value in table.get("columns", [])]
            table_unit = _unit_hint(" ".join(values))
            if table_unit:
                page_table_units[int(page_number)] = table_unit
            for row in table.get("rows", []):
                values.extend(str(value or "") for value in row.values())
            page_texts.setdefault(int(page_number), []).append(" ".join(values))
    page_units = {}
    fiscal_year = str(document.get("fiscal_year") or "")
    page_period_years = {}
    for page_number, texts in page_texts.items():
        page_text = " ".join(texts)
        table_unit = page_table_units.get(page_number)
        page_unit = _unit_hint(page_text)
        for match in PERIOD_HEADER.finditer(page_text):
            years = [match.group(1), match.group(2)]
            if fiscal_year in years:
                page_period_years[page_number] = years
                break
        # A bare VND table header often sits beside an explicit billion/million
        # scale in the report summary; preserve the scale when the table lacks it.
        page_units[page_number] = (
            page_unit if page_number <= 25 and table_unit in {None, "VND"}
            and page_unit not in {None, "VND"}
            else page_unit if table_unit == "VND" and page_unit not in {None, "VND"}
            else table_unit or page_unit
        )

    def add_candidate(key: str, page_number: int, values: list[str], quote: str) -> None:
        found.append({
            "company": document["company"],
            "fiscal_year": int(document["fiscal_year"]),
            "metric_name": key,
            "metric_label": METRIC_ONTOLOGY[key]["label"],
            "candidate_values": values,
            "unit": page_units.get(page_number),
            "document_id": document["document_id"],
            "page_number": page_number,
            "source_quote": quote,
            "source_quote_hash": hashlib.sha256(quote.encode()).hexdigest(),
            "source_url": document["official_url"],
            "allowed_roles": document["rbac"]["allowed_roles"],
            "status": "needs_review",
            "extraction_method": "rule_based_page_evidence",
            "extractor_model": None,
            "prompt_version": None,
            "selection_evidence": {},
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
            if len(text.split()) > 8:
                continue
            if re.search(
                r"\b(?:reached|reach|grew|growth|increased|increase|declined|decreased|margin|while|compared|brought)\b|"
                r"tăng trưởng|đạt mức|so với cùng kỳ",
                text, re.IGNORECASE,
            ):
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
            row_items = [(str(key), str(value or "").strip()) for key, value in row.items()]
            cells = [value for _, value in row_items]
            if len(cells) < 2:
                continue
            label_cell = cells[0]
            folded_label = label_cell.casefold()
            if "/" in label_cell or any(term in folded_label for term in NON_VALUE_ROW_TERMS):
                continue
            matched = set()
            for start, end, _, key in _label_matches(label_cell):
                prefix = label_cell[:start]
                qualifiers = re.findall(r"[\wÀ-ỹ]+", prefix.casefold())
                if all(word in ROW_QUALIFIERS for word in qualifiers):
                    suffix = label_cell[end:]
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
            fiscal_year_values = []
            for index, (column, cell) in enumerate(row_items[1:], start=1):
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
                    if fiscal_year and re.search(rf"(?<!\d){re.escape(fiscal_year)}(?!\d)", column):
                        fiscal_year_values.append(number)
            if values:
                period_years = page_period_years.get(int(page_number), [])
                if not fiscal_year_values and fiscal_year in period_years and len(values) >= len(period_years):
                    fiscal_year_values = [values[period_years.index(fiscal_year)]]
                    quote_items = [
                        f"{column}: {value}" for column, value in row_items
                        if not NUMBER.fullmatch(column.strip())
                    ]
                    quote_items.extend(
                        f"{year}: {value}" for year, value in zip(period_years, values)
                    )
                    quote = " | ".join(quote_items)
                else:
                    quote = " | ".join(f"{column}: {value}" for column, value in row_items)
                add_candidate(
                    key,
                    int(page_number),
                    fiscal_year_values or values,
                    quote[:500],
                )

    for page_number, page_chunks in sorted(page_texts.items()):
        if text_evidence_page_numbers is not None and page_number not in text_evidence_page_numbers:
            continue
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
                            or any(term in text[max(0, start - 500):start].casefold()
                                   for term in SEGMENT_SCOPE_TERMS)
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
