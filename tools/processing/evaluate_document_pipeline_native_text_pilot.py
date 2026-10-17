"""Compare saved pipeline output with unreviewed native PDF text-layer candidates."""

from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path

import fitz
from rapidfuzz.distance import Levenshtein

from evaluate_document_pipeline_pilot import load_page_text, normalize_text


ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "artifacts/evaluation/document-pipelines"
DEFAULT_MANIFEST = BASE / "pilot-v1/manifest.json"
DEFAULT_RESULTS = BASE / "results"
DEFAULT_OUTPUT = BASE / "results/follow-up-metrics/digital-born-pilot-v1.json"
DEFAULT_REVIEWED_OUTPUT = BASE / "results/follow-up-metrics/digital-born-pilot-v1-reviewed.json"
ENGINE_DIRS = {
    "pp-structurev3": DEFAULT_RESULTS / "pp-structurev3/document-pipeline-pilot",
    "mineru": DEFAULT_RESULTS / "mineru-basic/document-pipeline-pilot",
    "docling": DEFAULT_RESULTS / "docling/document-pipeline-pilot",
}


def read_native_text(pdf_path: Path) -> str:
    with fitz.open(pdf_path) as document:
        if len(document) != 1:
            raise ValueError(f"Expected one-page PDF, got {len(document)}: {pdf_path}")
        return document[0].get_text("text")


def score(reference: str, hypothesis: str) -> dict:
    ref = normalize_text(reference)
    hyp = normalize_text(hypothesis)
    ref_words, hyp_words = ref.split(), hyp.split()
    return {
        "reference_characters": len(ref),
        "reference_words": len(ref_words),
        "hypothesis_characters": len(hyp),
        "hypothesis_words": len(hyp_words),
        "cer": Levenshtein.distance(ref, hyp) / len(ref) if ref else None,
        "wer": Levenshtein.distance(ref_words, hyp_words) / len(ref_words) if ref_words else None,
    }


def summarize(rows: list[dict], engine: str) -> dict:
    available = [row for row in rows if row["engines"][engine]["cer"] is not None]
    ref_chars = sum(row["reference_characters"] for row in available)
    ref_words = sum(row["reference_words"] for row in available)
    char_edits = sum(
        Levenshtein.distance(
            row["normalized_reference"],
            row["engines"][engine]["normalized_hypothesis"],
        )
        for row in available
    )
    word_edits = sum(
        Levenshtein.distance(
            row["normalized_reference"].split(),
            row["engines"][engine]["normalized_hypothesis"].split(),
        )
        for row in available
    )
    return {
        "pages_scored": len(available),
        "outputs_found": sum(row["engines"][engine]["output_found"] for row in rows),
        "empty_outputs": sum(
            row["engines"][engine]["hypothesis_characters"] == 0 for row in available
        ),
        "micro_cer": char_edits / ref_chars if ref_chars else None,
        "micro_wer": word_edits / ref_words if ref_words else None,
        "macro_cer": statistics.mean(row["engines"][engine]["cer"] for row in available) if available else None,
        "macro_wer": statistics.mean(row["engines"][engine]["wer"] for row in available) if available else None,
        "reference_characters": ref_chars,
        "reference_words": ref_words,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--results-root", type=Path, default=DEFAULT_RESULTS)
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--reviewed-reference",
        type=Path,
        help="Optional reviewed-reference JSON from the matching native-text packet.",
    )
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    if args.output:
        output_path = args.output
    elif not args.reviewed_reference:
        output_path = DEFAULT_OUTPUT
    elif manifest.get("dataset_id") == "vietnam-enterprise-native-text-pilot-v1":
        output_path = DEFAULT_REVIEWED_OUTPUT
    else:
        dataset_slug = str(manifest.get("dataset_id", "native-text"))
        output_path = DEFAULT_RESULTS / "follow-up-metrics" / f"{dataset_slug}-reviewed.json"
    reviewed_by_id = {}
    review_provenance = "reviewer_provided_unspecified"
    if args.reviewed_reference:
        review = json.loads(args.reviewed_reference.read_text(encoding="utf-8"))
        if review.get("task") != "native-text":
            raise ValueError("Review export task must be 'native-text'.")
        if review.get("dataset_id") != manifest.get("dataset_id"):
            raise ValueError("Review export dataset does not match the pilot manifest.")
        review_provenance = review.get("review_provenance", review_provenance)
        if review_provenance not in {
            "human_review",
            "assistant_visual_adjudication",
            "reviewer_provided_unspecified",
        }:
            raise ValueError(f"Unsupported review provenance: {review_provenance}")
        manifest_ids = {page["id"] for page in manifest["pages"]}
        for item in review.get("reviewed_items", []):
            if item.get("id") in reviewed_by_id:
                raise ValueError(f"Duplicate review item: {item.get('id')}")
            if item.get("id") not in manifest_ids:
                raise ValueError(f"Review item is not in the pilot manifest: {item.get('id')}")
            if not item.get("reviewed"):
                continue
            if not str(item.get("reviewer", "")).strip():
                raise ValueError(f"Reviewed item has no reviewer ID: {item.get('id')}")
            source_type = item.get("reviewed_source_type")
            if source_type not in {"born_digital", "mixed", "physical_scan", "image_only"}:
                raise ValueError(f"Invalid reviewed source type for {item.get('id')}: {source_type}")
            if source_type == "born_digital" and not str(item.get("reviewed_native_text", "")).strip():
                raise ValueError(f"Born-digital item has no reviewed transcript: {item.get('id')}")
            reviewed_by_id[item["id"]] = item

    engines = {
        name: args.results_root / path.relative_to(DEFAULT_RESULTS)
        for name, path in ENGINE_DIRS.items()
    }
    rows = []
    excluded_reviewed_pages = 0
    for page in manifest["pages"]:
        if args.reviewed_reference:
            reviewed = reviewed_by_id.get(page["id"])
            if not reviewed:
                continue
            if reviewed["reviewed_source_type"] != "born_digital":
                excluded_reviewed_pages += 1
                continue
            source_type = reviewed["reviewed_source_type"]
            source = normalize_text(reviewed["reviewed_native_text"])
            reference_source = "reviewed PDF text-layer transcript"
        else:
            if page.get("source_type") != "born_digital":
                continue
            input_path = args.manifest.parent / page["input_pdf"]
            source = normalize_text(read_native_text(input_path))
            source_type = page.get("source_type")
            reference_source = "embedded PDF text layer; not visually reviewed"
        row = {
            "page_id": page["id"],
            "document_id": page.get("document_id"),
            "source_type_label": source_type,
            "source_pdf_sha256": page.get("source_pdf_sha256"),
            "input_pdf_sha256": page.get("input_pdf_sha256"),
            "reference_source": reference_source,
            "normalized_reference": source,
            "reference_characters": len(source),
            "reference_words": len(source.split()),
            "engines": {},
        }
        if args.reviewed_reference:
            row["reviewer"] = reviewed["reviewer"]
            row["review_note"] = reviewed.get("review_note", "")
        for engine, engine_root in engines.items():
            hypothesis, metadata = load_page_text(engine, page["id"], engine_root)
            normalized_hypothesis = normalize_text(hypothesis)
            row["engines"][engine] = {
                **score(source, hypothesis),
                "output_found": not bool(metadata.get("error")),
                "output_metadata": metadata,
                "normalized_hypothesis": normalized_hypothesis,
            }
        rows.append(row)

    if not rows:
        raise ValueError("No born-digital pages with usable references were selected.")

    summaries = {engine: summarize(rows, engine) for engine in engines}
    if not args.reviewed_reference:
        result_status = "exploratory_proxy_not_human_reviewed"
    elif review_provenance == "assistant_visual_adjudication":
        result_status = "assistant_adjudicated_native_text_diagnostic"
    elif manifest.get("dataset_id") == "vietnam-enterprise-native-text-pilot-v1":
        result_status = "reviewed_native_text_pilot"
    else:
        result_status = "reviewed_native_text_candidates"
    result = {
        "status": result_status,
        "dataset_id": manifest["dataset_id"],
        "review_provenance": review_provenance,
        "sample_count": len(rows),
        "reviewed_non_born_digital_pages_excluded": excluded_reviewed_pages,
        "source_document_count": len({
            row.get("document_id") or row.get("source_file") for row in rows
        }),
        "metric_note": (
            "Micro rates use pooled edit distance divided by pooled reference "
            "characters/words; macro rates average per-page rates."
        ),
        "normalization": "NFC, casefold, collapse whitespace; strip Markdown/HTML presentation syntax; retain punctuation and Vietnamese diacritics.",
        "reference_warning": (
            "Transcript text and source type were visually inspected by an "
            "assistant; this diagnostic is not independent human review. "
            "Page-level CER/WER may still confound recognition with reading "
            "order unless the page has verified linear order."
            if review_provenance == "assistant_visual_adjudication"
            else "Transcript text and source type have been reviewed against page "
            "images. This is pilot or development/validation evidence, not a "
            "confirmatory locked-test result."
            if args.reviewed_reference
            else "The manifest source-type labels and native text layer have "
            "not been visually validated. Native text order can differ from "
            "visual column order, so these CER/WER values confound content "
            "recognition with reading order and are only a "
            "pipeline/output-adapter diagnostic."
        ),
        "results": summaries,
        "items": rows,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "status": result["status"],
                "sample_count": len(rows),
                "results": summaries,
                "output": str(output_path),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
