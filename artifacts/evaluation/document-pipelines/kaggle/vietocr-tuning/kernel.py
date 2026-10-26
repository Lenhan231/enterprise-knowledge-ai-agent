"""Tune VietOCR inference settings on fixed owner-reviewed pilot pages."""

from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

subprocess.run([
    sys.executable, "-m", "pip", "install", "--quiet", "--no-deps", "vietocr==0.3.13", "rapidocr==3.9.2", "onnxruntime==1.23.2",
], check=True)

import cv2
import numpy as np
import torch
from PIL import Image
from rapidocr import RapidOCR
from vietocr.tool.config import Cfg
from vietocr.tool.predictor import Predictor

INPUT_ROOT = Path("/kaggle/input")
OUTPUT_ROOT = Path("/kaggle/working")
CANDIDATES = [
    {"max_width": 512, "beamsearch": False},
    {"max_width": 512, "beamsearch": True},
]

manifests = list(INPUT_ROOT.rglob("shared-html-reviewed-pages.jsonl"))
if len(manifests) != 1:
    raise RuntimeError(f"Expected one reviewed-pages manifest, found {manifests}")
input_root = manifests[0].parent
pages = [json.loads(line) for line in manifests[0].read_text().splitlines() if line.strip()]
if not pages:
    raise RuntimeError("The reviewed-pages dataset is empty")
if not torch.cuda.is_available():
    raise RuntimeError("Kaggle did not allocate a GPU")
print("GPU:", torch.cuda.get_device_name(0), flush=True)

# Detect once and reuse the exact same RapidOCR line crops for every candidate.
detector = RapidOCR()
fixed_lines = []
detection_seconds = 0.0
for page in pages:
    image = cv2.imread(str(input_root / page["image_file"]))
    if image is None:
        raise RuntimeError(f"Cannot read {page['image_file']}")
    started = time.perf_counter()
    result = detector(image, use_det=True, use_cls=False, use_rec=False)
    detection_seconds += time.perf_counter() - started
    lines = []
    boxes = getattr(result, "boxes", None)
    for box in ([] if boxes is None else boxes):
        quad = np.asarray(box, dtype=np.float32)
        top_left, top_right, bottom_right, bottom_left = quad
        width = max(int(np.linalg.norm(top_right - top_left)), int(np.linalg.norm(bottom_right - bottom_left)), 1)
        height = max(int(np.linalg.norm(bottom_left - top_left)), int(np.linalg.norm(bottom_right - top_right)), 1)
        target = np.array([[0, 0], [width - 1, 0], [width - 1, height - 1], [0, height - 1]], dtype=np.float32)
        line = cv2.warpPerspective(image, cv2.getPerspectiveTransform(quad, target), (width, height))
        if line.shape[0] > line.shape[1] * 1.5:
            line = cv2.rotate(line, cv2.ROTATE_90_CLOCKWISE)
        lines.append((quad.tolist(), Image.fromarray(cv2.cvtColor(line, cv2.COLOR_BGR2RGB))))
    fixed_lines.append((page, lines))

all_predictions = []
for candidate in CANDIDATES:
    config = Cfg.load_config_from_name("vgg_seq2seq")
    config["device"] = "cuda:0"
    config["dataset"]["image_max_width"] = candidate["max_width"]
    config["predictor"]["beamsearch"] = candidate["beamsearch"]
    recognizer = Predictor(config)
    for page, lines in fixed_lines:
        texts = [str(recognizer.predict(line) or "").strip() for _, line in lines]
        all_predictions.append({
            "config": candidate,
            "reference_id": page["reference_id"],
            "document_id": page["document_id"],
            "source_page_number_1based": page["source_page_number_1based"],
            "status": "ok",
            "line_count": len(lines),
            "text": "\n".join(text for text in texts if text),
            "lines": [{"bbox": box, "text": text} for (box, _), text in zip(lines, texts)],
        })
        print(candidate, page["reference_id"], len(lines), "lines", flush=True)
    del recognizer
    torch.cuda.empty_cache()

(OUTPUT_ROOT / "predictions.jsonl").write_text(
    "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in all_predictions),
    encoding="utf-8",
)
(OUTPUT_ROOT / "run-metadata.json").write_text(json.dumps({
    "engine": "RapidOCR detection-only (cached once) + VietOCR vgg_seq2seq",
    "device": torch.cuda.get_device_name(0),
    "owner_reviewed_page_ids": [page["reference_id"] for page in pages],
    "candidates": CANDIDATES,
    "fixed_line_detection_seconds": round(detection_seconds, 3),
    "prediction_count": len(all_predictions),
}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
