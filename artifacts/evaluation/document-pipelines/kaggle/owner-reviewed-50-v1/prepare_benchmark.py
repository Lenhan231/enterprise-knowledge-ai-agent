"""Build Kaggle inference inputs and local scoring references for reviewed pages."""

from __future__ import annotations

import hashlib
import json
import shutil
import zipfile
from pathlib import Path

import fitz


HERE = Path(__file__).resolve().parent
BASE = HERE.parents[1]
DATA = BASE / "data"
ARCHIVE = BASE / "archive/duplicate-review-pages-20261023T092149Z.json"
CORE_SOURCE = BASE.parents[2] / "src/core/document_processing"
RUNNER = HERE / "run_end_to_end_kaggle.py"
PACKAGE = HERE / "input-package"
REFERENCES = HERE / "references"
KERNELS = HERE / "kernels"
DATASET_ID = "letrongnhan/vietnamese-enterprise-owner-reviewed-e2e-50-v1"
PIPELINES = ("docling", "mineru", "pp-structurev3")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def pdf_index(*roots: Path) -> dict[str, Path]:
    files: dict[str, Path] = {}
    for root in roots:
        if root.exists():
            for path in root.rglob("*.pdf"):
                files.setdefault(sha256(path), path)
    return files


def read_reviewed_pages() -> list[dict]:
    state_path = DATA / "local-review-state.json"
    if state_path.is_file():
        state = json.loads(state_path.read_text(encoding="utf-8"))
        pages = [
            {**row["page_data"], "annotation_status": row.get("annotation_status")}
            for row in state.get("reviews", [])
            if row.get("annotation_status") == "owner_reviewed"
        ]
        if not pages:
            raise ValueError("Local review state contains no owner-reviewed pages")
        keys = {(row["source_pdf_sha256"], int(row["source_page_number"])) for row in pages}
        if len(keys) != len(pages):
            raise ValueError("Local review state contains duplicate source PDF/page identities")
        if any(not row.get("ocr_reference_draft") or not row.get("layout_regions") or not row.get("reading_order") for row in pages):
            raise ValueError("An owner-reviewed page is missing OCR, layout, or reading-order references")
        return sorted(pages, key=lambda row: (row["source_pdf_sha256"], int(row["source_page_number"])))

    snapshot = json.loads(ARCHIVE.read_text(encoding="utf-8"))
    removed = {row["removed_review"]["page_key"] for row in snapshot["removed_pages"]}
    pages = [
        row["page_data"]
        for row in snapshot["state_before"]["reviews"]
        if row["page_key"] not in removed
    ]
    if len(pages) != 35 or any(row.get("annotation_status") != "owner_reviewed" for row in pages):
        raise ValueError(f"Expected 35 owner-reviewed fallback pages; got {len(pages)}")
    keys = {(row["source_pdf_sha256"], int(row["source_page_number"])) for row in pages}
    if len(keys) != 35:
        raise ValueError("Review references contain duplicate source PDF/page identities")
    if any(not row.get("ocr_reference_draft") or not row.get("layout_regions") or not row.get("reading_order") for row in pages):
        raise ValueError("A reviewed page is missing OCR, layout, or reading-order references")
    return sorted(pages, key=lambda row: (row["source_pdf_sha256"], int(row["source_page_number"])))


def one_page_pdf(source: Path, page_number: int, output: Path) -> tuple[float, float]:
    with fitz.open(source) as document:
        if page_number < 1 or page_number > document.page_count:
            raise ValueError(f"Page {page_number} is outside {source.name} ({document.page_count} pages)")
        page = document.load_page(page_number - 1)
        width, height = page.rect.width, page.rect.height
        with fitz.open() as single_page:
            single_page.insert_pdf(document, from_page=page_number - 1, to_page=page_number - 1)
            single_page.save(output, garbage=3, deflate=True)
    return width, height


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")


def main() -> None:
    for path in (PACKAGE, REFERENCES, KERNELS):
        if path.exists():
            raise FileExistsError(f"Refusing to overwrite existing benchmark data: {path}")

    pages = read_reviewed_pages()
    page_pdfs = pdf_index(DATA / "pages", BASE / "archive/legacy/end-to-end/data/pages")
    source_pdfs = pdf_index(DATA / "uploads", BASE / "archive/legacy/end-to-end/data/source-documents/inputs")
    if not CORE_SOURCE.is_dir():
        raise FileNotFoundError(CORE_SOURCE)
    if not RUNNER.is_file():
        raise FileNotFoundError(RUNNER)

    (PACKAGE / "inputs").mkdir(parents=True)
    manifest: list[dict] = []
    ocr_refs: list[dict] = []
    layout_refs: list[dict] = []
    order_refs: list[dict] = []
    table_refs: list[dict] = []

    for index, page in enumerate(pages, start=1):
        input_id = f"OR50-{index:03d}"
        output_pdf = PACKAGE / "inputs" / f"{input_id}.pdf"
        page_hash = page.get("source_page_pdf_sha256")
        if page_hash and page_hash in page_pdfs:
            shutil.copyfile(page_pdfs[page_hash], output_pdf)
            with fitz.open(output_pdf) as doc:
                if doc.page_count != 1:
                    raise ValueError(f"Expected one page in {page_pdfs[page_hash]}")
                page_width, page_height = doc[0].rect.width, doc[0].rect.height
        else:
            source = source_pdfs.get(page["source_pdf_sha256"])
            if source is None:
                raise FileNotFoundError(f"Source PDF unavailable for {page['document_id']} page {page['source_page_number']}")
            page_width, page_height = one_page_pdf(source, int(page["source_page_number"]), output_pdf)

        input_hash = sha256(output_pdf)
        common = {
            "input_id": input_id,
            "document_id": page["document_id"],
            "source_page_number_1based": int(page["source_page_number"]),
            "source_pdf_sha256": page["source_pdf_sha256"],
            "source_image_sha256": page["source_image_sha256"],
            "reference_status": "owner_reviewed_against_original_source",
            "scoring_eligible": True,
            "owner_reviewed_at": page.get("owner_reviewed_at"),
        }
        manifest.append({
            "document_id": input_id,
            "input": f"inputs/{input_id}.pdf",
            "pages": 1,
            "sha256": input_hash,
            "source_document_id": page["document_id"],
            "source_page_number": int(page["source_page_number"]),
            "source_pdf_sha256": page["source_pdf_sha256"],
            "page_width_pt": page_width,
            "page_height_pt": page_height,
        })
        ocr_refs.append({**common, "ocr_reference_text": page["ocr_reference_draft"]})
        layout_refs.append({
            **common,
            "regions": [
                {key: region[key] for key in ("region_id", "label", "bbox_norm")}
                for region in page["layout_regions"]
            ],
        })
        order_refs.append({**common, "reading_order": page["reading_order"]})
        if page.get("table_reference_draft"):
            table_region = next(region for region in page["layout_regions"] if region["label"] == "table")
            table_refs.append({
                **common,
                "table_bbox_norm": table_region["bbox_norm"],
                "table_name": page["table_reference_draft"].get("table_name"),
                "cell_grid": page["table_reference_draft"]["grid"],
            })

    write_jsonl(PACKAGE / "manifest.jsonl", manifest)
    with zipfile.ZipFile(PACKAGE / "document_processing_source.zip", "w", zipfile.ZIP_DEFLATED) as source_archive:
        for source_file in CORE_SOURCE.rglob("*.py"):
            source_archive.write(source_file, source_file.relative_to(CORE_SOURCE.parents[1]))
    shutil.copyfile(RUNNER, PACKAGE / "run_end_to_end_kaggle.py")
    metadata = {
        "title": "Vietnamese Enterprise Owner Reviewed E2E 50 v1",
        "id": DATASET_ID,
        "licenses": [{"name": "other"}],
    }
    for filename in ("dataset-metadata.json", "datasets-metadata.json"):
        (PACKAGE / filename).write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    (PACKAGE / "README.md").write_text(
        "# Owner reviewed E2E inference inputs v1\n\n"
        "Private Kaggle input package with owner-reviewed one-page PDFs and source hashes. "
        "OCR/layout/table references are stored outside the Kaggle package.\n",
        encoding="utf-8",
    )

    REFERENCES.mkdir(parents=True)
    write_jsonl(REFERENCES / "ocr.jsonl", ocr_refs)
    write_jsonl(REFERENCES / "layout.jsonl", layout_refs)
    write_jsonl(REFERENCES / "reading-order.jsonl", order_refs)
    write_jsonl(REFERENCES / "tables-5.jsonl", table_refs)
    (REFERENCES / "README.md").write_text(
        "# Scoring references — owner-reviewed pages\n\n"
        "These references are deliberately excluded from the Kaggle input. "
        "Rows come from the saved local owner-review state.\n",
        encoding="utf-8",
    )

    for pipeline in PIPELINES:
        folder = KERNELS / pipeline
        folder.mkdir(parents=True)
        kernel_id = f"letrongnhan/e2e-owner-reviewed-50-v1-{pipeline}"
        kernel_meta = {
            "id": kernel_id,
            "title": f"E2E Owner Reviewed 50 v1 - {pipeline}",
            "code_file": "run.py",
            "language": "python",
            "kernel_type": "script",
            "is_private": "true",
            "enable_gpu": False,
            "enable_tpu": "false",
            "enable_internet": "true",
            "machine_shape": "",
            "dataset_sources": [DATASET_ID],
            "competition_sources": [],
            "kernel_sources": [],
            "model_sources": [],
        }
        (folder / "kernel-metadata.json").write_text(json.dumps(kernel_meta, indent=2) + "\n", encoding="utf-8")
        (folder / "run.py").write_text(
            "import os, runpy\nfrom pathlib import Path\n"
            f"os.environ['END_TO_END_PIPELINE'] = {pipeline!r}\n"
            "matches = list(Path('/kaggle/input').rglob('run_end_to_end_kaggle.py'))\n"
            "if len(matches) != 1:\n    raise RuntimeError(f'Expected one shared runner, found {matches}')\n"
            "runpy.run_path(str(matches[0]), run_name='__main__')\n",
            encoding="utf-8",
        )

    print(f"Prepared {len(manifest)} input pages; references: OCR/layout/order={len(ocr_refs)}, tables={len(table_refs)}")
    print(f"Inputs: {PACKAGE}")
    print(f"Private scoring references: {REFERENCES}")
    print(f"Kaggle kernels: {KERNELS}")


if __name__ == "__main__":
    main()
