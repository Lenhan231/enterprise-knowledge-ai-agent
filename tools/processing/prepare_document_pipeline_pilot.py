"""Package a fixed 20-page PDF pilot for document-pipeline comparisons."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path

import fitz


ROOT = Path(__file__).resolve().parents[2]
LAYOUT_MANIFEST = ROOT / "data/evaluation/layout/vn-enterprise-layout-pilot-v1.json"
OCR_MANIFEST = ROOT / "data/evaluation/ocr/vn-enterprise-ocr-large-v1_ground_truth.json"
OCR_REFERENCE = ROOT / "artifacts/evaluation/ocr/layout-pipeline-kaggle/dataset/ocr_ground_truth.json"
TABLE_REFERENCE = ROOT / "artifacts/evaluation/ocr/layout-pipeline-kaggle/dataset/table_ground_truth.json"
DEFAULT_OUTPUT = ROOT / "artifacts/evaluation/document-pipelines/pilot-v1"

# Additions bring the existing 14-page OCR/layout set to 20 pages and broaden
# its issuer/document coverage. Classification is retained from the manifests.
EXTRA_PAGES = [
    ("VNM-FS-2011-VI-SCAN-DIAGNOSTIC", 10),
    ("ACV-AR-2024", 7),
    ("HGM-AR-2024", 62),
    ("ACB-AR-2024", 14),
    ("HDBANK-AR-2024", 30),
    ("VNM-AR-2024-VI", 91),
]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def relative_path(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def source_entries() -> list[dict]:
    layout = read_json(LAYOUT_MANIFEST)
    ocr_pages = read_json(OCR_MANIFEST)["pages"]
    full_ocr = read_json(OCR_REFERENCE)["pages"]
    table_pages = read_json(TABLE_REFERENCE)["pages"]
    entries = []

    for page in layout["pages"]:
        entries.append(
            {
                "id": page["id"],
                "document_id": page["document_id"],
                "source_file": page["source_file"],
                "page_number": page["page_number"],
                "source_type": page["source_type"],
                "document_type": page["document_type"],
                "layout_reference_id": page["id"] if page.get("annotations") else None,
            }
        )

    # This page was included in the older pipeline pilot but not in the layout
    # manifest; reference it from the original PDF so all engines get the same
    # source input and the existing visual transcript remains discoverable.
    entries.append(
        {
            "id": "longhau-board-p003",
            "document_id": "HPT-LONGHAU-2008",
            "source_file": "data/raw/benchmark_data/HPT - To trinh thong qua danh sach Cong ty Kiem toan signed1.pdf",
            "page_number": 3,
            "source_type": "physical_scan",
            "document_type": "board_report",
            "layout_reference_id": None,
        }
    )

    for document_id, page_number in EXTRA_PAGES:
        matching = [
            row
            for row in ocr_pages
            if row["document_id"] == document_id and row["page"] == page_number
        ]
        if not matching:
            raise ValueError(f"No OCR corpus source for {document_id} page {page_number}")
        row = matching[0]
        entries.append(
            {
                "id": f"{document_id.lower()}-p{page_number:03d}",
                "document_id": document_id,
                "source_file": row["file"],
                "page_number": page_number,
                "source_type": None,
                "document_type": row.get("layout_type", "enterprise_report"),
                "layout_reference_id": None,
            }
        )

    if len(entries) != 20:
        raise ValueError(f"Expected exactly 20 pilot pages, got {len(entries)}")
    if len({(e["document_id"], e["page_number"]) for e in entries}) != len(entries):
        raise ValueError("Pilot selection contains duplicate source pages")

    for entry in entries:
        source = relative_path(entry["source_file"])
        if not source.is_file():
            raise FileNotFoundError(source)
        if entry["page_number"] < 1:
            raise ValueError(f"Invalid page number in {entry['id']}")

        pdf = fitz.open(source)
        index = entry["page_number"] - 1
        if index >= len(pdf):
            raise ValueError(f"{entry['id']} asks for page {entry['page_number']} of {len(pdf)}")
        native_text_chars = len(pdf[index].get_text().strip())
        entry["source_pdf_sha256"] = sha256(source)
        entry["native_text_char_count"] = native_text_chars
        if entry["source_type"] is None:
            entry["source_type"] = "image_only" if native_text_chars < 100 else "born_digital"
        entry["input_pdf"] = f"inputs/{entry['id']}.pdf"
        entry["ocr_reference_ids"] = [
            row["id"]
            for row in full_ocr
            if row["file"] == entry["source_file"]
            and row["page"] == entry["page_number"]
        ]
        entry["table_reference_ids"] = [
            row["id"]
            for row in table_pages
            if row["file"] == entry["source_file"]
            and row["page"] == entry["page_number"]
        ]
        entry["ocr_crop_reference_ids"] = [
            row["id"]
            for row in ocr_pages
            if row["file"] == entry["source_file"]
            and row["page"] == entry["page_number"]
        ]
        entry["ocr_crop_reference_manifest"] = (
            "data/evaluation/ocr/vn-enterprise-ocr-large-v1_ground_truth.json"
            if entry["ocr_crop_reference_ids"]
            else None
        )
        entry["labels_status"] = (
            "exploratory_review_required"
            if entry["layout_reference_id"]
            else "no_page_level_labels"
        )
    return entries


def package(output: Path) -> Path:
    output.mkdir(parents=True, exist_ok=True)
    (output / "inputs").mkdir(exist_ok=True)
    pages = source_entries()

    for row in pages:
        source = relative_path(row["source_file"])
        input_path = output / row["input_pdf"]
        source_pdf = fitz.open(source)
        one_page = fitz.open()
        one_page.insert_pdf(source_pdf, from_page=row["page_number"] - 1, to_page=row["page_number"] - 1)
        one_page.set_metadata(
            {
                "title": row["id"],
                "subject": "Single source page for document pipeline pilot; see manifest for provenance.",
            }
        )
        one_page.save(input_path, garbage=4, deflate=True)
        row["input_pdf_sha256"] = sha256(input_path)
        row["page_size_points"] = [
            round(source_pdf[row["page_number"] - 1].rect.width, 2),
            round(source_pdf[row["page_number"] - 1].rect.height, 2),
        ]

    manifest = {
        "dataset_id": "vietnamese-enterprise-document-pipeline-pilot-v1",
        "status": "inputs_packaged_labels_review_required",
        "purpose": "Same-source-page pilot for PP-StructureV3, MinerU, and Docling.",
        "input_unit": "one-page PDF preserving source vector/text content when present",
        "pipeline_candidates": ["PP-StructureV3", "MinerU", "Docling"],
        "page_count": len(pages),
        "source_type_counts": {
            source_type: sum(page["source_type"] == source_type for page in pages)
            for source_type in sorted({page["source_type"] for page in pages})
        },
        "pages": pages,
    }
    manifest_path = output / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    kaggle = output / "kaggle-dataset"
    if kaggle.exists():
        shutil.rmtree(kaggle)
    (kaggle / "inputs").mkdir(parents=True)
    (kaggle / "code").mkdir()
    shutil.copy2(manifest_path, kaggle / "manifest.json")
    shutil.copy2(
        ROOT / "tools/processing/run_document_pipeline_pilot.py",
        kaggle / "code/run_document_pipeline_pilot.py",
    )
    for row in pages:
        shutil.copy2(output / row["input_pdf"], kaggle / row["input_pdf"])
    (kaggle / "dataset-metadata.json").write_text(
        json.dumps(
            {
                "title": "Vietnamese Enterprise Document Pipeline Pilot v1",
                "id": "ltrngnhn/vietnamese-enterprise-document-pipeline-pilot-v1",
                "licenses": [{"name": "other"}],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return manifest_path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    manifest_path = package(args.output)
    print(f"Wrote {manifest_path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
