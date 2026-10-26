"""Benchmark VietOCR on the owner-reviewed full-page OCR references."""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import unicodedata
from datetime import datetime, timezone
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

TRACK_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(TRACK_ROOT / "tools"))

from metrics.text_metrics import character_error_count, token_error_count  # noqa: E402
from runners.line_detection import create_line_detector, crop_line, detect_line_boxes  # noqa: E402


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFC", text).casefold()).strip()


def score(references: list[dict], predictions: list[dict]) -> dict:
    from pyvi import ViTokenizer

    prediction_by_id = {row["reference_id"]: row for row in predictions}
    char_edits = ref_chars = pyvi_edits = ref_pyvi_words = space_edits = ref_space_words = 0
    pages = []
    for reference in references:
        prediction = prediction_by_id[reference["reference_id"]]
        expected, actual = normalize(reference["ocr_reference_text"]), normalize(prediction.get("text", ""))
        ce, nc = character_error_count(expected, actual)
        reference_words = ViTokenizer.tokenize(expected).split()
        predicted_words = ViTokenizer.tokenize(actual).split()
        we, nw = token_error_count(reference_words, predicted_words)
        se, ns = token_error_count(expected.split(), actual.split())
        char_edits += ce; ref_chars += nc
        pyvi_edits += we; ref_pyvi_words += nw
        space_edits += se; ref_space_words += ns
        pages.append({
            "reference_id": reference["reference_id"],
            "status": prediction["status"],
            "line_count": prediction.get("line_count", 0),
            "cer": ce / nc if nc else None,
            "wer_pyvi": we / nw if nw else None,
            "wer_whitespace": se / ns if ns else None,
        })
    return {
        "pages": len(references),
        "micro_cer": char_edits / ref_chars if ref_chars else None,
        "micro_wer_pyvi": pyvi_edits / ref_pyvi_words if ref_pyvi_words else None,
        "micro_wer_whitespace": space_edits / ref_space_words if ref_space_words else None,
        "character_edits": char_edits,
        "reference_characters": ref_chars,
        "wer_pyvi_edits": pyvi_edits,
        "reference_pyvi_words": ref_pyvi_words,
        "wer_whitespace_edits": space_edits,
        "reference_whitespace_words": ref_space_words,
        "pages_detail": pages,
    }


def run(args: argparse.Namespace) -> None:
    try:
        import torch
        from vietocr.tool.config import Cfg
        from vietocr.tool.predictor import Predictor
    except ImportError as error:
        raise SystemExit(
            f"Missing OCR runtime package: {error.name}. Install VietOCR and its runtime packages "
            "or add their directory to PYTHONPATH."
        ) from error

    references = read_jsonl(TRACK_ROOT / "data/ocr/reference.jsonl")
    if args.page_id:
        references = [row for row in references if row["reference_id"] == args.page_id]
        if not references:
            raise SystemExit(f"No OCR reference found for page: {args.page_id}")
    run_id = args.run_id or f"vietocr-html-{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}"
    output_dir = (args.output_dir or TRACK_ROOT / "results/shared-html" / run_id).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    device = "cuda:0" if torch.cuda.is_available() else "cpu"
    config = Cfg.load_config_from_name("vgg_seq2seq")
    config["device"] = device
    config["dataset"]["image_max_width"] = args.max_width
    config["predictor"]["beamsearch"] = False
    model_started = time.perf_counter()
    recognizer = Predictor(config)
    model_init_seconds = round(time.perf_counter() - model_started, 3)
    detector = create_line_detector()

    started_at = datetime.now(timezone.utc)
    page_runs = []
    prediction_path = output_dir / "predictions.jsonl"
    detection_seconds = recognition_seconds = 0.0
    with prediction_path.open("w", encoding="utf-8") as predictions_file:
        for reference in references:
            page_started = time.perf_counter()
            line_outputs = []
            try:
                image_path = TRACK_ROOT / "data" / reference["source_image"]
                image = cv2.imread(str(image_path))
                if image is None:
                    raise ValueError(f"Could not read source image: {image_path}")
                if args.rotate == 90:
                    image = cv2.rotate(image, cv2.ROTATE_90_CLOCKWISE)
                elif args.rotate == 180:
                    image = cv2.rotate(image, cv2.ROTATE_180)
                elif args.rotate == 270:
                    image = cv2.rotate(image, cv2.ROTATE_90_COUNTERCLOCKWISE)
                detected_started = time.perf_counter()
                boxes = detect_line_boxes(detector, image)
                detection_seconds += time.perf_counter() - detected_started
                for box in ([] if boxes is None else boxes):
                    line = crop_line(image, np.asarray(box))
                    if line.shape[0] > line.shape[1] * 1.5:
                        line = cv2.rotate(line, cv2.ROTATE_90_CLOCKWISE)
                    rgb_line = cv2.cvtColor(line, cv2.COLOR_BGR2RGB)
                    recognized_started = time.perf_counter()
                    text = recognizer.predict(Image.fromarray(rgb_line))
                    recognition_seconds += time.perf_counter() - recognized_started
                    line_outputs.append({"bbox": np.asarray(box).tolist(), "text": str(text or "").strip()})
                row = {
                    "reference_id": reference["reference_id"],
                    "document_id": reference["document_id"],
                    "source_page_number_1based": reference["source_page_number_1based"],
                    "source_image": reference["source_image"],
                    "rotation_degrees_clockwise": args.rotate,
                    "status": "ok",
                    "line_count": len(line_outputs),
                    "text": "\n".join(line["text"] for line in line_outputs if line["text"]),
                    "lines": line_outputs,
                }
            except Exception as error:
                row = {
                    "reference_id": reference["reference_id"],
                    "document_id": reference["document_id"],
                    "source_page_number_1based": reference["source_page_number_1based"],
                    "rotation_degrees_clockwise": args.rotate,
                    "status": "failed",
                    "error": repr(error),
                    "line_count": len(line_outputs),
                    "text": "\n".join(line["text"] for line in line_outputs if line["text"]),
                    "lines": line_outputs,
                }
            predictions_file.write(json.dumps(row, ensure_ascii=False) + "\n")
            predictions_file.flush()
            page_runs.append({"reference_id": row["reference_id"], "status": row["status"],
                              "seconds": round(time.perf_counter() - page_started, 3),
                              "line_count": row["line_count"]})
            print(f"{row['reference_id']} {row['status']} ({row['line_count']} lines)", flush=True)

    predictions = read_jsonl(prediction_path)
    evaluation = score(references, predictions)
    (output_dir / "evaluation.json").write_text(json.dumps(evaluation, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    try:
        package_versions = {name: version(name) for name in ("vietocr", "rapidocr", "torch", "onnxruntime")}
    except PackageNotFoundError:
        package_versions = {}
    metadata = {
        "dataset": "shared-html-owner-reviewed",
        "run_id": run_id,
        "engine": "RapidOCR detection-only + VietOCR vgg_seq2seq greedy",
        "device": device,
        "max_width": args.max_width,
        "rotation_degrees_clockwise": args.rotate,
        "page_filter": args.page_id,
        "page_count": len(references),
        "successful_pages": sum(row["status"] == "ok" for row in page_runs),
        "failed_pages": sum(row["status"] == "failed" for row in page_runs),
        "model_initialization_seconds": model_init_seconds,
        "detection_seconds": round(detection_seconds, 3),
        "recognition_seconds": round(recognition_seconds, 3),
        "finished_at_utc": datetime.now(timezone.utc).isoformat(),
        "packages": package_versions,
        "pages": page_runs,
        "predictions": str(prediction_path),
        "evaluation": str(output_dir / "evaluation.json"),
    }
    (output_dir / "run-metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"run_id": run_id, "device": device, "successful_pages": metadata["successful_pages"],
                      "failed_pages": metadata["failed_pages"], "micro_cer": evaluation["micro_cer"],
                      "micro_wer_pyvi": evaluation["micro_wer_pyvi"], "output_dir": str(output_dir)}, ensure_ascii=False))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", help="Defaults to vietocr-html-<UTC timestamp>")
    parser.add_argument("--output-dir", type=Path, help="Defaults to results/shared-html/<run-id>")
    parser.add_argument("--max-width", type=int, default=512, help="VietOCR resize ceiling, as in the previous benchmark")
    parser.add_argument("--page-id", help="Optionally run one reference page for a focused diagnostic")
    parser.add_argument("--rotate", type=int, choices=(0, 90, 180, 270), default=0,
                        help="Rotate each selected source image clockwise before line detection")
    run(parser.parse_args())


if __name__ == "__main__":
    main()
