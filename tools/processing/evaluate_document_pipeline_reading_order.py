"""Evaluate block reading order on assistant-adjudicated layout pages."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any
from zipfile import ZipFile


CLASS_MAP = {
    "doc_title": "title",
    "paragraph_title": "title",
    "section_header": "title",
    "text": "text",
    "paragraph": "text",
    "abstract": "text",
    "content": "text",
    "references": "text",
    "footnote": "text",
    "sidebar_text": "text",
    "list_item": "text",
    "table": "table",
    "image": "figure",
    "picture": "figure",
    "figure": "figure",
    "chart": "figure",
}


def _box(box: list[float], width: float, height: float) -> list[float]:
    x1, y1, x2, y2 = (float(value) for value in box)
    return [x1 / width, y1 / height, x2 / width, y2 / height]


def _iou(first: list[float], second: list[float]) -> float:
    x1, y1 = max(first[0], second[0]), max(first[1], second[1])
    x2, y2 = min(first[2], second[2]), min(first[3], second[3])
    intersection = max(0.0, x2 - x1) * max(0.0, y2 - y1)
    area_a = max(0.0, first[2] - first[0]) * max(0.0, first[3] - first[1])
    area_b = max(0.0, second[2] - second[0]) * max(0.0, second[3] - second[1])
    union = area_a + area_b - intersection
    return intersection / union if union else 0.0


def _docling_box(provenance: dict[str, Any], width: float, height: float) -> list[float]:
    bbox = provenance["bbox"]
    left, top, right, bottom = (float(bbox[key]) for key in ("l", "t", "r", "b"))
    if bbox.get("coord_origin") == "BOTTOMLEFT":
        top, bottom = height - top, height - bottom
    if top > bottom:
        top, bottom = bottom, top
    return _box([left, top, right, bottom], width, height)


def _predictions(engine: str, raw_root: Path, page_id: str) -> list[dict[str, Any]]:
    predictions: list[dict[str, Any]] = []
    if engine == "pp-structurev3":
        result = json.loads(
            (raw_root / "raw_pages" / f"{page_id}-page-001.json").read_text(encoding="utf-8")
        )["res"]
        width, height = result["width"], result["height"]
        for position, block in enumerate(result.get("parsing_res_list", [])):
            label = CLASS_MAP.get(block.get("block_label", ""))
            if label:
                order = block.get("block_order")
                predictions.append({
                    "class": label,
                    "box": _box(block["block_bbox"], width, height),
                    "order": float(order) if order is not None else None,
                    "source_position": position,
                })
        return predictions

    if engine == "docling":
        document = json.loads(
            (raw_root / "raw_pages" / f"{page_id}.json").read_text(encoding="utf-8")
        )
        page = next(iter(document["pages"].values()))
        width, height = page["size"]["width"], page["size"]["height"]
        for position, child in enumerate(document.get("body", {}).get("children", [])):
            collection, index = child["$ref"][2:].split("/")
            entry = document[collection][int(index)]
            if collection == "texts":
                label = CLASS_MAP.get(entry.get("label", ""))
            elif collection == "tables":
                label = "table"
            elif collection == "pictures":
                label = "figure"
            else:
                label = None
            if not label:
                continue
            for provenance in entry.get("prov", []):
                if provenance.get("page_no") == page["page_no"]:
                    predictions.append({
                        "class": label,
                        "box": _docling_box(provenance, width, height),
                        "order": float(position),
                        "source_position": position,
                    })
        return predictions

    if engine == "mineru":
        archive_path = raw_root / "mineru-output" / page_id / f"{page_id}.zip"
        with ZipFile(archive_path) as archive:
            document = json.loads(archive.read("middle_json.json"))
        blocks = document["pages"][0].get("blocks", [])
        for position, block in enumerate(blocks):
            label = CLASS_MAP.get(block.get("type", ""))
            if label:
                predictions.append({
                    "class": label,
                    "box": [float(value) for value in block["bbox"]],
                    "order": float(position),
                    "source_position": position,
                })
        return predictions

    raise ValueError(f"Unsupported engine: {engine}")


def _match(predictions: list[dict[str, Any]], references: list[dict[str, Any]], threshold: float):
    candidates = sorted(
        (
            (_iou(prediction["box"], reference["box"]), pred_index, ref_index)
            for pred_index, prediction in enumerate(predictions)
            for ref_index, reference in enumerate(references)
            if prediction["class"] == reference["class"]
        ),
        reverse=True,
    )
    used_predictions: set[int] = set()
    used_references: set[int] = set()
    matches = []
    for score, pred_index, ref_index in candidates:
        if score < threshold:
            break
        if pred_index not in used_predictions and ref_index not in used_references:
            used_predictions.add(pred_index)
            used_references.add(ref_index)
            matches.append((pred_index, ref_index, score))
    return matches, used_predictions, used_references


def _reviewed_order_pages(
    review_path: Path,
    dataset_id: str,
    layout_by_id: dict[str, dict[str, Any]],
    selected_splits: list[str] | None,
) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    review = json.loads(review_path.read_text(encoding="utf-8"))
    if review.get("task") != "reading-order" or review.get("dataset_id") != dataset_id:
        raise ValueError("Review export task or dataset does not match the reading-order reference")
    splits = selected_splits or ["validation", "locked_test"]
    expected_ids = {
        page_id for page_id, page in layout_by_id.items()
        if page.get("split") in splits
    }
    reviewed_by_id: dict[str, dict[str, Any]] = {}
    seen_ids: set[str] = set()
    for item in review.get("reviewed_items", []):
        page_id = item.get("id")
        if page_id in seen_ids:
            raise ValueError(f"Duplicate reading-order review item: {page_id}")
        seen_ids.add(page_id)
        if page_id not in expected_ids or item.get("split") != layout_by_id[page_id].get("split"):
            raise ValueError(f"Review item is outside selected splits or has wrong split: {page_id}")
        if not item.get("reviewed"):
            continue
        if not str(item.get("reviewer", "")).strip():
            raise ValueError(f"Reviewed page has no reviewer ID: {page_id}")
        try:
            blocks = json.loads(item["reference_blocks_json"])
            if not isinstance(blocks, list):
                raise ValueError("reference_blocks_json must be a list")
            expected_indices = {int(block["annotation_index"]) for block in blocks}
            order = [int(value.strip()) for value in item["ordered_annotation_indices"].split(",") if value.strip()]
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
            raise ValueError(f"Invalid reading-order fields for {page_id}") from error
        if len(order) != len(expected_indices) or set(order) != expected_indices:
            raise ValueError(f"Reading order must contain each reference block exactly once: {page_id}")
        layout_indices = set(range(len(layout_by_id[page_id].get("annotations", []))))
        if expected_indices != layout_indices:
            raise ValueError(f"Review blocks do not match the canonical layout annotations: {page_id}")
        reviewed_by_id[page_id] = {
            **item,
            "ordered_annotation_indices": order,
        }

    missing = expected_ids - set(reviewed_by_id)
    if missing:
        raise ValueError(
            f"Reading-order review is incomplete: {len(missing)} of {len(expected_ids)} "
            f"pages in {', '.join(splits)} are not marked reviewed"
        )
    pages = [
        {
            "page_id": page_id,
            "ordered_annotation_indices": reviewed_by_id[page_id]["ordered_annotation_indices"],
        }
        for page_id in sorted(expected_ids)
    ]
    return pages, reviewed_by_id


def run(args: argparse.Namespace) -> dict[str, Any]:
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    layout_reference = json.loads(args.layout_reference.read_text(encoding="utf-8"))
    order_reference = json.loads(args.reference.read_text(encoding="utf-8"))
    input_by_id = {page["id"]: page for page in manifest["pages"]}
    layout_by_id = {page["page_id"]: page for page in layout_reference["pages"]}
    page_results = []

    selected_splits = getattr(args, "splits", None)
    reviewed_by_id = {}
    if args.reviewed_reference:
        order_pages, reviewed_by_id = _reviewed_order_pages(
            args.reviewed_reference,
            order_reference["dataset_id"],
            layout_by_id,
            selected_splits,
        )
        if selected_splits is None:
            selected_splits = ["validation", "locked_test"]
    else:
        order_pages = [
            page for page in order_reference["pages"]
            if selected_splits is None or layout_by_id[page["page_id"]].get("split") in selected_splits
        ]
    for order_page in order_pages:
        page_id = order_page["page_id"]
        source_page = layout_by_id[page_id]
        input_page = input_by_id[page_id]
        if (source_page["source_file"], source_page["page_number"]) != (
            input_page["source_file"], input_page["page_number_source"]
        ):
            raise ValueError(f"Manifest provenance mismatch for {page_id}")
        ordered_indices = order_page["ordered_annotation_indices"]
        annotations = source_page["annotations"]
        references = [
            {
                "annotation_index": index,
                "class": annotations[index]["class"],
                "box": _box(annotations[index]["bbox_xyxy"], source_page["width_px"], source_page["height_px"]),
                "order": order,
            }
            for order, index in enumerate(ordered_indices)
        ]
        predictions = _predictions(args.engine, args.raw_root, page_id)
        matches, used_predictions, used_references = _match(predictions, references, args.iou_threshold)
        comparable = [
            (predictions[pred_index], references[ref_index], score)
            for pred_index, ref_index, score in matches
            if predictions[pred_index]["order"] is not None
        ]
        matched_details = [
            {
                "reference_annotation_index": references[ref_index]["annotation_index"],
                "class": references[ref_index]["class"],
                "reference_order": references[ref_index]["order"],
                "predicted_order": predictions[pred_index]["order"],
                "iou": round(score, 6),
            }
            for pred_index, ref_index, score in matches
        ]
        correct_pairs = 0
        total_pairs = 0
        tied_pairs = 0
        disagreements = []
        for left in range(len(comparable)):
            for right in range(left + 1, len(comparable)):
                pred_a, ref_a, _ = comparable[left]
                pred_b, ref_b, _ = comparable[right]
                if ref_a["order"] == ref_b["order"]:
                    continue
                if pred_a["order"] == pred_b["order"]:
                    tied_pairs += 1
                    continue
                total_pairs += 1
                is_correct = (pred_a["order"] < pred_b["order"]) == (ref_a["order"] < ref_b["order"])
                correct_pairs += int(is_correct)
                if not is_correct:
                    disagreements.append({
                        "reference_annotation_indices": [ref_a["annotation_index"], ref_b["annotation_index"]],
                        "reference_order": [ref_a["order"], ref_b["order"]],
                        "predicted_order": [pred_a["order"], pred_b["order"]],
                    })
        page_results.append({
            "page_id": page_id,
            "reviewer": reviewed_by_id.get(page_id, {}).get("reviewer"),
            "review_note": reviewed_by_id.get(page_id, {}).get("review_note", ""),
            "reference_blocks": len(references),
            "predicted_blocks": len(predictions),
            "matched_blocks": len(matches),
            "matched_blocks_with_defined_order": len(comparable),
            "matched_blocks_without_defined_order": len(matches) - len(comparable),
            "unmatched_reference_blocks": len(references) - len(used_references),
            "unmatched_prediction_blocks": len(predictions) - len(used_predictions),
            "matched_block_details": matched_details,
            "unmatched_reference_annotation_indices": [
                references[index]["annotation_index"]
                for index in range(len(references))
                if index not in used_references
            ],
            "unmatched_predictions": [
                {"class": prediction["class"], "source_position": prediction["source_position"]}
                for index, prediction in enumerate(predictions)
                if index not in used_predictions
            ],
            "pairwise_order_correct": correct_pairs,
            "pairwise_order_total": total_pairs,
            "pairs_without_distinct_predicted_order": tied_pairs,
            "pairwise_order_accuracy": correct_pairs / total_pairs if total_pairs else None,
            "disagreements": disagreements,
        })

    total_correct = sum(page["pairwise_order_correct"] for page in page_results)
    total_pairs = sum(page["pairwise_order_total"] for page in page_results)
    return {
        "dataset_id": order_reference["dataset_id"],
        "engine": args.engine,
        "provenance": (
            "prediction_blind_human_review_export"
            if args.reviewed_reference else order_reference["provenance"]
        ),
        "reviewed_reference": str(args.reviewed_reference) if args.reviewed_reference else None,
        "iou_threshold": args.iou_threshold,
        "page_count": len(page_results),
        "splits_scored": selected_splits or sorted({layout_by_id[page["page_id"]].get("split", "unspecified") for page in order_pages}),
        "matched_blocks": sum(page["matched_blocks"] for page in page_results),
        "matched_blocks_without_defined_order": sum(
            page["matched_blocks_without_defined_order"] for page in page_results
        ),
        "unmatched_reference_blocks": sum(page["unmatched_reference_blocks"] for page in page_results),
        "unmatched_prediction_blocks": sum(page["unmatched_prediction_blocks"] for page in page_results),
        "pairwise_order_correct": total_correct,
        "pairwise_order_total": total_pairs,
        "pairs_without_distinct_predicted_order": sum(
            page["pairs_without_distinct_predicted_order"] for page in page_results
        ),
        "pairwise_order_accuracy": total_correct / total_pairs if total_pairs else None,
        "pages": page_results,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--engine", choices=("pp-structurev3", "mineru", "docling"), required=True)
    parser.add_argument("--raw-root", type=Path, required=True, help="Engine result directory containing raw_pages/ or mineru-output/")
    parser.add_argument("--manifest", type=Path, default=Path("artifacts/evaluation/document-pipelines/layout/inputs/manifest.json"))
    parser.add_argument("--layout-reference", type=Path, default=Path("data/evaluation/layout/vn-enterprise-layout-v2-adjudicated-reference.json"))
    parser.add_argument("--reference", type=Path, default=Path("data/evaluation/layout/vn-enterprise-reading-order-reference.json"))
    parser.add_argument("--reviewed-reference", type=Path, help="Prediction-blind JSON export from the reading-order review page")
    parser.add_argument("--iou-threshold", type=float, default=0.5)
    parser.add_argument("--splits", nargs="+", choices=("development", "validation", "locked_test"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = run(args)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in result.items() if key != "pages"}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
