"""Build a table-stratified 200-page enterprise layout input set."""

from __future__ import annotations

import hashlib
import json
import shutil
from collections import defaultdict
from pathlib import Path

import fitz
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "artifacts/evaluation/document-pipelines"
OLD = BASE / "layout/exploratory/manifest.json"
TABLES = BASE / "tables/reference/reference.jsonl"
OUTPUT = BASE / "layout/inputs"
DPI = 180
TARGETS = {"development": 120, "validation": 40, "locked_test": 40}


def main() -> None:
    if OUTPUT.exists():
        raise FileExistsError(f"Refusing to overwrite {OUTPUT}")
    old_pages = json.loads(OLD.read_text(encoding="utf-8"))["pages"]
    table_rows = [json.loads(line) for line in TABLES.read_text(encoding="utf-8").splitlines()]
    table_page_map: dict[tuple[str, int], list[str]] = defaultdict(list)
    table_sources = {}
    for row in table_rows:
        key = (row["source_pdf_sha256"], int(row["page_number_1based"]))
        table_page_map[key].append(row["candidate_id"])
        table_sources[key] = row

    selected: dict[tuple[str, int], dict] = {}
    for key, row in table_sources.items():
        selected[key] = {
            "source_file": row["source_file"], "source_pdf_sha256": row["source_pdf_sha256"],
            "page_number": int(row["page_number_1based"]), "issuer": row["issuer"],
            "selection_reason": "unique source page containing an adjudicated complete table",
            "table_reference_ids": sorted(table_page_map[key]), "is_pilot_page": False,
        }

    old_pages_by_issuer: dict[str, list[dict]] = defaultdict(list)
    for row in old_pages:
        key = (row["source_pdf_sha256"], int(row["page_number_source"]))
        if key in selected:
            continue
        item = {
            "source_file": row["source_file"], "source_pdf_sha256": row["source_pdf_sha256"],
            "page_number": int(row["page_number_source"]), "issuer": row["issuer"],
            "selection_reason": "existing representative text/figure page",
            "table_reference_ids": [], "is_pilot_page": bool(row.get("is_pilot_page", False)),
        }
        old_pages_by_issuer[item["issuer"]].append(item)
    for rows in old_pages_by_issuer.values():
        rows.sort(key=lambda row: (row["source_file"], row["page_number"]))

    extras: list[dict] = []
    # Retain every pilot page in development, then sample the remaining issuer groups evenly.
    for issuer in sorted(old_pages_by_issuer):
        pilot_rows = [row for row in old_pages_by_issuer[issuer] if row["is_pilot_page"]]
        for row in pilot_rows:
            key = (row["source_pdf_sha256"], row["page_number"])
            selected[key] = row
        old_pages_by_issuer[issuer] = [row for row in old_pages_by_issuer[issuer] if not row["is_pilot_page"]]

    target_extras = 200 - len(selected)
    round_index = 0
    while len(extras) < target_extras:
        added = False
        for issuer in sorted(old_pages_by_issuer):
            rows = old_pages_by_issuer[issuer]
            if round_index < len(rows):
                extras.append(rows[round_index])
                added = True
                if len(extras) == target_extras:
                    break
        if not added:
            raise ValueError(f"Not enough additional pages: needed {target_extras}, found {len(extras)}")
        round_index += 1
    for row in extras:
        selected[(row["source_pdf_sha256"], row["page_number"])] = row
    pages = list(selected.values())
    if len(pages) != 200:
        raise ValueError(f"Expected 200 unique pages, found {len(pages)}")

    grouped: dict[str, list[dict]] = defaultdict(list)
    for row in pages:
        grouped[row["issuer"]].append(row)
    # Keep pilot issuers out of validation/test; assign the other issuers by page-count balance.
    split_counts = {name: 0 for name in TARGETS}
    issuer_split = {}
    for issuer in sorted(grouped):
        if issuer in {"Long Hau", "Hòa Phát"}:
            split = "development"
        else:
            split = min(TARGETS, key=lambda name: (split_counts[name] / TARGETS[name], name))
        issuer_split[issuer] = split
        split_counts[split] += len(grouped[issuer])

    OUTPUT.mkdir(parents=True)
    (OUTPUT / "inputs").mkdir()
    (OUTPUT / "page-images").mkdir()
    manifest_pages = []
    for index, row in enumerate(sorted(pages, key=lambda value: (value["issuer"], value["source_file"], value["page_number"])), start=1):
        page_id = f"LAYOUTV2-{index:03d}"
        source = ROOT / row["source_file"]
        if hashlib.sha256(source.read_bytes()).hexdigest() != row["source_pdf_sha256"]:
            raise ValueError(f"Source PDF changed since selection: {source}")
        with fitz.open(source) as document:
            page = document[row["page_number"] - 1]
            pix = page.get_pixmap(dpi=DPI, alpha=False)
            image = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
        image_rel = f"page-images/{page_id}.jpg"
        image.save(OUTPUT / image_rel, format="JPEG", quality=90)
        input_rel = f"inputs/{page_id}.pdf"
        pdf = fitz.open()
        target = pdf.new_page(width=image.width * 72 / DPI, height=image.height * 72 / DPI)
        target.insert_image(target.rect, stream=(OUTPUT / image_rel).read_bytes())
        pdf.save(OUTPUT / input_rel, garbage=4, deflate=True)
        pdf.close()
        manifest_pages.append({
            "id": page_id, "input_pdf": input_rel, "page_image": image_rel,
            "source_file": row["source_file"], "source_pdf_sha256": row["source_pdf_sha256"],
            "page_number_source": row["page_number"], "issuer": row["issuer"],
            "split": issuer_split[row["issuer"]], "is_pilot_page": row["is_pilot_page"],
            "selection_reason": row["selection_reason"], "table_reference_ids": row["table_reference_ids"],
            "render_dpi": DPI,
        })

    manifest = {
        "dataset_id": "vietnam-enterprise-layout-200-pages-v2",
        "status": "table-stratified-inputs_benchmark-labels-not-complete",
        "page_count": len(manifest_pages), "render_dpi": DPI,
        "selection": "All 115 unique pages represented by the 150 table references, all 13 pilot pages, and 72 issuer-round-robin text/figure pages from layout/exploratory.",
        "split_assignment": "Issuer-level, weighted toward 120/40/40 pages; pilot issuers are development-only.",
        "split_counts": {name: sum(row["split"] == name for row in manifest_pages) for name in TARGETS},
        "table_source_pages": sum(bool(row["table_reference_ids"]) for row in manifest_pages),
        "pilot_pages": sum(row["is_pilot_page"] for row in manifest_pages),
        "pages": manifest_pages,
    }
    (OUTPUT / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    dataset = OUTPUT / "kaggle-dataset"
    (dataset / "inputs").mkdir(parents=True)
    for path in (OUTPUT / "inputs").glob("*.pdf"):
        shutil.copy2(path, dataset / "inputs" / path.name)
    kaggle_manifest = {
        "dataset_id": manifest["dataset_id"], "page_count": manifest["page_count"],
        "pages": [{"id": row["id"], "input_pdf": row["input_pdf"], "split": row["split"]} for row in manifest_pages],
    }
    (dataset / "manifest.json").write_text(json.dumps(kaggle_manifest, indent=2) + "\n", encoding="utf-8")
    metadata = {
        "title": "Vietnamese Enterprise Layout Benchmark 200 Pages v2",
        "id": "ltrngnhn/vietnam-enterprise-layout-200-pages-v2",
        "licenses": [{"name": "other"}],
    }
    (dataset / "dataset-metadata.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "pages": len(manifest_pages), "unique_issuers": len(issuer_split),
        "table_source_pages": manifest["table_source_pages"], "pilot_pages": manifest["pilot_pages"],
        "split_counts": manifest["split_counts"], "input_pdfs": len(list((OUTPUT / "inputs").glob("*.pdf"))),
        "output": str(OUTPUT),
    }, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
