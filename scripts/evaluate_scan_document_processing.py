#!/usr/bin/env python3
"""Score real image-only PDF scan regions through the upload document processor."""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import fitz

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from core.document_processing.processors.document_processor import DocumentProcessor  # noqa: E402
from evaluate_ocr import edit_distance, error_rate, normalize, peak_memory_mb  # noqa: E402


def crop_pdf_page(source_pdf: bytes, page_number: int, clip_rect: list[float]) -> bytes:
    """Copy one source page and crop it without re-rendering its scan image."""
    source = fitz.open(stream=source_pdf, filetype="pdf")
    cropped = fitz.open()
    try:
        if page_number < 1 or page_number > len(source):
            raise ValueError(f"Page {page_number} is outside the source PDF")
        cropped.insert_pdf(source, from_page=page_number - 1, to_page=page_number - 1)
        page = cropped[0]
        crop_box = fitz.Rect(clip_rect) * page.derotation_matrix
        if not page.mediabox.contains(crop_box):
            raise ValueError(f"Clip {clip_rect} maps outside the source page MediaBox")
        page.set_cropbox(crop_box)
        return cropped.tobytes(no_new_id=True)
    finally:
        cropped.close()
        source.close()


def evaluate_region(spec: dict, source_pdf: bytes, tesseract_psm: int = 11, render_scale: float = 1.5) -> dict:
    cropped_pdf = crop_pdf_page(source_pdf, spec["page"], spec["clip_rect"])
    started = time.perf_counter()
    parsed = DocumentProcessor({
        "tesseract_psm": tesseract_psm,
        "ocr_render_scale": render_scale,
    }).process(
        Path(spec["file"]).name,
        cropped_pdf,
        {"document_id": spec["document_id"]},
    )
    elapsed = time.perf_counter() - started
    chunks = sorted(parsed["chunks"], key=lambda item: item["metadata"]["chunk_index"])
    extracted_text = "\n".join(chunk["text"] for chunk in chunks)
    reference = normalize(spec["reference_text"])
    hypothesis = normalize(extracted_text)
    reference_words = reference.split()
    hypothesis_words = hypothesis.split()
    methods = sorted({chunk["metadata"].get("text_extraction_method", "unknown") for chunk in chunks})
    return {
        "id": spec["id"],
        "document_id": spec["document_id"],
        "source_page_number": spec["page"],
        "language": spec["language"],
        "layout_type": spec.get("layout_type"),
        "physical_scan": bool(spec.get("physical_scan")),
        "source_pdf_sha256": hashlib.sha256(source_pdf).hexdigest(),
        "cropped_pdf_sha256": hashlib.sha256(cropped_pdf).hexdigest(),
        "text_extraction_methods": methods,
        "tesseract_page_segmentation_mode": tesseract_psm,
        "ocr_render_scale": render_scale,
        "ocr_used": any("tesseract" in method for method in methods),
        "chunk_count": len(chunks),
        "table_count": len(parsed["tables"]),
        "reference_characters": len(reference),
        "reference_words": len(reference_words),
        "hypothesis_characters": len(hypothesis),
        "character_edit_distance": edit_distance(reference, hypothesis),
        "word_edit_distance": edit_distance(reference_words, hypothesis_words),
        "cer": round(error_rate(reference, hypothesis), 6),
        "wer": round(error_rate(reference_words, hypothesis_words), 6),
        "latency_seconds": round(elapsed, 3),
        "pages_per_minute": round(60 / elapsed, 3) if elapsed else None,
        "extracted_text": extracted_text,
    }


def select_cases(pages: list[dict], case_ids: list[str]) -> list[dict]:
    if not case_ids:
        return [page for page in pages if page.get("physical_scan")]
    by_id = {page["id"]: page for page in pages}
    missing = sorted(set(case_ids) - by_id.keys())
    if missing:
        raise ValueError(f"Unknown case ID(s): {', '.join(missing)}")
    return [by_id[case_id] for case_id in dict.fromkeys(case_ids)]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dataset", type=Path,
        default=ROOT / "data/evaluation/vinamilk_ocr_ground_truth_v4.json",
    )
    parser.add_argument(
        "--output", type=Path,
        default=ROOT / "artifacts/evaluation/vinamilk-scan-document-processor-v1.json",
    )
    parser.add_argument(
        "--case-id", action="append", default=[],
        help="Evaluate this dataset case instead of the default physical scans; repeat to select multiple cases.",
    )
    parser.add_argument("--tesseract-psm", type=int, choices=(3, 6, 11, 12), default=11)
    parser.add_argument("--render-scale", type=float, choices=(1.5, 2.5), default=1.5)
    args = parser.parse_args()
    dataset_bytes = args.dataset.read_bytes()
    dataset = json.loads(dataset_bytes)
    try:
        selected_specs = select_cases(dataset["pages"], args.case_id)
    except ValueError as error:
        parser.error(str(error))
    if not selected_specs:
        parser.error("Dataset has no pages labeled physical_scan")

    results = []
    for spec in selected_specs:
        source_pdf = (ROOT / spec["file"]).read_bytes()
        result = evaluate_region(spec, source_pdf, args.tesseract_psm, args.render_scale)
        results.append(result)
        print(
            f"{result['id']}: OCR={result['ocr_used']} CER={result['cer']} "
            f"WER={result['wer']} in {result['latency_seconds']:.2f}s",
            file=sys.stderr,
            flush=True,
        )

    valid = [result for result in results if result["ocr_used"]]
    try:
        tesseract_version = subprocess.run(
            ["tesseract", "--version"], capture_output=True, check=True, text=True, timeout=10,
        ).stdout.splitlines()[0]
    except (OSError, subprocess.SubprocessError, IndexError):
        tesseract_version = None
    payload = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "dataset_id": dataset["dataset_id"],
        "dataset_sha256": hashlib.sha256(dataset_bytes).hexdigest(),
        "reference_quality": dataset["reference_quality"],
        "reference_method": dataset["reference_method"],
        "protocol": "Copy each selected manually labeled region from the original PDF page, preserving its source content; run the existing DocumentProcessor PDF upload path (PyMuPDF/Tesseract fallback), then score chunk text against the manual reference.",
        "limitations": "Production-parser OCR path only. Physical-scan status and layout type are reported per region. No table-cell or layout-structure labels, no paired OCR-engine comparison. Throughput includes parser/OCR invocation but excludes application embedding and database persistence.",
        "render_dpi": 72 * args.render_scale,
        "ocr_render_scale": args.render_scale,
        "tesseract_page_segmentation_mode": args.tesseract_psm,
        "tesseract_language": "vie+eng",
        "software": {
            "python": platform.python_version(),
            "pymupdf": fitz.VersionBind,
            "tesseract": tesseract_version,
        },
        "process_memory": peak_memory_mb(),
        "aggregate": {
            "ocr_pages": len(valid),
            "micro_cer": round(sum(x["character_edit_distance"] for x in valid) / sum(x["reference_characters"] for x in valid), 6) if valid else None,
            "micro_wer": round(sum(x["word_edit_distance"] for x in valid) / sum(x["reference_words"] for x in valid), 6) if valid else None,
            "mean_latency_seconds": round(sum(x["latency_seconds"] for x in valid) / len(valid), 3) if valid else None,
            "mean_pages_per_minute": round(sum(x["pages_per_minute"] for x in valid) / len(valid), 3) if valid else None,
        },
        "results": results,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), "aggregate": payload["aggregate"]}, ensure_ascii=False, indent=2))
    return 0 if valid else 1


if __name__ == "__main__":
    raise SystemExit(main())
