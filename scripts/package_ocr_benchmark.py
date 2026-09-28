#!/usr/bin/env python3
"""Package the reviewed v7 OCR corpus for a private Kaggle dataset."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DATASET_ID = "ltrngnhn/vinamilk-ocr-v7-benchmark-assets"


def package(output: Path) -> dict:
    output = output.resolve()
    if output.exists():
        raise FileExistsError(f"Output already exists; choose an empty path: {output}")

    labels_path = REPO_ROOT / "data/evaluation/vinamilk_ocr_ground_truth_v7.json"
    labels = json.loads(labels_path.read_text(encoding="utf-8"))
    source_paths = sorted({(REPO_ROOT / page["file"]).resolve() for page in labels["pages"]})
    for source in source_paths:
        if not source.is_relative_to(REPO_ROOT) or not source.is_file():
            raise FileNotFoundError(f"Missing or out-of-repository OCR source: {source}")

    project = output / "project"
    (project / "scripts").mkdir(parents=True)
    (project / "data/evaluation").mkdir(parents=True)
    for source in source_paths:
        destination = project / source.relative_to(REPO_ROOT)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
    shutil.copy2(REPO_ROOT / "scripts/evaluate_ocr.py", project / "scripts/evaluate_ocr.py")
    shutil.copy2(labels_path, project / "data/evaluation/vinamilk_ocr_ground_truth_v7.json")

    metadata = {
        "title": "Vinamilk OCR v7 Benchmark Assets",
        "id": DATASET_ID,
        "licenses": [{"name": "other"}],
        "subtitle": "Private reviewed OCR references and official source PDFs",
        "description": (
            "Private thesis benchmark bundle: v7 reviewed OCR references, their five official Vinamilk source PDFs, "
            "and the evaluator. Contains no credentials, private uploads, database access, or model outputs."
        ),
    }
    (output / "dataset-metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
    )
    readme = (
        "# Private Vinamilk OCR benchmark assets v7\n\n"
        "This bundle contains the evaluator, manually reviewed v7 references, and only the five official PDFs "
        "needed to render its ten labeled pages. It contains no credentials, private uploads, database access, "
        "or model outputs. Keep this Kaggle dataset private. Source PDFs remain property of their publishers; "
        "use the citations in the reviewed dataset when reporting results.\n"
    )
    (output / "README.md").write_text(readme, encoding="utf-8")

    return {
        "dataset_id": DATASET_ID,
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
    args = parser.parse_args()
    print(json.dumps(package(args.output), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
