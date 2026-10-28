"""Upload Test routes for isolated document-processing experiments."""

import hashlib
import logging
import time
import uuid
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import Response

from app.security import _require_same_origin, require_permission

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/api/upload-tests")
@router.post("/api/ocr-tests", include_in_schema=False)
async def create_upload_test(
    request: Request,
    file: UploadFile = File(...),
    parser_engine: str = Form(default="docling"),
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
    from document_processing.document_processor import DocumentProcessor, SUPPORTED_FORMATS
    if suffix not in SUPPORTED_FORMATS:
        raise HTTPException(415, "Unsupported Upload Test file format")
    if parser_engine != "docling":
        raise HTTPException(422, "Only Docling is available")
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
    try:
        if suffix == ".pdf":
            source = fitz.open(stream=content, filetype="pdf")
            page_count = len(source)
            if not 1 <= page_count <= 50:
                source.close()
                raise HTTPException(422, "Upload Test accepts PDFs with 1-50 pages")
            for page in source:
                scale = min(120 / 72, 1800 / page.rect.width, 2400 / page.rect.height)
                page_previews.append(page.get_pixmap(
                    matrix=fitz.Matrix(scale, scale), alpha=False,
                ).tobytes("png"))
            source.close()
        elif suffix in {".png", ".jpg", ".jpeg", ".tif", ".tiff"}:
            source = fitz.open(stream=content, filetype=suffix[1:])
            page_count = len(source)
            for page in source:
                scale = min(1.0, 1800 / page.rect.width, 2400 / page.rect.height)
                page_previews.append(page.get_pixmap(
                    matrix=fitz.Matrix(scale, scale), alpha=False,
                ).tobytes("png"))
            source.close()
    except HTTPException:
        raise
    except Exception as error:
        raise HTTPException(422, "Could not open the uploaded PDF") from error

    docling_settings = {
        "docling_device": docling_device,
        "docling_ocr": docling_ocr,
        "docling_ocr_language": docling_ocr_language,
        "docling_table_structure": docling_table_structure,
        "docling_num_threads": docling_num_threads,
    }
    config = {
        "parser_engine": "docling",
        "parser_settings": {"docling": docling_settings},
        **docling_settings,
        "vision_captioning": False,
    }
    run_id = uuid.uuid4()
    source_sha256 = hashlib.sha256(content).hexdigest()
    source_metadata = {"source_type": "upload_test", "source_sha256": source_sha256}
    document_processor = DocumentProcessor(config)
    processing_started = time.perf_counter()
    try:
        parsed = document_processor.process(filename, content, source_metadata)
    except (ValueError, RuntimeError) as error:
        status_code = 503 if isinstance(error, RuntimeError) else 422
        raise HTTPException(status_code, f"Upload Test processing failed: {error}") from error
    runtime_info = {
        "pymupdf": fitz.VersionBind,
        "docling": parsed["metadata"].get("docling_version"),
    }
    runtime_info["processing_time_ms"] = max(
        0, round((time.perf_counter() - processing_started) * 1000),
    )

    from core.database.upload_test_repository import UploadTestRepository
    repository = UploadTestRepository()
    try:
        repository.save_run(
            run_id, source_filename=filename, source_sha256=source_sha256,
            uploaded_by=user["sub"], processor_config=config, runtime_info=runtime_info,
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
        "element_count": len(parsed["elements"]),
        "table_count": len(parsed["tables"]),
        "processor_config": config, "runtime_info": runtime_info,
    }


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
