"""Evaluate Paddle PP-DocLayout models on the real-only HCMUS validation split."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import resource
import statistics
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

DATASET_ID = "hydroshiba/hcmus-doc-layout"
DATASET_REVISION = "06093e22dd6672ca282a2a60ca36049bd60d0ac7"
COMMON_CLASSES = ("title", "text", "table", "figure", "formula")

# Limit comparison to categories with a reasonable equivalent in both taxonomies.
GT_CLASS_MAP = {
    "catalogue": "title",
    "sec_1": "title",
    "sec_2": "title",
    "sec_3": "title",
    "para": "text",
    "para_equ": "text",
    "equ": "formula",
    "list": "text",
    "reference": "text",
    "foot": "text",
    "header": "text",
    "tab": "table",
    "fig": "figure",
    "title": "title",
    "text": "text",
    "table": "table",
    "figure": "figure",
    "formula": "formula",
}
PREDICTION_CLASS_MAP = {
    "doc_title": "title",
    "paragraph_title": "title",
    "text": "text",
    "abstract": "text",
    "content": "text",
    "references": "text",
    "reference": "text",
    "footnote": "text",
    "sidebar_text": "text",
    "aside_text": "text",
    "algorithm": "text",
    "header": "text",
    "footer": "text",
    "list": "text",
    "table": "table",
    "image": "figure",
    "figure": "figure",
    "chart": "figure",
    "formula": "formula",
}


def _iou(first: list[float], second: list[float]) -> float:
    x1, y1 = max(first[0], second[0]), max(first[1], second[1])
    x2, y2 = min(first[2], second[2]), min(first[3], second[3])
    intersection = max(0.0, x2 - x1) * max(0.0, y2 - y1)
    area_a = max(0.0, first[2] - first[0]) * max(0.0, first[3] - first[1])
    area_b = max(0.0, second[2] - second[0]) * max(0.0, second[3] - second[1])
    union = area_a + area_b - intersection
    return intersection / union if union else 0.0


def _class_metrics(
    pages: list[dict[str, Any]], class_name: str, score_threshold: float
) -> dict[str, float | int]:
    ground_truth = {
        index: [box["bbox_xyxy"] for box in page["ground_truth"] if box["class"] == class_name]
        for index, page in enumerate(pages)
    }
    total_gt = sum(map(len, ground_truth.values()))
    predictions = sorted(
        (
            (index, box)
            for index, page in enumerate(pages)
            for box in page["predictions"]
            if box["class"] == class_name
        ),
        key=lambda item: item[1]["score"],
        reverse=True,
    )

    matched: set[tuple[int, int]] = set()
    tp_flags: list[int] = []
    fp_flags: list[int] = []
    tp_at_threshold = fp_at_threshold = 0
    for page_index, prediction in predictions:
        candidates = [
            (_iou(prediction["bbox_xyxy"], box), target_index)
            for target_index, box in enumerate(ground_truth[page_index])
            if (page_index, target_index) not in matched
        ]
        overlap, target_index = max(candidates, default=(0.0, -1))
        matched_prediction = overlap >= 0.5
        if matched_prediction:
            matched.add((page_index, target_index))
        tp_flags.append(int(matched_prediction))
        fp_flags.append(int(not matched_prediction))
        if prediction["score"] >= score_threshold:
            tp_at_threshold += int(matched_prediction)
            fp_at_threshold += int(not matched_prediction)

    fn_at_threshold = total_gt - tp_at_threshold
    precision = tp_at_threshold / (tp_at_threshold + fp_at_threshold) if tp_at_threshold + fp_at_threshold else 0.0
    recall = tp_at_threshold / total_gt if total_gt else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    ap = 0.0
    if total_gt and predictions:
        cumulative_tp = cumulative_fp = 0
        points: list[tuple[float, float]] = []
        for is_tp, is_fp in zip(tp_flags, fp_flags):
            cumulative_tp += is_tp
            cumulative_fp += is_fp
            points.append((cumulative_tp / total_gt, cumulative_tp / (cumulative_tp + cumulative_fp)))
        ap = sum(
            max((precision_at_recall for recall_at_rank, precision_at_recall in points if recall_at_rank >= target_recall), default=0.0)
            for target_recall in (step / 100 for step in range(101))
        ) / 101

    return {
        "ground_truth": total_gt,
        "predictions_at_threshold": sum(1 for _, box in predictions if box["score"] >= score_threshold),
        "precision_at_threshold": precision,
        "recall_at_threshold": recall,
        "f1_at_threshold": f1,
        "ap50_101_point": ap,
        "true_positives": tp_at_threshold,
        "false_positives": fp_at_threshold,
        "false_negatives": fn_at_threshold,
    }


def _json_payload(result: Any) -> dict[str, Any]:
    payload = result.json
    if isinstance(payload, str):
        payload = json.loads(payload)
    return payload.get("res", payload)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _select_images(images: list[dict[str, Any]], max_pages: int) -> list[dict[str, Any]]:
    if max_pages <= 0 or max_pages >= len(images):
        return images
    if max_pages == 1:
        return [images[0]]
    indices = [round(index * (len(images) - 1) / (max_pages - 1)) for index in range(max_pages)]
    return [images[index] for index in indices]


def run(args: argparse.Namespace) -> dict[str, Any]:
    import paddle
    from paddleocr import LayoutDetection

    if args.device.startswith("gpu") and (
        not paddle.is_compiled_with_cuda() or paddle.device.cuda.device_count() < 1
    ):
        raise RuntimeError("A CUDA-enabled Paddle runtime and visible GPU are required.")

    annotations_path = Path(args.coco_json)
    images_root = Path(args.images_root)
    coco = json.loads(annotations_path.read_text())
    evaluation_images = _select_images(coco["images"], args.max_pages)
    category_names = {category["id"]: category["name"] for category in coco["categories"]}
    annotations_by_image: dict[int, list[dict[str, Any]]] = {}
    for annotation in coco["annotations"]:
        annotations_by_image.setdefault(annotation["image_id"], []).append(annotation)

    start = time.perf_counter()
    enable_mkldnn = not args.device.startswith("cpu")
    detector = LayoutDetection(
        model_name=args.model_name,
        device=args.device,
        enable_mkldnn=enable_mkldnn,
    )
    initialization_seconds = time.perf_counter() - start

    warmup_count = min(args.warmup_pages, len(evaluation_images))
    for image_info in evaluation_images[:warmup_count]:
        with Image.open(images_root / image_info["file_name"]) as source_image:
            image = np.asarray(source_image.convert("RGB"))
        detector.predict(input=image, batch_size=1, threshold=args.score_floor, layout_nms=True)
    if args.device.startswith("gpu"):
        reset_peak = getattr(paddle.device.cuda, "reset_peak_memory_stats", None)
        if reset_peak:
            reset_peak(0)

    pages = []
    latencies = []
    unexpected_labels: dict[str, int] = {}
    for index, image_info in enumerate(evaluation_images):
        image_path = images_root / image_info["file_name"]
        with Image.open(image_path) as source_image:
            image = source_image.convert("RGB")
        gt = []
        for annotation in annotations_by_image.get(image_info["id"], []):
            class_name = GT_CLASS_MAP.get(category_names[annotation["category_id"]])
            if class_name:
                x, y, width, height = annotation["bbox"]
                gt.append({"class": class_name, "bbox_xyxy": [x, y, x + width, y + height]})

        started = time.perf_counter()
        output = next(iter(detector.predict(
            input=np.asarray(image),
            batch_size=1,
            threshold=args.score_floor,
            layout_nms=True,
        )))
        latencies.append(time.perf_counter() - started)
        predictions = []
        for box in _json_payload(output).get("boxes", []):
            source_label = str(box.get("label", "")).casefold()
            class_name = PREDICTION_CLASS_MAP.get(source_label)
            if not class_name:
                if source_label:
                    unexpected_labels[source_label] = unexpected_labels.get(source_label, 0) + 1
                continue
            coordinate = box.get("coordinate", [])
            if len(coordinate) >= 4:
                predictions.append({
                    "class": class_name,
                    "bbox_xyxy": [float(value) for value in coordinate[:4]],
                    "score": float(box.get("score", 0.0)),
                })
        pages.append({"image": image_info["file_name"], "ground_truth": gt, "predictions": predictions})
        if (index + 1) % 100 == 0:
            print(f"{args.model_name}: {index + 1}/{len(evaluation_images)} pages")

    metrics = {name: _class_metrics(pages, name, args.operating_threshold) for name in COMMON_CLASSES}
    ap_values = [float(metrics[name]["ap50_101_point"]) for name in COMMON_CLASSES if metrics[name]["ground_truth"]]
    cuda = paddle.device.cuda if args.device.startswith("gpu") else None
    allocated = getattr(cuda, "max_memory_allocated", None) if cuda else None
    reserved = getattr(cuda, "max_memory_reserved", None) if cuda else None
    gpu_name = getattr(cuda.get_device_properties(0), "name", "GPU") if cuda else None
    latencies.sort()
    result = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "dataset": {
            "id": args.dataset_id,
            "revision": args.dataset_revision,
            "split": args.split,
            "source_split_image_count": len(coco["images"]),
            "image_count": len(pages),
            "coco_json_sha256": _sha256(annotations_path),
            "sampling": "full split" if len(evaluation_images) == len(coco["images"]) else "evenly spaced by source order",
            "evaluated_images": [image["file_name"] for image in evaluation_images],
            "annotation_classes": sorted(category_names.values()),
            "evaluated_classes": list(COMMON_CLASSES),
            "source_class_map": GT_CLASS_MAP,
        },
        "model": {
            "name": args.model_name,
            "device": args.device,
            "gpu_name": gpu_name,
            "paddle_version": paddle.__version__,
        },
        "settings": {
            "score_floor": args.score_floor,
            "operating_threshold": args.operating_threshold,
            "iou_threshold": 0.5,
            "layout_nms": True,
            "enable_mkldnn": enable_mkldnn,
            "warmup_pages": warmup_count,
        },
        "metrics": {
            "macro_ap50_101_point": sum(ap_values) / len(ap_values) if ap_values else 0.0,
            "per_class": metrics,
            "unexpected_predicted_labels": unexpected_labels,
        },
        "resources": {
            "model_initialization_seconds": initialization_seconds,
            "median_page_latency_seconds": statistics.median(latencies),
            "p95_page_latency_seconds": latencies[max(0, math.ceil(0.95 * len(latencies)) - 1)],
            "mean_pages_per_second": len(latencies) / sum(latencies),
            "process_peak_rss_mb": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024,
            "paddle_peak_gpu_allocated_mb": allocated(0) / (1024 * 1024) if allocated else None,
            "paddle_peak_gpu_reserved_mb": reserved(0) / (1024 * 1024) if reserved else None,
        },
        "pages": pages,
    }
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"model": result["model"], "metrics": result["metrics"], "resources": result["resources"]}, indent=2))
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--coco-json", required=True)
    parser.add_argument("--images-root", required=True)
    parser.add_argument("--model-name", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--device", default="gpu:0")
    parser.add_argument("--dataset-id", default=DATASET_ID)
    parser.add_argument("--dataset-revision", default=DATASET_REVISION)
    parser.add_argument("--split", default="val")
    parser.add_argument("--score-floor", type=float, default=0.01)
    parser.add_argument("--operating-threshold", type=float, default=0.30)
    parser.add_argument("--warmup-pages", type=int, default=3)
    parser.add_argument("--max-pages", type=int, default=0, help="Evenly sample this many validation pages; 0 uses the full split.")
    args = parser.parse_args()
    run(args)


if __name__ == "__main__":
    main()
