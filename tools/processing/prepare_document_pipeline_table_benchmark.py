"""Build the assistant-adjudicated table crop benchmark package."""

from __future__ import annotations

import csv
import hashlib
import json
import argparse
from pathlib import Path

import fitz

ROOT = Path(__file__).resolve().parents[2]
QUEUE = ROOT / "artifacts/evaluation/document-pipelines/tables/candidate-review"
ADJUDICATION = QUEUE / "adjudication-v1.csv"
OUTPUT = ROOT / "artifacts/evaluation/document-pipelines/tables/reference"
ACCEPTED_ADDITIONAL = {
    151, 152, 153, 154, 156, 157, 158, 159, 160, 161, 162, 164, 165, 166,
    167, 168, 169, 172, 173, 174, 176, 177, 179, 180, 181, 183, 186, 188,
    190, 191, 192, 193, 194, 195, 196, 197, 199, 201,
}
REJECTED_FIRST_BATCH = {
    4, 5, 9, 12, 14, 16, 18, 19, 24, 37, 38, 39, 46, 50, 51, 56, 58, 59, 62,
    63, 79, 81, 90, 91, 93, 96, 97, 98, 106, 108, 109, 111, 129, 135, 136,
    143, 149, 150,
}


def make_adjudication(items: list[dict]) -> list[dict]:
    decisions = []
    for item in items:
        number = int(item["table_id"].split("-")[1])
        if number <= 150:
            accepted = number not in REJECTED_FIRST_BATCH
        else:
            accepted = number in ACCEPTED_ADDITIONAL
        decisions.append({
            "candidate_id": item["table_id"],
            "decision": "accept" if accepted else "reject",
            "reason": (
                "Visually confirmed complete 18x5 financial-ratio table and source-PDF cell grid against the full page; not independently human-reviewed."
                if item["table_id"] == "TBL-201" else
                "Full table crop and 26x6 cell grid visually adjudicated from the source page; see provenance in the reference."
                if item["table_id"] == "TBL-197" else
                "False positive: source page is an industrial-park photograph with narrative text, not a table; excluded after full-page visual review."
                if item["table_id"] == "TBL-014" else
                "Visually confirmed complete tabular region; references use the source PDF cell grid."
                if accepted else
                "Visual review rejected as non-table, partial, decorative, or unsuitable as a complete table."
            ),
            "adjudication_method": "assistant visual review; not human-reviewed",
        })
    return decisions


def image_only_pdf(source: Path, bbox: list[float], page_number: int, target: Path) -> None:
    with fitz.open(source) as document:
        page = document[page_number - 1]
        clip = fitz.Rect(bbox) & page.rect
        pix = page.get_pixmap(dpi=180, clip=clip, alpha=False)
    image = fitz.Pixmap(pix, 0) if pix.alpha else pix
    page_width = image.width * 72 / 180
    page_height = image.height * 72 / 180
    pdf = fitz.open()
    output_page = pdf.new_page(width=page_width, height=page_height)
    output_page.insert_image(output_page.rect, stream=image.tobytes("png"))
    pdf.save(target, garbage=4, deflate=True)
    pdf.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--update-existing", action="store_true", help="Refresh the existing package in place after correcting candidates.")
    args = parser.parse_args()
    if OUTPUT.exists() and not args.update_existing:
        raise FileExistsError(f"Refusing to overwrite {OUTPUT}")
    queue = json.loads((QUEUE / "candidates.json").read_text(encoding="utf-8"))
    items = queue["items"]
    decisions = make_adjudication(items)
    QUEUE.mkdir(parents=True, exist_ok=True)
    with ADJUDICATION.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=list(decisions[0]))
        writer.writeheader()
        writer.writerows(decisions)

    decision_by_id = {row["candidate_id"]: row for row in decisions}
    selected = [item for item in items if decision_by_id[item["table_id"]]["decision"] == "accept"]
    if len(selected) != 150:
        raise ValueError(f"Expected 150 valid accepted tables after excluding TBL-014, got {len(selected)}")
    output = OUTPUT
    inputs = output / "inputs"
    inputs.mkdir(parents=True, exist_ok=True)
    previous_manifest = output / "kaggle-dataset" / "manifest.json"
    stable_ids = {}
    if previous_manifest.exists():
        previous = json.loads(previous_manifest.read_text(encoding="utf-8"))
        stable_ids = {item["candidate_id"]: item["reference_id"] for item in previous.get("items", [])}
    next_reference_number = max(
        (int(reference_id.split("-")[1]) for reference_id in stable_ids.values()),
        default=0,
    ) + 1
    for stale_input in inputs.glob("TAB-*.pdf"):
        stale_input.unlink()
    reference_rows = []
    for item in selected:
        reference_id = stable_ids.get(item["table_id"])
        if reference_id is None:
            reference_id = f"TAB-{next_reference_number:03d}"
            next_reference_number += 1
        input_file = f"{reference_id}.pdf"
        source = ROOT / item["source_file"]
        if hashlib.sha256(source.read_bytes()).hexdigest() != item["source_pdf_sha256"]:
            raise ValueError(f"Source PDF changed since table scan: {source}")
        image_only_pdf(source, item["bbox_pdf_points"], item["page_number_1based"], inputs / input_file)
        grid = [[str(cell or "").strip() for cell in row] for row in item["cell_grid_candidate"]]
        reference_rows.append({
            "reference_id": reference_id,
            "candidate_id": item["table_id"],
            "source_file": item["source_file"],
            "source_pdf_sha256": item["source_pdf_sha256"],
            "issuer": item["issuer"],
            "page_number_1based": item["page_number_1based"],
            "bbox_pdf_points": item["bbox_pdf_points"],
            "input_pdf": f"inputs/{input_file}",
            "cell_grid": grid,
            "row_count": len(grid),
            "column_count": max((len(row) for row in grid), default=0),
            "reference_provenance": (
                "Assistant visual adjudication of the complete 18x5 table extent and source-PDF cell grid; not independently human-reviewed"
                if item["table_id"] == "TBL-201" else
                "Assistant visual adjudication of full table extent and 26x6 cell grid, checked against source PDF text; not human-reviewed"
                if item["table_id"] == "TBL-197" else
                "PyMuPDF source-PDF cell extraction, visually confirmed table extent; cell text not independently human-reviewed"
            ),
            "split": "",
        })

    issuers = sorted({row["issuer"] for row in reference_rows})
    dev_issuers = set(issuers[: round(len(issuers) * 0.6)])
    validation_issuers = set(issuers[round(len(issuers) * 0.6): round(len(issuers) * 0.8)])
    previous_scores = ROOT / "artifacts/evaluation/document-pipelines/results/table-150-v1/table-comparison-149.json"
    previous_split_by_reference = {}
    previous_split_by_issuer = {}
    if previous_scores.exists():
        previous_items = json.loads(previous_scores.read_text(encoding="utf-8")).get("items", [])
        for item in previous_items:
            previous_split_by_reference[item["reference_id"]] = item["split"]
            previous_split_by_issuer.setdefault(item["issuer"], item["split"])
    for row in reference_rows:
        if row["reference_id"] in previous_split_by_reference:
            row["split"] = previous_split_by_reference[row["reference_id"]]
        elif row["issuer"] in previous_split_by_issuer:
            row["split"] = previous_split_by_issuer[row["issuer"]]
        else:
            row["split"] = "development" if row["issuer"] in dev_issuers else "validation" if row["issuer"] in validation_issuers else "locked_test"

    with (output / "reference.jsonl").open("w", encoding="utf-8") as file:
        for row in reference_rows:
            file.write(json.dumps(row, ensure_ascii=False) + "\n")
    manifest = {
        "dataset_id": "vietnam-enterprise-table-reference-v1",
        "status": "assistant-adjudicated_table_extents_and_cell_grids; TAB-149 manually reconstructed",
        "table_count": len(reference_rows),
        "source_document_count": len({row["source_file"] for row in reference_rows}),
        "issuer_count": len(issuers),
        "split_table_counts": {name: sum(row["split"] == name for row in reference_rows) for name in ("development", "validation", "locked_test")},
        "input": "isolated 180-DPI image-only PDF crop per table; no source PDF text layer",
        "label_limitations": "Table extents are assistant-adjudicated, not human-reviewed. Cell text is generally derived from the source PDF text layer; TAB-149 was manually reconstructed as a 26x6 grid and TAB-151's complete 18x5 financial-ratio grid was visually checked against its source page. Merged-cell spans are not independently reviewed; do not claim TEDS/TEDS-Struct.",
        "items": [{key: row[key] for key in ("reference_id", "candidate_id", "issuer", "source_file", "page_number_1based", "input_pdf", "split")} for row in reference_rows],
        "pages": [
            {"page_id": row["reference_id"], "input_pdf": row["input_pdf"], "split": row["split"]}
            for row in reference_rows
        ],
    }
    (output / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    dataset = output / "kaggle-dataset"
    dataset_inputs = dataset / "inputs"
    dataset_inputs.mkdir(parents=True, exist_ok=True)
    for stale_input in dataset_inputs.glob("TAB-*.pdf"):
        stale_input.unlink()
    for path in inputs.glob("*.pdf"):
        (dataset_inputs / path.name).write_bytes(path.read_bytes())
    kaggle_manifest = {**manifest, "items": manifest["items"]}
    (dataset / "manifest.json").write_text(json.dumps(kaggle_manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    metadata = {
        "title": "Vietnam Enterprise Table Recognition Benchmark v1",
        "id": "ltrngnhn/vietnam-enterprise-table-reference-v1",
        "licenses": [{"name": "other"}],
        "keywords": ["table-recognition", "vietnamese", "enterprise-documents"],
        "description": f"{len(reference_rows)} valid isolated image-only table crops. Labels and source-document identities are withheld from model inputs.",
    }
    (dataset / "dataset-metadata.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: manifest[key] for key in ("table_count", "source_document_count", "issuer_count", "split_table_counts")}, indent=2))


if __name__ == "__main__":
    main()
