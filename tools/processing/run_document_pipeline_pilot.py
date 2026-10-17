"""Run one document parser on the fixed enterprise pilot inputs."""

from __future__ import annotations

import argparse
import json
import os
import platform
import resource
import shutil
import subprocess
import sys
import time
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    def serialize(item: object) -> object:
        if hasattr(item, "tolist"):
            return item.tolist()
        if hasattr(item, "item"):
            return item.item()
        return str(item)

    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=serialize) + "\n", encoding="utf-8")


def system_metadata() -> dict:
    gpu = subprocess.run(["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader"], capture_output=True, text=True)
    return {
        "python": sys.version,
        "platform": platform.platform(),
        "cpu_count": os.cpu_count(),
        "gpu": gpu.stdout.strip() if gpu.returncode == 0 else None,
        "gpu_query_error": gpu.stderr.strip() if gpu.returncode else None,
        "peak_rss_mb": round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 1),
    }


def package_versions(names: list[str]) -> dict[str, str | None]:
    versions = {}
    for name in names:
        try:
            versions[name] = version(name)
        except PackageNotFoundError:
            versions[name] = None
    return versions


def run_paddle(inputs: list[Path], output: Path) -> dict:
    from paddleocr import PPStructureV3

    init_started = time.perf_counter()
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
    initialization_seconds = time.perf_counter() - init_started
    pages_dir = output / "raw_pages"
    rows = []
    for pdf in inputs:
        item_id = pdf.stem
        started = time.perf_counter()
        try:
            results = list(pipeline.predict(input=str(pdf)))
            for index, result in enumerate(results, start=1):
                payload = getattr(result, "json", result)
                if isinstance(payload, str):
                    payload = json.loads(payload)
                write_json(pages_dir / f"{item_id}-page-{index:03d}.json", payload)
                markdown = getattr(result, "markdown", None)
                if markdown is not None:
                    write_json(pages_dir / f"{item_id}-page-{index:03d}-markdown.json", markdown)
            rows.append({"id": item_id, "status": "ok", "seconds": time.perf_counter() - started, "pages_returned": len(results)})
        except Exception as error:
            rows.append({"id": item_id, "status": "error", "seconds": time.perf_counter() - started, "error": repr(error)})
    return {"initialization_seconds": initialization_seconds, "pages": rows}


def run_docling(inputs: list[Path], output: Path) -> dict:
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
    init_started = time.perf_counter()
    converter = DocumentConverter(
        format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=options)}
    )
    initialization_seconds = time.perf_counter() - init_started
    pages_dir = output / "raw_pages"
    rows = []
    for pdf in inputs:
        started = time.perf_counter()
        try:
            result = converter.convert(pdf)
            document = result.document
            write_json(pages_dir / f"{pdf.stem}.json", document.export_to_dict())
            (pages_dir / f"{pdf.stem}.md").write_text(document.export_to_markdown(), encoding="utf-8")
            rows.append({"id": pdf.stem, "seconds": time.perf_counter() - started, "status": str(result.status)})
        except Exception as error:
            rows.append({"id": pdf.stem, "seconds": time.perf_counter() - started, "status": "error", "error": repr(error)})
    return {"initialization_seconds": initialization_seconds, "pages": rows}


def run_mineru(inputs: list[Path], output: Path) -> dict:
    output.mkdir(parents=True, exist_ok=True)
    environment = os.environ.copy()
    environment["CUDA_VISIBLE_DEVICES"] = "0"
    model_info = subprocess.run(["mineru-kit", "models", "show"], capture_output=True, text=True, env=environment)
    (output / "models-show.stdout.log").write_text(model_info.stdout, encoding="utf-8")
    (output / "models-show.stderr.log").write_text(model_info.stderr, encoding="utf-8")
    pages_dir = output / "mineru-output"
    work_dir = output / "inputs"
    rows = []
    started_all = time.perf_counter()
    for pdf in inputs:
        page_output = pages_dir / pdf.stem
        page_input_dir = work_dir / pdf.stem
        page_input_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(pdf, page_input_dir / pdf.name)
        command = ["mineru-kit", "parse", str(page_input_dir / pdf.name), "-o", str(page_output), "--format", "zip", "--tier", "basic"]
        started = time.perf_counter()
        process = subprocess.run(command, capture_output=True, text=True, env=environment)
        elapsed = time.perf_counter() - started
        (output / "logs").mkdir(parents=True, exist_ok=True)
        (output / "logs" / f"{pdf.stem}.stdout.log").write_text(process.stdout, encoding="utf-8")
        (output / "logs" / f"{pdf.stem}.stderr.log").write_text(process.stderr, encoding="utf-8")
        archives = sorted(str(path.relative_to(output)) for path in page_output.rglob("*.zip")) if page_output.exists() else []
        rows.append({"id": pdf.stem, "status": "ok" if process.returncode == 0 and archives else "error", "seconds": elapsed, "exit_code": process.returncode, "output_archives": archives, "error": process.stderr[-2000:] if process.returncode else None})
    return {
        "tier": "basic",
        "mode": "one CLI process per page; includes process and model startup",
        "exit_code": 0 if all(row["status"] == "ok" for row in rows) else 1,
        "batch_seconds_including_process_startup": time.perf_counter() - started_all,
        "pages": rows,
        "model_selection": model_info.stdout.strip(),
        "note": "Per-page process isolation keeps one parser failure from aborting other pilot pages; timings include repeated CLI/model startup and are not directly comparable to persistent-process timings.",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--engine", choices=("pp-structurev3", "docling", "mineru"), required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    inputs_dir = args.manifest.parent / "inputs"
    inputs = [inputs_dir / Path(row["input_pdf"]).name for row in manifest["pages"]]
    missing = [path for path in inputs if not path.is_file()]
    if missing:
        raise FileNotFoundError(f"Missing {len(missing)} pilot input PDFs: {missing[:3]}")
    args.output.mkdir(parents=True, exist_ok=True)

    started = time.perf_counter()
    if args.engine == "pp-structurev3":
        inference = run_paddle(inputs, args.output)
    elif args.engine == "docling":
        inference = run_docling(inputs, args.output)
    else:
        inference = run_mineru(inputs, args.output)
    write_json(
        args.output / "run-metadata.json",
        {
            "dataset_id": manifest["dataset_id"],
            "engine": args.engine,
            "page_count": len(inputs),
            "run_seconds": time.perf_counter() - started,
            "engine_config": {
                "pp-structurev3": {"device": "gpu:0", "layout": "PP-DocLayout-S", "ocr": "PP-OCRv5 mobile", "table_recognition": True},
                "docling": {"device": "CUDA", "ocr": "RapidOCR ONNX Runtime, vi", "table_structure": True},
                "mineru": {"device": "CUDA_VISIBLE_DEVICES=0", "tier": "basic", "mode": "one CLI process per page"},
            }[args.engine],
            "inference": inference,
            "system": system_metadata(),
            "packages": package_versions(
                ["paddlepaddle-gpu", "paddleocr", "paddlex", "mineru", "docling", "torch"]
            ),
        },
    )
    print(json.dumps(inference, ensure_ascii=False, indent=2, default=str))
    if args.engine == "mineru" and inference["exit_code"]:
        print("Some MinerU pages failed; see per-page logs and run metadata.", file=sys.stderr)


if __name__ == "__main__":
    main()
