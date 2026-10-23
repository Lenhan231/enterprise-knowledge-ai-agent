"""Run Docling on every owner-reviewed HTML page and write normalized predictions."""

from __future__ import annotations

import argparse
import json
import resource
import sys
import time
from datetime import datetime, timezone
from importlib.metadata import version
from pathlib import Path

import numpy as np

TRACK_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(REPO_ROOT / "src"))
DATA_ROOT = TRACK_ROOT / "data"

LABEL_MAP = {
    "doc_title": "title", "paragraph_title": "title", "section_header": "title",
    "title": "title", "document_title": "title",
    "text": "text", "paragraph": "text", "list_item": "text", "abstract": "text",
    "content": "text", "references": "text", "footnote": "text", "sidebar_text": "text",
}


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def normalized_box(provenance: dict, width: float, height: float) -> list[float]:
    box = provenance["bbox"]
    left, top, right, bottom = map(float, (box["l"], box["t"], box["r"], box["b"]))
    if box.get("coord_origin") == "BOTTOMLEFT":
        top, bottom = height - top, height - bottom
    return [left / width, min(top, bottom) / height, right / width, max(top, bottom) / height]


def extract_grid(table: dict) -> list[list[str]]:
    data = table.get("data", {})
    rows, columns = int(data.get("num_rows", 0)), int(data.get("num_cols", 0))
    grid = [[""] * columns for _ in range(rows)]
    for cell in data.get("table_cells", []):
        row, column = int(cell.get("start_row_offset_idx", 0)), int(cell.get("start_col_offset_idx", 0))
        if 0 <= row < rows and 0 <= column < columns:
            grid[row][column] = str(cell.get("text") or "").strip()
    return grid


def normalize_document(document: dict, reference: dict, engine: str, run_id: str) -> dict:
    page = next(iter(document.get("pages", {}).values()), {})
    width, height = float(page.get("size", {}).get("width", 0)), float(page.get("size", {}).get("height", 0))
    if width <= 0 or height <= 0:
        raise ValueError(f"Docling output is missing page dimensions: {reference['reference_id']}")
    elements = []
    for item in document.get("texts", []):
        text = str(item.get("text") or "").strip()
        provenance = next((p for p in item.get("prov", []) if p.get("page_no") == page.get("page_no")), None)
        if not text or not provenance or not provenance.get("bbox"):
            continue
        label = LABEL_MAP.get(str(item.get("label", "")).lower(), "other")
        elements.append({
            "order": len(elements), "text": text, "label": label,
            "bbox_norm": normalized_box(provenance, width, height),
        })
    for item in document.get("pictures", []):
        provenance = next((p for p in item.get("prov", []) if p.get("page_no") == page.get("page_no")), None)
        if provenance and provenance.get("bbox"):
            elements.append({
                "order": len(elements), "text": "", "label": "figure",
                "bbox_norm": normalized_box(provenance, width, height),
            })

    tables = []
    for item in document.get("tables", []):
        provenance = next((p for p in item.get("prov", []) if p.get("page_no") == page.get("page_no")), None)
        grid = extract_grid(item)
        if not provenance or not provenance.get("bbox") or not grid or not grid[0]:
            continue
        header_rows = {
            int(cell.get("start_row_offset_idx", 0))
            for cell in item.get("data", {}).get("table_cells", [])
            if cell.get("column_header")
        }
        if 0 in header_rows:
            columns, body = grid[0], grid[1:]
        else:
            columns, body = [f"column_{i + 1}" for i in range(len(grid[0]))], grid
        tables.append({"bbox_norm": normalized_box(provenance, width, height), "columns": columns, "rows": body})

    return {
        "schema_version": 1, "engine": engine, "run_id": run_id,
        "document_id": reference["document_id"],
        "source_page_number_1based": int(reference["source_page_number_1based"]),
        "elements": elements, "tables": tables,
    }


def run(args: argparse.Namespace) -> None:
    references = read_jsonl(DATA_ROOT / "layout/reference.jsonl")
    if args.page_id:
        references = [row for row in references if row["reference_id"] == args.page_id]
        if not references:
            raise SystemExit(f"No layout reference found for page: {args.page_id}")
    output_dir = (args.output_dir or TRACK_ROOT / "results/shared-html" / args.run_id).resolve()
    raw_dir = output_dir / "raw_pages"
    output_dir.mkdir(parents=True, exist_ok=True)
    raw_dir.mkdir(parents=True, exist_ok=True)
    started_at = datetime.now(timezone.utc)
    started = time.perf_counter()

    reused_metadata = None
    table_rotation_page_setter = None
    tableformer_predictor = None
    layout_rotation_page_setter = None
    layout_model = None
    vietocr_model = None
    if args.reuse_raw:
        source_raw = args.reuse_raw.resolve()
        source_metadata = args.reuse_metadata or source_raw.parent / "run-metadata.json"
        if source_metadata.is_file():
            reused_metadata = json.loads(source_metadata.read_text(encoding="utf-8"))
        converter = None
    else:
        from docling.datamodel.accelerator_options import AcceleratorDevice, AcceleratorOptions
        from docling.datamodel.base_models import InputFormat
        from docling.datamodel.pipeline_options import (
            LayoutObjectDetectionOptions, PdfPipelineOptions, TableFormerMode,
            TableStructureOptions, TesseractCliOcrOptions,
        )
        from docling.datamodel.stage_model_specs import ObjectDetectionModelSpec
        from docling.document_converter import DocumentConverter, ImageFormatOption

        if args.ocr_engine == "vietocr":
            from docling_vietocr import VietOcrOptions, register_vietocr

            register_vietocr()
            ocr_options = VietOcrOptions()
        else:
            ocr_options = TesseractCliOcrOptions(lang=args.ocr_languages.split("+"), psm=args.psm)

        layout_repos = {
            "heron": ("layout_heron", "docling-project/docling-layout-heron"),
            "egret-medium": ("layout_egret_medium", "docling-project/docling-layout-egret-medium"),
        }
        layout_name, layout_repo = layout_repos[args.layout_model]

        options = PdfPipelineOptions(
            accelerator_options=AcceleratorOptions(device=AcceleratorDevice.CPU, num_threads=args.threads),
            do_ocr=True,
            do_table_structure=True,
            layout_options=LayoutObjectDetectionOptions(
                model_spec=ObjectDetectionModelSpec(name=layout_name, repo_id=layout_repo)
            ),
            table_structure_options=TableStructureOptions(
                mode=TableFormerMode.ACCURATE,
                do_cell_matching=not args.no_cell_matching,
            ),
            ocr_options=ocr_options,
        )
        converter = DocumentConverter(format_options={InputFormat.IMAGE: ImageFormatOption(pipeline_options=options)})
        if args.table_rotation or args.ocr_engine == "vietocr":
            converter.initialize_pipeline(InputFormat.IMAGE)
            pipeline = next(iter(converter.initialized_pipelines.values()))
            if args.ocr_engine == "vietocr":
                vietocr_model = pipeline.ocr_model
            if args.layout_rotation == "auto":
                from layout_rotation import enable_layout_rotation

                layout_model = pipeline.layout_model
                layout_rotation_page_setter = enable_layout_rotation(layout_model)
            if args.table_rotation:
                from tableformer_rotation import enable_table_crop_rotation

                tableformer_predictor = pipeline.table_model.tf_predictor
                table_rotation_page_setter = enable_table_crop_rotation(
                    tableformer_predictor, args.table_rotation
                )
        source_raw = raw_dir

    predictions, page_runs = [], []
    for reference in references:
        page_id = reference["reference_id"]
        source_path = source_raw / f"{page_id}.json"
        page_started = time.perf_counter()
        try:
            if converter is not None:
                if layout_rotation_page_setter is not None:
                    layout_rotation_page_setter(page_id)
                if vietocr_model is not None:
                    vietocr_model.current_reference_id = page_id
                if table_rotation_page_setter is not None:
                    table_rotation_page_setter(page_id)
                image_path = DATA_ROOT / reference["source_image"]
                converted = converter.convert(image_path)
                document = converted.document.export_to_dict()
                source_path.write_text(json.dumps(document, ensure_ascii=False) + "\n", encoding="utf-8")
                status = str(converted.status)
            else:
                document = json.loads(source_path.read_text(encoding="utf-8"))
                status = "reused_raw_output"
            predictions.append(normalize_document(document, reference, args.engine, args.run_id))
            page_runs.append({"reference_id": page_id, "status": status, "seconds": round(time.perf_counter() - page_started, 3)})
            print(f"{page_id} {status}", flush=True)
        except Exception as error:
            predictions.append({
                "schema_version": 1, "engine": args.engine, "run_id": args.run_id,
                "document_id": reference["document_id"],
                "source_page_number_1based": int(reference["source_page_number_1based"]),
                "elements": [], "tables": [],
            })
            page_runs.append({"reference_id": page_id, "status": "failed", "error": repr(error), "seconds": round(time.perf_counter() - page_started, 3)})
            print(f"{page_id} failed: {error}", flush=True)

    predictions_path = output_dir / "predictions.jsonl"
    predictions_path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in predictions), encoding="utf-8")
    peak_rss_mib = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024
    if args.table_rotation == "auto":
        table_structure = "Docling TableFormer accurate + per-crop Tesseract OSD"
    else:
        table_structure = f"Docling TableFormer accurate + table crop rotated {args.table_rotation} degrees clockwise"
    if args.no_cell_matching:
        table_structure += "; model-predicted cell text"
    else:
        table_structure += "; OCR cell matching"
    metadata = {
        "dataset": "shared-html-owner-reviewed", "engine": args.engine, "run_id": args.run_id,
        "started_at_utc": started_at.isoformat(),
        "finished_at_utc": datetime.now(timezone.utc).isoformat(),
        "device": "CPU", "ocr": (
            "Docling layout + Tesseract OSD per OCR crop + RapidOCR detection + VietOCR vgg_seq2seq greedy"
            if args.ocr_engine == "vietocr"
            else f"Tesseract {args.ocr_languages} PSM {args.psm}"
        ),
        "layout_model": "Layout " + args.layout_model,
        "table_structure": table_structure, "threads": args.threads,
        "page_filter": args.page_id, "page_count": len(references), "successful_pages": sum(x["status"] != "failed" for x in page_runs),
        "failed_pages": sum(x["status"] == "failed" for x in page_runs),
        "wall_seconds": round(time.perf_counter() - started, 3), "peak_process_rss_mib": round(peak_rss_mib, 1),
        "prediction_generation_seconds": round(time.perf_counter() - started, 3),
        "reused_raw_outputs": bool(args.reuse_raw),
        "raw_output_directory": str(source_raw), "predictions": str(predictions_path), "pages": page_runs,
    }
    if tableformer_predictor is not None and args.table_rotation == "auto":
        metadata["table_orientation_detections"] = getattr(
            tableformer_predictor, "table_rotation_diagnostics", []
        )
    if layout_model is not None:
        metadata["layout_orientation_detections"] = layout_model.orientation_diagnostics
    if vietocr_model is not None:
        metadata["ocr_orientation_detections"] = vietocr_model.orientation_diagnostics
    if reused_metadata:
        metadata["inference_wall_seconds"] = reused_metadata.get("inference_wall_seconds", reused_metadata.get("wall_seconds"))
        metadata["inference_peak_process_rss_mib"] = reused_metadata.get("peak_process_rss_mib")
        metadata["inference_page_seconds"] = reused_metadata.get("inference_page_seconds", {
            item["reference_id"]: item["seconds"] for item in reused_metadata.get("pages", []) if "seconds" in item
        })
        metadata["inference_successful_pages"] = reused_metadata.get("successful_pages", len(references))
    elif not args.reuse_raw:
        metadata["inference_wall_seconds"] = metadata["wall_seconds"]
        metadata["inference_page_seconds"] = {item["reference_id"]: item["seconds"] for item in page_runs if "seconds" in item}
        metadata["inference_successful_pages"] = metadata["successful_pages"]
    try:
        metadata["docling_version"] = version("docling")
    except Exception:
        metadata["docling_version"] = None
    if not args.reuse_raw:
        from tableformer_rotation import _detect_rotation_clockwise
        from PIL import Image

        metadata["page_orientation_detections"] = []
        for reference in references:
            image_path = DATA_ROOT / reference["source_image"]
            with Image.open(image_path) as image:
                rotation, confidence = _detect_rotation_clockwise(
                    np.asarray(image.convert("RGB"))
                )
            metadata["page_orientation_detections"].append({
                "reference_id": reference["reference_id"],
                "rotation_clockwise": rotation,
                "osd_confidence": confidence,
                "minimum_osd_confidence": 5.0,
            })
    (output_dir / "run-metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: metadata[k] for k in ("run_id", "successful_pages", "failed_pages", "wall_seconds", "predictions")}, ensure_ascii=False))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", default=f"docling-html-{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}")
    parser.add_argument("--engine", choices=("docling", "docling-vietocr"), default=None)
    parser.add_argument("--ocr-engine", choices=("tesseract", "vietocr"), default="tesseract")
    parser.add_argument("--layout-model", choices=("heron", "egret-medium"), default="heron")
    parser.add_argument("--output-dir", type=Path, help="Defaults to results/shared-html/<run-id>")
    parser.add_argument("--page-id", help="Optionally run one owner-reviewed page for a focused comparison")
    parser.add_argument("--reuse-raw", type=Path, help="Normalize previously saved Docling raw page outputs without rerunning inference.")
    parser.add_argument("--reuse-metadata", type=Path, help="Inference metadata to preserve when --reuse-raw is used.")
    parser.add_argument("--ocr-languages", default="vie+eng")
    parser.add_argument("--psm", type=int, default=6)
    parser.add_argument("--no-cell-matching", action="store_true", help="Use TableFormer-predicted cell text instead of matching OCR text into the grid.")
    parser.add_argument("--table-rotation", type=lambda value: value if value == "auto" else int(value), choices=("auto", 0, 90, 180, 270), default=0, help="Rotate table crops clockwise before TableFormer; auto uses per-crop Tesseract OSD (minimum orientation confidence 5.0).")
    parser.add_argument("--layout-rotation", choices=("auto",), help="Rotate the page image for layout inference only using Tesseract OSD, then map layout boxes back to source coordinates.")
    parser.add_argument("--threads", type=int, default=2)
    args = parser.parse_args()
    args.engine = args.engine or ("docling-vietocr" if args.ocr_engine == "vietocr" else "docling")
    run(args)


if __name__ == "__main__":
    main()
