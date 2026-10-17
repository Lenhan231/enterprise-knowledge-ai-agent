"""Calibrate confidence thresholds on HCMUS theses and evaluate held-out theses.

This does not run inference. Thresholds are selected on calibration documents;
held-out documents estimate within-dataset transfer, not enterprise quality.
"""

from __future__ import annotations

import argparse
import bisect
import hashlib
import json
import math
import random
import re
from pathlib import Path
from typing import Any

from benchmark_hcmus_layout import COMMON_CLASSES, _class_metrics, _iou


MODEL_FILES = {
    "PP-DocLayout-S": "paddle/hcmus-layout-results-formula-v2/pp-doclayout-s.json",
    "PP-DocLayout-M": "paddle/hcmus-layout-results-formula-v2/pp-doclayout-m.json",
    "PP-DocLayout-L": "paddle/hcmus-layout-results-formula-v2/pp-doclayout-l.json",
    "PP-DocLayout_plus-L": "paddle/hcmus-layout-results-formula-v2/pp-doclayout_plus-l.json",
    "DocLayout-YOLO-DocStructBench": "yolo/hcmus-layout-yolo-formula-v2/doclayout-yolo-docstructbench.json",
    "DocLayout-YOLO-DocStructBench-640": "yolo-640/hcmus-layout-yolo-formula-v2-640/doclayout-yolo-docstructbench-640.json",
    "DocLayout-YOLO-DocStructBench-512": "yolo-size-sweep/hcmus-layout-yolo-size-sweep/imgsz-512/doclayout-yolo-docstructbench-512.json",
    "DocLayout-YOLO-DocStructBench-768": "yolo-size-sweep/hcmus-layout-yolo-size-sweep/imgsz-768/doclayout-yolo-docstructbench-768.json",
    "DocLayout-YOLO-640-NMS-0.5": "yolo-nms-sweep/hcmus-layout-yolo-nms-sweep/nms-iou-0.5/doclayout-yolo-docstructbench-640.json",
    "DocLayout-YOLO-640-NMS-0.7": "yolo-nms-sweep/hcmus-layout-yolo-nms-sweep/nms-iou-0.7/doclayout-yolo-docstructbench-640.json",
    "DocLayout-YOLO-640-NMS-0.9": "yolo-nms-sweep/hcmus-layout-yolo-nms-sweep/nms-iou-0.9/doclayout-yolo-docstructbench-640.json",
}
THRESHOLDS = [index / 100 for index in range(1, 100)]
DEFAULT_THRESHOLD = 0.30
HOLDOUT_SEED = 20261012


def _document_key(image: str) -> str:
    stem = Path(image).stem
    stem = re.sub(r"_p\d+$", "", stem, flags=re.IGNORECASE)
    while True:
        reduced = re.sub(
            r"_(?:\d+|bia|tltk|tomtat|phuluc|camon|danhmuc|modau|mucluc|ketluan)$",
            "",
            stem,
            flags=re.IGNORECASE,
        )
        if reduced == stem:
            return stem
        stem = reduced


def _split_by_document(pages: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[str], list[str]]:
    groups = sorted({_document_key(page["image"]) for page in pages})
    if len(groups) < 3:
        raise ValueError(f"Need at least 3 source documents for a held-out tuning split; found {len(groups)}.")
    shuffled = groups.copy()
    random.Random(HOLDOUT_SEED).shuffle(shuffled)
    holdout_count = max(1, math.ceil(len(groups) * 0.30))
    holdout_groups = set(shuffled[:holdout_count])
    calibration = [page for page in pages if _document_key(page["image"]) not in holdout_groups]
    holdout = [page for page in pages if _document_key(page["image"]) in holdout_groups]
    return calibration, holdout, sorted(set(groups) - holdout_groups), sorted(holdout_groups)


def _class_sweep(
    pages: list[dict[str, Any]], class_name: str
) -> dict[float, dict[str, float | int]]:
    ground_truth = {
        page_index: [
            box["bbox_xyxy"]
            for box in page["ground_truth"]
            if box["class"] == class_name
        ]
        for page_index, page in enumerate(pages)
    }
    total_ground_truth = sum(map(len, ground_truth.values()))
    if total_ground_truth == 0:
        return {threshold: {"precision": 0.0, "recall": 0.0, "f1": 0.0} for threshold in THRESHOLDS}

    predictions = sorted(
        (
            (page_index, box)
            for page_index, page in enumerate(pages)
            for box in page["predictions"]
            if box["class"] == class_name
        ),
        key=lambda item: item[1]["score"],
        reverse=True,
    )
    matched: set[tuple[int, int]] = set()
    true_positive_prefix: list[int] = []
    false_positive_prefix: list[int] = []
    true_positives = false_positives = 0
    for page_index, prediction in predictions:
        candidates = [
            (_iou(prediction["bbox_xyxy"], target), target_index)
            for target_index, target in enumerate(ground_truth[page_index])
            if (page_index, target_index) not in matched
        ]
        overlap, target_index = max(candidates, default=(0.0, -1))
        if overlap >= 0.5:
            matched.add((page_index, target_index))
            true_positives += 1
        else:
            false_positives += 1
        true_positive_prefix.append(true_positives)
        false_positive_prefix.append(false_positives)

    negative_scores = [-box["score"] for _, box in predictions]
    sweep = {}
    for threshold in THRESHOLDS:
        prediction_count = bisect.bisect_right(negative_scores, -threshold)
        tp = true_positive_prefix[prediction_count - 1] if prediction_count else 0
        fp = false_positive_prefix[prediction_count - 1] if prediction_count else 0
        fn = total_ground_truth - tp
        precision = tp / (tp + fp) if tp + fp else 0.0
        recall = tp / total_ground_truth
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        sweep[threshold] = {
            "precision": precision,
            "recall": recall,
            "f1": f1,
            "tp": tp,
            "fp": fp,
            "fn": fn,
        }
    return sweep


def run(results_dir: Path, output_path: Path) -> dict[str, Any]:
    models = []
    expected_dataset_hash = None
    split_metadata = None
    for model_name, relative_path in MODEL_FILES.items():
        result = json.loads((results_dir / relative_path).read_text())
        dataset = result["dataset"]
        dataset_hash = dataset["coco_json_sha256"]
        if expected_dataset_hash is None:
            expected_dataset_hash = dataset_hash
        elif dataset_hash != expected_dataset_hash:
            raise ValueError(f"Dataset annotation hash differs for {model_name}.")

        calibration, holdout, calibration_groups, holdout_groups = _split_by_document(result["pages"])
        if split_metadata is None:
            split_metadata = {
                "seed": HOLDOUT_SEED,
                "strategy": "deterministic 70/30 split by source thesis name; all pages of a thesis stay together",
                "calibration_documents": calibration_groups,
                "holdout_documents": holdout_groups,
                "calibration_pages": len(calibration),
                "holdout_pages": len(holdout),
            }
        elif split_metadata["holdout_documents"] != holdout_groups:
            raise ValueError("Models do not have the same evaluated document split.")

        class_curves = {
            class_name: _class_sweep(calibration, class_name)
            for class_name in COMMON_CLASSES
        }
        macro_f1_by_threshold = {
            threshold: sum(class_curves[name][threshold]["f1"] for name in COMMON_CLASSES)
            / len(COMMON_CLASSES)
            for threshold in THRESHOLDS
        }
        best_global = max(THRESHOLDS, key=macro_f1_by_threshold.get)
        per_class = {}
        classwise_holdout_f1 = []
        for class_name, curve in class_curves.items():
            best = max(THRESHOLDS, key=lambda threshold: curve[threshold]["f1"])
            holdout_metrics = _class_sweep(holdout, class_name)
            classwise_holdout = holdout_metrics[best]
            classwise_holdout_f1.append(classwise_holdout["f1"])
            per_class[class_name] = {
                "best_threshold_on_calibration": best,
                "best_metrics_on_calibration": curve[best],
                "holdout_metrics_at_default_threshold": holdout_metrics[DEFAULT_THRESHOLD],
                "holdout_metrics_at_selected_global_threshold": holdout_metrics[best_global],
                "holdout_metrics_at_classwise_calibration_threshold": classwise_holdout,
                "holdout_ap50": _class_metrics(holdout, class_name, best_global)["ap50_101_point"],
            }
        holdout_macro_f1 = sum(
            per_class[name]["holdout_metrics_at_selected_global_threshold"]["f1"]
            for name in COMMON_CLASSES
        ) / len(COMMON_CLASSES)
        holdout_macro_f1_default = sum(
            per_class[name]["holdout_metrics_at_default_threshold"]["f1"]
            for name in COMMON_CLASSES
        ) / len(COMMON_CLASSES)
        holdout_macro_ap50 = sum(per_class[name]["holdout_ap50"] for name in COMMON_CLASSES) / len(COMMON_CLASSES)
        models.append(
            {
                "model": model_name,
                "selected_global_threshold_on_calibration": best_global,
                "calibration_macro_f1_at_selected_threshold": macro_f1_by_threshold[best_global],
                "calibration_macro_f1_at_default_threshold": macro_f1_by_threshold[DEFAULT_THRESHOLD],
                "holdout_macro_f1_at_classwise_calibration_thresholds": sum(classwise_holdout_f1) / len(classwise_holdout_f1),
                "holdout_macro_f1_at_selected_threshold": holdout_macro_f1,
                "holdout_macro_f1_at_default_threshold": holdout_macro_f1_default,
                "holdout_macro_ap50": holdout_macro_ap50,
                "per_class": per_class,
            }
        )

    payload = {
        "dataset_id": "hydroshiba/hcmus-doc-layout",
        "dataset_revision": "06093e22dd6672ca282a2a60ca36049bd60d0ac7",
        "annotation_sha256": expected_dataset_hash,
        "image_count": split_metadata["calibration_pages"] + split_metadata["holdout_pages"],
        "iou_threshold": 0.5,
        "default_confidence_threshold": DEFAULT_THRESHOLD,
        "threshold_grid": THRESHOLDS,
        "split": split_metadata,
        "selection_note": "One global confidence threshold is selected on calibration theses and evaluated on held-out theses. This estimates transfer within HCMUS; enterprise reports still need a separate human-labeled holdout.",
        "models": models,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({
        model["model"]: {
            "threshold": model["selected_global_threshold_on_calibration"],
            "calibration_macro_f1": model["calibration_macro_f1_at_selected_threshold"],
            "holdout_macro_f1": model["holdout_macro_f1_at_selected_threshold"],
        }
        for model in models
    }, indent=2))
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    run(args.results_dir, args.output)


if __name__ == "__main__":
    main()
