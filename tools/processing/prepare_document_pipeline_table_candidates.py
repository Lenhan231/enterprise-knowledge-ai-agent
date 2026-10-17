"""Find ruled table candidates in the enterprise OCR source PDFs."""

from __future__ import annotations

import csv
import argparse
import hashlib
import json
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import fitz
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
OCR_REFS = ROOT / "artifacts/evaluation/document-pipelines/ocr/reference/reference.csv"
OUTPUT = ROOT / "artifacts/evaluation/document-pipelines/tables/candidate-review"


def scan_pdf(source_file: str) -> list[dict]:
    path = ROOT / source_file
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    result = []
    with fitz.open(path) as document:
        for page_number, page in enumerate(document, start=1):
            try:
                tables = page.find_tables().tables
            except Exception:
                continue
            for index, table in enumerate(tables, start=1):
                cells = table.extract()
                columns = max((len(row) for row in cells), default=0)
                if len(cells) < 3 or columns < 2:
                    continue
                nonempty = sum(bool(str(cell or "").strip()) for row in cells for cell in row)
                if nonempty < max(6, len(cells) * columns * 0.25):
                    continue
                result.append({
                    "source_file": source_file,
                    "source_pdf_sha256": digest,
                    "page_number_1based": page_number,
                    "candidate_index_on_page": index,
                    "bbox_pdf_points": [round(v, 2) for v in table.bbox],
                    "row_count_candidate": len(cells),
                    "column_count_candidate": columns,
                    "cell_grid_candidate": [[str(v or "").strip() for v in row] for row in cells],
                    "candidate_method": "PyMuPDF find_tables; requires visual assistant adjudication",
                    "status": "candidate_only_not_ground_truth",
                })
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--count", type=int, default=220)
    args = parser.parse_args()
    output = args.output if args.output.is_absolute() else ROOT / args.output
    if output.exists():
        raise FileExistsError(f"Refusing to overwrite {output}")
    with OCR_REFS.open(encoding="utf-8-sig", newline="") as file:
        refs = list(csv.DictReader(file))
    sources = sorted({row["source_file"] for row in refs})
    issuer_by_source = {}
    for row in refs:
        issuer_by_source.setdefault(row["source_file"], row["issuer"])

    candidates: list[dict] = []
    with ProcessPoolExecutor(max_workers=2) as pool:
        futures = {pool.submit(scan_pdf, source): source for source in sources}
        for future in as_completed(futures):
            found = future.result()
            for candidate in found:
                candidate["issuer"] = issuer_by_source[candidate["source_file"]]
                candidates.append(candidate)
            print(f"scanned {futures[future]}: +{len(found)} candidates; total={len(candidates)}", flush=True)

    grouped: dict[str, list[dict]] = defaultdict(list)
    for item in candidates:
        grouped[item["issuer"]].append(item)
    for items in grouped.values():
        items.sort(key=lambda x: (x["source_file"], x["page_number_1based"], x["candidate_index_on_page"]))
    selected: list[dict] = []
    round_index = 0
    while len(selected) < min(args.count, len(candidates)):
        added = False
        for issuer in sorted(grouped):
            if round_index < len(grouped[issuer]):
                item = grouped[issuer][round_index]
                item["table_id"] = f"TBL-{len(selected)+1:03d}"
                selected.append(item)
                added = True
                if len(selected) == args.count:
                    break
        if not added:
            break
        round_index += 1

    output.mkdir(parents=True)
    crops_dir = output / "crops"
    crops_dir.mkdir()
    for item in selected:
        with fitz.open(ROOT / item["source_file"]) as document:
            page = document[item["page_number_1based"] - 1]
            clip = fitz.Rect(item["bbox_pdf_points"]) & page.rect
            pix = page.get_pixmap(dpi=120, clip=clip, alpha=False)
            image = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
            image.save(crops_dir / f"{item['table_id']}.jpg", quality=92)
        item["crop_image"] = f"crops/{item['table_id']}.jpg"

    (output / "candidates.json").write_text(json.dumps({
        "dataset_id": "vietnam-enterprise-table-candidates-v1",
        "status": "candidate_queue_not_adjudicated",
        "candidate_count": len(candidates),
        "selected_count": len(selected),
        "requested_candidate_count": args.count,
        "selected_source_documents": len({x["source_file"] for x in selected}),
        "selected_issuers": len({x["issuer"] for x in selected}),
        "selection_unit": "detector-generated ruled table bounding box; visual verification required",
        "items": selected,
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"candidates": len(candidates), "selected": len(selected),
                      "source_documents": len({x['source_file'] for x in selected}),
                      "issuers": len({x['issuer'] for x in selected}), "output": str(output)}, indent=2))


if __name__ == "__main__":
    main()
