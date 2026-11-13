"""Upload Test routes for isolated document-processing experiments."""

import asyncio
import base64
import hashlib
import logging
import os
import time
import uuid
from io import BytesIO
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import Response
from PIL import Image

from app.security import _require_same_origin, require_permission

logger = logging.getLogger(__name__)
router = APIRouter()
# ponytail: in-process job state fits the single Upload Test API replica; use a durable queue if it must survive restarts or scale-out.
_UPLOAD_TEST_JOBS: dict[uuid.UUID, dict[str, str | float]] = {}
_UPLOAD_TEST_TASKS: set[asyncio.Task] = set()


def _process_and_save_upload_test(
    *, run_id, filename, content, source_sha256, uploaded_by, config,
    source_metadata, page_previews, preview_page_sizes, page_count, pymupdf_version,
):
    processing_started = time.perf_counter()
    from core.services.client import post

    processing_url = os.environ.get("DOCUMENT_PROCESSING_URL")
    if not processing_url:
        raise RuntimeError("DOCUMENT_PROCESSING_URL is required")
    try:
        parsed = post(processing_url, "/parse", {
            "filename": filename,
            "content": base64.b64encode(content).decode("ascii"),
            "metadata": source_metadata,
            "config": config,
        }, timeout=600)
    except (ValueError, RuntimeError) as error:
        status_code = 503 if isinstance(error, RuntimeError) else 422
        raise HTTPException(status_code, f"Upload Test processing failed: {error}") from error

    page_orientation_corrections = parsed.get("page_orientation_corrections") or {}
    for page_number, raw_correction in page_orientation_corrections.items():
        correction = int(raw_correction) % 360
        index = int(page_number) - 1
        if correction == 0 or not 0 <= index < len(page_previews):
            continue
        with Image.open(BytesIO(page_previews[index])) as source_preview:
            oriented_preview = source_preview.rotate(-correction, expand=True)
            buffer = BytesIO()
            oriented_preview.save(buffer, format="PNG")
            page_previews[index] = buffer.getvalue()
        if correction in {90, 270}:
            page_size = preview_page_sizes[str(page_number)]
            preview_page_sizes[str(page_number)] = {
                "width": page_size["height"],
                "height": page_size["width"],
            }

    runtime_info = {
        "pymupdf": pymupdf_version,
        "pipeline_id": parsed["metadata"].get("pipeline_id"),
        "preview_page_sizes": preview_page_sizes,
        "parser_page_sizes": parsed.get("page_sizes") or preview_page_sizes,
        "page_orientation_corrections": page_orientation_corrections,
        "processing_time_ms": max(0, round((time.perf_counter() - processing_started) * 1000)),
    }
    if parsed.get("invoice_extraction") is not None:
        runtime_info["invoice_extraction"] = parsed["invoice_extraction"]
    if parsed["metadata"].get("docling_version"):
        runtime_info["docling"] = parsed["metadata"]["docling_version"]

    from core.database.upload_test_repository import UploadTestRepository

    repository = UploadTestRepository()
    try:
        repository.save_run(
            run_id, source_filename=filename, source_sha256=source_sha256,
            uploaded_by=uploaded_by, processor_config=config, runtime_info=runtime_info,
            page_previews=page_previews, elements=parsed["elements"], tables=parsed["tables"],
        )
    except Exception as error:
        logger.exception("Could not persist upload test run %s", run_id)
        raise HTTPException(503, "Upload processing completed, but its test output could not be saved") from error
    finally:
        repository.close()

    return {
        "run_id": str(run_id), "source_filename": filename,
        "source_sha256": source_sha256, "page_count": page_count,
        "element_count": len(parsed["elements"]), "table_count": len(parsed["tables"]),
        "processor_config": config, "runtime_info": runtime_info,
    }


async def _run_upload_test_job(run_id: uuid.UUID, job_args: dict) -> None:
    try:
        await asyncio.to_thread(_process_and_save_upload_test, **job_args)
    except HTTPException as error:
        _UPLOAD_TEST_JOBS[run_id] = {
            "status": "failed", "error": str(error.detail), "finished_at": time.monotonic(),
        }
    except Exception:
        logger.exception("Upload Test background run %s failed", run_id)
        _UPLOAD_TEST_JOBS[run_id] = {
            "status": "failed", "error": "Upload Test processing failed", "finished_at": time.monotonic(),
        }
    else:
        _UPLOAD_TEST_JOBS.pop(run_id, None)


@router.post("/api/upload-tests")
@router.post("/api/ocr-tests", include_in_schema=False)
async def create_upload_test(
    request: Request,
    file: UploadFile = File(...),
    intent: str = Form(default="document"),
    docling_device: str = Form(default="cpu"),
    docling_ocr: bool = Form(default=True),
    docling_ocr_language: str = Form(default="vie+eng"),
    docling_table_structure: bool = Form(default=True),
    docling_num_threads: int = Form(default=4),
    user: dict = Depends(require_permission("run_upload_tests")),
):
    """Run the upload pipeline and save inspectable output outside the corpus."""
    _require_same_origin(request)
    filename = Path((file.filename or "").replace("\\", "/")).name
    suffix = Path(filename).suffix.lower()
    from document_processing.document_processor import SUPPORTED_FORMATS, render_svg, render_webp
    if suffix not in SUPPORTED_FORMATS:
        raise HTTPException(415, "Unsupported Upload Test file format")
    if intent not in {"document", "invoice", "image_caption"}:
        raise HTTPException(422, "Choose document, invoice, or image caption processing")
    if intent in {"invoice", "image_caption"} and suffix not in {".pdf", ".png", ".jpg", ".jpeg", ".tif", ".tiff", ".webp", ".svg"}:
        raise HTTPException(422, "Invoice extraction and image captioning support PDF and image files only")
    if docling_device not in {"cpu", "cuda"} or docling_ocr_language not in {"vie+eng", "eng"} or not 1 <= docling_num_threads <= 16:
        raise HTTPException(422, "Unsupported Docling device, OCR language, or thread count")
    content = await file.read(20 * 1024 * 1024 + 1)
    if len(content) > 20 * 1024 * 1024:
        raise HTTPException(413, "Upload Test file exceeds the 20 MiB limit")
    if suffix == ".pdf" and b"%PDF-" not in content[:1024]:
        raise HTTPException(415, "The uploaded file is not a PDF")

    import fitz

    page_count = 0
    page_previews = []
    preview_page_sizes = {}
    try:
        if suffix == ".pdf":
            source = fitz.open(stream=content, filetype="pdf")
            page_count = len(source)
            if not 1 <= page_count <= 50:
                source.close()
                raise HTTPException(422, "Upload Test accepts PDFs with 1-50 pages")
            for page_number, page in enumerate(source, start=1):
                preview_page_sizes[str(page_number)] = {
                    "width": float(page.rect.width),
                    "height": float(page.rect.height),
                }
                scale = min(120 / 72, 1800 / page.rect.width, 2400 / page.rect.height)
                page_previews.append(page.get_pixmap(
                    matrix=fitz.Matrix(scale, scale), alpha=False,
                ).tobytes("png"))
            source.close()
        elif suffix in {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".svg", ".webp"}:
            preview_content = render_svg(content) if suffix == ".svg" else render_webp(content) if suffix == ".webp" else content
            source = fitz.open(stream=preview_content, filetype="png" if suffix in {".svg", ".webp"} else suffix[1:])
            page_count = len(source)
            for page_number, page in enumerate(source, start=1):
                preview_page_sizes[str(page_number)] = {
                    "width": float(page.rect.width),
                    "height": float(page.rect.height),
                }
                scale = min(1.0, 1800 / page.rect.width, 2400 / page.rect.height)
                page_previews.append(page.get_pixmap(
                    matrix=fitz.Matrix(scale, scale), alpha=False,
                ).tobytes("png"))
            source.close()
    except HTTPException:
        raise
    except Exception as error:
        raise HTTPException(422, "Could not open the uploaded file") from error

    docling_settings = {
        "docling_device": docling_device,
        "docling_ocr": docling_ocr,
        "docling_ocr_language": docling_ocr_language,
        "docling_table_structure": docling_table_structure,
        "docling_num_threads": docling_num_threads,
    }
    config = {
        "parser_engine": "vintern_image_caption" if intent == "image_caption" else "docling",
        "intent": intent,
        "parser_settings": {"docling": docling_settings},
        **docling_settings,
        "vision_captioning": False,
    }
    run_id = uuid.uuid4()
    source_sha256 = hashlib.sha256(content).hexdigest()
    source_metadata = {"source_type": "upload_test", "source_sha256": source_sha256}
    job_args = {
        "run_id": run_id,
        "filename": filename,
        "content": content,
        "source_sha256": source_sha256,
        "uploaded_by": user["sub"],
        "config": config,
        "source_metadata": source_metadata,
        "page_previews": page_previews,
        "preview_page_sizes": preview_page_sizes,
        "page_count": page_count,
        "pymupdf_version": fitz.VersionBind,
    }
    now = time.monotonic()
    for old_id, state in list(_UPLOAD_TEST_JOBS.items()):
        if state.get("status") == "failed" and now - state.get("finished_at", now) > 3600:
            _UPLOAD_TEST_JOBS.pop(old_id, None)
    if len(_UPLOAD_TEST_TASKS) >= 1:
        raise HTTPException(429, "Another Upload Test is already running")
    _UPLOAD_TEST_JOBS[run_id] = {"status": "processing"}
    task = asyncio.create_task(_run_upload_test_job(run_id, job_args))
    _UPLOAD_TEST_TASKS.add(task)
    task.add_done_callback(_UPLOAD_TEST_TASKS.discard)
    return {"run_id": str(run_id), "status": "processing"}


@router.get("/api/upload-tests")
@router.get("/api/ocr-tests", include_in_schema=False)
def list_upload_tests(user: dict = Depends(require_permission("review_upload_tests"))):
    from core.database.upload_test_repository import UploadTestRepository

    repository = UploadTestRepository()
    try:
        return {"runs": repository.list_runs()}
    finally:
        repository.close()


@router.get("/api/upload-tests/{run_id}")
@router.get("/api/ocr-tests/{run_id}", include_in_schema=False)
def inspect_upload_test(
    run_id: uuid.UUID,
    user: dict = Depends(require_permission("review_upload_tests")),
):
    job = _UPLOAD_TEST_JOBS.get(run_id)
    if job is not None:
        if job.get("status") == "processing":
            return {"run_id": str(run_id), "status": "processing"}
        return {"run_id": str(run_id), "status": "failed", "error": job.get("error")}

    from core.database.upload_test_repository import UploadTestRepository

    repository = UploadTestRepository()
    try:
        run = repository.get_run(run_id)
        if run is None:
            raise HTTPException(404, "Upload Test run not found")
        return run
    finally:
        repository.close()


@router.get("/api/upload-tests/{run_id}/pages/{page_number}/preview")
@router.get("/api/ocr-tests/{run_id}/pages/{page_number}/preview", include_in_schema=False)
def get_upload_test_preview(
    run_id: uuid.UUID, page_number: int,
    user: dict = Depends(require_permission("review_upload_tests")),
):
    from core.database.upload_test_repository import UploadTestRepository

    repository = UploadTestRepository()
    try:
        preview = repository.get_page_preview(run_id, page_number)
        if preview is None:
            raise HTTPException(404, "Upload Test page preview not found")
        return Response(content=preview, media_type="image/png")
    finally:
        repository.close()
