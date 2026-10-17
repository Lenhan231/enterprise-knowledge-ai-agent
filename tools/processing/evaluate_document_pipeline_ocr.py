"""Score document pipeline OCR outputs against the assistant-adjudicated crop set."""

from __future__ import annotations

import argparse
import csv
import json
import statistics
from pathlib import Path

from rapidfuzz.distance import Levenshtein

from evaluate_document_pipeline_pilot import load_page_text, normalize_text

ROOT = Path(__file__).resolve().parents[2]
DATASET = ROOT / "artifacts/evaluation/document-pipelines/ocr/reference"
RESULTS = ROOT / "artifacts/evaluation/document-pipelines/results/ocr-500-crops-v1"


def score_text(reference: str, hypothesis: str) -> dict:
    ref = normalize_text(reference)
    hyp = normalize_text(hypothesis)
    ref_words, hyp_words = ref.split(), hyp.split()
    return {
        "reference_characters": len(ref),
        "reference_words": len(ref_words),
        "cer": Levenshtein.distance(ref, hyp) / len(ref) if ref else None,
        "wer": Levenshtein.distance(ref_words, hyp_words) / len(ref_words) if ref_words else None,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--references", type=Path, default=DATASET / "reference.csv")
    parser.add_argument("--pp-root", type=Path, default=RESULTS / "pp-structurev3/ocr-500-crops-v1")
    parser.add_argument("--mineru-root", type=Path, default=RESULTS / "mineru-basic/ocr-500-crops-v1")
    parser.add_argument("--docling-root", type=Path, default=RESULTS / "docling/ocr-500-crops-v1")
    parser.add_argument("--output", type=Path, default=RESULTS / "ocr-comparison.json")
    parser.add_argument("--include-locked-test", action="store_true", help="Score the locked test split only after configurations are frozen")
    args = parser.parse_args()

    roots = {
        "pp-structurev3": args.pp_root,
        "mineru-basic": args.mineru_root,
        "docling": args.docling_root,
    }
    rows: list[dict] = []
    with args.references.open(encoding="utf-8-sig", newline="") as file:
        for reference in csv.DictReader(file):
            if reference.get("split") == "locked_test" and not args.include_locked_test:
                continue
            sample_id = reference["sample_id"]
            expected = reference["corrected_transcript"]
            row = {
                "sample_id": sample_id,
                "document_id": reference.get("document_id"),
                "issuer": reference.get("issuer"),
                "split": reference.get("split"),
                "reference_characters": len(expected),
                "reference_provenance": reference.get("reference_provenance"),
                "engines": {},
            }
            for engine, root in roots.items():
                actual, output_metadata = load_page_text(engine, sample_id, root)
                metrics = score_text(expected, actual)
                found = (
                    output_metadata.get("raw_files", 0) > 0
                    if engine == "pp-structurev3"
                    else output_metadata.get("raw_markdown", False)
                    if engine == "docling"
                    else output_metadata.get("archives", 0) > 0
                )
                if not found:
                    metrics = {
                        "reference_characters": len(expected),
                        "reference_words": len(expected.split()),
                        "cer": None,
                        "wer": None,
                    }
                row["engines"][engine] = {**metrics, "hypothesis_characters": len(actual), "output_found": found, **output_metadata}
            rows.append(row)

    def summarize(engine: str, selected_rows: list[dict]) -> dict:
        available = [row["engines"][engine] for row in selected_rows if row["engines"][engine]["cer"] is not None]
        return {
            "sample_count": len(selected_rows),
            "outputs_found": sum(row["engines"][engine]["output_found"] for row in selected_rows),
            "micro_cer": sum(value["cer"] * value["reference_characters"] for value in available) / sum(value["reference_characters"] for value in available) if available else None,
            "macro_cer": statistics.mean(value["cer"] for value in available) if available else None,
            "macro_wer": statistics.mean(value["wer"] for value in available) if available else None,
            "micro_wer": sum(value["wer"] * value["reference_words"] for value in available) / sum(value["reference_words"] for value in available) if available else None,
            "reference_characters_scored": sum(value["reference_characters"] for value in available),
        }

    summary = {}
    for engine in roots:
        summary[engine] = summarize(engine, rows)
        summary[engine]["by_split"] = {
            split: summarize(engine, [row for row in rows if row["split"] == split])
            for split in sorted({row["split"] for row in rows if row["split"]})
        }

    report = {
        "status": "official_ocr_track_results" if all(v["outputs_found"] == len(rows) for v in summary.values()) else "incomplete_run",
        "dataset_id": "vietnam-enterprise-ocr-500-crops-v1",
        "adjudication": "Assistant-adjudicated under owner instruction; not human-reviewed.",
        "split_scored": "all" if args.include_locked_test else "development_and_validation_only",
        "scoring": "NFC, casefold, whitespace-collapse; Vietnamese diacritics and punctuation retained. Micro CER/WER use total edit distance divided by reference characters/words; macro CER/WER average per-crop rates.",
        "results": summary,
        "items": rows,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "results": summary, "output": str(args.output)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
