#!/usr/bin/env python3
"""Download the official public reports listed in the Vietnam corpus manifest."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from scripts.ingestion.source_downloaders.registry import get_downloader, source_extension  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output", type=Path, default=Path("data/raw/vietnam_enterprises")
    )
    parser.add_argument("--force", action="store_true")
    parser.add_argument(
        "--ids", nargs="+", help="Download only these manifest document IDs"
    )
    args = parser.parse_args()

    manifest_path = REPO_ROOT / "data/vietnam_enterprises/manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    documents = manifest["documents"] if isinstance(manifest, dict) else manifest
    if args.ids:
        by_id = {document["document_id"]: document for document in documents}
        unknown = sorted(set(args.ids) - by_id.keys())
        if unknown:
            parser.error(f"unknown document IDs: {', '.join(unknown)}")
        documents = [by_id[document_id] for document_id in args.ids]
    failures = 0
    for document in documents:
        destination = args.output / document["ticker"].lower() / (
            document["document_id"].lower() + source_extension(document)
        )
        try:
            status = get_downloader(document).download(
                document["source_url"], destination, force=args.force
            )
        except Exception as error:
            failures += 1
            print(f"failed     {document['document_id']}: {error}", file=sys.stderr)
            continue
        print(f"{status:10} {document['document_id']} -> {destination}")

    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
