#!/usr/bin/env python3
"""Download Apple documents from a local XLSX or public Google Sheet."""

from __future__ import annotations

import argparse
import os
import re
import shutil
import sys
import tempfile
import urllib.request
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse
from xml.etree import ElementTree as ET
from zipfile import ZipFile

from dotenv import load_dotenv

from scripts.source_downloaders import download_source, source_extension


load_dotenv()


DEFAULT_IDS = (
    "APL-CMP-001",
    "APL-CMP-003",
    "APL-CMP-004",
    "APL-PRC-001",
    "APL-SUP-001",
)

DEFAULT_MANIFEST = os.getenv(
    "APPLE_CORPUS_MANIFEST_URL",
    "data/manifests/apple/FA26AI69_Apple_Corpus_Manifest_v1.xlsx",
)

# The manifest intentionally records landing pages for documents whose direct
# URLs can move. Pin the resolved English PDF used by this vertical slice.
RESOLVED_URLS = {
    "APL-ENV-001": (
        "https://www.apple.com/environment/pdf/"
        "Apple_Environmental_Progress_Report_2026.pdf"
    ),
    "APL-ENV-004": (
        "https://www.apple.com/environment/pdf/"
        "Apple_Environmental_Progress_Report_2023.pdf"
    ),
    "APL-ENV-005": (
        "https://www.apple.com/environment/pdf/"
        "Apple_Environmental_Progress_Report_2022.pdf"
    ),
    "APL-SUP-001": (
        "https://www.supplychainreports.apple/"
        "Supplier-Code-of-Conduct-and-Supplier-Responsibility-Standards"
    ),
    "APL-SUP-002": (
        "https://s203.q4cdn.com/367071867/files/doc_downloads/gov_docs/2026/"
        "Apple-Supply-Chain-2026-Progress-Report.pdf"
    ),
    "APL-SUP-003": (
        "https://s203.q4cdn.com/367071867/files/doc_downloads/"
        "PeopleandEnvironment/2025/Apple-Supply-Chain-2025-Progress-Report.pdf"
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


def google_sheets_export_url(url: str) -> str:
    """Convert a Google Sheets sharing URL to its XLSX export endpoint."""
    parsed = urlparse(url)
    if parsed.netloc not in {"docs.google.com", "www.docs.google.com"}:
        raise ValueError(f"Not a Google Sheets URL: {url}")
    match = re.search(r"/spreadsheets/d/([a-zA-Z0-9_-]+)", parsed.path)
    if match is None:
        raise ValueError(f"Could not find a spreadsheet ID in URL: {url}")

    query = parse_qs(parsed.query)
    fragment = parse_qs(parsed.fragment)
    gid = (query.get("gid") or fragment.get("gid") or [None])[0]
    parameters = {"format": "xlsx"}
    if gid:
        parameters["gid"] = gid
    return (
        f"https://docs.google.com/spreadsheets/d/{match.group(1)}/export?"
        f"{urlencode(parameters)}"
    )


def _read_xlsx_manifest(path: Path) -> list[dict[str, str]]:
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
        # Prefer the conventional name, but accept the first worksheet for
        # Google Sheets (whose default tab name is locale-dependent).
        sheet = next(
            (item for item in sheets if item.attrib["name"] == "Manifest"),
            sheets[0] if len(sheets) else None,
        )
        if sheet is None:
            raise ValueError("Workbook has no worksheets")
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


def read_manifest(source: Path | str) -> list[dict[str, str]]:
    """Read a local XLSX file or a publicly accessible Google Sheet."""
    source_text = str(source)
    if not source_text.startswith(("https://", "http://")):
        return _read_xlsx_manifest(Path(source))

    export_url = google_sheets_export_url(source_text)
    request = urllib.request.Request(
        export_url,
        headers={"User-Agent": "AppleCorpusDownloader/1.0"},
    )
    with urllib.request.urlopen(request, timeout=90) as response, tempfile.NamedTemporaryFile(
        suffix=".xlsx", delete=False
    ) as temporary:
        shutil.copyfileobj(response, temporary)
        temporary_path = Path(temporary.name)
    try:
        return _read_xlsx_manifest(temporary_path)
    finally:
        temporary_path.unlink(missing_ok=True)


def document_extension(document: dict[str, str]) -> str:
    """Choose a storage extension using the registered source downloader."""
    return source_extension(document)


def safe_filename(document: dict[str, str]) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", document["title"].lower()).strip("_")
    return f"{document['document_id'].lower()}_{slug}{document_extension(document)}"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--manifest",
        default=DEFAULT_MANIFEST,
        help="Local XLSX path or public docs.google.com/spreadsheets URL",
    )
    parser.add_argument("--output", type=Path, default=Path("data/raw/apple"))
    selection = parser.add_mutually_exclusive_group()
    selection.add_argument(
        "--ids",
        nargs="+",
        metavar="DOCUMENT_ID",
        help="Download only these document IDs (replaces the default selection)",
    )
    selection.add_argument(
        "--all",
        action="store_true",
        help="Download every document in the manifest",
    )
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    manifest_rows = read_manifest(args.manifest)
    documents = {row["document_id"]: row for row in manifest_rows}
    selected_ids = (
        list(documents)
        if args.all
        else args.ids if args.ids is not None else list(DEFAULT_IDS)
    )
    missing = [document_id for document_id in selected_ids if document_id not in documents]
    if missing:
        print(f"Unknown document IDs: {', '.join(missing)}", file=sys.stderr)
        return 2

    downloaded = 0
    existing = 0
    failures: list[tuple[str, str]] = []
    for document_id in selected_ids:
        document = documents[document_id]
        try:
            domain = DOMAIN_DIRS[document["domain"]]
            destination = args.output / domain / safe_filename(document)
            url = RESOLVED_URLS.get(document_id, document["official_url"])
            status = download_source(document, url, destination, args.force)
            downloaded += status == "downloaded"
            existing += status == "exists"
            print(f"{status:10} {document_id} -> {destination}")
        except Exception as error:
            failures.append((document_id, str(error)))
            print(f"failed     {document_id} -> {error}", file=sys.stderr)

    print(
        f"Summary: {downloaded} downloaded, {existing} existing, "
        f"{len(failures)} failed"
    )
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
