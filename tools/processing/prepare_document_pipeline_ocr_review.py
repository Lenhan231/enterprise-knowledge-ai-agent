#!/usr/bin/env python3
"""Build a deterministic, human-reviewable OCR crop queue for the pipeline benchmark."""
from __future__ import annotations

import csv
import argparse
import hashlib
import json
from collections import defaultdict
from pathlib import Path

import fitz
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "artifacts/evaluation/document-pipelines/ocr/candidate-review"
TARGET = 500
DEFAULT_COUNT = 520
DPI = 180


def issuer_of(page: dict) -> str:
    return page.get("company") or Path(page.get("file", "unknown")).parent.name


def key_of(page: dict) -> tuple:
    return (
        page.get("source_pdf_sha256") or page.get("file"),
        page.get("page"),
        tuple(round(float(v), 3) for v in (page.get("clip_rect") or [])),
    )


def reference_rank(page: dict) -> tuple:
    method = (page.get("reference_annotation_method") or "").lower()
    manual = int("manual" in method or "single_reviewer_visual_checked" in method)
    reviewed = int("visual_checked" in method or "visual_review" in method or "corrected" in method)
    text = page.get("reference_text") or ""
    return (manual, reviewed, bool(text), len(text))


def round_robin(rows: list[dict], count: int, *, per_issuer_cap: int, page_cap: int,
                excluded_pages: set[tuple] | None = None) -> list[dict]:
    groups: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        groups[row["issuer"]].append(row)
    for group in groups.values():
        group.sort(key=lambda r: (r["source_file"], r["page"], r["sample_key"]))
    issuers = sorted(groups)
    selected: list[dict] = []
    issuer_counts: dict[str, int] = defaultdict(int)
    page_counts: dict[tuple, int] = defaultdict(int)
    excluded_pages = excluded_pages or set()
    while len(selected) < count:
        added = False
        for issuer in issuers:
            if issuer_counts[issuer] >= per_issuer_cap:
                continue
            for row in groups[issuer]:
                page_key = (row["source_hash"], row["page"])
                if row.get("selected") or page_key in excluded_pages or page_counts[page_key] >= page_cap:
                    continue
                row["selected"] = True
                selected.append(row)
                issuer_counts[issuer] += 1
                page_counts[page_key] += 1
                added = True
                break
            if len(selected) >= count:
                break
        if not added:
            raise RuntimeError(f"Could not select {count} samples; got {len(selected)}")
    return selected


def main() -> None:
    global OUTPUT, TARGET
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUTPUT, help="New output directory (must not exist)")
    parser.add_argument("--count", type=int, default=DEFAULT_COUNT, help=f"Number of candidate crops to select (default: {DEFAULT_COUNT})")
    args = parser.parse_args()
    if args.count < TARGET:
        parser.error(f"--count must be at least {TARGET}")
    TARGET = args.count
    OUTPUT = args.output if args.output.is_absolute() else ROOT / args.output
    if OUTPUT.exists():
        raise FileExistsError(f"Refusing to overwrite existing review package: {OUTPUT}")

    pilot = json.loads((ROOT / "artifacts/evaluation/document-pipelines/pilot-v1/manifest.json").read_text())
    pilot_files = {str(Path(item["source_file"])) for item in pilot["pages"]}
    grouped: dict[tuple, list[tuple[str, dict, dict]]] = defaultdict(list)
    for manifest_path in sorted((ROOT / "data/evaluation/ocr").glob("*_ground_truth.json")):
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        if "commerce" in str(data.get("dataset_id", "")).lower():
            continue
        for page in data.get("pages", []):
            if "commerce" in str(page.get("company", "")).lower():
                continue
            grouped[key_of(page)].append((str(manifest_path.relative_to(ROOT)), data, page))

    candidates: list[dict] = []
    excluded_missing: set[str] = set()
    source_hashes: dict[str, str] = {}
    for sample_key, records in grouped.items():
        records.sort(key=lambda item: (reference_rank(item[2]), item[0]), reverse=True)
        manifest, data, page = records[0]
        source_rel = page.get("file")
        if not source_rel or not Path(source_rel).is_file():
            if source_rel:
                excluded_missing.add(source_rel)
            continue
        if source_rel in pilot_files:
            continue
        if page.get("layout_type") in {"table", "financial_table"}:
            continue
        if page.get("page") is None:
            continue
        source_path = ROOT / source_rel
        if source_rel not in source_hashes:
            source_hashes[source_rel] = hashlib.sha256(source_path.read_bytes()).hexdigest()
        source_hash = source_hashes[source_rel]
        expected_hash = page.get("source_pdf_sha256")
        if expected_hash and source_hash != expected_hash:
            raise ValueError(f"Source hash mismatch: {source_rel}")
        candidates.append({
            "sample_key": hashlib.sha256(repr(sample_key).encode()).hexdigest()[:12],
            "records": records,
            "manifest": manifest,
            "dataset_id": data.get("dataset_id"),
            "page_spec": page,
            "source_file": source_rel,
            "source_hash": source_hash,
            "page": int(page["page"]),
            "issuer": issuer_of(page),
            "has_clip": bool(page.get("clip_rect")),
        })

    clipped = [row for row in candidates if row["has_clip"]]
    full_page = [row for row in candidates if not row["has_clip"]]
    # Maximize region crops, then fill the queue with whole-page text candidates.
    selected = round_robin(clipped, min(len(clipped), TARGET), per_issuer_cap=24, page_cap=8)
    remaining = TARGET - len(selected)
    selected_pages = {(row["source_hash"], row["page"]) for row in selected}
    if remaining:
        selected.extend(round_robin(full_page, remaining, per_issuer_cap=12, page_cap=1,
                                    excluded_pages=selected_pages))
    if len(selected) != TARGET:
        raise RuntimeError(f"Expected {TARGET} selected samples, got {len(selected)}")
    if len({(r["source_hash"], r["page"]) for r in selected}) < 100:
        raise RuntimeError("Selected queue does not cover the 100-page minimum")
    if len({r["source_file"] for r in selected}) < 30:
        raise RuntimeError("Selected queue does not cover the 30-document minimum")

    OUTPUT.mkdir(parents=True)
    crops_dir = OUTPUT / "crops"
    crops_dir.mkdir()
    review_rows = []
    json_items = []
    for index, row in enumerate(selected, start=1):
        page_spec = row["page_spec"]
        sample_id = f"OCR-CAND-{index:03d}"
        with fitz.open(ROOT / row["source_file"]) as pdf:
            if not (1 <= row["page"] <= len(pdf)):
                raise ValueError(f"Page out of range for {row['source_file']}: {row['page']}")
            page = pdf[row["page"] - 1]
            clip = fitz.Rect(page_spec["clip_rect"]) if page_spec.get("clip_rect") else None
            if clip:
                clip = clip & page.rect
                if clip.is_empty:
                    raise ValueError(f"Empty crop for {sample_id}")
            pix = page.get_pixmap(dpi=DPI, alpha=False, clip=clip)
            image = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
            crop_rel = f"crops/{sample_id}.jpg"
            image.save(OUTPUT / crop_rel, format="JPEG", quality=92, optimize=True)

        ref_text = page_spec.get("reference_text") or ""
        alternate_refs = []
        seen_refs = {ref_text}
        for _, alt_data, alt_page in row["records"]:
            text = alt_page.get("reference_text") or ""
            if text and text not in seen_refs:
                alternate_refs.append({
                    "manifest": _,
                    "dataset_id": alt_data.get("dataset_id"),
                    "reference_annotation_method": alt_page.get("reference_annotation_method"),
                    "reference_text": text,
                })
                seen_refs.add(text)
        status = "needs_review"
        review_rows.append({
            "sample_id": sample_id,
            "crop_image": crop_rel,
            "include_in_prose_ocr": "",
            "corrected_transcript": "",
            "issue_tags": "",
            "reviewer_id": "",
            "review_status": status,
            "source_file": row["source_file"],
            "source_pdf_sha256": row["source_hash"],
            "page_number_1based": row["page"],
            "clip_rect_pdf_points": json.dumps(page_spec.get("clip_rect"), ensure_ascii=False),
            "issuer": row["issuer"],
            "document_id": page_spec.get("document_id"),
            "layout_type_candidate": page_spec.get("layout_type"),
            "scan_candidate": page_spec.get("physical_scan") is True or page_spec.get("image_only") is True,
            "reference_text_candidate": ref_text,
            "reference_annotation_method_candidate": page_spec.get("reference_annotation_method"),
            "source_manifest": row["manifest"],
            "source_record_id": page_spec.get("id"),
        })
        json_items.append({
            **review_rows[-1],
            "alternate_reference_candidates": alternate_refs,
            "source_pdf_url": page_spec.get("source_url"),
            "crop_dpi": DPI,
        })

    columns = list(review_rows[0])
    with (OUTPUT / "review.csv").open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()
        writer.writerows(review_rows)
    (OUTPUT / "queue.json").write_text(json.dumps({
        "dataset_id": "vietnamese-enterprise-ocr-review",
        "status": "candidate_queue_needs_human_review",
        "sample_count": TARGET,
        "crop_dpi": DPI,
        "items": json_items,
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    source_counts: dict[str, int] = defaultdict(int)
    issuer_counts: dict[str, int] = defaultdict(int)
    for row in selected:
        source_counts[row["source_file"]] += 1
        issuer_counts[row["issuer"]] += 1
    summary = {
        "sample_count": len(selected),
        "bounded_crop_count": sum(row["has_clip"] for row in selected),
        "full_page_crop_count": sum(not row["has_clip"] for row in selected),
        "unique_pages": len({(r["source_hash"], r["page"]) for r in selected}),
        "source_pdfs": len(source_counts),
        "issuers": len(issuer_counts),
        "scan_candidate_count": sum(
            r["page_spec"].get("physical_scan") is True or r["page_spec"].get("image_only") is True
            for r in selected
        ),
        "pilot_source_pdfs_excluded": len(pilot_files),
        "missing_source_paths_excluded": sorted(excluded_missing),
        "source_pdf_sha256_verified": True,
        "split_assignment": "none; assign after human review and group by document/issuer",
        "source_counts": dict(sorted(source_counts.items())),
        "issuer_counts": dict(sorted(issuer_counts.items())),
    }
    (OUTPUT / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (OUTPUT / "README.md").write_text(
        "# OCR review queue\n\n"
        "This is a review queue, not accepted ground truth or benchmark scores. "
        "All 500 images were rendered from source PDFs at 180 DPI. The existing transcript is only a candidate; "
        "inspect the crop, correct it in `review.csv`, mark whether it belongs in prose CER/WER, add issue tags, "
        "reviewer ID, and set review status. Use `include_in_prose_ocr=no` for table-only or unusable crops.\n\n"
        "`queue.json` preserves alternate transcript candidates when the same crop appeared in multiple manifests. "
        "No development/validation/test split is assigned yet. When labels are adjudicated, split by issuer/document "
        "and keep all pilot source documents out of the locked test.\n\n"
        "This candidate queue is separate from the canonical scoring input at `ocr/reference/`. "
        "The script refuses to overwrite an existing queue.\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
