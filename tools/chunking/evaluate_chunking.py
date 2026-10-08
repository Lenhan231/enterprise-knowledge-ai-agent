#!/usr/bin/env python3
"""Compare fixed and sentence-aware boundaries on one source PDF, without writes."""

from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path

import fitz

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

from core.document_processing.processors.text_processor import split_ranges  # noqa: E402


def summarize(texts: list[str]) -> dict:
    lengths = [len(text) for text in texts]
    boundaries = [text.rstrip()[-1:] for text in texts[:-1] if text.rstrip()]
    return {
        "chunk_count": len(texts),
        "mean_chars": round(statistics.mean(lengths), 1) if lengths else 0,
        "p95_chars": sorted(lengths)[max(0, int(len(lengths) * 0.95) - 1)] if lengths else 0,
        "max_chars": max(lengths, default=0),
        "sentence_boundary_fraction": round(
            sum(char in ".!?。！？" for char in boundaries) / len(boundaries), 4
        ) if boundaries else None,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdf", type=Path)
    parser.add_argument("--document-id", required=True)
    parser.add_argument("--chunk-size", type=int, default=1100)
    parser.add_argument("--overlap", type=int, default=120)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.chunk_size <= 0 or args.overlap < 0 or args.overlap >= args.chunk_size:
        parser.error("chunk-size must be positive and overlap smaller than chunk-size")
    if not args.pdf.is_file():
        parser.error(f"PDF not found: {args.pdf}")

    page_texts = []
    with fitz.open(args.pdf) as pdf:
        for page_number, page in enumerate(pdf, start=1):
            text = " ".join(page.get_text("text").split())
            if text:
                page_texts.append((page_number, text))

    strategies = {}
    for strategy in ("fixed", "sentence"):
        chunks = []
        page_summaries = []
        for page_number, text in page_texts:
            page_chunks = [text[start:end].strip() for start, end in split_ranges(
                text, size=args.chunk_size,
                overlap=args.overlap if strategy == "fixed" else 0,
                strategy=strategy,
            )]
            chunks.extend(page_chunks)
            page_summaries.append({"page_number": page_number, **summarize(page_chunks)})
        strategies[strategy] = {
            **summarize(chunks),
            "pages": page_summaries,
        }

    payload = args.pdf.read_bytes()
    report = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "document_id": args.document_id,
        "pdf": str(args.pdf),
        "pdf_sha256": hashlib.sha256(payload).hexdigest(),
        "page_count": len(page_texts),
        "chunk_size_chars": args.chunk_size,
        "fixed_overlap_chars": args.overlap,
        "reference": "PyMuPDF native text on born-digital PDF pages",
        "limitations": "Boundary/size diagnostic only. It does not run OCR, embeddings, retrieval, QA, or represent PDF parser metadata. Rerun the same queries on both persisted chunk sets before choosing a strategy.",
        "strategies": strategies,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        key: {name: value[name] for name in (
            "chunk_count", "mean_chars", "p95_chars", "max_chars", "sentence_boundary_fraction"
        )}
        for key, value in strategies.items()
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
