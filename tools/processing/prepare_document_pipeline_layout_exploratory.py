"""Select and render a balanced 200-page full-page layout benchmark input set."""

from __future__ import annotations

import csv
import hashlib
import json
from collections import defaultdict
from pathlib import Path

import fitz
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "artifacts/evaluation/document-pipelines"
OCR_REFS = BASE / "ocr/reference/reference.csv"
PILOT = BASE / "pilot-v1/manifest.json"
OUTPUT = BASE / "layout/exploratory"
DPI = 180


def key(row: dict) -> tuple[str, int]:
    return row["source_pdf_sha256"], int(row["page_number"])


def main() -> None:
    if OUTPUT.exists():
        raise FileExistsError(f"Refusing to overwrite {OUTPUT}")
    with OCR_REFS.open(encoding="utf-8-sig", newline="") as file:
        refs = list(csv.DictReader(file))
    grouped: dict[str, dict[tuple[str, int], dict]] = defaultdict(dict)
    for row in refs:
        page = {
            "source_file": row["source_file"],
            "source_pdf_sha256": row["source_pdf_sha256"],
            "page_number": int(row["page_number_1based"]),
            "issuer": row["issuer"],
            "document_id": row["document_id"],
        }
        grouped[row["issuer"]].setdefault(key(page), page)

    pilot = json.loads(PILOT.read_text(encoding="utf-8"))
    pages: list[dict] = []
    pilot_docs = set()
    for row in pilot["pages"]:
        if not row.get("layout_reference_id"):
            continue
        source = row["source_file"]
        issuer = "Hòa Phát" if "/hpg/" in source else "Long Hau"
        item = {
            "source_file": source,
            "source_pdf_sha256": row["source_pdf_sha256"],
            "page_number": int(row["page_number"]),
            "issuer": issuer,
            "document_id": row["document_id"],
            "pilot_layout_reference_id": row["layout_reference_id"],
            "is_pilot_page": True,
        }
        pages.append(item)
        pilot_docs.add(source)

    for group in grouped.values():
        for page_key in list(group):
            if group[page_key]["source_file"] in pilot_docs:
                del group[page_key]
    selected = []
    round_index = 0
    need = 200 - len(pages)
    issuers = sorted(grouped, key=lambda value: hashlib.sha256(value.encode()).hexdigest())
    while len(selected) < need:
        added = False
        for issuer in issuers:
            candidates = sorted(grouped[issuer].values(), key=lambda p: (p["source_file"], p["page_number"]))
            if round_index < len(candidates):
                selected.append(candidates[round_index])
                added = True
                if len(selected) == need:
                    break
        if not added:
            raise RuntimeError(f"Only found {len(pages)+len(selected)} distinct eligible pages")
        round_index += 1
    pages.extend(selected)

    # Keep the source-document grouping intact and force all pilot issuer groups into development.
    issuer_counts = defaultdict(int)
    for page in pages:
        issuer_counts[page["issuer"]] += 1
    targets = {"development": 0.60, "validation": 0.20, "locked_test": 0.20}
    split_counts = {name: 0 for name in targets}
    issuer_split = {"Hòa Phát": "development", "Long Hau": "development"}
    for issuer in sorted(issuer_counts, key=lambda name: (-issuer_counts[name], name)):
        if issuer in issuer_split:
            split_counts["development"] += issuer_counts[issuer]
            continue
        name = min(targets, key=lambda value: (split_counts[value] / targets[value], value))
        issuer_split[issuer] = name
        split_counts[name] += issuer_counts[issuer]

    OUTPUT.mkdir(parents=True)
    (OUTPUT / "inputs").mkdir()
    (OUTPUT / "page-images").mkdir()
    output_pages = []
    for index, row in enumerate(pages, start=1):
        page_id = f"LAYOUT-{index:03d}"
        source = ROOT / row["source_file"]
        if hashlib.sha256(source.read_bytes()).hexdigest() != row["source_pdf_sha256"]:
            raise ValueError(f"Source changed after annotation: {row['source_file']}")
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
        output_pages.append({
            "id": page_id,
            "input_pdf": input_rel,
            "split": issuer_split[row["issuer"]],
            **row,
            "page_number_source": row.pop("page_number"),
            "page_image": image_rel,
            "render_dpi": DPI,
        })

    data = {
        "dataset_id": "vietnam-enterprise-layout-200-pages-v1",
        "status": "input_set_selected_labels_not_complete",
        "page_count": len(output_pages),
        "render_dpi": DPI,
        "split_assignment": "Issuer-level 60/20/20; pilot pages remain in development; labels are not attached to Kaggle.",
        "split_counts": split_counts,
        "pages": output_pages,
    }
    (OUTPUT / "manifest.json").write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "pages": len(output_pages),
        "issuers": len(issuer_split),
        "pilot_pages": sum(row.get("is_pilot_page", False) for row in output_pages),
        "split_counts": split_counts,
        "input_pdfs": len(list((OUTPUT / "inputs").glob("*.pdf"))),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
