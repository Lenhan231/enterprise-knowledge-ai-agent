# scripts/download_apple_corpus.py::read_manifest

#!/usr/bin/env python3
"""Download selected Apple documents from the committed XLSX manifest."""
"""python scripts/download_apple_corpus.py \
  --output data/raw/apple_review1
USE THIS FOR REVIEW 1 DEMO  
"""

from __future__ import annotations

import argparse
import re
import shutil
import sys
import tempfile
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from core.database.document_repository import DocumentRepository  # noqa: E402

DEFAULT_IDS = (
    "APL-CMP-003",
    "APL-CMP-004",
    "APL-PRC-002",
    "APL-PRC-015",
    "APL-ENV-002",
)

def read_manifest() -> list[dict]:
    repository = DocumentRepository()
    try:
        return repository.list_documents()
    finally:
        repository.close()


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
    parser.add_argument("--output", type=Path, default=Path("data/raw/apple"))
    parser.add_argument("--ids", nargs="+", default=list(DEFAULT_IDS))
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    documents = {row["document_id"]: row for row in read_manifest()}
    missing = [document_id for document_id in args.ids if document_id not in documents]
    if missing:
        print(f"Unknown document IDs: {', '.join(missing)}", file=sys.stderr)
        return 2

    for document_id in args.ids:
        document = documents[document_id]
        domain = re.sub(r"[^a-z0-9]+", "_", document["domain"].lower()).strip("_")
        destination = args.output / domain / safe_filename(document)
        url = document["official_url"]
        status = download(url, destination, args.force)
        print(f"{status:10} {document_id} -> {destination}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())