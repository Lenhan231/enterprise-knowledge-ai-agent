"""Run one document pipeline on the private Kaggle end-to-end input set."""

from __future__ import annotations

import hashlib
import json
import os
import platform
import resource
import shutil
import subprocess
import sys
import time
import zipfile
from datetime import datetime, timezone
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any


PIPELINE = os.environ.get("END_TO_END_PIPELINE", "")
PIPELINES = {"docling", "mineru", "pp-structurev3"}
INPUT_ROOT = Path("/kaggle/input")
WORK_ROOT = Path("/kaggle/working")


def install_runtime() -> None:
    commands = {
        "docling": [
            "docling[onnxruntime]==2.129.0", "rapidocr==3.9.2", "PyMuPDF==1.27.2.3",
        ],
        "mineru": ["mineru[torch]==4.0.12", "PyMuPDF==1.27.2.3"],
        "pp-structurev3": [
            "paddlepaddle==3.3.1", "paddleocr==3.4.1", "paddlex[ocr]==3.4.3",
            "PyMuPDF==1.27.2.3",
        ],
    }
    packages = commands[PIPELINE]
    if PIPELINE == "docling":
        subprocess.run(["apt-get", "update", "-qq"], check=True)
        subprocess.run(
            ["apt-get", "install", "-y", "tesseract-ocr", "tesseract-ocr-vie"],
            check=True,
        )
    subprocess.run([
        sys.executable, "-m", "pip", "--default-timeout=300", "--retries=5",
        "install", *packages,
    ], check=True)


def package_version(name: str) -> str | None:
    try:
        return version(name)
    except PackageNotFoundError:
        return None


def json_default(value: Any) -> Any:
    if hasattr(value, "tolist"):
        return value.tolist()
    if hasattr(value, "item"):
        return value.item()
    return str(value)


def main() -> int:
    if PIPELINE not in PIPELINES:
        raise ValueError(f"END_TO_END_PIPELINE must be one of {sorted(PIPELINES)}")

    manifests = list(INPUT_ROOT.rglob("manifest.jsonl"))
    if len(manifests) != 1:
        raise RuntimeError(f"Expected one input manifest, found {manifests}")
    data_root = manifests[0].parent
    source_root = data_root / "document_processing_source"
    if not (source_root / "core" / "document_processing" / "document_processor.py").is_file():
        source_zip = data_root / "document_processing_source.zip"
        if not source_zip.is_file():
            raise FileNotFoundError(f"Parser source bundle is missing under {data_root}")
        source_root = WORK_ROOT / "parser-source"
        source_root.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(source_zip) as archive:
            archive.extractall(source_root)
    sys.path.insert(0, str(source_root))

    os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")
    os.environ.setdefault("PADDLE_PDX_CACHE_HOME", "/kaggle/temp/paddlex-cache")
    os.environ["CUDA_VISIBLE_DEVICES"] = ""
    if PIPELINE == "mineru":
        os.environ["MINERU_MODEL_SOURCE"] = "huggingface"
        os.environ["MINERU_MODEL_SMALL_BACKEND"] = "onnx"

    install_runtime()
    if PIPELINE == "mineru":
        subprocess.run([
            "mineru-kit", "models", "download", "--tier", "basic",
            "--small-backend", "onnx", "--source", "huggingface",
        ], check=True)
        subprocess.run([
            "mineru-kit", "models", "verify", "--tier", "basic",
            "--small-backend", "onnx",
        ], check=True)

    config: dict[str, Any] = {"parser_engine": PIPELINE}
    if PIPELINE == "docling":
        config.update({
            "docling_device": "cpu", "docling_num_threads": 4,
            "docling_ocr": True, "docling_ocr_language": "vi",
        })
    elif PIPELINE == "pp-structurev3":
        config.update({
            "paddle_device": "cpu", "paddle_formula_recognition": False,
            "paddle_chart_recognition": False,
        })
    else:
        config["mineru_force_ocr"] = True

    from core.document_processing.document_processor import DocumentProcessor

    processor = DocumentProcessor(config)
    rows = [
        json.loads(line)
        for line in manifests[0].read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    output_root = WORK_ROOT / "results" / PIPELINE
    output_root.mkdir(parents=True, exist_ok=True)
    started_at = datetime.now(timezone.utc).isoformat()
    run_started = time.perf_counter()
    statuses = []

    for item in rows:
        item_started = time.perf_counter()
        record: dict[str, Any] = {
            "document_id": item["document_id"], "pipeline": PIPELINE,
            "source_sha256": item["sha256"],
        }
        try:
            matches = list(data_root.rglob(Path(item["input"]).name))
            if len(matches) != 1:
                raise FileNotFoundError(
                    f"Expected one mounted input named {Path(item['input']).name}, found {len(matches)}"
                )
            source = matches[0].resolve()
            source.relative_to(data_root.resolve())
            content = source.read_bytes()
            if hashlib.sha256(content).hexdigest() != item["sha256"]:
                raise ValueError("input SHA-256 does not match manifest")
            output = processor.process(
                source.name, content,
                {"document_id": item["document_id"], "source_type": "end_to_end_benchmark"},
            )
            record.update({
                "status": "complete", "pages_in_source": item["pages"],
                "chunk_count": len(output.get("chunks", [])),
                "table_count": len(output.get("tables", [])), "output": output,
            })
        except Exception as error:
            record.update({
                "status": "failed", "error_type": type(error).__name__,
                "error": str(error)[:1500],
            })
        record["elapsed_seconds"] = round(time.perf_counter() - item_started, 3)
        (output_root / f"{item['document_id']}.json").write_text(
            json.dumps(record, ensure_ascii=False, indent=2, default=json_default) + "\n",
            encoding="utf-8",
        )
        statuses.append({key: record[key] for key in (
            "document_id", "status", "elapsed_seconds", "pages_in_source",
            "chunk_count", "table_count", "error_type", "error",
        ) if key in record})
        print(f"{record['status']} {item['document_id']} {record['elapsed_seconds']}s", flush=True)

    try:
        gpu = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader"],
            capture_output=True, text=True,
        )
        gpu_info = gpu.stdout.strip() if gpu.returncode == 0 else None
    except FileNotFoundError:
        gpu_info = None
    metadata = {
        "pipeline": PIPELINE, "started_at_utc": started_at,
        "finished_at_utc": datetime.now(timezone.utc).isoformat(),
        "wall_seconds": round(time.perf_counter() - run_started, 3),
        "process_peak_rss_mib": round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 2),
        "python": platform.python_version(), "platform": platform.platform(),
        "cpu_count": os.cpu_count(), "device": "cpu",
        "gpu": gpu_info,
        "package_versions": {
            name: package_version(name) for name in (
                "docling", "rapidocr", "mineru", "paddleocr", "paddlepaddle-gpu", "paddlex", "PyMuPDF",
            )
        },
        "items": statuses,
        "completed": sum(row["status"] == "complete" for row in statuses),
        "failed": sum(row["status"] == "failed" for row in statuses),
    }
    (output_root / "run-metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
    )
    archive = shutil.make_archive(str(WORK_ROOT / f"{PIPELINE}-results"), "zip", output_root)
    print(f"Saved {archive}")
    return 0 if metadata["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
