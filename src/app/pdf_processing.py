"""Parse large PDF uploads in bounded ranges that can be resumed from PostgreSQL."""

import base64
import hashlib
import logging
import os

import fitz

from core.database.pdf_job_repository import pdf_jobs
from core.services.client import post

PDF_BATCH_SIZE = 20
logger = logging.getLogger(__name__)


def pdf_page_count(content: bytes) -> int:
    try:
        with fitz.open(stream=content, filetype="pdf") as source:
            return source.page_count if not source.needs_pass else 0
    except (fitz.FileDataError, fitz.EmptyFileError):
        # Let the regular parser report invalid PDFs through its existing error path.
        return 0


def _parse_range(source, job, first_page, last_page, url):
    with fitz.open() as batch:
        batch.insert_pdf(source, from_page=first_page - 1, to_page=last_page - 1)
        content = batch.tobytes(garbage=3, deflate=True)
    result = post(url, "/parse", {
        "filename": job["filename"],
        "content": base64.b64encode(content).decode("ascii"),
        "metadata": job["document_metadata"],
        "config": {**job["parser_config"], "require_complete_pdf": True},
    }, timeout=int(os.getenv("DOCUMENT_PROCESSING_TIMEOUT_SECONDS", "600")))
    expected_pages = set(range(1, last_page - first_page + 2))
    if {int(page) for page in result.get("page_sizes", {})} != expected_pages:
        raise ValueError("Parser did not return every page in the requested range")
    return result


def _shift_page(item, offset):
    if isinstance(item.get("page_number"), int):
        item["page_number"] += offset


def merge_checkpoints(checkpoints, page_count, batch_size):
    """Restore original page numbers, references, and reading order."""
    elements, tables = [], []
    page_sizes, metadata = {}, {}
    section_path = []
    diagnostic_lists = ("ocr_cleanup", "ocr_routing_diagnostics", "ocr_orientation_diagnostics")
    expected_starts = list(range(1, page_count + 1, batch_size))
    if [row["first_page"] for row in checkpoints] != expected_starts:
        raise ValueError("PDF checkpoint sequence is incomplete")
    for row in checkpoints:
        offset = row["first_page"] - 1
        output = row["output"]
        batch_metadata = output["metadata"]
        if not metadata:
            metadata.update({key: value for key, value in batch_metadata.items()
                             if key not in (*diagnostic_lists, "table_dash_recovery")})
        page_sizes.update({str(int(page) + offset): size for page, size in output["page_sizes"].items()})
        for key in diagnostic_lists:
            for entry in batch_metadata.get(key, []):
                _shift_page(entry, offset)
                metadata.setdefault(key, []).append(entry)
        for page, cells in batch_metadata.get("table_dash_recovery", {}).items():
            metadata.setdefault("table_dash_recovery", {})[str(int(page) + offset)] = cells

        table_offset = len(tables)
        batch_tables = output["tables"]
        for item in [*output["elements"], *batch_tables]:
            _shift_page(item, offset)
            item_metadata = item.setdefault("metadata", {})
            _shift_page(item_metadata, offset)
            item_metadata["page_count"] = page_count
        for element in output["elements"]:
            item_metadata = element["metadata"]
            if item_metadata.get("element_type") == "title" and element.get("text"):
                heading = element["text"]
                section_path = (section_path[:1] + [heading]
                                if item_metadata.get("docling_label") == "section_header" else [heading])
            if "section_path" in item_metadata:
                item_metadata.update(section_path=list(section_path),
                                     section_title=section_path[-1] if section_path else None,
                                     heading_level=min(len(section_path), 2) or None)
            if "table_ref" in element:
                element["table_ref"] += table_offset
            elements.append(element)
        tables.extend(batch_tables)

    if len(page_sizes) != page_count:
        raise ValueError("Merged parser output has incomplete page coverage")
    metadata["page_count"] = page_count
    return {"elements": elements, "tables": tables, "metadata": metadata, "page_sizes": page_sizes}


def process_pdf_job(document_id, attempt, read_source, finish_upload):
    try:
        with pdf_jobs() as jobs:
            job = jobs.claim(document_id, attempt)
            if job is None:
                return
            first_page = None
            try:
                page_count, batch_size = job["page_count"], job["batch_size"]
                if job["pages_processed"] < page_count:
                    first_page = job["pages_processed"] + 1
                    url = os.environ["DOCUMENT_PROCESSING_URL"]
                    content = read_source(job["storage_path"])
                    if hashlib.sha256(content).hexdigest() != job["source_sha256"]:
                        raise ValueError("The stored PDF differs from the original upload")
                    with fitz.open(stream=content, filetype="pdf") as source:
                        for first_page in range(first_page, page_count + 1, batch_size):
                            last_page = min(first_page + batch_size - 1, page_count)
                            result = _parse_range(source, job, first_page, last_page, url)
                            jobs.save_checkpoint(document_id, first_page, last_page, result)
                first_page = None
                parsed = merge_checkpoints(jobs.checkpoints(document_id), page_count, batch_size)
                result = finish_upload(job, parsed, jobs.connection)
                jobs.complete(document_id, result)
            except Exception:
                logger.exception("PDF processing failed for %s at range start %s", document_id, first_page)
                jobs.fail(document_id, first_page)
    except Exception:
        logger.exception("Could not start or update PDF processing job %s", document_id)
