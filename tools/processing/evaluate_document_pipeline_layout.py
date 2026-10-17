"""Score assistant-adjudicated layout regions from enterprise benchmark runs."""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from zipfile import ZipFile


CLASS_MAP = {
    "doc_title": "title",
    "paragraph_title": "title",
    "text": "text",
    "abstract": "text",
    "content": "text",
    "references": "text",
    "footnote": "text",
    "sidebar_text": "text",
    "table": "table",
    "image": "figure",
    "figure": "figure",
    "chart": "figure",
}
# A chart is part of the reference taxonomy's figure class; chart titles remain captions.
SCORED_CLASSES = ("title", "text", "table", "figure")
DOCLING_TEXT_MAP = {
    "section_header": "title",
    "title": "title",
    "document_title": "title",
    "paragraph_title": "title",
    "text": "text",
    "paragraph": "text",
    "list_item": "text",
}
MINERU_MAP = {
    "doc_title": "title",
    "paragraph_title": "title",
    "text": "text",
    "table": "table",
    "image": "figure",
    "chart": "figure",
}


def _iou(first: list[float], second: list[float]) -> float:
    x1, y1 = max(first[0], second[0]), max(first[1], second[1])
    x2, y2 = min(first[2], second[2]), min(first[3], second[3])
    intersection = max(0.0, x2 - x1) * max(0.0, y2 - y1)
    area_first = max(0.0, first[2] - first[0]) * max(0.0, first[3] - first[1])
    area_second = max(0.0, second[2] - second[0]) * max(0.0, second[3] - second[1])
    union = area_first + area_second - intersection
    return intersection / union if union else 0.0


def _counts(tp: int, fp: int, fn: int) -> dict[str, float | int]:
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    return {
        "true_positive": tp,
        "false_positive": fp,
        "false_negative": fn,
        "precision": precision,
        "recall": recall,
        "f1": 2 * precision * recall / (precision + recall) if precision + recall else 0.0,
    }


def _match(
    predictions: list[list[float]], references: list[list[float]], threshold: float
) -> tuple[int, int, int]:
    candidates = sorted(
        ((_iou(pred, ref), i, j) for i, pred in enumerate(predictions) for j, ref in enumerate(references)),
        reverse=True,
    )
    used_predictions: set[int] = set()
    used_references: set[int] = set()
    for score, pred_index, ref_index in candidates:
        if score < threshold:
            break
        if pred_index not in used_predictions and ref_index not in used_references:
            used_predictions.add(pred_index)
            used_references.add(ref_index)
    tp = len(used_predictions)
    return tp, len(predictions) - tp, len(references) - tp


def _normalized_box(box: list[float], width: float, height: float) -> list[float]:
    if len(box) != 4 or width <= 0 or height <= 0:
        raise ValueError(f"Invalid box or image size: {box}, {width}x{height}")
    x1, y1, x2, y2 = (float(value) for value in box)
    return [x1 / width, y1 / height, x2 / width, y2 / height]


def _docling_box(provenance: dict[str, Any], width: float, height: float) -> list[float]:
    box = provenance["bbox"]
    left, top, right, bottom = (float(box[key]) for key in ("l", "t", "r", "b"))
    if box.get("coord_origin") == "BOTTOMLEFT":
        top, bottom = height - top, height - bottom
    return _normalized_box([left, top, right, bottom], width, height)


def _validate_aspect_ratio(width: float, height: float, reference_page: dict[str, Any]) -> None:
    reference_ratio = reference_page["width_px"] / reference_page["height_px"]
    output_ratio = width / height
    if abs(reference_ratio - output_ratio) > 1e-3:
        raise ValueError(
            f"Page aspect ratio changed for {reference_page['page_id']}: "
            f"reference={reference_ratio:.6f}, output={output_ratio:.6f}"
        )


def _predictions(
    engine: str, raw_root: Path, input_id: str, reference_page: dict[str, Any]
) -> tuple[dict[str, list[list[float]]], Counter[str]]:
    predictions: dict[str, list[list[float]]] = defaultdict(list)
    ignored: Counter[str] = Counter()
    if engine == "pp-structurev3":
        document = json.loads(
            (raw_root / "raw_pages" / f"{input_id}-page-001.json").read_text(encoding="utf-8")
        )["res"]
        width, height = document["width"], document["height"]
        _validate_aspect_ratio(width, height, reference_page)
        for block in document.get("parsing_res_list", []):
            model_label = block.get("block_label", "")
            label = CLASS_MAP.get(model_label)
            if label is None:
                ignored[model_label] += 1
            else:
                predictions[label].append(_normalized_box(block["block_bbox"], width, height))
        return predictions, ignored

    if engine == "docling":
        document = json.loads(
            (raw_root / "raw_pages" / f"{input_id}.json").read_text(encoding="utf-8")
        )
        pages = document.get("pages", {})
        if len(pages) != 1:
            raise ValueError(f"Expected one page in Docling output {input_id}, got {len(pages)}")
        page = next(iter(pages.values()))
        width, height = page["size"]["width"], page["size"]["height"]
        _validate_aspect_ratio(width, height, reference_page)
        for entry in document.get("texts", []):
            model_label = entry.get("label", "")
            label = DOCLING_TEXT_MAP.get(model_label)
            if label is None:
                ignored[model_label] += 1
                continue
            for provenance in entry.get("prov", []):
                if provenance.get("page_no") == page["page_no"]:
                    predictions[label].append(_docling_box(provenance, width, height))
        for collection, label in (("tables", "table"), ("pictures", "figure")):
            for entry in document.get(collection, []):
                for provenance in entry.get("prov", []):
                    if provenance.get("page_no") == page["page_no"]:
                        predictions[label].append(_docling_box(provenance, width, height))
        return predictions, ignored

    if engine == "mineru":
        archive_path = raw_root / "mineru-output" / input_id / f"{input_id}.zip"
        with ZipFile(archive_path) as archive:
            document = json.loads(archive.read("structured_content.json"))
        pages = document.get("pages", [])
        if len(pages) != 1:
            raise ValueError(f"Expected one page in MinerU output {input_id}, got {len(pages)}")
        layout_pages = document.get("extensions", {}).get("docvortex_layout", {}).get("pages", [])
        if len(layout_pages) != 1:
            raise ValueError(f"Missing MinerU page dimensions for {input_id}")
        _validate_aspect_ratio(layout_pages[0]["width_pt"], layout_pages[0]["height_pt"], reference_page)
        for block in pages[0].get("blocks", []):
            model_label = block.get("type", "")
            label = MINERU_MAP.get(model_label)
            if label is None:
                ignored[model_label] += 1
                continue
            predictions[label].append(_normalized_box(block["bbox"], 1.0, 1.0))
        return predictions, ignored

    raise ValueError(f"Unsupported engine: {engine}")


def run(args: argparse.Namespace) -> dict[str, Any]:
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    reference = json.loads(args.reference.read_text(encoding="utf-8"))
    metadata_path = args.raw_root / "run-metadata.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    engine = args.engine or metadata["engine"]
    if metadata["engine"] != engine:
        raise ValueError(f"Expected {engine} run metadata, got {metadata['engine']}")

    input_by_source_page = {
        (page["source_file"], page["page_number_source"]): page
        for page in manifest["pages"]
    }
    prediction_counts: Counter[str] = Counter()
    reference_counts: Counter[str] = Counter()
    per_class: dict[str, list[int]] = defaultdict(lambda: [0, 0, 0])
    per_page: list[dict[str, Any]] = []
    pages_scored = 0

    reference_pages = [
        page for page in reference["pages"]
        if args.splits is None or page.get("split") in args.splits
    ]
    split_counts = Counter(page.get("split", "unspecified") for page in reference_pages)
    scored_scope = ", ".join(
        f"{count} {split} page{'s' if count != 1 else ''}"
        for split, count in sorted(split_counts.items())
    )
    label_scope = (
        f"{len(reference_pages)} assistant-adjudicated full-page labels scored ({scored_scope}); "
        "not independently human-reviewed."
    )
    scored_classes = args.scored_classes or list(SCORED_CLASSES)
    for reference_page in reference_pages:
        key = (reference_page["source_file"], reference_page["page_number"])
        input_page = input_by_source_page.get(key)
        if input_page is None:
            raise ValueError(f"Adjudicated page missing from layout inputs: {key}")
        predictions, ignored_labels = _predictions(engine, args.raw_root, input_page["id"], reference_page)

        truths: dict[str, list[list[float]]] = defaultdict(list)
        for annotation in reference_page["annotations"]:
            label = annotation["class"]
            if label in scored_classes:
                truths[label].append(
                    _normalized_box(annotation["bbox_xyxy"], reference_page["width_px"], reference_page["height_px"])
                )
        page_metrics: dict[str, Any] = {}
        for label in scored_classes:
            tp, fp, fn = _match(predictions[label], truths[label], args.iou_threshold)
            for index, value in enumerate((tp, fp, fn)):
                per_class[label][index] += value
            prediction_counts[label] += len(predictions[label])
            reference_counts[label] += len(truths[label])
            if args.positive_regions_only:
                page_metrics[label] = {
                    "matched_known_regions": tp,
                    "unmatched_model_regions_not_scored_as_fp": fp,
                    "missed_known_regions": fn,
                    "known_region_recall": tp / (tp + fn) if tp + fn else 0.0,
                }
            else:
                page_metrics[label] = _counts(tp, fp, fn)
        per_page.append(
            {
                "page_id": reference_page["page_id"],
                "input_id": input_page["id"],
                "ignored_model_labels": dict(sorted(ignored_labels.items())),
                "classes": page_metrics,
            }
        )
        pages_scored += 1

    classes = {
        label: (
            {
                "matched_known_regions": per_class[label][0],
                "unmatched_model_regions_not_scored_as_fp": per_class[label][1],
                "missed_known_regions": per_class[label][2],
                "known_region_recall": (
                    per_class[label][0] / (per_class[label][0] + per_class[label][2])
                    if per_class[label][0] + per_class[label][2] else 0.0
                ),
            }
            if args.positive_regions_only else _counts(*per_class[label])
        )
        for label in scored_classes
    }
    micro_tp = sum(value[0] for value in per_class.values())
    micro_fp = sum(value[1] for value in per_class.values())
    micro_fn = sum(value[2] for value in per_class.values())
    return {
        "dataset_id": reference["dataset_id"],
        "engine": engine,
        "kernel_id": args.kernel_id,
        "pages_scored": pages_scored,
        "splits_scored": args.splits or sorted({p.get("split", "unspecified") for p in reference_pages}),
        "iou_threshold": args.iou_threshold,
        "score_threshold": None,
        "score_threshold_note": "Exported pipeline blocks expose no per-box confidence; all mapped blocks are included.",
        "class_mapping": (
            CLASS_MAP
            if engine == "pp-structurev3"
            else DOCLING_TEXT_MAP
            if engine == "docling"
            else MINERU_MAP
        ),
        "metrics": (
            {
                "known_positive_regions": classes,
                "unmatched_predictions_not_scored_as_false_positives": dict(
                    (label, per_class[label][1]) for label in scored_classes
                ),
                "known_positive_region_counts": dict(reference_counts),
                "model_region_counts": dict(prediction_counts),
            }
            if args.positive_regions_only else
            {
                "per_class": classes,
                "micro": _counts(micro_tp, micro_fp, micro_fn),
                "predicted_regions": dict(prediction_counts),
                "reference_regions": dict(reference_counts),
            }
        ),
        "provenance": {
            **reference["provenance"],
            **(
                {"split_policy": "locked_test scored once on frozen baseline outputs; do not reuse for tuning."}
                if args.splits == ["locked_test"]
                else {}
            ),
            "layout_input_manifest": str(args.manifest),
            "prediction_metadata": str(metadata_path),
            "label_scope": label_scope,
            "scored_page_scope": label_scope,
            "adjudicator_scope": label_scope,
            "caveats": [
                "This is a fixed-output region matching score, not AP/mAP.",
                "Assistant-adjudicated labels are not independent human ground truth.",
                "The model output coordinates are normalized to the input page aspect ratio before IoU matching.",
                *( ["Only known-positive regions are labeled; unmatched predictions are not scored as false positives."] if args.positive_regions_only else ["The scored adjudicated subset is small and not representative of the 200-page set."] ),
            ],
        },
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "pages": per_page,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=Path("artifacts/evaluation/document-pipelines/layout/inputs/manifest.json"))
    parser.add_argument("--reference", type=Path, default=Path("data/evaluation/layout/vn-enterprise-layout-pilot-v1-adjudicated-reference.json"))
    parser.add_argument("--engine", choices=("pp-structurev3", "docling", "mineru"), required=True)
    parser.add_argument("--kernel-id")
    parser.add_argument("--raw-root", type=Path, required=True, help="Downloaded run directory containing run-metadata.json and raw_pages/")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--iou-threshold", type=float, default=0.5)
    parser.add_argument("--scored-classes", nargs="+", choices=SCORED_CLASSES)
    parser.add_argument("--splits", nargs="+", choices=("development", "validation", "locked_test"))
    parser.add_argument("--positive-regions-only", action="store_true")
    args = parser.parse_args()
    if args.kernel_id is None:
        args.kernel_id = f"ltrngnhn/enterprise-layout-200-v2-{args.engine}"
    result = run(args)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result["metrics"], ensure_ascii=False, indent=2))
    print(f"Saved {args.output}")


if __name__ == "__main__":
    main()
