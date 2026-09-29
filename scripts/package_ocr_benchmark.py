#!/usr/bin/env python3
"""Package reviewed OCR references and source PDFs for a private Kaggle dataset."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from urllib.parse import urlparse
from urllib.request import Request, urlopen
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATASET = REPO_ROOT / "data/evaluation/vinamilk_ocr_ground_truth_v7.json"
DEFAULT_DATASET_ID = "ltrngnhn/vinamilk-ocr-v7-benchmark-assets"


def ensure_dataset_source(labels: dict, source: Path) -> None:
    if source.is_file():
        return
    url = labels.get("source_download_url")
    expected_hash = labels.get("source_pdf_sha256")
    if not url or not expected_hash:
        raise FileNotFoundError(f"Missing OCR source PDF and no checksummed download is configured: {source}")
    if urlparse(url).scheme != "https":
        raise ValueError("OCR benchmark source downloads must use HTTPS")
    headers = {"User-Agent": "EnterpriseKnowledgeOCRBenchmark/1.0"}
    if labels.get("source_download_referer"):
        headers["Referer"] = labels["source_download_referer"]
    with urlopen(Request(url, headers=headers), timeout=45) as response:
        payload = response.read()
    actual_hash = hashlib.sha256(payload).hexdigest()
    if not payload.startswith(b"%PDF-") or actual_hash != expected_hash:
        raise ValueError(f"Downloaded OCR source PDF failed magic/hash verification: {source}")
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_bytes(payload)


def package(output: Path, labels_path: Path = DEFAULT_DATASET, dataset_id: str = DEFAULT_DATASET_ID) -> dict:
    output = output.resolve()
    if output.exists():
        raise FileExistsError(f"Output already exists; choose an empty path: {output}")

    labels_path = labels_path.resolve()
    if not labels_path.is_relative_to(REPO_ROOT):
        raise ValueError(f"Dataset must be inside the repository: {labels_path}")
    labels = json.loads(labels_path.read_text(encoding="utf-8"))
    source_paths = sorted({(REPO_ROOT / page["file"]).resolve() for page in labels["pages"]})
    for source in source_paths:
        if source.is_relative_to(REPO_ROOT):
            ensure_dataset_source(labels, source)
    for source in source_paths:
        if not source.is_relative_to(REPO_ROOT) or not source.is_file():
            raise FileNotFoundError(f"Missing or out-of-repository OCR source: {source}")
    expected_hash = labels.get("source_pdf_sha256")
    if expected_hash and len(source_paths) == 1:
        actual_hash = hashlib.sha256(source_paths[0].read_bytes()).hexdigest()
        if actual_hash != expected_hash:
            raise ValueError(f"Source PDF SHA-256 does not match reviewed dataset: {source_paths[0]}")

    project = output / "project"
    (project / "scripts").mkdir(parents=True)
    (project / "data/evaluation").mkdir(parents=True)
    for source in source_paths:
        destination = project / source.relative_to(REPO_ROOT)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
    shutil.copy2(REPO_ROOT / "scripts/evaluate_ocr.py", project / "scripts/evaluate_ocr.py")
    dataset_relative_path = labels_path.relative_to(REPO_ROOT)
    dataset_copy = project / dataset_relative_path
    dataset_copy.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(labels_path, dataset_copy)

    title = labels.get("dataset_title", "Vinamilk OCR v7 Benchmark Assets")
    metadata = {
        "title": title,
        "id": dataset_id,
        "licenses": [{"name": "other"}],
        "subtitle": "Private reviewed OCR references and source PDFs",
        "description": (
            f"Private thesis OCR benchmark bundle: {labels.get('dataset_id', labels_path.stem)}, "
            f"{len(labels['pages'])} reviewed page(s), source PDFs, and the evaluator. "
            "Contains no credentials, private uploads, database access, or model outputs."
        ),
    }
    (output / "dataset-metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
    )
    readme = (
        f"# {title}\n\n"
        f"This private bundle contains the evaluator, references in `{dataset_relative_path}`, and the "
        f"{len(source_paths)} source PDF(s) needed to render its {len(labels['pages'])} labeled page(s). "
        "It contains no credentials, private uploads, database access, or model outputs. Keep this Kaggle "
        "dataset private. Source PDFs remain property of their publishers; follow the provenance and "
        "limitations recorded in the reviewed dataset.\n"
    )
    (output / "README.md").write_text(readme, encoding="utf-8")

    return {
        "dataset_id": dataset_id,
        "dataset": labels.get("dataset_id"),
        "pages": len(labels["pages"]),
        "source_pdfs": [str(path.relative_to(REPO_ROOT)) for path in source_paths],
        "source_sha256": {
            str(path.relative_to(REPO_ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in source_paths
        },
        "output": str(output),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path, help="New empty output directory for Kaggle dataset files")
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--dataset-id", default=DEFAULT_DATASET_ID)
    args = parser.parse_args()
    dataset = args.dataset if args.dataset.is_absolute() else REPO_ROOT / args.dataset
    print(json.dumps(package(args.output, dataset, args.dataset_id), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
