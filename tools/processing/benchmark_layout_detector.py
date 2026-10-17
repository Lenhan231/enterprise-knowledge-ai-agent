"""Benchmark Paddle layout detectors against the ViFinTab validation split.

The source labels table subtypes as rotated quadrilaterals. This pilot collapses
those subtypes to a single ``table`` class and compares axis-aligned envelopes
with axis-aligned detector boxes at IoU 0.50.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import importlib.metadata
import json
import math
import platform
import resource
import statistics
import time
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import Any

import numpy as np
import pyarrow.parquet as pq
from PIL import Image


def _bbox_from_polygon(coordinates: list[float]) -> list[float]:
    xs = coordinates[0::2]
    ys = coordinates[1::2]
    return [min(xs), min(ys), max(xs), max(ys)]


def _iou(first: list[float], second: list[float]) -> float:
    x1 = max(first[0], second[0])
    y1 = max(first[1], second[1])
    x2 = min(first[2], second[2])
    y2 = min(first[3], second[3])
    intersection = max(0.0, x2 - x1) * max(0.0, y2 - y1)
    area_first = max(0.0, first[2] - first[0]) * max(0.0, first[3] - first[1])
    area_second = max(0.0, second[2] - second[0]) * max(0.0, second[3] - second[1])
    union = area_first + area_second - intersection
    return intersection / union if union else 0.0


def _match_at_threshold(
    pages: list[dict[str, Any]], score_threshold: float, iou_threshold: float = 0.5
) -> tuple[int, int, int]:
    matched: set[tuple[int, int]] = set()
    true_positives = false_positives = 0
    predictions = [
        (page_index, prediction)
        for page_index, page in enumerate(pages)
        for prediction in page["predictions"]
        if prediction["score"] >= score_threshold
    ]
    predictions.sort(key=lambda item: item[1]["score"], reverse=True)
    for page_index, prediction in predictions:
        ground_truth = pages[page_index]["ground_truth"]
        best = max(
            (
                (_iou(prediction["bbox_xyxy"], target), index)
                for index, target in enumerate(ground_truth)
                if (page_index, index) not in matched
            ),
            default=(0.0, -1),
        )
        if best[0] >= iou_threshold:
            matched.add((page_index, best[1]))
            true_positives += 1
        else:
            false_positives += 1
    total_ground_truth = sum(len(page["ground_truth"]) for page in pages)
    false_negatives = total_ground_truth - true_positives
    return true_positives, false_positives, false_negatives


def _ap50(pages: list[dict[str, Any]]) -> float:
    total_ground_truth = sum(len(page["ground_truth"]) for page in pages)
    if not total_ground_truth:
        return 0.0
    predictions = [
        (page_index, prediction)
        for page_index, page in enumerate(pages)
        for prediction in page["predictions"]
    ]
    predictions.sort(key=lambda item: item[1]["score"], reverse=True)
    matched: set[tuple[int, int]] = set()
    true_positives: list[int] = []
    false_positives: list[int] = []
    for page_index, prediction in predictions:
        ground_truth = pages[page_index]["ground_truth"]
        best = max(
            (
                (_iou(prediction["bbox_xyxy"], target), index)
                for index, target in enumerate(ground_truth)
                if (page_index, index) not in matched
            ),
            default=(0.0, -1),
        )
        if best[0] >= 0.5:
            matched.add((page_index, best[1]))
            true_positives.append(1)
            false_positives.append(0)
        else:
            true_positives.append(0)
            false_positives.append(1)
    tp = np.cumsum(true_positives)
    fp = np.cumsum(false_positives)
    recall = tp / total_ground_truth
    precision = tp / np.maximum(tp + fp, 1)
    recall_points = np.linspace(0.0, 1.0, 101)
    return float(
        np.mean(
            [
                np.max(precision[recall >= point], initial=0.0)
                for point in recall_points
            ]
        )
    )


def _row_image(row: dict[str, Any]) -> Image.Image:
    encoded = row["image_base64"]
    if encoded.startswith('"'):
        encoded = json.loads(encoded)
    return Image.open(BytesIO(base64.b64decode(encoded))).convert("RGB")


def _iter_rows(path: Path):
    parquet = pq.ParquetFile(path)
    for batch in parquet.iter_batches(
        columns=["image_path", "image_base64", "objects"], batch_size=16
    ):
        for row in batch.to_pylist():
            yield row


def _result_json(result: Any) -> dict[str, Any]:
    payload = result.json
    if isinstance(payload, str):
        payload = json.loads(payload)
    if "res" in payload:
        payload = payload["res"]
    return payload


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def run(args: argparse.Namespace) -> dict[str, Any]:
    import paddle
    from paddleocr import LayoutDetection

    if args.device.startswith("gpu") and (
        not paddle.is_compiled_with_cuda() or paddle.device.cuda.device_count() < 1
    ):
        raise RuntimeError("A CUDA-enabled Paddle runtime and visible GPU are required.")

    source = Path(args.parquet)
    if not source.is_file():
        raise FileNotFoundError(source)
    source_hash = _sha256_file(source)
    rows = _iter_rows(source)

    initialization_started = time.perf_counter()
    detector = LayoutDetection(model_name=args.model_name, device=args.device)
    initialization_seconds = time.perf_counter() - initialization_started

    if args.device.startswith("gpu"):
        reset = getattr(paddle.device.cuda, "reset_peak_memory_stats", None)
        if reset:
            reset(0)

    pages: list[dict[str, Any]] = []
    elapsed: list[float] = []
    unexpected_labels: dict[str, int] = {}
    warmup_count = min(args.warmup_pages, pq.ParquetFile(source).metadata.num_rows)
    warmup_rows = []
    for _ in range(warmup_count):
        warmup_rows.append(next(rows))
    for row in warmup_rows:
        detector.predict(
            input=np.asarray(_row_image(row)),
            batch_size=1,
            threshold=args.score_floor,
            layout_nms=True,
        )

    rows = _iter_rows(source)
    for row_index, row in enumerate(rows):
        image = _row_image(row)
        gt_boxes = [
            _bbox_from_polygon(obj["coordinates"])
            for obj in (row["objects"] or [])
            if len(obj.get("coordinates", [])) >= 8
        ]
        started = time.perf_counter()
        outputs = detector.predict(
            input=np.asarray(image),
            batch_size=1,
            threshold=args.score_floor,
            layout_nms=True,
        )
        elapsed.append(time.perf_counter() - started)
        output = next(iter(outputs))
        predictions = []
        for box in _result_json(output).get("boxes", []):
            label = str(box.get("label", "")).lower()
            if label != "table":
                if label:
                    unexpected_labels[label] = unexpected_labels.get(label, 0) + 1
                continue
            coordinate = box.get("coordinate", [])
            if len(coordinate) < 4:
                continue
            predictions.append(
                {
                    "bbox_xyxy": [float(value) for value in coordinate[:4]],
                    "score": float(box.get("score", 0.0)),
                }
            )
        pages.append(
            {
                "image_path": row["image_path"],
                "ground_truth": gt_boxes,
                "predictions": predictions,
            }
        )
        if (row_index + 1) % 50 == 0:
            print(f"{args.model_name}: {row_index + 1} pages")

    true_positives, false_positives, false_negatives = _match_at_threshold(
        pages, args.operating_threshold
    )
    precision = true_positives / (true_positives + false_positives) if true_positives + false_positives else 0.0
    recall = true_positives / (true_positives + false_negatives) if true_positives + false_negatives else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    peak_gpu_allocated_mb = peak_gpu_reserved_mb = None
    gpu_name = None
    if args.device.startswith("gpu"):
        cuda = paddle.device.cuda
        peak_allocated = getattr(cuda, "max_memory_allocated", None)
        peak_reserved = getattr(cuda, "max_memory_reserved", None)
        if peak_allocated:
            peak_gpu_allocated_mb = peak_allocated(0) / (1024 * 1024)
        if peak_reserved:
            peak_gpu_reserved_mb = peak_reserved(0) / (1024 * 1024)
        properties = cuda.get_device_properties(0)
        gpu_name = getattr(properties, "name", str(properties))

    rss_kb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    timings = sorted(elapsed)
    p95_index = max(0, math.ceil(0.95 * len(timings)) - 1)
    result = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "dataset": {
            "id": "ngnquan/ViFinTab",
            "split": "valid",
            "revision": args.dataset_revision,
            "parquet_sha256": source_hash,
            "pages": len(pages),
            "ground_truth_table_regions": sum(len(page["ground_truth"]) for page in pages),
            "ground_truth_class_handling": "collapse all financial-statement table classes to one table class",
            "ground_truth_geometry": "OBB quadrilateral converted to axis-aligned envelope",
        },
        "model": {
            "name": args.model_name,
            "paddle_version": paddle.__version__,
            "paddleocr_version": importlib.metadata.version("paddleocr"),
            "paddlex_version": importlib.metadata.version("paddlex"),
            "device": args.device,
        },
        "settings": {
            "score_floor": args.score_floor,
            "operating_threshold": args.operating_threshold,
            "iou_threshold": 0.5,
            "warmup_pages": warmup_count,
            "layout_nms": True,
        },
        "metrics": {
            "ap50_101_point": _ap50(pages),
            "precision_at_operating_threshold": precision,
            "recall_at_operating_threshold": recall,
            "f1_at_operating_threshold": f1,
            "true_positives": true_positives,
            "false_positives": false_positives,
            "false_negatives": false_negatives,
            "predicted_table_regions": sum(len(page["predictions"]) for page in pages),
            "unexpected_predicted_labels": unexpected_labels,
        },
        "resources": {
            "model_initialization_seconds_including_first_load": initialization_seconds,
            "median_page_latency_seconds": statistics.median(timings),
            "p95_page_latency_seconds": timings[p95_index],
            "mean_pages_per_second": len(timings) / sum(timings) if sum(timings) else 0.0,
            "process_peak_rss_mb": rss_kb / 1024,
            "gpu_name": gpu_name,
            "paddle_peak_gpu_allocated_mb": peak_gpu_allocated_mb,
            "paddle_peak_gpu_reserved_mb": peak_gpu_reserved_mb,
        },
        "pages": pages,
    }
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"model": args.model_name, "metrics": result["metrics"], "resources": result["resources"]}, indent=2))
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--parquet", required=True)
    parser.add_argument("--model-name", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--device", default="gpu:0")
    parser.add_argument("--score-floor", type=float, default=0.01)
    parser.add_argument("--operating-threshold", type=float, default=0.3)
    parser.add_argument("--warmup-pages", type=int, default=3)
    parser.add_argument("--dataset-revision", default="unknown")
    args = parser.parse_args()
    run(args)


if __name__ == "__main__":
    main()
