#!/usr/bin/env python3
"""Compare available OCR engines on the same rendered Vinamilk report pages."""

from __future__ import annotations

import argparse
import gc
import importlib.metadata
import hashlib
import json
import platform
import re
import shutil
import subprocess
import sys
import time
import unicodedata
from html.parser import HTMLParser
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


class _HTMLText(HTMLParser):
    """Collect visible text from Surya 2's HTML layout output."""

    def __init__(self):
        super().__init__()
        self.parts = []
        self.block_tags = {"p", "div", "h1", "h2", "h3", "li", "tr"}

    def handle_starttag(self, tag, _attrs):
        if tag in self.block_tags and self.parts and self.parts[-1] != "\n":
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in self.block_tags and self.parts and self.parts[-1] != "\n":
            self.parts.append("\n")

    def handle_data(self, data):
        text = data.strip()
        if text:
            self.parts.append(text)


def environment_gpu() -> tuple[bool, str]:
    try:
        import torch

        available = bool(torch.cuda.is_available())
        if available:
            return True, torch.cuda.get_device_name(0)
        return False, "CPU; CUDA unavailable"
    except (ImportError, RuntimeError, AttributeError):
        return False, "CPU; PyTorch/CUDA unavailable"


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).casefold()
    return " ".join(re.findall(r"\w+", text, flags=re.UNICODE))


def edit_distance(left: str, right: str) -> int:
    previous = list(range(len(right) + 1))
    for i, left_char in enumerate(left, 1):
        current = [i]
        for j, right_char in enumerate(right, 1):
            current.append(min(current[-1] + 1, previous[j] + 1, previous[j - 1] + (left_char != right_char)))
        previous = current
    return previous[-1]


def error_rate(reference: str, hypothesis: str) -> float:
    if not reference:
        return 0.0 if not hypothesis else 1.0
    return edit_distance(reference, hypothesis) / len(reference)


def summarize_pages(rows: list[dict]) -> dict:
    valid = [row for row in rows if row.get("cer") is not None]
    reference_characters = sum(row["reference_characters"] for row in valid)
    reference_words = sum(row["reference_words"] for row in valid)
    character_edits = sum(row["character_edit_distance"] for row in valid)
    word_edits = sum(row["word_edit_distance"] for row in valid)
    return {
        "valid_pages": len(valid),
        "macro_mean_page_cer": round(sum(row["cer"] for row in valid) / len(valid), 6) if valid else None,
        "micro_cer": round(character_edits / reference_characters, 6) if reference_characters else None,
        "macro_mean_page_wer": round(sum(row["wer"] for row in valid) / len(valid), 6) if valid else None,
        "micro_wer": round(word_edits / reference_words, 6) if reference_words else None,
        "mean_latency_seconds": round(sum(row["latency_seconds"] for row in valid) / len(valid), 3) if valid else None,
    }


def create_engine(engine: str, language: str):
    if engine == "paddleocr":
        import torch
        from paddleocr import PaddleOCR
        # PaddleOCR 2.x exposes `.ocr`; 3.x exposes `.predict`. Keep both
        # versions usable without changing the evaluated engine/model.
        try:
            gpu_available = torch.cuda.is_available()
            return PaddleOCR(
                lang="en", use_doc_orientation_classify=False,
                use_doc_unwarping=False, use_textline_orientation=False,
                device="gpu:0" if gpu_available else "cpu",
                cpu_threads=2, enable_mkldnn=False, show_log=False,
            )
        except (TypeError, ValueError):
            return PaddleOCR(
                lang="en", use_angle_cls=False,
                use_gpu=torch.cuda.is_available(), show_log=False,
                cpu_threads=2, enable_mkldnn=False,
            )
    if engine == "easyocr":
        import easyocr

        import torch
        return easyocr.Reader(["vi", "en"], gpu=torch.cuda.is_available(), verbose=False)
    if engine == "surya":
        try:
            from surya.inference import SuryaInferenceManager
            from surya.recognition import RecognitionPredictor

            return RecognitionPredictor(SuryaInferenceManager())
        except ImportError:
            from surya.recognition import RecognitionPredictor
            from surya.detection import DetectionPredictor

            return RecognitionPredictor(DetectionPredictor())
    return None


def engine_version(engine: str) -> str | None:
    if engine == "tesseract":
        result = subprocess.run(
            ["tesseract", "--version"], capture_output=True, text=True,
            timeout=10, check=False,
        )
        return result.stdout.splitlines()[0] if result.returncode == 0 and result.stdout else None
    package = {"paddleocr": "paddleocr", "easyocr": "easyocr", "surya": "surya-ocr"}.get(engine)
    if package is None:
        return None
    try:
        return importlib.metadata.version(package)
    except importlib.metadata.PackageNotFoundError:
        return None


def run_engine(engine: str, model, image_path: Path, language: str) -> tuple[str, float, str | None]:
    started = time.perf_counter()
    try:
        if engine == "tesseract":
            command = ["tesseract", str(image_path), "stdout", "-l", language, "--psm", "3"]
            result = subprocess.run(command, capture_output=True, text=True, check=True)
            return result.stdout, time.perf_counter() - started, None
        if engine == "paddleocr":
            if hasattr(model, "predict"):
                result = model.predict(str(image_path))
                texts = []
                for page in result:
                    payload = page.json if hasattr(page, "json") else page
                    payload = payload.get("res", payload)
                    texts.extend(payload.get("rec_texts", []))
            else:
                result = model.ocr(str(image_path), cls=False)
                texts = [line[1][0] for page in (result or []) for line in (page or [])]
            return "\n".join(texts), time.perf_counter() - started, None
        if engine == "easyocr":
            result = model.readtext(str(image_path), detail=0, paragraph=True)
            return "\n".join(result), time.perf_counter() - started, None
        if engine == "surya":
            from PIL import Image

            image = Image.open(image_path).convert("RGB")
            prediction = model([image])
            page = prediction[0]
            lines = getattr(page, "text_lines", None)
            if lines is not None:
                text = "\n".join(line.text for line in lines)
            else:
                parser = _HTMLText()
                for block in getattr(page, "blocks", []):
                    markup = block.get("html", "") if isinstance(block, dict) else getattr(block, "html", "")
                    parser.feed(markup)
                text = "".join(parser.parts).strip()
            return text, time.perf_counter() - started, None
        raise ValueError(f"Unknown engine: {engine}")
    except Exception as error:  # Keep failures visible in the report, not as fabricated empty scores.
        return "", time.perf_counter() - started, f"{type(error).__name__}: {error}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=REPO_ROOT / "data/evaluation/ocr_pages.json")
    parser.add_argument("--engines", nargs="+", choices=("paddleocr", "easyocr", "surya", "tesseract"), default=("paddleocr", "easyocr", "surya"))
    parser.add_argument("--dpi", type=int, default=160)
    parser.add_argument("--max-pages", type=int, help="Optional first-N-page slice for resource-constrained smoke runs")
    parser.add_argument("--output", type=Path, default=REPO_ROOT / "artifacts/evaluation/vinamilk-ocr-comparison.json")
    args = parser.parse_args()
    if args.dpi < 72:
        parser.error("--dpi must be at least 72")
    if args.max_pages is not None and args.max_pages < 1:
        parser.error("--max-pages must be positive")

    import fitz

    dataset = json.loads(args.dataset.read_text(encoding="utf-8"))
    output_dir = REPO_ROOT / "artifacts/evaluation/ocr-rendered"
    output_dir.mkdir(parents=True, exist_ok=True)
    engines = {}
    for engine in args.engines:
        available = (shutil.which("tesseract") is not None) if engine == "tesseract" else __import__("importlib.util").util.find_spec(engine) is not None
        engines[engine] = {
            "available": available,
            "engine_version": engine_version(engine) if available else None,
            "pages": [],
            "model_initialization_seconds": None,
            "model_initialization_error": None,
        }

    page_specs = dataset["pages"][:args.max_pages]
    prepared_pages = []
    for page_spec in page_specs:
        pdf_path = REPO_ROOT / page_spec["file"]
        if not pdf_path.is_file():
            raise FileNotFoundError(pdf_path)
        with fitz.open(pdf_path) as pdf:
            page = pdf[page_spec["page"] - 1]
            clip = fitz.Rect(page_spec["clip_rect"]) if page_spec.get("clip_rect") else None
            reference = page_spec.get("reference_text")
            if reference is None:
                reference = page.get_text("text", clip=clip)
            pixmap = page.get_pixmap(dpi=args.dpi, alpha=False, clip=clip)
        image_path = output_dir / f"{page_spec['document_id']}-p{page_spec['page']}-{page_spec.get('id', 'full')}.png"
        pixmap.save(image_path)
        source_pdf_sha256 = hashlib.sha256(pdf_path.read_bytes()).hexdigest()
        rendered_image_sha256 = hashlib.sha256(image_path.read_bytes()).hexdigest()
        normalized_reference = normalize(reference)
        prepared_pages.append({
            "spec": page_spec,
            "image_path": image_path,
            "source_pdf_sha256": source_pdf_sha256,
            "rendered_image_sha256": rendered_image_sha256,
            "reference": normalized_reference,
        })

    # Keep only one neural OCR model resident at a time on memory-constrained hosts.
    for engine in args.engines:
        engine_data = engines[engine]
        model = None
        if engine_data["available"] and engine != "tesseract":
            model_started = time.perf_counter()
            try:
                model = create_engine(engine, "vie+eng")
                engine_data["model_initialization_seconds"] = round(time.perf_counter() - model_started, 3)
            except Exception as error:
                engine_data["available"] = False
                engine_data["model_initialization_error"] = f"{type(error).__name__}: {error}"

        for prepared in prepared_pages:
            page_spec = prepared["spec"]
            normalized_reference = prepared["reference"]
            if not engine_data["available"]:
                error = engine_data["model_initialization_error"] or "engine package or executable unavailable"
                engine_data["pages"].append({"document_id": page_spec["document_id"], "page": page_spec["page"], "error": error})
                continue
            hypothesis, seconds, error = run_engine(engine, model, prepared["image_path"], "vie+eng")
            normalized_hypothesis = normalize(hypothesis)
            reference_words = normalized_reference.split()
            hypothesis_words = normalized_hypothesis.split()
            character_edits = edit_distance(normalized_reference, normalized_hypothesis)
            word_edits = edit_distance(reference_words, hypothesis_words)
            row = {
                "document_id": page_spec["document_id"],
                "page": page_spec["page"],
                "language": page_spec["language"],
                "source_pdf_sha256": prepared["source_pdf_sha256"],
                "rendered_image_sha256": prepared["rendered_image_sha256"],
                "reference_source": "manual_transcription" if page_spec.get("reference_text") is not None else "native_pdf_text_unreviewed",
                "reference_characters": len(normalized_reference),
                "reference_words": len(reference_words),
                "hypothesis_characters": len(normalized_hypothesis),
                "character_edit_distance": character_edits if not error else None,
                "word_edit_distance": word_edits if not error else None,
                "cer": round(character_edits / len(normalized_reference), 6) if not error and normalized_reference else None,
                "wer": round(word_edits / len(reference_words), 6) if not error and reference_words else None,
                "latency_seconds": round(seconds, 3),
                "error": error,
            }
            engine_data["pages"].append(row)
            print(f"{engine}: {page_spec['document_id']} p.{page_spec['page']} CER={row['cer']} in {seconds:.1f}s", file=sys.stderr, flush=True)

        del model
        gc.collect()

    for engine_data in engines.values():
        engine_data["aggregate"] = summarize_pages(engine_data["pages"])
        engine_data["by_language"] = {
            language: summarize_pages([row for row in engine_data["pages"] if row.get("language") == language])
            for language in sorted({page["language"] for page in page_specs})
        }
    cuda_available, gpu_name = environment_gpu()
    report = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "dataset": dataset["dataset_id"],
        "dataset_sha256": __import__("hashlib").sha256(args.dataset.read_bytes()).hexdigest(),
        "reference_method": dataset["reference_method"],
        "reference_quality": dataset.get("reference_quality", "unspecified"),
        "primary_metric_selection_eligible": dataset.get("primary_metric_selection_eligible", False),
        "limitations": dataset["limitations"],
        "render_dpi": args.dpi,
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "gpu": gpu_name,
            "cuda_available": cuda_available,
        },
        "ocr_configuration": {
            "render_dpi": args.dpi,
            "tesseract_language": "vie+eng",
            "tesseract_page_segmentation_mode": 3,
        },
        "engines": engines,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), "engines": {name: data["aggregate"] for name, data in engines.items()}}, ensure_ascii=False, indent=2))
    return 0 if any(value["aggregate"]["valid_pages"] for value in engines.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
