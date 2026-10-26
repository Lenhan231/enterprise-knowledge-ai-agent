"""Loopback-only review UI backed by a local JSON store."""

from __future__ import annotations

import json
import hashlib
import logging
import os
import re
import shutil
import sys
import threading
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

PIPELINE_DIR = Path(__file__).resolve().parent
DATA_DIR = PIPELINE_DIR / "data"
sys.path.insert(0, str(DATA_DIR))

import fitz
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool
from auto_review_tracks import LABELS, build_tracks, write_tracks
from agents.bbox import run_bbox_agent
from agents.page_draft import run_page_draft_agent
from agents.table import run_table_agent
from agents.transcript import run_transcript_agent

STATE_PATH = DATA_DIR / "local-review-state.json"
STATE_LOCK = threading.Lock()
app = FastAPI(title="Document pipeline local review")
MAX_PDF_BYTES = 50 * 1024 * 1024
MAX_SELECTED_PAGES = 100
MAX_RENDER_PIXELS = 24_000_000
logger = logging.getLogger(__name__)


class PageReview(BaseModel):
    document_id: str = Field(min_length=1)
    source_page_number: int = Field(gt=0)
    draft_revision: int | None = None
    annotation_status: Literal["needs_owner_review", "owner_reviewed"]
    page_data: dict


def read_state() -> dict:
    try:
        state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {"format_version": 1, "source": "local review store", "reviews": []}
    except (OSError, json.JSONDecodeError) as error:
        raise HTTPException(503, "Could not read local review state") from error
    if not isinstance(state.get("reviews"), list):
        raise HTTPException(503, "Local review state has an invalid format")
    return state


def write_state(state: dict) -> None:
    temporary_path = STATE_PATH.with_suffix(".json.tmp")
    try:
        temporary_path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.replace(temporary_path, STATE_PATH)
    except OSError as error:
        temporary_path.unlink(missing_ok=True)
        raise HTTPException(503, "Could not save local review state") from error


def parse_page_selection(selection: str, page_count: int) -> list[int]:
    pages: set[int] = set()
    try:
        for part in selection.split(","):
            part = part.strip()
            if not part:
                continue
            if "-" in part:
                start_text, end_text = part.split("-", 1)
                start, end = int(start_text), int(end_text)
                if end < start:
                    raise ValueError
                if end - start + 1 > MAX_SELECTED_PAGES:
                    raise HTTPException(400, f"Select at most {MAX_SELECTED_PAGES} pages per upload")
                pages.update(range(start, end + 1))
            else:
                pages.add(int(part))
    except ValueError as error:
        raise HTTPException(400, "Pages must be numbers or ranges, for example 1,3-5") from error
    if not pages:
        raise HTTPException(400, "Select at least one PDF page")
    if len(pages) > MAX_SELECTED_PAGES:
        raise HTTPException(400, f"Select at most {MAX_SELECTED_PAGES} pages per upload")
    if min(pages) < 1 or max(pages) > page_count:
        raise HTTPException(400, f"Page numbers must be between 1 and {page_count}")
    return sorted(pages)


def safe_document_id(filename: str, digest: str) -> str:
    stem = Path(filename).stem.lower()
    slug = re.sub(r"[^a-z0-9]+", "-", stem).strip("-")[:48] or "document"
    return f"UPLOAD-{slug}-{digest[:10]}"


@app.on_event("startup")
def build_initial_tracks() -> None:
    with STATE_LOCK:
        write_tracks(read_state()["reviews"])


@app.get("/api/reviews")
def list_reviews() -> list[dict]:
    with STATE_LOCK:
        return read_state()["reviews"]


@app.get("/api/reviews/export")
def export_reviewed_references() -> dict:
    with STATE_LOCK:
        records, summary = build_tracks(read_state()["reviews"])
    return {
        "format": "owner-reviewed-benchmark-references-v1",
        "status": "owner_reviewed",
        "generated_at": summary["generated_at"],
        "track_record_counts": summary["track_record_counts"],
        "references": records,
    }


@app.post("/api/reviews/{document_id}/pages/{page_number}/generate-draft")
async def generate_page_draft(document_id: str, page_number: int) -> dict:
    page_key = f"{document_id}:p{page_number}"
    with STATE_LOCK:
        state = read_state()
        row = next((item for item in state["reviews"] if item.get("page_key") == page_key), None)
        if row is None:
            raise HTTPException(404, "Save this page in the local review store before generating a draft")
        if row.get("annotation_status") != "needs_owner_review":
            raise HTTPException(409, "AI drafts are available only for pages that still need owner review")
        page_data = json.loads(json.dumps(row.get("page_data") or {}))
        expected_updated_at = row.get("updated_at")

    if shutil.which("codex") is None:
        raise HTTPException(503, "Codex CLI is not installed or is missing from the review server PATH")
    source_image = page_data.get("source_image")
    if not isinstance(source_image, str) or not source_image:
        raise HTTPException(400, "This page has no source image")
    image_path = (DATA_DIR / source_image).resolve()
    if not image_path.is_relative_to(DATA_DIR.resolve()) or not image_path.is_file():
        raise HTTPException(404, "The source page image is missing")
    image_bytes = image_path.read_bytes()
    source_hash = page_data.get("source_image_sha256")
    if source_hash and hashlib.sha256(image_bytes).hexdigest() != source_hash:
        raise HTTPException(409, "The source image no longer matches its recorded SHA-256")

    try:
        draft, model = await run_in_threadpool(run_page_draft_agent, image_bytes)
    except ValueError as error:
        raise HTTPException(502, str(error)) from error
    except Exception as error:
        logger.exception("Codex CLI page-draft request failed for %s", page_key)
        raise HTTPException(502, f"Codex CLI could not generate this draft: {error}") from error

    generated_at = datetime.now(timezone.utc).isoformat()
    page_data.update({
        "ocr_reference_draft": draft.ocr_text,
        "ocr_draft_source": f"Codex CLI vision draft from source page; {model}; verify against the original image.",
        "layout_regions": [
            {
                "region_id": region.region_id,
                "label": region.label,
                "bbox_norm": region.bbox_norm,
                "coordinate_system": "normalized_top_left_0_1",
                "bbox_status": "assistant_draft",
            }
            for region in draft.regions
        ],
        "reading_order": draft.reading_order,
        "table_presence_reviewed": False,
        "table_reference_drafts": [
            {
                "region_id": table.region_id,
                "table_name": table.table_name,
                "source_candidate_id": f"AI-CODEX-{page_number}-T{index}",
                "source_candidate_status": "assistant_visual_draft",
                "draft_origin": f"Codex CLI vision model; {model}; owner review required before scoring.",
                "grid": table.grid,
            }
            for index, table in enumerate(draft.tables, start=1)
        ],
        "ai_draft_metadata": {
            "provider": "codex_cli",
            "model": model,
            "generated_at": generated_at,
            "uncertain_items": draft.uncertain_items,
        },
        "draft_completeness": "codex_visual_draft_requires_owner_review",
        "annotation_status": "needs_owner_review",
        "draft_revision": int(page_data.get("draft_revision") or 0) + 1,
    })
    page_data.pop("owner_reviewed_at", None)
    page_data.pop("reviewed_draft_revision", None)
    page_data.pop("stale_review", None)

    with STATE_LOCK:
        state = read_state()
        reviews = state["reviews"]
        row_index = next((i for i, item in enumerate(reviews) if item.get("page_key") == page_key), None)
        if row_index is None or reviews[row_index].get("updated_at") != expected_updated_at:
            raise HTTPException(409, "This page changed while Codex was generating; reload it and try again")
        updated_at = datetime.now(timezone.utc).isoformat()
        reviews[row_index] = {
            "page_key": page_key,
            "draft_revision": page_data["draft_revision"],
            "annotation_status": "needs_owner_review",
            "page_data": page_data,
            "updated_at": updated_at,
        }
        state["source"] = "local review store"
        state["exported_at"] = updated_at
        write_state(state)
        track_counts = write_tracks(reviews)
    return {"page_data": page_data, "track_counts": track_counts}


@app.post("/api/reviews/{document_id}/pages/{page_number}/generate-bbox-draft")
async def generate_bbox_draft(document_id: str, page_number: int) -> dict:
    page_key = f"{document_id}:p{page_number}"
    with STATE_LOCK:
        state = read_state()
        row = next((item for item in state["reviews"] if item.get("page_key") == page_key), None)
        if row is None:
            raise HTTPException(404, "Save this page in the local review store before generating bbox draft")
        if row.get("annotation_status") != "needs_owner_review":
            raise HTTPException(409, "AI bbox drafts are available only for pages that still need owner review")
        page_data = json.loads(json.dumps(row.get("page_data") or {}))
        expected_updated_at = row.get("updated_at")

    regions = page_data.get("layout_regions")
    if not isinstance(regions, list) or not regions:
        raise HTTPException(409, "Draw at least one layout region before asking Codex to refine its boxes")
    source_image = page_data.get("source_image")
    if not isinstance(source_image, str) or not source_image:
        raise HTTPException(400, "This page has no source image")
    image_path = (DATA_DIR / source_image).resolve()
    if not image_path.is_relative_to(DATA_DIR.resolve()) or not image_path.is_file():
        raise HTTPException(404, "The source page image is missing")
    image_bytes = image_path.read_bytes()
    source_hash = page_data.get("source_image_sha256")
    if source_hash and hashlib.sha256(image_bytes).hexdigest() != source_hash:
        raise HTTPException(409, "The source image no longer matches its recorded SHA-256")

    try:
        draft, model = await run_in_threadpool(run_bbox_agent, image_bytes, regions)
    except ValueError as error:
        raise HTTPException(502, str(error)) from error
    except Exception as error:
        logger.exception("Codex CLI bbox-draft request failed for %s", page_key)
        raise HTTPException(502, f"Codex CLI could not generate bbox draft: {error}") from error

    generated_at = datetime.now(timezone.utc).isoformat()
    boxes = {region.region_id: region.bbox_norm for region in draft.regions}
    page_data["layout_regions"] = [
        {**region, "bbox_norm": boxes[region["region_id"]], "bbox_status": "assistant_draft"}
        for region in regions
    ]
    page_data["bbox_draft_metadata"] = {
        "provider": "codex_cli",
        "model": model,
        "generated_at": generated_at,
    }
    page_data["annotation_status"] = "needs_owner_review"
    page_data["draft_revision"] = int(page_data.get("draft_revision") or 0) + 1
    page_data.pop("owner_reviewed_at", None)
    page_data.pop("reviewed_draft_revision", None)
    page_data.pop("stale_review", None)

    with STATE_LOCK:
        state = read_state()
        reviews = state["reviews"]
        row_index = next((i for i, item in enumerate(reviews) if item.get("page_key") == page_key), None)
        if row_index is None or reviews[row_index].get("updated_at") != expected_updated_at:
            raise HTTPException(409, "This page changed while Codex was generating; reload it and try again")
        updated_at = datetime.now(timezone.utc).isoformat()
        reviews[row_index] = {
            "page_key": page_key,
            "draft_revision": page_data["draft_revision"],
            "annotation_status": "needs_owner_review",
            "page_data": page_data,
            "updated_at": updated_at,
        }
        state["source"] = "local review store"
        state["exported_at"] = updated_at
        write_state(state)
        track_counts = write_tracks(reviews)
    return {"page_data": page_data, "track_counts": track_counts}


async def generate_content_draft(
    document_id: str, page_number: int, task: Literal["transcript", "table"]
) -> dict:
    page_key = f"{document_id}:p{page_number}"
    with STATE_LOCK:
        state = read_state()
        row = next((item for item in state["reviews"] if item.get("page_key") == page_key), None)
        if row is None:
            raise HTTPException(404, "Save this page in the local review store before generating a draft")
        if task != "table" and row.get("annotation_status") != "needs_owner_review":
            raise HTTPException(409, "Codex drafts are available only for pages that still need owner review")
        page_data = json.loads(json.dumps(row.get("page_data") or {}))
        expected_updated_at = row.get("updated_at")

    source_image = page_data.get("source_image")
    if not isinstance(source_image, str) or not source_image:
        raise HTTPException(400, "This page has no source image")
    image_path = (DATA_DIR / source_image).resolve()
    if not image_path.is_relative_to(DATA_DIR.resolve()) or not image_path.is_file():
        raise HTTPException(404, "The source page image is missing")
    image_bytes = image_path.read_bytes()
    source_hash = page_data.get("source_image_sha256")
    if source_hash and hashlib.sha256(image_bytes).hexdigest() != source_hash:
        raise HTTPException(409, "The source image no longer matches its recorded SHA-256")

    layout_regions = page_data.get("layout_regions")
    if not isinstance(layout_regions, list):
        raise HTTPException(409, "This page has no valid layout regions")
    generated_at = datetime.now(timezone.utc).isoformat()
    try:
        if task == "transcript":
            draft, model = await run_in_threadpool(run_transcript_agent, image_bytes)
            page_data["ocr_reference_draft"] = draft.ocr_text
            page_data["ocr_draft_source"] = (
                f"Codex CLI transcript draft from source page; {model}; verify against the original image."
            )
            uncertain_items = draft.uncertain_items
        else:
            table_regions = [region for region in layout_regions if region.get("label") == "table"]
            if not table_regions:
                raise HTTPException(409, "Draw and label the table region before asking Codex to fill its grid")
            draft, model = await run_in_threadpool(
                run_table_agent, image_bytes, table_regions
            )
            old_drafts = page_data.get("table_reference_drafts") or []
            legacy_draft = page_data.get("table_reference_draft")
            if legacy_draft and legacy_draft.get("region_id"):
                old_drafts = [*old_drafts, legacy_draft]
            old_by_region = {
                item.get("region_id"): item for item in old_drafts if item.get("region_id")
            }
            page_data["table_presence_reviewed"] = False
            page_data["table_reference_drafts"] = [
                {
                    **old_by_region.get(table.region_id, {}),
                    "region_id": table.region_id,
                    "table_name": old_by_region.get(table.region_id, {}).get("table_name", ""),
                    "source_candidate_id": old_by_region.get(table.region_id, {}).get(
                        "source_candidate_id", f"AI-CODEX-{page_number}-T{index}"
                    ),
                    "source_candidate_status": "assistant_visual_draft",
                    "draft_origin": f"Codex CLI vision model; {model}; owner review required before scoring.",
                    "grid": table.grid,
                }
                for index, table in enumerate(draft.tables, start=1)
            ]
            page_data.pop("table_reference_draft", None)
            uncertain_items = draft.uncertain_items
    except HTTPException:
        raise
    except ValueError as error:
        raise HTTPException(502, str(error)) from error
    except Exception as error:
        logger.exception("Codex CLI %s draft failed for %s", task, page_key)
        raise HTTPException(502, f"Codex CLI could not generate {task} draft: {error}") from error

    page_data["content_draft_metadata"] = {
        "provider": "codex_cli",
        "task": task,
        "model": model,
        "generated_at": generated_at,
        "uncertain_items": uncertain_items,
    }
    page_data["annotation_status"] = "needs_owner_review"
    page_data["draft_revision"] = int(page_data.get("draft_revision") or 0) + 1
    page_data.pop("owner_reviewed_at", None)
    page_data.pop("reviewed_draft_revision", None)
    page_data.pop("stale_review", None)

    with STATE_LOCK:
        state = read_state()
        reviews = state["reviews"]
        row_index = next((i for i, item in enumerate(reviews) if item.get("page_key") == page_key), None)
        if row_index is None or reviews[row_index].get("updated_at") != expected_updated_at:
            raise HTTPException(409, "This page changed while Codex was generating; reload it and try again")
        updated_at = datetime.now(timezone.utc).isoformat()
        reviews[row_index] = {
            "page_key": page_key,
            "draft_revision": page_data["draft_revision"],
            "annotation_status": "needs_owner_review",
            "page_data": page_data,
            "updated_at": updated_at,
        }
        state["source"] = "local review store"
        state["exported_at"] = updated_at
        write_state(state)
        track_counts = write_tracks(reviews)
    return {"page_data": page_data, "track_counts": track_counts}


@app.post("/api/reviews/{document_id}/pages/{page_number}/generate-transcript-draft")
async def generate_transcript_draft(document_id: str, page_number: int) -> dict:
    return await generate_content_draft(document_id, page_number, "transcript")


@app.post("/api/reviews/{document_id}/pages/{page_number}/generate-table-draft")
async def generate_table_draft(document_id: str, page_number: int) -> dict:
    return await generate_content_draft(document_id, page_number, "table")


@app.put("/api/reviews")
def save_review(review: PageReview) -> dict:
    page_key = f"{review.document_id}:p{review.source_page_number}"
    row = {
        "page_key": page_key,
        "draft_revision": review.draft_revision,
        "annotation_status": review.annotation_status,
        "page_data": review.page_data,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    with STATE_LOCK:
        state = read_state()
        reviews = state["reviews"]
        source_hash = review.page_data.get("source_pdf_sha256")
        source_number = review.page_data.get("source_page_number", review.source_page_number)
        image_hash = review.page_data.get("source_image_sha256")
        for saved in reviews:
            saved_page = saved.get("page_data") or {}
            same_source = source_hash and saved_page.get("source_pdf_sha256") == source_hash and saved_page.get("source_page_number") == source_number
            same_image = image_hash and saved_page.get("source_image_sha256") == image_hash
            if saved.get("page_key") != page_key and (same_source or same_image):
                raise HTTPException(409, f"Duplicate source page already saved as {saved['page_key']}; refresh the review page")
        for index, saved in enumerate(reviews):
            if saved.get("page_key") == page_key:
                reviews[index] = row
                break
        else:
            reviews.append(row)
        state["source"] = "local review store"
        state["exported_at"] = datetime.now(timezone.utc).isoformat()
        write_state(state)
        track_counts = write_tracks(reviews)
        records, _ = build_tracks(reviews)
        layout_labels = Counter(region["label"] for page in records["layout"] for region in page["regions"])
    return {
        "page_key": page_key,
        "status": "saved_and_exported_local",
        "track_counts": track_counts,
        "layout_label_counts": {label: layout_labels[label] for label in sorted(LABELS)},
    }


@app.post("/api/upload-pdf")
async def upload_pdf(
    file: UploadFile = File(...),
    pages: str = Form(...),
    title: str = Form(""),
) -> dict:
    filename = Path(file.filename or "upload.pdf").name
    if not filename.lower().endswith(".pdf"):
        raise HTTPException(400, "Upload a PDF file")
    content = await file.read(MAX_PDF_BYTES + 1)
    if len(content) > MAX_PDF_BYTES:
        raise HTTPException(413, "PDF must be 50 MiB or smaller")
    if not content.startswith(b"%PDF-"):
        raise HTTPException(400, "The uploaded file is not a valid PDF")

    try:
        source_pdf = fitz.open(stream=content, filetype="pdf")
    except (fitz.FileDataError, RuntimeError) as error:
        raise HTTPException(400, "Could not read the uploaded PDF") from error
    if source_pdf.is_encrypted:
        raise HTTPException(400, "Encrypted PDFs are not supported")
    page_numbers = parse_page_selection(pages, source_pdf.page_count)
    digest = hashlib.sha256(content).hexdigest()
    document_id = safe_document_id(filename, digest)
    display_title = title.strip() or Path(filename).stem

    upload_dir = DATA_DIR / "uploads"
    page_dir = DATA_DIR / "pages"
    image_dir = DATA_DIR / "raw"
    upload_dir.mkdir(exist_ok=True)
    page_dir.mkdir(exist_ok=True)
    image_dir.mkdir(exist_ok=True)
    stored_pdf = upload_dir / f"{document_id}.pdf"
    new_pages: list[dict] = []
    duplicate_pages: list[dict] = []
    added_pages = 0
    with STATE_LOCK:
        state = read_state()
        reviews = state["reviews"]
        existing_sources: dict[tuple[str, int], dict] = {}
        existing_images: dict[str, dict] = {}
        for saved in sorted(reviews, key=lambda row: row.get("annotation_status") != "owner_reviewed"):
            page_data = saved.get("page_data") or {}
            source_hash = page_data.get("source_pdf_sha256")
            source_number = page_data.get("source_page_number")
            image_hash = page_data.get("source_image_sha256")
            if source_hash and source_number:
                existing_sources.setdefault((source_hash, source_number), saved)
            if image_hash:
                existing_images.setdefault(image_hash, saved)
            if source_hash == digest:
                candidate = (DATA_DIR / str(page_data.get("source_pdf") or "")).resolve()
                if candidate.is_relative_to(upload_dir.resolve()) and candidate.is_file():
                    stored_pdf = candidate

        for page_number in page_numbers:
            page_key = f"{document_id}:p{page_number}"
            saved = existing_sources.get((digest, page_number))
            if saved is not None:
                new_pages.append(saved["page_data"])
                duplicate_pages.append({"requested_page": page_number, "existing_page_key": saved["page_key"]})
                continue

            source_page = source_pdf[page_number - 1]
            width_pt, height_pt = source_page.rect.width, source_page.rect.height
            scale = min(2.0, (MAX_RENDER_PIXELS / max(width_pt * height_pt * 4, 1)) ** 0.5)
            pixmap = source_page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
            image_bytes = pixmap.tobytes("png")
            image_hash = hashlib.sha256(image_bytes).hexdigest()
            saved = existing_images.get(image_hash)
            if saved is not None:
                new_pages.append(saved["page_data"])
                duplicate_pages.append({"requested_page": page_number, "existing_page_key": saved["page_key"]})
                continue
            if not stored_pdf.exists():
                temporary_pdf = stored_pdf.with_suffix(".pdf.tmp")
                temporary_pdf.write_bytes(content)
                os.replace(temporary_pdf, stored_pdf)
            suffix = f"p{page_number:04d}"
            image_path = image_dir / f"{document_id.lower()}-{suffix}.png"
            page_pdf_path = page_dir / f"{document_id}-{suffix}.pdf"
            image_path.write_bytes(image_bytes)
            one_page = fitz.open()
            one_page.insert_pdf(source_pdf, from_page=page_number - 1, to_page=page_number - 1)
            page_pdf_bytes = one_page.tobytes(garbage=4, deflate=True)
            one_page.close()
            page_pdf_path.write_bytes(page_pdf_bytes)

            page_data = {
                "document_id": document_id,
                "doc_title": display_title,
                "source_page_number": page_number,
                "source_pdf": f"uploads/{stored_pdf.name}",
                "source_pdf_name": filename,
                "source_pdf_sha256": digest,
                "source_page_pdf": f"pages/{page_pdf_path.name}",
                "source_page_pdf_sha256": hashlib.sha256(page_pdf_bytes).hexdigest(),
                "source_image": f"raw/{image_path.name}",
                "source_image_sha256": image_hash,
                "image_width": pixmap.width,
                "image_height": pixmap.height,
                "annotation_status": "needs_owner_review",
                "ocr_reference_draft": "",
                "ocr_draft_source": "Blank review draft from uploaded source PDF; transcribe and verify against the original page.",
                "layout_regions": [],
                "reading_order": [],
                "table_presence_reviewed": False,
                "table_reference_drafts": [],
                "draft_revision": 1,
                "draft_completeness": "blank_manual_review",
            }
            row = {
                "page_key": page_key,
                "draft_revision": 1,
                "annotation_status": "needs_owner_review",
                "page_data": page_data,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
            reviews.append(row)
            new_pages.append(page_data)
            existing_sources[(digest, page_number)] = row
            existing_images[image_hash] = row
            added_pages += 1

        if added_pages:
            state["source"] = "local review store"
            state["exported_at"] = datetime.now(timezone.utc).isoformat()
            write_state(state)
            track_counts = write_tracks(reviews)
        else:
            _, summary = build_tracks(reviews)
            track_counts = summary["track_record_counts"]
    source_pdf.close()
    return {
        "document_id": document_id,
        "pages": new_pages,
        "added_pages": added_pages,
        "duplicate_pages": duplicate_pages,
        "track_counts": track_counts,
    }


@app.get("/")
def review_page() -> FileResponse:
    return FileResponse(DATA_DIR / "review.html")


@app.get("/api/reports")
def pipeline_reports() -> dict:
    results_dir = PIPELINE_DIR / "results/shared-html"
    runs = []
    if results_dir.is_dir():
        run_dirs = [path for path in results_dir.iterdir() if path.is_dir() and not path.is_symlink()]

        def timestamp_from_run_id(run_id: str) -> datetime | None:
            match = re.fullmatch(r"paddle-layout-(?:pilot-5|all-reviewed)-(\d{8})-(\d{6})", run_id)
            if not match:
                return None
            try:
                return datetime.strptime("".join(match.groups()), "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc)
            except ValueError:
                return None

        def run_sort_key(run_dir: Path) -> tuple[float, str]:
            try:
                metadata = json.loads((run_dir / "run-metadata.json").read_text(encoding="utf-8"))
                started_at = metadata.get("started_at_utc")
                if started_at:
                    parsed = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
                    if parsed.tzinfo is None:
                        parsed = parsed.replace(tzinfo=timezone.utc)
                    return parsed.timestamp(), run_dir.name
            except (OSError, json.JSONDecodeError, TypeError, ValueError):
                pass
            encoded_start = timestamp_from_run_id(run_dir.name)
            if encoded_start:
                return encoded_start.timestamp(), run_dir.name
            return run_dir.stat().st_mtime, run_dir.name

        for run_dir in sorted(run_dirs, key=run_sort_key, reverse=True):
            report_path = run_dir / "report.md"
            evaluation_path = run_dir / "evaluation.json"
            metadata_path = run_dir / "run-metadata.json"
            predictions_path = run_dir / "predictions.jsonl"
            report = report_path.read_text(encoding="utf-8") if report_path.is_file() else None
            try:
                evaluation = json.loads(evaluation_path.read_text(encoding="utf-8")) if evaluation_path.is_file() else {}
            except (OSError, json.JSONDecodeError):
                evaluation = {}
            try:
                run_metadata = json.loads(metadata_path.read_text(encoding="utf-8")) if metadata_path.is_file() else {}
            except (OSError, json.JSONDecodeError):
                run_metadata = {}
            # VietOCR tuning stores one aggregate score per recognizer configuration,
            # rather than the usual single-run evaluation object. Expose each config
            # as an OCR-only comparison row in the Report tab.
            if isinstance(evaluation, list):
                for result in evaluation:
                    config = result.get("config", {})
                    width = config.get("max_width", "unknown")
                    decoding = "beam" if config.get("beamsearch") else "greedy"
                    run_id = f"{run_dir.name}-width-{width}-{decoding}"
                    ocr_scores = {
                        key: result[key]
                        for key in (
                            "pages", "micro_cer", "micro_wer_pyvi", "micro_wer_whitespace",
                            "character_edits", "reference_characters", "wer_pyvi_edits",
                            "reference_pyvi_words",
                        )
                        if key in result
                    }
                    if "micro_wer_whitespace" in result:
                        ocr_scores["micro_whitespace_error"] = result["micro_wer_whitespace"]
                    ocr_evaluation = {
                        "run_id": run_id,
                        "selected_reference_ids": run_metadata.get("owner_reviewed_page_ids", []),
                        "layer_scores": {"ocr": ocr_scores},
                    }
                    runs.append({
                        "id": run_id,
                        "report": (
                            f"OCR-only VietOCR tuning · width {width} · {decoding} decoding. "
                            f"Scored on {result.get('pages', 0)} owner-reviewed pages with "
                            "RapidOCR line detection held fixed."
                        ),
                        "evaluation": ocr_evaluation,
                        "started_at_utc": run_metadata.get("started_at_utc"),
                        "finished_at_utc": run_metadata.get("finished_at_utc"),
                        "wall_seconds": run_metadata.get("wall_seconds"),
                        "inference_wall_seconds": run_metadata.get("inference_wall_seconds"),
                        "pages": [],
                        "predictions": [],
                    })
                continue
            started_at_utc = run_metadata.get("started_at_utc")
            if not started_at_utc:
                encoded_start = timestamp_from_run_id(run_dir.name)
                started_at_utc = encoded_start.isoformat() if encoded_start else None
            selected_reference_ids = evaluation.get("selected_reference_ids") or []
            score_by_page = {}
            for score in evaluation.get("layer_scores", {}).get("ocr", {}).get("page_scores", []):
                key = (score.get("document_id"), score.get("source_page_number_1based"))
                score_by_page[key] = (score, "OCR layer")
            for score in evaluation.get("end_to_end_scores", {}).get("ocr", {}).get("page_scores", []):
                key = (score.get("document_id"), score.get("source_page_number_1based"))
                score_by_page[key] = (score, "end-to-end")
            pages = []
            dashboard_predictions = []
            if predictions_path.is_file():
                for line in predictions_path.read_text(encoding="utf-8").splitlines():
                    if not line.strip():
                        continue
                    try:
                        prediction = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    document_id = prediction.get("document_id", "")
                    page_number = prediction.get("source_page_number_1based")
                    label_counts = Counter(
                        element.get("label", "other") for element in prediction.get("elements", [])
                    )
                    page_score = score_by_page.get((document_id, page_number))
                    pages.append({
                        "id": f"{document_id}-p{page_number}",
                        "document_id": document_id,
                        "page_number": page_number,
                        "regions": len(prediction.get("elements", [])),
                        "labels": dict(sorted(label_counts.items())),
                        "tables": len(prediction.get("tables", [])),
                        "ocr": page_score[0] if page_score else None,
                        "ocr_scope": page_score[1] if page_score else None,
                    })
                    dashboard_predictions.append(prediction)
            runs.append({
                "id": run_dir.name,
                "report": report,
                "evaluation": evaluation,
                "started_at_utc": started_at_utc,
                "finished_at_utc": run_metadata.get("finished_at_utc"),
                "wall_seconds": run_metadata.get("wall_seconds"),
                "inference_wall_seconds": run_metadata.get(
                    "inference_wall_seconds",
                    evaluation.get("runtime", {}).get("inference_wall_seconds"),
                ),
                "pages": pages,
                # The static viewer already contains full runs. Return inline predictions
                # only for small scored pilots whose evaluation points at that same run.
                "predictions": dashboard_predictions
                if evaluation.get("run_id") == run_dir.name and selected_reference_ids and len(selected_reference_ids) <= 10
                else [],
            })
    return {"runs": runs}


@app.delete("/api/runs/{run_id}")
def delete_pipeline_run(run_id: str) -> dict:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,199}", run_id):
        raise HTTPException(400, "Invalid run id")
    results_dir = (PIPELINE_DIR / "results/shared-html").resolve()
    run_dir = results_dir / run_id
    if run_dir.is_symlink() or run_dir.resolve().parent != results_dir:
        raise HTTPException(400, "Invalid run directory")
    if not run_dir.is_dir():
        raise HTTPException(404, "Run not found")
    run_directories = [path for path in results_dir.iterdir() if path.is_dir() and not path.is_symlink()]
    if len(run_directories) <= 1:
        raise HTTPException(409, "Keep at least one run in the results directory")
    try:
        shutil.rmtree(run_dir)
    except OSError as error:
        raise HTTPException(500, "Could not remove run directory") from error
    return {"deleted": run_id}


@app.get("/api/runs/{run_id}/predictions")
def pipeline_run_predictions(run_id: str) -> dict:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,199}", run_id):
        raise HTTPException(400, "Invalid run id")
    results_dir = (PIPELINE_DIR / "results/shared-html").resolve()
    run_dir = results_dir / run_id
    if run_dir.is_symlink() or run_dir.resolve().parent != results_dir:
        raise HTTPException(400, "Invalid run directory")
    predictions_path = run_dir / "predictions.jsonl"
    if not predictions_path.is_file():
        raise HTTPException(404, "Run predictions not found")

    references = {}
    reference_path = DATA_DIR / "layout/reference.jsonl"
    if reference_path.is_file():
        for line in reference_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                reference = json.loads(line)
                references[(reference["document_id"], int(reference["source_page_number_1based"]))] = reference

    predictions = []
    for line in predictions_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        prediction = json.loads(line)
        reference = references.get((prediction.get("document_id"), int(prediction.get("source_page_number_1based", 0))))
        source_image = reference.get("source_image") if reference else None
        if source_image:
            image_path = (DATA_DIR / source_image).resolve()
            raw_root = (DATA_DIR / "raw").resolve()
            try:
                relative_image = image_path.relative_to(raw_root)
            except ValueError:
                pass
            else:
                if image_path.is_file():
                    prediction["image"] = f"/dashboard-images/raw/{relative_image.as_posix()}"
        predictions.append(prediction)
    return {"run_id": run_id, "predictions": predictions}


@app.get("/dashboard")
def results_dashboard() -> HTMLResponse:
    dashboard_path = PIPELINE_DIR / "results/shared-html/document-pipeline-results-viewer.html"
    if not dashboard_path.is_file():
        raise HTTPException(status_code=404, detail="Results dashboard not found")
    dashboard = dashboard_path.read_text(encoding="utf-8")
    dashboard = dashboard.replace("../../data/raw/", "/dashboard-images/raw/")
    dashboard = dashboard.replace(
        "../../kaggle/shared-html/input-package/", "/dashboard-images/kaggle/"
    )
    return HTMLResponse(dashboard)


app.mount("/dashboard-images/raw", StaticFiles(directory=DATA_DIR / "raw"), name="dashboard-raw")
app.mount(
    "/dashboard-images/kaggle",
    StaticFiles(directory=PIPELINE_DIR / "kaggle/archive/shared-html-51-page-legacy/input-package"),
    name="dashboard-kaggle-images",
)
app.mount("/", StaticFiles(directory=DATA_DIR), name="review-assets")
