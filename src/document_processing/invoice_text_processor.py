"""Extract compact invoice JSON from existing OCR elements and table cells."""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
from typing import Any

from pydantic import BaseModel, ConfigDict, StrictStr, field_validator


MODEL_ID = "Qwen/Qwen3-0.6B"
MODEL_REVISION = "c1899de289a04d12100db370d81485cdf75e47ca"
ADAPTER_ID = "lenhanm1/qwen3-0.6b-invoice-lora-900"
ADAPTER_REVISION = "7e062bb552f77af64b1c3bc9e205fa107c68c3d3"
SCHEMA_VERSION = "invoice.v1"
SCHEMA = {
    "invoice_no": None,
    "date": None,
    "seller": None,
    "buyer": None,
    "items": [{
        "description": None,
        "quantity": None,
        "unit": None,
        "unit_price": None,
        "amount": None,
    }],
    "subtotal": None,
    "tax_amount": None,
    "total_amount": None,
}
HEADER_SCHEMA = {
    key: SCHEMA[key]
    for key in (
        "invoice_no", "date", "seller", "buyer", "subtotal", "tax_amount", "total_amount",
    )
}
TABLE_SCHEMA = {
    "items": SCHEMA["items"],
}
_MAX_EVIDENCE_CHARS = 12_000
_TABLE_CHUNK_CHARS = 2_400


class InvoiceItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    description: StrictStr | None = None
    quantity: StrictStr | None = None
    unit: StrictStr | None = None
    unit_price: StrictStr | None = None
    amount: StrictStr | None = None

    @field_validator("quantity", "unit_price", "amount", mode="before")
    @classmethod
    def numeric_values_to_text(cls, value: Any) -> Any:
        return _numeric_text(value)


class InvoiceFields(BaseModel):
    model_config = ConfigDict(extra="forbid")

    invoice_no: StrictStr | None = None
    date: StrictStr | None = None
    seller: StrictStr | None = None
    buyer: StrictStr | None = None
    items: list[InvoiceItem] = []
    subtotal: StrictStr | None = None
    tax_amount: StrictStr | None = None
    total_amount: StrictStr | None = None

    @field_validator("subtotal", "tax_amount", "total_amount", mode="before")
    @classmethod
    def numeric_values_to_text(cls, value: Any) -> Any:
        return _numeric_text(value)


def _numeric_text(value: Any) -> Any:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return str(value)
    if isinstance(value, str) and re.search(r"[+=×*]", value):
        return None
    return value


def _prepare_extraction_input(
    elements: list[dict[str, Any]], tables: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "elements": [
            {
                "element_type": element.get("element_type") or element.get("type"),
                "page_number": (element.get("metadata") or {}).get("page_number"),
                "docling_label": (element.get("metadata") or {}).get("docling_label"),
                "bbox": (element.get("metadata") or {}).get("bbox"),
                "section_path": (element.get("metadata") or {}).get("section_path"),
                "text": str(element.get("text") or "").strip(),
            }
            for element in elements
            if str(element.get("text") or "").strip()
        ],
        "tables": [
            {
                key: table[key]
                for key in ("table_index", "page_number", "bbox", "columns", "rows", "context")
                if key in table
            }
            for table in tables
        ],
    }


def _parse_json_response(response: str) -> dict[str, Any] | None:
    text = response.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.IGNORECASE)
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end < start:
        return None
    try:
        parsed = InvoiceFields.model_validate_json(text[start:end + 1])
    except Exception:
        return None
    return parsed.model_dump(mode="json")


def _record_chunks(records: list[dict[str, Any]], max_chars: int) -> list[list[dict[str, Any]]]:
    chunks: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    current_size = 0
    for record in records:
        size = len(json.dumps(record, ensure_ascii=False))
        if current and current_size + size > max_chars:
            chunks.append(current)
            current, current_size = [], 0
        current.append(record)
        current_size += size
    if current:
        chunks.append(current)
    return chunks


def _extraction_jobs(ocr_input: dict[str, Any]) -> list[dict[str, Any]]:
    jobs: list[dict[str, Any]] = []
    elements = ocr_input["elements"]
    tables = ocr_input["tables"]
    instructions = (
        "Trích xuất hóa đơn tiếng Việt chỉ từ OCR EVIDENCE; không dùng kiến thức ngoài bằng chứng. "
        "Không bịa, đoán, chuẩn hóa, tự tính hoặc sửa dữ liệu OCR. Giá trị không nhìn thấy hoặc "
        "không chắc là null; danh sách items không có dòng hàng là [].\n"
        "OUTPUT phải là đúng một JSON object hợp lệ khớp SCHEMA: chỉ được dùng các key trong "
        "SCHEMA, không markdown, không code fence, không giải thích. Mọi giá trị lá khác null "
        "phải là JSON string, được chép từ đúng vùng bằng chứng. Giữ nguyên chữ số và dấu phân "
        "cách OCR; không xuất giá trị số dưới dạng JSON number hoặc biểu thức tính toán.\n"
    )

    if not tables:
        for index, chunk in enumerate(_record_chunks(elements, _MAX_EVIDENCE_CHARS), start=1):
            jobs.append({
                "kind": "document",
                "source": f"OCR elements {index}",
                "max_new_tokens": 1024,
                "prompt": (
                    instructions + "MODE: FULL INVOICE. Trích xuất các trường hóa đơn và dòng hàng.\n"
                    f"SCHEMA:\n{json.dumps(SCHEMA, ensure_ascii=False)}\n"
                    f"OCR EVIDENCE:\n{json.dumps(chunk, ensure_ascii=False)}"
                ),
            })
        return jobs

    for index, chunk in enumerate(_record_chunks(elements, _MAX_EVIDENCE_CHARS), start=1):
        jobs.append({
            "kind": "header",
            "source": f"OCR elements {index}",
            "max_new_tokens": 256,
            "prompt": (
                instructions + "MODE: INVOICE FIELDS. Trích invoice_no, date, seller, buyer và các tổng "
                "có nhãn rõ (subtotal, tax_amount, total_amount) từ OCR EVIDENCE. Seller là bên phát "
                "hành; buyer là bên mua. Chép seller/buyer từ vùng có nhãn tương ứng; không lấy tiêu "
                "đề, watermark, ghi chú hoặc địa chỉ làm tên bên mua/bán. invoice_no phải là số hóa đơn "
                "được ghi rõ, không phải mã phiếu xuất kho. Chép ngày và số tổng đúng như OCR; không "
                "tính tổng hoặc thuế từ dòng hàng. Không trích items.\n"
                f"SCHEMA:\n{json.dumps(HEADER_SCHEMA, ensure_ascii=False)}\n"
                f"OCR EVIDENCE:\n{json.dumps(chunk, ensure_ascii=False)}"
            ),
        })

    for table_index, table in enumerate(tables, start=1):
        columns = table.get("columns", [])
        rows = table.get("rows", [])
        row_records = [
            {"source_row": row_index, "cells": row}
            for row_index, row in enumerate(rows, start=1)
            if isinstance(row, dict)
        ]
        chunks = _record_chunks(row_records, _TABLE_CHUNK_CHARS)
        for chunk_index, chunk in enumerate(chunks, start=1):
            table_evidence = {
                "table_index": table.get("table_index", table_index),
                "page_number": table.get("page_number"),
                "bbox": table.get("bbox"),
                "columns": columns,
                "rows": chunk,
            }
            jobs.append({
                "kind": "table",
                "source": f"table {table_index}, row chunk {chunk_index}",
                "max_new_tokens": 1024,
                "prompt": (
                    instructions + "MODE: TABLE. Chỉ xuất key items theo SCHEMA; không xuất bất kỳ "
                    "field tổng nào. Chép từng mặt hàng theo từng dòng và đúng theo tiêu đề cột trong "
                    "bảng; tên/thứ tự cột có thể thay đổi. description lấy từ ô tên hàng, quantity từ "
                    "ô số lượng, unit từ ô đơn vị, unit_price từ ô đơn giá, amount từ ô thành tiền. "
                    "Không chuyển giá trị giữa cột, không tính toán, không thêm lời giải thích vào giá "
                    "trị. Mọi giá trị phải là chuỗi JSON giữ nguyên OCR hoặc null nếu ô trống/không rõ; "
                    "không dùng chuỗi rỗng. Với description, chép nguyên văn toàn bộ chữ trong ô tên "
                    "hàng của dòng đó. Giữ thứ tự dòng; "
                    "bỏ dòng tiêu đề và dòng tổng/thuế.\n"
                    f"SCHEMA:\n{json.dumps(TABLE_SCHEMA, ensure_ascii=False)}\n"
                    f"OCR TABLE EVIDENCE:\n{json.dumps(table_evidence, ensure_ascii=False)}"
                ),
            })
    return jobs


def _merge_job_fields(
    parsed_jobs: list[tuple[dict[str, Any], dict[str, Any]]],
) -> tuple[dict[str, Any], dict[str, list[str]]]:
    fields = InvoiceFields().model_dump(mode="json")
    conflicts: dict[str, list[str]] = {}
    scalar_fields = (
        "invoice_no", "date", "seller", "buyer", "subtotal", "tax_amount", "total_amount",
    )
    items: list[dict[str, Any]] = []
    owner_by_field = {
        "invoice_no": {"header", "document"}, "date": {"header", "document"},
        "seller": {"header", "document"}, "buyer": {"header", "document"},
        "subtotal": {"header", "document"},
        "tax_amount": {"header", "document"},
        "total_amount": {"header", "document"},
    }
    for field in scalar_fields:
        candidates = [
            str(result[field]).strip()
            for job, result in parsed_jobs
            if job["kind"] in owner_by_field[field] and result.get(field) is not None
            and str(result[field]).strip()
        ]
        unique = list(dict.fromkeys(candidates))
        if len(unique) == 1:
            fields[field] = unique[0]
        elif len(unique) > 1:
            conflicts[field] = unique

    for job, result in parsed_jobs:
        if job["kind"] in {"table", "document"}:
            items.extend(item for item in result.get("items", []) if isinstance(item, dict))
    fields["items"] = items
    return InvoiceFields.model_validate(fields).model_dump(mode="json"), conflicts


class InvoiceTextProcessor:
    """Use an isolated Qwen+LoRA worker after Docling extracts text and tables."""

    def __init__(self, config: dict[str, Any] | None = None):
        self.config = config or {}

    def process(
        self, elements: list[dict[str, Any]], tables: list[dict[str, Any]],
    ) -> dict[str, Any]:
        ocr_input = _prepare_extraction_input(elements, tables)
        if not ocr_input["elements"] and not ocr_input["tables"]:
            raise ValueError("No OCR elements or tables were extracted from the invoice")

        model_id = str(
            self.config.get("invoice_model")
            or os.environ.get("DOCUMENT_PROCESSING_INVOICE_MODEL")
            or MODEL_ID
        )
        revision = str(
            self.config.get("invoice_model_revision")
            or os.environ.get("DOCUMENT_PROCESSING_INVOICE_REVISION")
            or (MODEL_REVISION if model_id == MODEL_ID else "main")
        )
        adapter_id = str(
            self.config.get("invoice_adapter")
            or os.environ.get("DOCUMENT_PROCESSING_INVOICE_ADAPTER")
            or ADAPTER_ID
        )
        adapter_revision = str(
            self.config.get("invoice_adapter_revision")
            or os.environ.get("DOCUMENT_PROCESSING_INVOICE_ADAPTER_REVISION")
            or (ADAPTER_REVISION if adapter_id == ADAPTER_ID else "main")
        )
        from document_processing.vintern_processor import resolve_vintern_python

        python_path = resolve_vintern_python(self.config)
        if python_path is None or not python_path.is_file():
            raise RuntimeError(
                "Invoice text extraction needs the isolated Transformers runtime; "
                "set DOCUMENT_PROCESSING_VINTERN_PYTHON."
            )

        jobs = _extraction_jobs(ocr_input)
        with tempfile.TemporaryDirectory(prefix="invoice-text-") as temp_dir:
            request_path = Path(temp_dir) / "request.json"
            response_path = Path(temp_dir) / "response.json"
            request_path.write_text(json.dumps({
                "model_id": model_id,
                "revision": revision,
                "adapter_id": adapter_id,
                "adapter_revision": adapter_revision,
                "jobs": jobs,
                "cpu_threads": int(self.config.get("invoice_cpu_threads", 2)),
            }, ensure_ascii=False), encoding="utf-8")
            env = os.environ.copy()
            source_root = str(Path(__file__).resolve().parents[1])
            env["PYTHONPATH"] = os.pathsep.join(
                filter(None, [source_root, env.get("PYTHONPATH", "")])
            )
            timeout = int(self.config.get(
                "invoice_timeout_seconds",
                os.environ.get("DOCUMENT_PROCESSING_INVOICE_TIMEOUT_SECONDS", 600),
            ))
            completed = subprocess.run(
                [str(python_path), "-m", "document_processing.invoice_text_worker",
                 str(request_path), str(response_path)],
                capture_output=True, text=True, env=env, timeout=timeout, check=False,
            )
            if completed.returncode != 0:
                details = (completed.stderr or completed.stdout).strip()[-3000:]
                raise RuntimeError(
                    "Invoice text model failed in its isolated runtime. "
                    f"{details or f'Worker exited with code {completed.returncode}.'}"
                )
            try:
                worker_result = json.loads(response_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as error:
                raise RuntimeError("Invoice text worker returned invalid output") from error

        responses = worker_result.get("responses", [])
        parsed_jobs: list[tuple[dict[str, Any], dict[str, Any]]] = []
        invalid_sources = []
        if len(responses) != len(jobs):
            invalid_sources.append(
                f"worker returned {len(responses)} responses for {len(jobs)} extraction jobs"
            )
        for job, response in zip(jobs, responses):
            parsed = _parse_json_response(str(response))
            if parsed is None:
                invalid_sources.append(job["source"])
                continue
            parsed_jobs.append((job, parsed))
        fields, field_conflicts = _merge_job_fields(parsed_jobs)
        raw_response = json.dumps(
            [
                {"source": job["source"], "response": response}
                for job, response in zip(jobs, responses)
            ],
            ensure_ascii=False,
        )
        parse_error = None
        if invalid_sources:
            parse_error = "Invalid JSON/schema from: " + ", ".join(invalid_sources)
        elif not parsed_jobs:
            parse_error = "Model response did not match invoice.v1"
        return {
            "model": model_id,
            "revision": worker_result.get("revision", revision),
            "adapter": worker_result.get("adapter", adapter_id),
            "adapter_revision": worker_result.get("adapter_revision", adapter_revision),
            "schema_version": SCHEMA_VERSION,
            "status": "review_required",
            "review_required": True,
            "fields": fields,
            "raw_response": raw_response,
            "parse_error": parse_error,
            "field_conflicts": field_conflicts,
            "metrics": {
                **worker_result.get("metrics", {}),
                "extraction_jobs": len(jobs),
                "invalid_jobs": invalid_sources,
            },
        }
