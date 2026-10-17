"""Evaluate the DocLayout-YOLO DocStructBench checkpoint on HCMUS COCO pages."""

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

from benchmark_hcmus_layout import (
    COMMON_CLASSES,
    DATASET_ID,
    DATASET_REVISION,
    GT_CLASS_MAP,
    _class_metrics,
    _select_images,
)


YOLO_CLASS_MAP = {
    "title": "title",
    "plain text": "text",
    "figure": "figure",
    "table": "table",
    "formula": "formula",
    "isolate_formula": "formula",
    "signature": "signature",
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def run(args: argparse.Namespace) -> dict[str, Any]:
    import torch
    from PIL import Image
    from doclayout_yolo import YOLOv10

    if args.device.startswith("cuda") and not torch.cuda.is_available():
        raise RuntimeError("A CUDA-enabled PyTorch runtime and visible GPU are required.")
    if args.device == "cpu":
        torch.set_num_threads(args.cpu_threads)

    coco_path = Path(args.coco_json)
    image_root = Path(args.images_root)
    checkpoint_path = Path(args.model_path)
    coco = json.loads(coco_path.read_text())
    selected_images = _select_images(coco["images"], args.max_pages)
    categories = {category["id"]: category["name"] for category in coco["categories"]}
    annotations: dict[int, list[dict[str, Any]]] = {}
    for annotation in coco["annotations"]:
        annotations.setdefault(annotation["image_id"], []).append(annotation)

    init_started = time.perf_counter()
    detector = YOLOv10(str(checkpoint_path))
    initialization_seconds = time.perf_counter() - init_started
    warmup_count = min(args.warmup_pages, len(selected_images))
    for image_info in selected_images[:warmup_count]:
        detector.predict(
            str(image_root / image_info["file_name"]),
            imgsz=args.image_size,
            conf=args.score_floor,
            iou=args.nms_iou,
            half=args.half,
            device=args.device,
            verbose=False,
        )
    if args.device.startswith("cuda"):
        torch.cuda.reset_peak_memory_stats()

    pages = []
    latencies = []
    unexpected_labels: dict[str, int] = {}
    for index, image_info in enumerate(selected_images):
        gt = []
        for annotation in annotations.get(image_info["id"], []):
            name = GT_CLASS_MAP.get(categories[annotation["category_id"]])
            if name:
                x, y, width, height = annotation["bbox"]
                gt.append({"class": name, "bbox_xyxy": [x, y, x + width, y + height]})

        if args.device.startswith("cuda"):
            torch.cuda.synchronize()
        started = time.perf_counter()
        result = detector.predict(
            str(image_root / image_info["file_name"]),
            imgsz=args.image_size,
            conf=args.score_floor,
            iou=args.nms_iou,
            half=args.half,
            device=args.device,
            verbose=False,
        )[0]
        if args.device.startswith("cuda"):
            torch.cuda.synchronize()
        latencies.append(time.perf_counter() - started)

        predictions = []
        if result.boxes is not None:
            for coordinate, class_id, score in zip(
                result.boxes.xyxy.tolist(),
                result.boxes.cls.tolist(),
                result.boxes.conf.tolist(),
            ):
                source_label = str(result.names[int(class_id)]).casefold()
                class_name = YOLO_CLASS_MAP.get(source_label)
                if class_name:
                    predictions.append({
                        "class": class_name,
                        "bbox_xyxy": [float(value) for value in coordinate],
                        "score": float(score),
                    })
                else:
                    unexpected_labels[source_label] = unexpected_labels.get(source_label, 0) + 1
        pages.append({"image": image_info["file_name"], "ground_truth": gt, "predictions": predictions})
        if (index + 1) % 25 == 0:
            print(f"DocLayout-YOLO: {index + 1}/{len(selected_images)} pages")

    metrics = {name: _class_metrics(pages, name, args.operating_threshold) for name in COMMON_CLASSES}
    ap_values = [float(metrics[name]["ap50_101_point"]) for name in COMMON_CLASSES if metrics[name]["ground_truth"]]
    latencies.sort()
    result = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "dataset": {
            "id": args.dataset_id,
            "revision": args.dataset_revision,
            "split": args.split,
            "source_split_image_count": len(coco["images"]),
            "image_count": len(pages),
            "coco_json_sha256": _sha256(coco_path),
            "sampling": "full split" if len(selected_images) == len(coco["images"]) else "evenly spaced by source order",
            "evaluated_images": [image["file_name"] for image in selected_images],
            "evaluated_classes": list(COMMON_CLASSES),
            "ground_truth_class_map": GT_CLASS_MAP,
        },
        "model": {
            "name": "DocLayout-YOLO-DocStructBench",
            "architecture": "YOLOv10",
            "checkpoint_sha256": _sha256(checkpoint_path),
            "device": args.device,
            "torch_version": torch.__version__,
            "gpu_name": torch.cuda.get_device_name(0) if args.device.startswith("cuda") else None,
        },
        "settings": {
            "image_size": args.image_size,
            "score_floor": args.score_floor,
            "operating_threshold": args.operating_threshold,
            "nms_iou": args.nms_iou,
            "half_precision": args.half,
            "evaluation_iou_threshold": 0.5,
            "warmup_pages": warmup_count,
            "cpu_threads": args.cpu_threads if args.device == "cpu" else None,
            "class_map": YOLO_CLASS_MAP,
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
            "torch_peak_gpu_allocated_mb": torch.cuda.max_memory_allocated() / (1024 * 1024) if args.device.startswith("cuda") else None,
            "torch_peak_gpu_reserved_mb": torch.cuda.max_memory_reserved() / (1024 * 1024) if args.device.startswith("cuda") else None,
        },
        "pages": pages,
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"model": result["model"], "metrics": result["metrics"], "resources": result["resources"]}, indent=2))
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--coco-json", required=True)
    parser.add_argument("--images-root", required=True)
    parser.add_argument("--model-path", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--dataset-id", default=DATASET_ID)
    parser.add_argument("--dataset-revision", default=DATASET_REVISION)
    parser.add_argument("--split", default="val")
    parser.add_argument("--image-size", type=int, default=1024)
    parser.add_argument("--score-floor", type=float, default=0.01)
    parser.add_argument("--operating-threshold", type=float, default=0.30)
    parser.add_argument("--nms-iou", type=float, default=0.70)
    parser.add_argument("--half", action="store_true", help="Use FP16 inference on a supported GPU.")
    parser.add_argument("--warmup-pages", type=int, default=3)
    parser.add_argument("--max-pages", type=int, default=0)
    parser.add_argument("--cpu-threads", type=int, default=8)
    run(parser.parse_args())


if __name__ == "__main__":
    main()
