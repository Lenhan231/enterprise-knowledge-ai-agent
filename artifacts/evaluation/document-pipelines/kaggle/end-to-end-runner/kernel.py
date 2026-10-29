"""Run Docling OCR, layout, and table extraction on reviewed page images."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import torch
from PIL import Image

INPUT_ROOT = Path("/kaggle/input")
OUTPUT_ROOT = Path("/kaggle/working")

manifests = list(INPUT_ROOT.rglob("shared-html-reviewed-pages.jsonl"))
if len(manifests) != 1:
    raise RuntimeError(f"Expected one reviewed-pages manifest, found {manifests}")
input_root = manifests[0].parent
pages = [json.loads(line) for line in manifests[0].read_text(encoding="utf-8").splitlines() if line.strip()]
if not pages:
    raise RuntimeError("The reviewed-pages manifest is empty")
pipeline_config = json.loads((input_root / "pipeline-config.json").read_text(encoding="utf-8"))
ocr_engine = pipeline_config.get("ocr_engine", "tesseract")
if ocr_engine not in {"tesseract", "vietocr"}:
    raise ValueError(f"Unsupported OCR engine: {ocr_engine}")
if not torch.cuda.is_available():
    raise RuntimeError("Kaggle did not allocate a GPU")

print("GPU:", torch.cuda.get_device_name(0), flush=True)
print("Reviewed pages:", len(pages), flush=True)
subprocess.run(["apt-get", "update", "-qq"], check=True)
subprocess.run(["apt-get", "install", "-y", "tesseract-ocr", "tesseract-ocr-vie"], check=True)
subprocess.run([
    sys.executable, "-m", "pip", "--default-timeout=300", "--retries=5",
    "install", "docling[onnxruntime]==2.129.0", "PyMuPDF==1.27.2.3",
], check=True)
if ocr_engine == "vietocr":
    subprocess.run([
        sys.executable, "-m", "pip", "--default-timeout=300", "--retries=5",
        "install", "--no-deps", "vietocr==0.3.13", "rapidocr==3.9.2",
    ], check=True)
    subprocess.run([
        sys.executable, "-m", "pip", "--default-timeout=300", "--retries=5",
        "install", "einops==0.2.0", "gdown==4.4.0",
    ], check=True)

import onnxruntime as ort

if "CUDAExecutionProvider" not in ort.get_available_providers():
    raise RuntimeError(f"ONNX Runtime has no CUDA provider: {ort.get_available_providers()}")

from docling.datamodel.accelerator_options import AcceleratorDevice, AcceleratorOptions
from docling.datamodel.base_models import InputFormat
from docling.datamodel.object_detection_engine_options import TransformersObjectDetectionEngineOptions
from docling.datamodel.pipeline_options import (
    LayoutObjectDetectionOptions,
    PdfPipelineOptions,
    TableFormerMode,
    TableStructureOptions,
    TesseractCliOcrOptions,
)
from docling.datamodel.stage_model_specs import ObjectDetectionModelSpec
from docling.document_converter import DocumentConverter, ImageFormatOption

if ocr_engine == "vietocr":
    sys.path.insert(0, str(input_root))
    from docling_vietocr import VietOcrOptions, register_vietocr

    register_vietocr()
    ocr_options = VietOcrOptions()
    engine_name = "docling-vietocr-heron-tableformer"
    ocr_name = "VietOCR vgg_seq2seq width 512 greedy; RapidOCR line detection"
else:
    ocr_options = TesseractCliOcrOptions(lang=["vie", "eng"], psm=6)
    engine_name = "docling-tesseract-heron-tableformer"
    ocr_name = "Tesseract vie+eng PSM 6"

options = PdfPipelineOptions(
    accelerator_options=AcceleratorOptions(device=AcceleratorDevice.CUDA, num_threads=2),
    do_ocr=True,
    do_table_structure=True,
    layout_options=LayoutObjectDetectionOptions(
        engine_options=TransformersObjectDetectionEngineOptions(score_threshold=0.4),
        model_spec=ObjectDetectionModelSpec(
            name="layout_heron", repo_id="docling-project/docling-layout-heron",
        ),
    ),
    table_structure_options=TableStructureOptions(
        mode=TableFormerMode.ACCURATE,
        do_cell_matching=True,
    ),
    ocr_options=ocr_options,
)
converter = DocumentConverter(
    format_options={InputFormat.IMAGE: ImageFormatOption(pipeline_options=options)},
)
vietocr_model = None
if ocr_engine == "vietocr":
    converter.initialize_pipeline(InputFormat.IMAGE)
    pipeline = next(iter(converter.initialized_pipelines.values()))
    vietocr_model = pipeline.ocr_model
raw_root = OUTPUT_ROOT / "docling-raw-pages"
raw_root.mkdir(parents=True, exist_ok=True)
started_at = datetime.now(timezone.utc)
run_started = time.perf_counter()
page_seconds = {}
page_status = []

for row in pages:
    page_id = row["reference_id"]
    if vietocr_model is not None:
        vietocr_model.current_reference_id = page_id
    image_path = input_root / row["image_file"]
    page_started = time.perf_counter()
    try:
        digest = hashlib.sha256(image_path.read_bytes()).hexdigest()
        if digest != row["image_sha256"]:
            raise ValueError(f"Input image hash mismatch: {page_id}")
        with Image.open(image_path) as image:
            image.verify()
        result = converter.convert(image_path)
        document = result.document.export_to_dict()
        status = str(result.status)
        (raw_root / f"{page_id}.json").write_text(
            json.dumps(document, ensure_ascii=False) + "\n", encoding="utf-8",
        )
        state = "failed" if "FAILURE" in status.upper() else "complete"
        page_status.append({"reference_id": page_id, "status": state, "conversion_status": status})
        print(page_id, status, flush=True)
    except Exception as error:
        (raw_root / f"{page_id}.json").write_text(
            json.dumps({"error_type": type(error).__name__, "error": str(error)[:1500]}) + "\n",
            encoding="utf-8",
        )
        page_status.append({"reference_id": page_id, "status": "failed", "error": str(error)[:1500]})
        print(page_id, "failed:", error, flush=True)
    page_seconds[page_id] = round(time.perf_counter() - page_started, 3)

metadata = {
    "engine": engine_name,
    "model": "Docling Layout Heron + TableFormer accurate",
    "ocr": ocr_name,
    "device": torch.cuda.get_device_name(0),
    "started_at_utc": started_at.isoformat(),
    "finished_at_utc": datetime.now(timezone.utc).isoformat(),
    "wall_seconds": round(time.perf_counter() - run_started, 3),
    "page_count": len(pages),
    "successful_pages": sum(page["status"] != "failed" for page in page_status),
    "failed_pages": sum(page["status"] == "failed" for page in page_status),
    "page_seconds": page_seconds,
    "pages": page_status,
}
(OUTPUT_ROOT / "docling-metadata.json").write_text(
    json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
)
print("Wrote Docling raw page results", flush=True)
