#!/usr/bin/env python3
"""Measure cold/warm parser runs and fingerprint extracted text and table cells.

Run with PYTHONPATH=src and the same file/config on each revision being compared.
"""
import argparse
import hashlib
import json
import time
from pathlib import Path

from document_processing.document_processor import DocumentProcessor


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--repeats", type=int, default=2)
    parser.add_argument("--config", default='{"docling_ocr_engine":"vietocr"}')
    args = parser.parse_args()
    if args.repeats < 1:
        parser.error("--repeats must be positive")
    config = json.loads(args.config)
    content = args.source.read_bytes()
    processor = DocumentProcessor(config)
    report = {"source_sha256": hashlib.sha256(content).hexdigest(), "config": config, "runs": []}
    for index in range(args.repeats):
        started = time.perf_counter()
        result = processor.process(args.source.name, content, {})
        elapsed = time.perf_counter() - started
        # Exclude generated IDs and geometry so the check focuses on content.
        semantic = {
            "texts": [element.get("text", "") for element in result.get("elements", [])],
            "tables": [{"columns": table.get("columns"), "rows": table.get("rows")}
                       for table in result.get("tables", [])],
        }
        digest = hashlib.sha256(json.dumps(semantic, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        row = {"run": index, "seconds": elapsed, "content_sha256": digest,
               "elements": len(semantic["texts"]), "tables": len(semantic["tables"])}
        report["runs"].append(row)
        args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(row), flush=True)


if __name__ == "__main__":
    main()
