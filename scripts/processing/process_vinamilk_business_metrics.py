#!/usr/bin/env python3
"""Extract review-only operational/product metrics from Vinamilk source pages."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from core.analytics.business_metric_extraction import extract_business_metric_candidates  # noqa: E402
from core.analytics.business_metric_catalog import BUSINESS_DECISION_PROFILES  # noqa: E402


def process_business_source(document_id: str, document: dict, path: Path) -> tuple[dict, str]:
    """Run the stable parser configuration used by business-metric extraction."""
    import hashlib

    from core.document_processing.processors.document_processor import DocumentProcessor

    content = path.read_bytes()
    source_sha256 = hashlib.sha256(content).hexdigest()
    processed = DocumentProcessor({
        "chunking_strategy": "sentence",
        "chunk_size": 1100,
        "chunk_overlap": 0,
        "extract_tables": True,
        "paddle_layout": os.getenv("DOCUMENT_PADDLE_LAYOUT", "false").strip().lower() == "true",
        "paddle_formula_recognition": os.getenv(
            "DOCUMENT_PADDLE_FORMULA_RECOGNITION", "false",
        ).strip().lower() == "true",
        "vision_captioning": os.getenv("DOCUMENT_VISION_CAPTIONS", "false").strip().lower() == "true",
        "tesseract_psm": 11,
        "tesseract_table_psm": 3,
        "ocr_render_scale": 1.5,
        "ocr_table_render_scale": 2.5,
    }).process(path.name, content, {
        "document_id": document_id,
        "company": document["company"],
        "source_type": "public_report",
        "source_sha256": source_sha256,
        "source_url": document.get("official_url") or document.get("source_url"),
        "domain": document.get("domain"),
        "document_type": document.get("document_type"),
        "fiscal_year": document.get("fiscal_year"),
        "allowed_roles": document.get("rbac", {}).get("allowed_roles", []),
    })
    return processed, source_sha256

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ids", nargs="+", required=True, help="Manifest report IDs")
    parser.add_argument("--decision-domain", choices=sorted(BUSINESS_DECISION_PROFILES), required=True,
                        help="Restrict extraction to one curated business decision profile")
    parser.add_argument("--metric", help="Optionally target one primary metric in the selected domain")
    parser.add_argument("--save-candidates", action="store_true")
    parser.add_argument("--max-chunks", "--max-pages", dest="max_chunks", type=int, default=10,
                        help="Maximum parser-produced table chunks passed to the LLM (legacy alias: --max-pages)")
    args = parser.parse_args()
    if args.metric and args.metric not in BUSINESS_DECISION_PROFILES[args.decision_domain]["primary_metrics"]:
        parser.error(f"Metric {args.metric!r} is not primary in {args.decision_domain!r}")
    manifest = json.loads((ROOT / "data/vietnam_enterprises/manifest.json").read_text())
    documents = {row["document_id"]: row for row in manifest["documents"]}
    unknown = set(args.ids) - documents.keys()
    if unknown:
        parser.error(f"Unknown document IDs: {', '.join(sorted(unknown))}")
    rows = []
    for document_id in args.ids:
        document = documents[document_id]
        path = ROOT / "data/raw/vietnam_enterprises" / document["ticker"].lower() / f"{document_id.lower()}.pdf"
        if not path.is_file():
            parser.error(f"Missing source PDF: {path}")
        processed, _ = process_business_source(document_id, document, path)
        from core.llm.groq_provider import GroqProvider

        extractor = GroqProvider()
        try:
            candidates, selected_chunks = extract_business_metric_candidates(
                processed["chunks"], processed.get("tables", []),
                {**document, "source_url": document.get("official_url") or document.get("source_url"),
                 "business_decision_domain": args.decision_domain,
                 "rbac": document.get("rbac", {"allowed_roles": ["executive", "admin"]})},
                extractor, max_chunks=args.max_chunks,
                metric_names=[args.metric] if args.metric else None,
            )
        finally:
            extractor.close()
        rows.extend(candidates)
        parsed_chunks = ", ".join(
            f"p{page['page_number']}/c{','.join(str(chunk['chunk_index']) for chunk in page['chunks'])}"
            for page in selected_chunks
        ) or "none"
        audit = "; ".join(
            f"p{page['page_number']}: returned={page.get('llm_metrics_returned', 0)}, "
            f"accepted={page.get('llm_metrics_accepted', 0)}, "
            f"rejected={page.get('validation_rejections', {})}"
            for page in selected_chunks
        ) or "no pages evaluated"
        print(
            f"{document_id} [{args.decision_domain}/{args.metric or 'all primary metrics'}]: "
            f"selected {parsed_chunks}; candidates={len(candidates)}; {audit}",
            file=sys.stderr,
        )
    print(json.dumps(rows, ensure_ascii=False, indent=2))
    if args.save_candidates and rows:
        from core.database.document_repository import DocumentRepository

        repository = DocumentRepository()
        try:
            saved = repository.save_business_metric_candidates(rows)
        finally:
            repository.close()
        print(f"Saved {saved} observations as needs_review; no reviewed rows were changed.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
