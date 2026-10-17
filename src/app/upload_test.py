"""Upload Test routes for isolated parser and chunk experiments."""

import hashlib
import logging
import re
import subprocess
import time
import uuid
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import Response

from app.security import _require_same_origin, require_permission

logger = logging.getLogger(__name__)
OCR_LANGUAGES = {"eng", "vie+eng"}
router = APIRouter()


@router.post("/api/upload-tests")
@router.post("/api/ocr-tests", include_in_schema=False)
async def create_upload_test(
    request: Request,
    file: UploadFile = File(...),
    tesseract_psm: int = Form(default=11),
    tesseract_table_psm: int = Form(default=3),
    render_scale: float = Form(default=1.5),
    table_render_scale: float = Form(default=2.5),
    ocr_language: str = Form(default="vie+eng"),
    thresholding_method: int = Form(default=0),
    preserve_interword_spaces: bool = Form(default=False),
    load_system_dawg: bool = Form(default=True),
    load_freq_dawg: bool = Form(default=True),
    tessedit_do_invert: bool = Form(default=True),
    textord_tablefind_recognize_tables: bool = Form(default=False),
    textord_tabfind_find_tables: bool = Form(default=True),
    lstm_use_matrix: bool = Form(default=True),
    lstm_rating_coefficient: int = Form(default=5),
    tessdata_variant: str = Form(default="system"),
    parser_engine: str = Form(default="built_in"),
    paddle_device: str = Form(default="cpu"),
    paddle_render_scale: float = Form(default=1.5),
    paddle_formula_recognition: bool = Form(default=False),
    paddle_chart_recognition: bool = Form(default=False),
    mineru_force_ocr: bool = Form(default=False),
    mineru_page_range: str = Form(default=""),
    docling_device: str = Form(default="cpu"),
    docling_ocr: bool = Form(default=True),
    docling_ocr_language: str = Form(default="vi"),
    docling_table_structure: bool = Form(default=True),
    docling_num_threads: int = Form(default=4),
    chunking_strategy: str = Form(default="sentence"),
    chunk_size: int = Form(default=1100),
    chunk_overlap: int = Form(default=120),
    paddle_layout: bool = Form(default=False),
    layout_detector: str = Form(default="none"),
    layout_image_size: int = Form(default=640),
    layout_confidence_threshold: float = Form(default=0.30),
    user: dict = Depends(require_permission("run_upload_tests")),
):
    """Run the upload pipeline and save inspectable output outside the corpus."""
    _require_same_origin(request)
    filename = Path((file.filename or "").replace("\\", "/")).name
    suffix = Path(filename).suffix.lower()
    from core.document_processing.document_processor import DocumentProcessor, SUPPORTED_FORMATS
    if suffix not in SUPPORTED_FORMATS:
        raise HTTPException(415, "Unsupported Upload Test file format")
    if parser_engine not in {"built_in", "pp-structurev3", "mineru", "docling"}:
        raise HTTPException(422, "Unsupported Upload Test parser")
    if parser_engine == "built_in" and (tesseract_psm not in {3, 6, 11, 12} or tesseract_table_psm not in {3, 4, 6, 11, 12}):
        raise HTTPException(422, "Unsupported Tesseract page segmentation mode")
    supported_scales = (1.5, 167 / 72, 2.5, 3.5)
    if parser_engine == "built_in" and not all(any(abs(value - scale) < 1e-9 for scale in supported_scales) for value in (render_scale, table_render_scale)):
        raise HTTPException(422, "Render scale must be 1.5, 167 DPI, 2.5, or 3.5")
    if parser_engine == "built_in" and ocr_language not in OCR_LANGUAGES:
        raise HTTPException(422, "OCR language must be eng or vie+eng")
    if parser_engine == "built_in" and (thresholding_method not in {0, 1, 2} or lstm_rating_coefficient not in {3, 5, 7}):
        raise HTTPException(422, "Unsupported Tesseract parameter")
    if parser_engine == "built_in" and tessdata_variant not in {"system", "fast", "best"}:
        raise HTTPException(422, "Unsupported Tesseract traineddata variant")
    if parser_engine == "pp-structurev3" and (paddle_device not in {"cpu", "gpu:0"} or not any(abs(paddle_render_scale - scale) < 1e-9 for scale in supported_scales)):
        raise HTTPException(422, "Unsupported PP-StructureV3 device or render scale")
    if parser_engine == "mineru" and mineru_page_range and not re.fullmatch(r"\d+(?:-\d+)?(?:,\d+(?:-\d+)?)*", mineru_page_range.strip()):
        raise HTTPException(422, "MinerU page range must look like 1-3,5")
    if parser_engine == "mineru" and mineru_page_range.strip() and suffix != ".pdf":
        raise HTTPException(422, "MinerU page range applies only to PDFs")
    if parser_engine == "docling" and (
        docling_device not in {"cpu", "cuda"}
        or docling_ocr_language not in {"vi", "en"}
        or not 1 <= docling_num_threads <= 16
    ):
        raise HTTPException(422, "Unsupported Docling device, OCR language, or thread count")
    if layout_detector not in {"none", "doclayout-yolo"}:
        raise HTTPException(422, "Unsupported Upload Test layout detector")
    if chunking_strategy not in {"sentence", "fixed"} or not 100 <= chunk_size <= 5000 or not 0 <= chunk_overlap < chunk_size:
        raise HTTPException(422, "Unsupported shared chunking configuration")
    if layout_image_size not in {512, 640, 768, 1024}:
        raise HTTPException(422, "Layout image size must be 512, 640, 768, or 1024")
    if layout_confidence_threshold not in {0.30, 0.50, 0.67}:
        raise HTTPException(422, "Unsupported layout confidence threshold")
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
            if parser_engine == "mineru" and mineru_page_range:
                for item in mineru_page_range.split(","):
                    bounds = [int(part) for part in item.split("-")]
                    first_page, last_page = bounds[0], bounds[-1]
                    if first_page < 1 or last_page < first_page or last_page > page_count:
                        source.close()
                        raise HTTPException(422, "MinerU page range must be within this PDF and in ascending order")
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

    tesseract_settings = {
        "tesseract_psm": tesseract_psm,
        "tesseract_table_psm": tesseract_table_psm,
        "ocr_language": ocr_language,
        "ocr_render_scale": render_scale,
        "ocr_table_render_scale": table_render_scale,
        "tesseract_config": {
            "thresholding_method": thresholding_method,
            "preserve_interword_spaces": preserve_interword_spaces,
            "load_system_dawg": load_system_dawg,
            "load_freq_dawg": load_freq_dawg,
            "tessedit_do_invert": tessedit_do_invert,
            "textord_tablefind_recognize_tables": textord_tablefind_recognize_tables,
            "textord_tabfind_find_tables": textord_tabfind_find_tables,
            "lstm_use_matrix": lstm_use_matrix,
            "lstm_rating_coefficient": lstm_rating_coefficient,
        },
        "tessdata_variant": tessdata_variant,
    }
    pp_settings = {
        "paddle_device": paddle_device,
        "paddle_render_scale": paddle_render_scale,
        "paddle_formula_recognition": paddle_formula_recognition,
        "paddle_chart_recognition": paddle_chart_recognition,
    }
    mineru_settings = {
        "mineru_force_ocr": mineru_force_ocr,
        "mineru_page_range": mineru_page_range.strip(),
    }
    docling_settings = {
        "docling_device": docling_device,
        "docling_ocr": docling_ocr,
        "docling_ocr_language": docling_ocr_language,
        "docling_table_structure": docling_table_structure,
        "docling_num_threads": docling_num_threads,
    }
    selected_settings = {
        "built_in": tesseract_settings,
        "pp-structurev3": pp_settings,
        "mineru": mineru_settings,
        "docling": docling_settings,
    }[parser_engine]
    config = {
        "chunking_strategy": chunking_strategy,
        "chunk_size": chunk_size,
        "chunk_overlap": chunk_overlap,
        "parser_engine": parser_engine,
        "parser_settings": {parser_engine: selected_settings},
        **selected_settings,
        "paddle_layout": parser_engine == "pp-structurev3" or paddle_layout,
        "vision_captioning": False,
        "layout_detector": layout_detector,
        "layout_image_size": layout_image_size,
        "layout_confidence_threshold": layout_confidence_threshold,
    }
    run_id = uuid.uuid4()
    source_sha256 = hashlib.sha256(content).hexdigest()
    source_metadata = {"source_type": "upload_test", "source_sha256": source_sha256}
    document_processor = DocumentProcessor(config)
    processing_started = time.perf_counter()
    try:
        parsed = document_processor.process(filename, content, source_metadata)
        parsed = document_processor.prepare_upload_test_output(parsed, source_metadata, parser_engine)
    except (ValueError, RuntimeError) as error:
        status_code = 503 if isinstance(error, RuntimeError) else 422
        raise HTTPException(status_code, f"Upload Test processing failed: {error}") from error
    runtime_info = {"pymupdf": fitz.VersionBind}
    if parser_engine == "built_in":
        try:
            runtime_info["tesseract"] = subprocess.run(
                ["tesseract", "--version"], capture_output=True, check=True,
                text=True, timeout=10,
            ).stdout.splitlines()[0]
        except (OSError, subprocess.SubprocessError, IndexError):
            runtime_info["tesseract"] = None
    if parser_engine == "mineru":
        runtime_info["mineru"] = parsed["metadata"].get("mineru_version")
        if parsed["metadata"].get("mineru_preprocessing"):
            runtime_info["mineru_preprocessing"] = parsed["metadata"]["mineru_preprocessing"]
    if parser_engine == "docling":
        runtime_info["docling"] = parsed["metadata"].get("docling_version")
    if layout_detector == "doclayout-yolo" and page_previews:
        try:
            from core.document_processing.utils.layout.doclayout_yolo import detect_layout

            runtime_info["layout_detections"] = detect_layout(
                page_previews,
                image_size=layout_image_size,
                threshold=layout_confidence_threshold,
            )
        except Exception as error:
            logger.exception("DocLayout-YOLO failed during isolated upload test %s", run_id)
            raise HTTPException(
                503,
                "DocLayout-YOLO is unavailable. Install the layout-yolo extra and check model download access.",
            ) from error
    elif layout_detector == "doclayout-yolo":
        runtime_info["layout_detections"] = []
        runtime_info["layout_detector_note"] = "No rendered page or image preview is available for this format."

    embedding_status = "not_run"
    runtime_info["processing_time_ms"] = max(
        0, round((time.perf_counter() - processing_started) * 1000),
    )

    from core.database.upload_test_repository import UploadTestRepository
    repository = UploadTestRepository()
    try:
        repository.save_run(
            run_id, source_filename=filename, source_sha256=source_sha256,
            uploaded_by=user["sub"], processor_config=config, runtime_info=runtime_info,
            page_previews=page_previews, chunks=parsed["chunks"], tables=parsed["tables"],
            token_bounded_chunks=[], embeddings=[],
            embedding_status=embedding_status, embedding_error=None,
        )
    except Exception as error:
        logger.exception("Could not persist upload test run %s", run_id)
        raise HTTPException(503, "Upload processing completed, but its test output could not be saved") from error
    finally:
        repository.close()
    return {
        "run_id": str(run_id), "source_filename": filename,
        "source_sha256": source_sha256, "page_count": page_count,
        "chunk_count": len(parsed["chunks"]),
        "embedding_status": embedding_status,
        "embedding_error": None,
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
