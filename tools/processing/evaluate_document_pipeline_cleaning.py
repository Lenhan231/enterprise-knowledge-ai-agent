"""Score reviewed spans against the saved production PDF text-cleaning output."""

from __future__ import annotations

import argparse
import json
import re
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "artifacts/evaluation/document-pipelines"
DEFAULT_REVIEW = BASE / "human-review/cleaning-pilot-v3/cleaning-review-results.json"
DEFAULT_OUTPUT = BASE / "results/follow-up-metrics/cleaning-pilot-v1/cleaning-scores.json"
DEFAULT_PRODUCTION = BASE / "results/follow-up-metrics/cleaning-pilot-v1/production-output.json"
DATASET_ID = "vietnam-enterprise-cleaning-candidates-v1"
OCR_LABELS = {"new_valid", "duplicate", "noise"}


def normalize(text: str) -> str:
    return " ".join(unicodedata.normalize("NFC", text).casefold().split())


def occurrence_count(text: str, output: str) -> int:
    needle = normalize(text)
    if not needle:
        return 0
    pattern = re.compile(rf"(?<!\w){re.escape(needle)}(?!\w)")
    return sum(1 for _ in pattern.finditer(normalize(output)))


def extra_occurrence_count(text: str, output: str, native: str) -> int:
    return max(occurrence_count(text, output) - occurrence_count(text, native), 0)


def aggregate_metrics(counts: dict[str, int]) -> dict:
    def rate(numerator: int, denominator: int) -> float | None:
        return round(numerator / denominator, 6) if denominator else None

    return {
        **counts,
        "valid_content_recall": rate(counts["valid_span_retained"], counts["valid_span_count"]),
        "valid_character_recall": rate(counts["valid_char_retained"], counts["valid_char_count"]),
        "false_deletion_rate": rate(
            counts["valid_span_count"] - counts["valid_span_retained"], counts["valid_span_count"],
        ),
        "residual_duplicate_rate": rate(
            counts["ocr_duplicate_residual_count"], counts["ocr_duplicate_span_count"],
        ),
        "residual_ocr_noise_rate": rate(
            counts["ocr_noise_residual_count"], counts["ocr_noise_span_count"],
        ),
    }


def _validate_spans(value: str, allowed: set[str], field: str, page_id: str) -> list[dict]:
    try:
        spans = json.loads(value)
    except json.JSONDecodeError as error:
        raise ValueError(f"{page_id}: {field} is not valid JSON") from error
    if not isinstance(spans, list):
        raise ValueError(f"{page_id}: {field} must be a list")
    for index, span in enumerate(spans):
        if not isinstance(span, dict) or not str(span.get("text", "")).strip():
            raise ValueError(f"{page_id}: {field}[{index}] has no text")
        if span.get("classification") not in allowed:
            raise ValueError(f"{page_id}: {field}[{index}] has an invalid classification")
    return spans


def score(review_path: Path, production_path: Path, *, allow_partial: bool = False) -> dict:
    review = json.loads(review_path.read_text(encoding="utf-8"))
    production = json.loads(production_path.read_text(encoding="utf-8"))
    if review.get("task") != "cleaning" or review.get("dataset_id") != DATASET_ID:
        raise ValueError("Review export task or dataset_id does not match the cleaning candidates")
    review_provenance = review.get("review_provenance", "reviewer_provided_unspecified")
    if review_provenance not in {
        "human_review",
        "assistant_visual_adjudication",
        "reviewer_provided_unspecified",
    }:
        raise ValueError(f"Unsupported review provenance: {review_provenance}")
    if production.get("dataset_id") != DATASET_ID:
        raise ValueError("Production outputs use a different dataset_id")

    reviewed = {row.get("id"): row for row in review.get("reviewed_items", [])}
    outputs = {row.get("id"): row for row in production.get("pages", [])}
    if not reviewed or not set(reviewed).issubset(outputs):
        raise ValueError("Review export pages must be a nonempty subset of the production output")
    if not allow_partial and set(reviewed) != set(outputs):
        raise ValueError("Review export is partial; pass --allow-partial-review for a pilot score")

    pages = []
    sums = {
        "valid_span_count": 0,
        "valid_span_retained": 0,
        "valid_char_count": 0,
        "valid_char_retained": 0,
        "ocr_duplicate_span_count": 0,
        "ocr_duplicate_residual_count": 0,
        "ocr_noise_span_count": 0,
        "ocr_noise_residual_count": 0,
    }
    split_sums = {split: dict.fromkeys(sums, 0) for split in ("development", "validation")}
    for page_id, review_row in reviewed.items():
        if not review_row.get("reviewed") or not str(review_row.get("reviewer", "")).strip():
            raise ValueError(f"{page_id}: every page must be reviewed and have a reviewer ID")
        if review_row.get("split") not in {"development", "validation"}:
            raise ValueError(f"{page_id}: unsupported split")
        ocr_spans = _validate_spans(
            review_row.get("reviewed_ocr_spans_json", ""), OCR_LABELS,
            "reviewed_ocr_spans_json", page_id,
        )
        output_row = outputs[page_id]
        if output_row.get("split") != review_row.get("split"):
            raise ValueError(f"{page_id}: split differs between review and output")
        native = str(output_row.get("native_text", ""))
        cleaned = str(output_row.get("cleaned_text", ""))

        page_counts = {key: 0 for key in sums}
        for span in ocr_spans:
            label, text = span["classification"], span["text"]
            if label == "new_valid":
                retained = extra_occurrence_count(text, cleaned, native) > 0
                page_counts["valid_span_count"] += 1
                page_counts["valid_span_retained"] += int(retained)
                page_counts["valid_char_count"] += len(normalize(text))
                page_counts["valid_char_retained"] += len(normalize(text)) if retained else 0
            elif label == "duplicate":
                page_counts["ocr_duplicate_span_count"] += 1
                page_counts["ocr_duplicate_residual_count"] += int(
                    extra_occurrence_count(text, cleaned, native) > 0
                )
            else:
                page_counts["ocr_noise_span_count"] += 1
                page_counts["ocr_noise_residual_count"] += int(
                    extra_occurrence_count(text, cleaned, native) > 0
                )
        for key in sums:
            sums[key] += page_counts[key]
            split_sums[review_row["split"]][key] += page_counts[key]
        pages.append({"id": page_id, "split": review_row["split"], "reviewer": review_row["reviewer"], **page_counts})

    return {
        "dataset_id": DATASET_ID,
        "review_provenance": review_provenance,
        "status": (
            "assistant_adjudicated_cleaning_diagnostic"
            if review_provenance == "assistant_visual_adjudication"
            else "human_reviewed_cleaning_pilot"
            if review_provenance == "human_review" and len(reviewed) < len(outputs)
            else "human_reviewed_cleaning_full_candidate_set"
            if review_provenance == "human_review"
            else "reviewer_adjudicated_cleaning_pilot"
            if len(reviewed) < len(outputs)
            else "reviewer_adjudicated_cleaning_full_candidate_set"
        ),
        "reviewed_page_count": len(reviewed),
        "available_page_count": len(outputs),
        "metric_definitions": {
            "valid_content_recall": "Exact normalized OCR-span retention for spans labeled new_valid, measured as an extra occurrence beyond the native PDF text.",
            "valid_character_recall": "Character-weighted exact normalized retention for OCR spans labeled new_valid.",
            "false_deletion_rate": "1 - valid_content_recall for legitimate OCR additions.",
            "residual_duplicate_rate": "Duplicate OCR spans still present as extra occurrences beyond native text / labeled duplicate spans.",
            "residual_ocr_noise_rate": "Noise OCR spans still present as extra occurrences beyond native text / labeled noise spans.",
            "page_counter_removal": "Not evaluated: the candidate inventory contains no trailing page-counter examples.",
        },
        "aggregate": aggregate_metrics(sums),
        "by_split": {split: aggregate_metrics(counts) for split, counts in split_sums.items()},
        "reviewer_ids": sorted({row["reviewer"] for row in pages}),
        "pages": pages,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reviewed-reference", type=Path, default=DEFAULT_REVIEW)
    parser.add_argument("--production-output", type=Path, default=DEFAULT_PRODUCTION)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--allow-partial-review", action="store_true",
                        help="Score a reviewed pilot subset; result is diagnostic, not the full candidate-set score.")
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(f"Refusing to overwrite cleaning scores: {args.output}")
    result = score(args.reviewed_reference, args.production_output, allow_partial=args.allow_partial_review)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": result["status"], "aggregate": result["aggregate"], "output": str(args.output)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
