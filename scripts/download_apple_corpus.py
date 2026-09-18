#!/usr/bin/env python3
"""Download selected Apple documents from the committed XLSX manifest."""

from __future__ import annotations

import argparse
import re
import shutil
import sys
import tempfile
import urllib.request
from pathlib import Path
from xml.etree import ElementTree as ET
from zipfile import ZipFile


DEFAULT_IDS = (
    "APL-CMP-001",
    "APL-CMP-003",
    "APL-CMP-004",
    "APL-PRC-001",
    "APL-SUP-001",
)

# The manifest intentionally records landing pages for documents whose direct
# URLs can move. Pin the resolved English PDF used by this vertical slice.
RESOLVED_URLS = {
    "APL-SUP-001": (
        "https://www.supplychainreports.apple/"
        "Supplier-Code-of-Conduct-and-Supplier-Responsibility-Standards"
    ),
}

DOMAIN_DIRS = {
    "Compliance": "compliance",
    "Procurement": "procurement",
    "Finance": "finance",
    "Supply Chain": "supply_chain",
    "Environment": "environment",
}

XML_NS = {
    "m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
}


def _cell_text(cell: ET.Element, shared: list[str]) -> str:
    cell_type = cell.attrib.get("t")
    if cell_type == "inlineStr":
        return "".join(
            node.text or ""
            for node in cell.iter(f"{{{XML_NS['m']}}}t")
        )
    value = cell.find("m:v", XML_NS)
    if value is None or value.text is None:
        return ""
    return shared[int(value.text)] if cell_type == "s" else value.text


def read_manifest(path: Path) -> list[dict[str, str]]:
    """Read the Manifest sheet without adding a spreadsheet dependency."""
    with ZipFile(path) as archive:
        shared: list[str] = []
        if "xl/sharedStrings.xml" in archive.namelist():
            root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
            for item in root.findall("m:si", XML_NS):
                shared.append(
                    "".join(
                        node.text or ""
                        for node in item.iter(f"{{{XML_NS['m']}}}t")
                    )
                )

        workbook = ET.fromstring(archive.read("xl/workbook.xml"))
        relationships = ET.fromstring(
            archive.read("xl/_rels/workbook.xml.rels")
        )
        targets = {
            relationship.attrib["Id"]: relationship.attrib["Target"]
            for relationship in relationships
        }
        sheets = workbook.find("m:sheets", XML_NS)
        if sheets is None:
            raise ValueError("Workbook has no sheets")
        sheet = next(
            item
            for item in sheets
            if item.attrib["name"] == "Manifest"
        )
        relationship_id = sheet.attrib[f"{{{XML_NS['r']}}}id"]
        target = targets[relationship_id].lstrip("/")
        if not target.startswith("xl/"):
            target = f"xl/{target}"
        worksheet = ET.fromstring(archive.read(target))

        rows: list[list[str]] = []
        for row in worksheet.findall(".//m:sheetData/m:row", XML_NS):
            values_by_column: dict[int, str] = {}
            for cell in row.findall("m:c", XML_NS):
                reference = cell.attrib["r"]
                letters = re.match(r"[A-Z]+", reference)
                if letters is None:
                    continue
                column = 0
                for letter in letters.group(0):
                    column = column * 26 + ord(letter) - ord("A") + 1
                values_by_column[column - 1] = _cell_text(cell, shared)
            if values_by_column:
                width = max(values_by_column) + 1
                rows.append([values_by_column.get(i, "") for i in range(width)])

    headers = rows[0]
    return [dict(zip(headers, row, strict=False)) for row in rows[1:]]


def safe_filename(document: dict[str, str]) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", document["title"].lower()).strip("_")
    return f"{document['document_id'].lower()}_{slug}.pdf"


def download(url: str, destination: Path, force: bool = False) -> str:
    if destination.exists() and not force:
        return "exists"
    destination.parent.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(url, headers={"User-Agent": "AppleCorpusDownloader/1.0"})
    with urllib.request.urlopen(request, timeout=90) as response, tempfile.NamedTemporaryFile(
        dir=destination.parent, delete=False
    ) as temporary:
        shutil.copyfileobj(response, temporary)
        temporary_path = Path(temporary.name)
    try:
        if temporary_path.read_bytes()[:5] != b"%PDF-":
            raise ValueError(f"Downloaded content is not a PDF: {url}")
        temporary_path.replace(destination)
    finally:
        temporary_path.unlink(missing_ok=True)
    return "downloaded"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path("src/data/Apple/FA26AI69_Apple_Corpus_Manifest_v1.xlsx"),
    )
    parser.add_argument("--output", type=Path, default=Path("data/raw/apple"))
    parser.add_argument("--ids", nargs="+", default=list(DEFAULT_IDS))
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    documents = {row["document_id"]: row for row in read_manifest(args.manifest)}
    missing = [document_id for document_id in args.ids if document_id not in documents]
    if missing:
        print(f"Unknown document IDs: {', '.join(missing)}", file=sys.stderr)
        return 2

    for document_id in args.ids:
        document = documents[document_id]
        domain = DOMAIN_DIRS[document["domain"]]
        destination = args.output / domain / safe_filename(document)
        url = RESOLVED_URLS.get(document_id, document["official_url"])
        status = download(url, destination, args.force)
        print(f"{status:10} {document_id} -> {destination}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
