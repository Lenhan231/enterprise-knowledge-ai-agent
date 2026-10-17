"""Build the Kaggle notebook for MinerU preprocessing runs (development/validation only)."""

from __future__ import annotations

import json
import argparse
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
KERNEL_DIR = ROOT / "artifacts/evaluation/document-pipelines/kernels/mineru-preprocessing"
PREPROCESSOR = ROOT / "tools/processing/prepare_mineru_preprocessing_variants.py"
RUNNER = ROOT / "tools/processing/run_mineru_preprocessing_variant.py"
PERFORMANCE_RUNNER = ROOT / "tools/processing/run_document_pipeline_performance.py"


def code_cell(source: str, cell_id: str) -> dict:
    return {
        "cell_type": "code",
        "execution_count": None,
        "metadata": {},
        "outputs": [],
        "source": source.splitlines(keepends=True),
        "id": cell_id,
    }


def build(
    selected_variant_ids: tuple[str, ...] | None = None,
    selected_tracks: tuple[str, ...] | None = None,
    selected_splits: tuple[str, ...] | None = None,
) -> None:
    all_variant_ids = ["V0", "V1", "V2", "V3"] + [
        f"V4-skew{skew:g}-contrast{quantile}"
        for skew in (0.5, 1.0, 1.5)
        for quantile in (25, 50)
    ]
    if selected_variant_ids is not None:
        unknown = set(selected_variant_ids) - set(all_variant_ids)
        if unknown or not selected_variant_ids or len(set(selected_variant_ids)) != len(selected_variant_ids):
            raise ValueError(f"Invalid or duplicate variant IDs: {sorted(unknown) or selected_variant_ids}")
    all_tracks = ("ocr", "tables", "layout")
    all_splits = ("development", "validation", "locked_test")
    default_splits = ("development", "validation")
    for label, selected, allowed in (
        ("tracks", selected_tracks, all_tracks),
        ("splits", selected_splits, all_splits),
    ):
        if selected is not None:
            unknown = set(selected) - set(allowed)
            if unknown or not selected or len(set(selected)) != len(selected):
                raise ValueError(f"Invalid or duplicate {label}: {sorted(unknown) or selected}")
    tracks = selected_tracks or all_tracks
    splits = selected_splits or default_splits
    locked_test_run = "locked_test" in splits
    if locked_test_run:
        if splits != ("locked_test",):
            raise ValueError("Locked-test inference must run separately from development/validation.")
        if selected_variant_ids is None or len(selected_variant_ids) not in (1, 2):
            raise ValueError("Locked-test inference requires one selected variant, optionally paired with V0.")
        if selected_variant_ids != ("V0",) and "V0" not in selected_variant_ids:
            raise ValueError("A locked-test candidate run must include V0 as the control.")
    if KERNEL_DIR.exists():
        metadata_path = KERNEL_DIR / "kernel-metadata.json"
        if not metadata_path.is_file() or json.loads(metadata_path.read_text(encoding="utf-8")).get("id") != "letrongnhan/mineru-preprocessing-tuning-v1":
            raise FileExistsError(f"Refusing to overwrite an unrecognized kernel package: {KERNEL_DIR}")
    else:
        KERNEL_DIR.mkdir(parents=True)
    preprocessor_source = PREPROCESSOR.read_text(encoding="utf-8")
    runner_source = RUNNER.read_text(encoding="utf-8")
    performance_source = PERFORMANCE_RUNNER.read_text(encoding="utf-8")

    install = '''from pathlib import Path
import os, subprocess, sys

WORK = Path("/kaggle/working")
RUNTIME_INPUT = Path("/kaggle/input/mineru-offline-runtime-v1")
RUNTIME = WORK / "mineru-offline-runtime"
RUNTIME.mkdir(parents=True, exist_ok=True)
wheel_dir = RUNTIME_INPUT / "wheels" / "wheels"
mounted_model_repo = RUNTIME_INPUT / "models" / "models"
model_base = RUNTIME / "models"
model_base.mkdir(parents=True, exist_ok=True)
model_repo = model_base / "MinerU-4_models_torch"
if not wheel_dir.is_dir() or not (mounted_model_repo / ".mineru_complete").is_file():
    raise FileNotFoundError(f"Offline runtime dataset is missing mounted wheels or model files: {RUNTIME_INPUT}")
if not model_repo.exists():
    model_repo.symlink_to(mounted_model_repo, target_is_directory=True)
subprocess.run([
    sys.executable, "-m", "pip", "install", "--no-index", "--find-links", str(wheel_dir),
    "mineru[torch]==4.0.12",
], check=True)
os.environ["MINERU_MODEL_BASE_DIR"] = str(model_base)
os.environ["MINERU_MODEL_SOURCE"] = "local"
os.environ["MINERU_MODEL_SMALL_BACKEND"] = "torch"
subprocess.run([
    "mineru-kit", "models", "verify", "--tier", "basic", "--small-backend", "torch",
], check=True)
import torch
print({"torch": torch.__version__, "cuda_runtime": torch.version.cuda, "cuda_available": torch.cuda.is_available()})
if torch.cuda.is_available():
    print("GPU:", torch.cuda.get_device_name(0))
else:
    print("Running MinerU on CPU; do not compare these timings with GPU pipeline baselines.")
'''
    execute = f'''from pathlib import Path
import hashlib, importlib.util, json, os, shutil, subprocess, sys, time, zipfile
import numpy as np

WORK = Path("/kaggle/working")
CODE = WORK / "pipeline_code"
CODE.mkdir(exist_ok=True)
PREPROCESSOR_SOURCE = {preprocessor_source!r}
RUNNER_SOURCE = {runner_source!r}
PERFORMANCE_SOURCE = {performance_source!r}
(CODE / "prepare_mineru_preprocessing_variants.py").write_text(PREPROCESSOR_SOURCE, encoding="utf-8")
(CODE / "run_mineru_preprocessing_variant.py").write_text(RUNNER_SOURCE, encoding="utf-8")
(CODE / "run_document_pipeline_performance.py").write_text(PERFORMANCE_SOURCE, encoding="utf-8")
sys.path.insert(0, str(CODE))
import prepare_mineru_preprocessing_variants as prep

INPUT_ROOT = Path("/kaggle/input")
DATASET_IDS = {{
    "ocr": "vietnam-enterprise-ocr-500-crops-v1",
    "tables": "vietnam-enterprise-table-reference-v1",
    "layout": "vietnam-enterprise-layout-200-pages-v2",
}}
manifest_paths = list(INPUT_ROOT.rglob("manifest.json"))
found = {{}}
for manifest_path in manifest_paths:
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception:
        continue
    dataset_id = str(data.get("dataset_id", ""))
    for track, expected in DATASET_IDS.items():
        if dataset_id == expected:
            found[track] = (manifest_path, data)
if set(found) != set(DATASET_IDS):
    raise RuntimeError(f"Expected manifests for all three benchmark inputs; found={{list(found)}}; roots={{[str(p) for p in INPUT_ROOT.iterdir()]}}")

def resolve_input_root(track, manifest_path, data):
    root = manifest_path.parent
    rows = data.get("items", []) if track == "tables" else data.get("pages", [])
    if rows and (root / rows[0]["input_pdf"]).is_file():
        return root
    archives = list(root.rglob("inputs.zip"))
    if len(archives) != 1:
        raise FileNotFoundError(f"Cannot resolve {{track}} input PDFs from {{root}}; archives={{archives}}")
    extracted = WORK / "input-cache" / track
    extracted.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archives[0]) as archive:
        for member in archive.infolist():
            if member.filename.endswith(".pdf") and Path(member.filename).name:
                destination = extracted / "inputs" / Path(member.filename).name
                destination.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(member) as src, destination.open("wb") as dst:
                    shutil.copyfileobj(src, dst)
    shutil.copy2(manifest_path, extracted / "manifest.json")
    return extracted

roots = {{}}
manifests = {{}}
for track, (path, data) in found.items():
    roots[track] = resolve_input_root(track, path, data)
    manifests[track] = roots[track] / "manifest.json"

variants = [("V0", None, None), ("V1", None, None), ("V2", None, None), ("V3", None, None)]
variants.extend((f"V4-skew{{skew:g}}-contrast{{quantile}}", skew, quantile) for skew in (0.5, 1.0, 1.5) for quantile in (25, 50))
RUN_VARIANT_IDS = {selected_variant_ids!r}
if RUN_VARIANT_IDS is not None:
    variants = [variant for variant in variants if variant[0] in RUN_VARIANT_IDS]
if not variants:
    raise ValueError("No preprocessing variants selected")
RUN_TRACKS = {tracks!r}
RUN_SPLITS = {splits!r}
RUN_VARIANT_IDS = [variant[0] for variant in variants]

# Derive thresholds and seed shared features only when this run includes V4.
feature_cache = {{"version": 1, "dpi": prep.DPI, "items": {{}}}}
thresholds = {{}}
if any(variant_id.startswith("V4-") for variant_id, _, _ in variants):
    ocr_data = json.loads(manifests["ocr"].read_text(encoding="utf-8"))
    ocr_dev = [row for row in ocr_data["pages"] if row.get("split") == "development"]
    contrast_ranges = []
    for row in ocr_dev:
        input_pdf = roots["ocr"] / row["input_pdf"]
        image, _, _ = prep.rasterize(input_pdf)
        features = prep.grayscale_features(image)
        contrast_ranges.append(features["contrast_p95_p5"])
        feature_cache["items"][prep.sha256(input_pdf)] = {{"grayscale_features": features, "skew_estimate": None}}
        image.close()
    thresholds = {{q: float(np.percentile(contrast_ranges, q)) for q in (25, 50)}}
    print("OCR development samples used for adaptive thresholds:", len(contrast_ranges), thresholds)
OUTPUT = WORK / "mineru-preprocessing"
OUTPUT.mkdir(exist_ok=True)
FEATURE_CACHE = WORK / "quality-feature-cache.json"
FEATURE_CACHE.write_text(json.dumps(feature_cache, ensure_ascii=False), encoding="utf-8")
if not __import__("torch").cuda.is_available():
    os.environ["CUDA_VISIBLE_DEVICES"] = ""
expected_groups = len(variants) * len(RUN_TRACKS) * len(RUN_SPLITS)
summary = {{"dataset_ids": DATASET_IDS, "contrast_thresholds_from_ocr_development": thresholds, "variant_ids": RUN_VARIANT_IDS, "tracks": RUN_TRACKS, "splits": RUN_SPLITS, "expected_group_count": expected_groups, "runs": []}}
print("planned_groups=", expected_groups, flush=True)
for variant_id, skew_threshold, contrast_quantile in variants:
    engine_variant = "V4" if variant_id.startswith("V4-") else variant_id
    for track in RUN_TRACKS:
        for split in RUN_SPLITS:
            out = OUTPUT / variant_id / track / split
            command = [
                sys.executable, str(CODE / "run_mineru_preprocessing_variant.py"),
                "--track", track, "--manifest", str(manifests[track]), "--input-root", str(roots[track]),
                "--split", split, "--variant", engine_variant, "--output", str(out),
                "--feature-cache", str(FEATURE_CACHE),
            ]
            if engine_variant == "V4":
                command.extend(["--skew-threshold", str(skew_threshold), "--contrast-threshold", str(thresholds[contrast_quantile])])
            started = time.perf_counter()
            process = subprocess.run(command, capture_output=True, text=True)
            tail = process.stdout.strip().splitlines()[-1:] + process.stderr.strip().splitlines()[-2:]
            run = {{"variant": variant_id, "track": track, "split": split, "return_code": process.returncode, "elapsed_seconds": round(time.perf_counter()-started, 2), "output": str(out), "log_tail": tail}}
            summary["runs"].append(run)
            print(json.dumps(run, ensure_ascii=False), flush=True)
(OUTPUT / "kernel-summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\\n", encoding="utf-8")
print("Completed variant groups:", len(summary["runs"]), "of", expected_groups)
'''

    notebook = {
        "cells": [
            {
                "cell_type": "markdown",
                "metadata": {},
                "source": [
                    "# MinerU Basic preprocessing ablation\n",
                    "\n",
                    f"Runs {', '.join(selected_variant_ids) if selected_variant_ids else 'V0–V3 plus six predefined V4 threshold combinations'} on tracks {', '.join(tracks)} and splits {', '.join(splits)}. Ground-truth references are not included. {'This is a one-time locked-test run for a single validation-selected configuration, optionally paired with V0, and must not guide tuning.' if locked_test_run else 'Locked test is excluded from this development/validation tuning run.'} This run uses the selected Kaggle accelerator (currently CPU); CPU timings are exploratory and must not be compared with GPU pipeline baselines.\n",
                ],
                "id": "overview",
            },
            code_cell(install, "install-mineru"),
            code_cell(execute, "run-variants"),
        ],
        "metadata": {
            "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
            "language_info": {"name": "python", "version": "3.11.0"},
        },
        "nbformat": 4,
        "nbformat_minor": 5,
    }
    notebook_path = KERNEL_DIR / "mineru_preprocessing_tuning.ipynb"
    notebook_path.write_text(json.dumps(notebook, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    metadata = {
        "id": "letrongnhan/mineru-preprocessing-tuning-v1",
        "title": "MinerU Preprocessing Tuning V1",
        "code_file": notebook_path.name,
        "language": "python",
        "kernel_type": "notebook",
        "is_private": "true",
        "enable_gpu": "false",
        "enable_tpu": "false",
        "enable_internet": "false",
        "dataset_sources": [
            "letrongnhan/vietnamese-enterprise-ocr-500-crops-v1",
            "letrongnhan/vietnam-enterprise-table-reference-v1",
            "letrongnhan/vietnam-enterprise-layout-200-pages-v2",
            "letrongnhan/mineru-offline-runtime-v1",
        ],
        "competition_sources": [],
        "kernel_sources": [],
        "model_sources": [],
    }
    (KERNEL_DIR / "kernel-metadata.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    variant_count = len(selected_variant_ids) if selected_variant_ids is not None else len(all_variant_ids)
    group_count = variant_count * len(tracks) * len(splits)
    print(json.dumps({"kernel_dir": str(KERNEL_DIR), "groups": group_count, "variant_count": variant_count, "tracks": tracks, "splits": splits, "source_hashes": {"preprocessor": __import__("hashlib").sha256(preprocessor_source.encode()).hexdigest(), "runner": __import__("hashlib").sha256(runner_source.encode()).hexdigest(), "performance_runner": __import__("hashlib").sha256(performance_source.encode()).hexdigest()}}, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--variants", help="Comma-separated variant IDs; defaults to the full sweep.")
    parser.add_argument("--tracks", help="Comma-separated track IDs; defaults to ocr,tables,layout.")
    parser.add_argument("--splits", help="Comma-separated split IDs; defaults to development,validation.")
    args = parser.parse_args()
    def parse_list(value: str | None) -> tuple[str, ...] | None:
        return tuple(item.strip() for item in value.split(",")) if value else None

    build(parse_list(args.variants), parse_list(args.tracks), parse_list(args.splits))
