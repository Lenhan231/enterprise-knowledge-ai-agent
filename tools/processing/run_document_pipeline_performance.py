"""Measure warmed, repeated inference for one document pipeline on fixed pages."""

from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import statistics
import subprocess
import sys
import tempfile
import threading
import time
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

import psutil


def percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    position = (len(ordered) - 1) * fraction
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    weight = position - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


class ResourceSampler:
    """Sample runner process-tree RSS and GPU process/device memory once per second."""

    def __init__(self) -> None:
        self.process = psutil.Process()
        self.stop_event = threading.Event()
        self.peak_tree_rss_bytes = 0
        self.peak_gpu_process_mib: int | None = None
        self.peak_gpu_device_mib: int | None = None
        self.thread = threading.Thread(target=self._sample, daemon=True)

    def start(self) -> None:
        self.thread.start()

    def stop(self) -> dict:
        self.stop_event.set()
        self.thread.join()
        return {
            "sample_interval_seconds": 1,
            "peak_process_tree_rss_mib": round(self.peak_tree_rss_bytes / (1024 * 1024), 1),
            "peak_gpu_process_memory_mib": self.peak_gpu_process_mib,
            "peak_gpu_device_used_mib": self.peak_gpu_device_mib,
            "gpu_memory_note": "GPU process memory is matched by process-tree PID when nvidia-smi exposes it; device-used memory is system-wide.",
            "host_memory_note": "Process-tree RSS is the sum of RSS values and may count shared pages more than once.",
        }

    def _sample(self) -> None:
        while not self.stop_event.is_set():
            try:
                processes = [self.process, *self.process.children(recursive=True)]
                pids = set()
                total_rss = 0
                for process in processes:
                    try:
                        pids.add(process.pid)
                        total_rss += process.memory_info().rss
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        continue
                self.peak_tree_rss_bytes = max(self.peak_tree_rss_bytes, total_rss)
                self._sample_gpu(pids)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
            self.stop_event.wait(1)

    def _sample_gpu(self, pids: set[int]) -> None:
        try:
            device = subprocess.run(
                ["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=5,
            )
        except (OSError, subprocess.SubprocessError):
            return
        if device.returncode == 0:
            values = [int(line.strip()) for line in device.stdout.splitlines() if line.strip().isdigit()]
            if values:
                current = max(values)
                self.peak_gpu_device_mib = max(self.peak_gpu_device_mib or 0, current)

        try:
            processes = subprocess.run(
                ["nvidia-smi", "--query-compute-apps=pid,used_memory", "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=5,
            )
        except (OSError, subprocess.SubprocessError):
            return
        if processes.returncode == 0:
            current = 0
            for line in processes.stdout.splitlines():
                parts = [part.strip() for part in line.split(",")]
                if len(parts) == 2:
                    try:
                        pid, memory = int(parts[0]), int(parts[1])
                    except ValueError:
                        continue
                    if pid in pids:
                        current += memory
            if current:
                self.peak_gpu_process_mib = max(self.peak_gpu_process_mib or 0, current)


def initialize(engine: str):
    started = time.perf_counter()
    if engine == "pp-structurev3":
        from paddleocr import PPStructureV3

        pipeline = PPStructureV3(
            device="gpu:0",
            layout_detection_model_name="PP-DocLayout-S",
            text_detection_model_name="PP-OCRv5_mobile_det",
            text_recognition_model_name="PP-OCRv5_mobile_rec",
            use_doc_orientation_classify=False,
            use_doc_unwarping=False,
            use_textline_orientation=False,
            use_formula_recognition=False,
            use_chart_recognition=False,
            use_seal_recognition=False,
        )
        return pipeline, time.perf_counter() - started

    if engine == "docling":
        from docling.datamodel.accelerator_options import AcceleratorDevice, AcceleratorOptions
        from docling.datamodel.base_models import InputFormat
        from docling.datamodel.pipeline_options import PdfPipelineOptions, RapidOcrOptions
        from docling.document_converter import DocumentConverter, PdfFormatOption

        options = PdfPipelineOptions(
            accelerator_options=AcceleratorOptions(device=AcceleratorDevice.CUDA),
            do_ocr=True,
            do_table_structure=True,
            ocr_options=RapidOcrOptions(lang=["vi"], backend="onnxruntime"),
        )
        converter = DocumentConverter(
            format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=options)}
        )
        return converter, time.perf_counter() - started

    return None, time.perf_counter() - started


def infer(engine: str, model, pdf: Path, output_dir: Path | None = None) -> None:
    if engine == "pp-structurev3":
        list(model.predict(input=str(pdf)))
    elif engine == "docling":
        model.convert(pdf)
    else:
        assert output_dir is not None
        output_dir.mkdir(parents=True, exist_ok=True)
        result = subprocess.run(
            ["mineru-kit", "parse", str(pdf), "-o", str(output_dir), "--format", "zip", "--tier", "basic"],
            capture_output=True, text=True,
        )
        archives = list(output_dir.rglob("*.zip"))
        if result.returncode or not archives:
            raise RuntimeError(f"MinerU failed for {pdf.name}: {result.stderr[-1200:]}")


def package_versions(names: list[str]) -> dict[str, str | None]:
    versions = {}
    for name in names:
        try:
            versions[name] = version(name)
        except PackageNotFoundError:
            versions[name] = None
    return versions


def run(args: argparse.Namespace) -> dict:
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    input_dir = args.manifest.parent / "inputs"
    inputs = [input_dir / Path(row["input_pdf"]).name for row in manifest["pages"]]
    missing = [path for path in inputs if not path.is_file()]
    if missing:
        raise FileNotFoundError(f"Missing {len(missing)} benchmark PDFs: {missing[:3]}")

    os.environ["CUDA_VISIBLE_DEVICES"] = "0"
    sampler = ResourceSampler()
    sampler.start()
    model, initialization_seconds = initialize(args.engine)
    warmup_seconds = None
    with tempfile.TemporaryDirectory(prefix="layout-perf-") as temp:
        temp_root = Path(temp)
        warmup_dir = temp_root / "warmup"
        started = time.perf_counter()
        infer(args.engine, model, inputs[0], warmup_dir if args.engine == "mineru" else None)
        warmup_seconds = time.perf_counter() - started

        repeats = []
        for repeat in range(1, args.repeats + 1):
            page_rows = []
            pass_started = time.perf_counter()
            for page_index, pdf in enumerate(inputs):
                output_dir = temp_root / f"repeat-{repeat}" / pdf.stem if args.engine == "mineru" else None
                started = time.perf_counter()
                try:
                    infer(args.engine, model, pdf, output_dir)
                    status, error = "ok", None
                except Exception as exc:
                    status, error = "error", repr(exc)
                elapsed = time.perf_counter() - started
                page_rows.append({"id": pdf.stem, "status": status, "seconds": elapsed, "error": error})
                if output_dir is not None:
                    shutil.rmtree(output_dir.parent, ignore_errors=True)
                if page_index and page_index % 25 == 0:
                    print(f"repeat={repeat}/{args.repeats} pages={page_index}/{len(inputs)}", flush=True)
            page_seconds = [row["seconds"] for row in page_rows if row["status"] == "ok"]
            repeats.append({
                "repeat": repeat,
                "pages_succeeded": len(page_seconds),
                "pages_failed": [row for row in page_rows if row["status"] != "ok"],
                "total_wall_seconds": time.perf_counter() - pass_started,
                "median_seconds_per_page": statistics.median(page_seconds) if page_seconds else None,
                "p95_seconds_per_page": percentile(page_seconds, 0.95) if page_seconds else None,
                "pages": page_rows,
            })
            print(f"completed repeat {repeat}: {len(page_seconds)}/{len(inputs)}", flush=True)
    resource_usage = sampler.stop()
    return {
        "dataset_id": manifest["dataset_id"],
        "engine": args.engine,
        "measurement_protocol": {
            "input_pages": len(inputs),
            "warmup_pages": 1,
            "measured_repeats": args.repeats,
            "measured_page_latency": "wall time for the parser call; MinerU includes one CLI process and output generation per input",
            "resource_sampling": "one-second process-tree RSS and nvidia-smi GPU sampling across initialization, warm-up, and measured repeats",
        },
        "initialization_seconds": initialization_seconds,
        "warmup_page_id": inputs[0].stem,
        "warmup_seconds": warmup_seconds,
        "repeats": repeats,
        "resources": resource_usage,
        "system": {
            "python": sys.version,
            "platform": platform.platform(),
            "cpu_count": os.cpu_count(),
            "gpu": subprocess.run(["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader"], capture_output=True, text=True).stdout.strip(),
        },
        "packages": package_versions(["paddlepaddle-gpu", "paddleocr", "paddlex", "mineru", "docling", "torch", "psutil"]),
        "configuration": {
            "pp-structurev3": {"device": "gpu:0", "layout": "PP-DocLayout-S", "ocr": "PP-OCRv5 mobile", "table_recognition": True},
            "docling": {"device": "CUDA", "ocr": "RapidOCR ONNX Runtime, vi", "table_structure": True},
            "mineru": {"device": "CUDA_VISIBLE_DEVICES=0", "tier": "basic", "mode": "one CLI process per page"},
        }[args.engine],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--engine", choices=("pp-structurev3", "docling", "mineru"), required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--repeats", type=int, default=3)
    args = parser.parse_args()
    if args.repeats < 1:
        parser.error("--repeats must be at least 1")
    result = run(args)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"engine": args.engine, "initialization_seconds": result["initialization_seconds"], "resources": result["resources"], "repeats": [{key: repeat[key] for key in ("repeat", "pages_succeeded", "median_seconds_per_page", "p95_seconds_per_page", "total_wall_seconds")} for repeat in result["repeats"]]}, indent=2))


if __name__ == "__main__":
    main()
