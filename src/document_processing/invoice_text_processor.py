"""Extract compact invoice JSON from existing OCR elements and table cells."""

from __future__ import annotations

import json
import hashlib
import hmac
import os
from pathlib import Path
import re
import subprocess
import tempfile
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

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
    "subtotal": SCHEMA["subtotal"],
    "tax_amount": SCHEMA["tax_amount"],
    "total_amount": SCHEMA["total_amount"],
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
                    instructions + "MODE: TABLE. Trích items và các field tổng có nhãn rõ trong bảng. "
                    "Chép từng mặt hàng theo từng dòng và đúng theo tiêu đề cột trong "
                    "bảng; tên/thứ tự cột có thể thay đổi. description lấy từ ô tên hàng, quantity từ "
                    "ô số lượng, unit từ ô đơn vị, unit_price từ ô đơn giá, amount từ ô thành tiền. "
                    "subtotal là giá trị ở dòng/ô có nhãn cộng tiền hàng hoặc subtotal; tax_amount "
                    "là giá trị ở dòng/ô thuế VAT/tiền thuế; total_amount là giá trị ở dòng/ô tổng "
                    "cộng thanh toán/tổng tiền thanh toán/tổng thanh toán. Chỉ gán field tổng khi "
                    "nhãn tương ứng xuất hiện rõ trong bằng chứng; amount của một mặt hàng không "
                    "tự động là total_amount. Nếu một dòng tổng xuất hiện trong chunk này, trích "
                    "giá trị của nó, không bỏ qua dòng đó. "
                    "Không chuyển giá trị giữa cột, không tính toán, không thêm lời giải thích vào giá "
                    "trị. Mọi giá trị phải là chuỗi JSON giữ nguyên OCR hoặc null nếu ô trống/không rõ; "
                    "không dùng chuỗi rỗng. Với description, chép nguyên văn toàn bộ chữ trong ô tên "
                    "hàng của dòng đó. Giữ thứ tự dòng; bỏ dòng tiêu đề.\n"
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
        "subtotal": {"header", "document", "table"},
        "tax_amount": {"header", "document", "table"},
        "total_amount": {"header", "document", "table"},
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
    """Extract invoice JSON from Docling OCR using a configured text model."""

    def __init__(self, config: dict[str, Any] | None = None):
        self.config = config or {}

    def process(
        self, elements: list[dict[str, Any]], tables: list[dict[str, Any]],
    ) -> dict[str, Any]:
        ocr_input = _prepare_extraction_input(elements, tables)
        if not ocr_input["elements"] and not ocr_input["tables"]:
            raise ValueError("No OCR elements or tables were extracted from the invoice")

        provider = str(
            self.config.get("invoice_provider")
            or os.environ.get("DOCUMENT_PROCESSING_INVOICE_PROVIDER")
            or "modal"
        ).strip().lower()
        if provider not in {"gemini", "modal", "local"}:
            raise ValueError(f"Unsupported invoice extraction provider: {provider}")

        if provider == "gemini":
            model_id = str(
                self.config.get("gemini_invoice_model")
                or os.environ.get("DOCUMENT_PROCESSING_GEMINI_INVOICE_MODEL")
                or "gemini-3.1-flash-lite"
            )
            revision = "Gemini API"
            adapter_id = None
            adapter_revision = None
        else:
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
        jobs = _extraction_jobs(ocr_input)
        request_payload = {
            "model_id": model_id,
            "revision": revision,
            "adapter_id": adapter_id,
            "adapter_revision": adapter_revision,
            "jobs": jobs,
            "cpu_threads": int(self.config.get("invoice_cpu_threads", 2)),
        }
        timeout = int(self.config.get(
            "invoice_timeout_seconds",
            os.environ.get("DOCUMENT_PROCESSING_INVOICE_TIMEOUT_SECONDS", 1200),
        ))
        modal_url = str(
            self.config.get("invoice_modal_url")
            or os.environ.get("DOCUMENT_PROCESSING_INVOICE_MODAL_URL")
            or ""
        ).strip()
        if provider == "gemini":
            worker_result = _infer_with_gemini(
                jobs,
                api_key=os.environ.get("GEMINI_API") or os.environ.get("GEMINI_API_KEY") or "",
                model_id=model_id,
                timeout=min(timeout, 180),
            )
        elif provider == "modal" and modal_url:
            if not modal_url.startswith("https://"):
                raise ValueError("DOCUMENT_PROCESSING_INVOICE_MODAL_URL must use HTTPS")
            token = os.environ.get("HF_INVOICE_LLM_TOKEN", "")
            if not token:
                raise RuntimeError("HF_INVOICE_LLM_TOKEN is required to authenticate with Modal")
            canonical = json.dumps(
                request_payload, ensure_ascii=False, separators=(",", ":"),
            ).encode("utf-8")
            signed_payload = {
                **request_payload,
                "auth_signature": hmac.new(
                    token.encode("utf-8"), canonical, hashlib.sha256,
                ).hexdigest(),
            }
            request = Request(
                modal_url,
                data=json.dumps(signed_payload, ensure_ascii=False).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            try:
                with urlopen(request, timeout=timeout) as response:
                    worker_result = json.loads(response.read().decode("utf-8"))
            except HTTPError as error:
                detail = error.read(1000).decode("utf-8", errors="replace")
                raise RuntimeError(
                    f"Modal invoice endpoint returned HTTP {error.code}: {detail}"
                ) from error
            except (URLError, TimeoutError, json.JSONDecodeError) as error:
                raise RuntimeError(f"Modal invoice endpoint request failed: {error}") from error
        else:
            from document_processing.vintern_processor import resolve_vintern_python

            python_path = resolve_vintern_python(self.config)
            if python_path is None or not python_path.is_file():
                raise RuntimeError(
                    "Invoice text extraction needs the isolated Transformers runtime; "
                    "set DOCUMENT_PROCESSING_VINTERN_PYTHON."
                )
            with tempfile.TemporaryDirectory(prefix="invoice-text-") as temp_dir:
                request_path = Path(temp_dir) / "request.json"
                response_path = Path(temp_dir) / "response.json"
                request_path.write_text(
                    json.dumps(request_payload, ensure_ascii=False), encoding="utf-8",
                )
                env = os.environ.copy()
                source_root = str(Path(__file__).resolve().parents[1])
                env["PYTHONPATH"] = os.pathsep.join(
                    filter(None, [source_root, env.get("PYTHONPATH", "")])
                )
                try:
                    completed = subprocess.run(
                        [str(python_path), "-m", "document_processing.invoice_text_worker",
                         str(request_path), str(response_path)],
                        capture_output=True, text=True, env=env, timeout=timeout, check=False,
                    )
                except subprocess.TimeoutExpired as error:
                    raise RuntimeError(
                        f"Invoice text worker exceeded the {timeout}s timeout"
                    ) from error
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


def _infer_with_gemini(
    jobs: list[dict[str, Any]], *, api_key: str, model_id: str, timeout: int,
) -> dict[str, Any]:
    if not api_key:
        raise RuntimeError("GEMINI_API is required when DOCUMENT_PROCESSING_INVOICE_PROVIDER=gemini")

    responses: list[str] = []
    prompt_tokens = generated_tokens = 0
    elapsed = 0.0
    model_version = model_id
    endpoint = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"{model_id}:generateContent?key={quote(api_key, safe='')}"
    )
    for job in jobs:
        body = json.dumps({
            "contents": [{"role": "user", "parts": [{"text": job["prompt"]}]}],
            "generationConfig": {
                "temperature": 0,
                "maxOutputTokens": int(job.get("max_new_tokens", 1024)),
                "responseMimeType": "application/json",
            },
        }, ensure_ascii=False).encode("utf-8")
        for attempt in range(3):
            request = Request(
                endpoint,
                data=body,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            started = time.perf_counter()
            try:
                with urlopen(request, timeout=timeout) as response:
                    result = json.loads(response.read().decode("utf-8"))
                elapsed += time.perf_counter() - started
                candidates = result.get("candidates") or []
                parts = ((candidates[0].get("content") or {}).get("parts") or []) if candidates else []
                responses.append("".join(part.get("text", "") for part in parts))
                usage = result.get("usageMetadata") or {}
                prompt_tokens += int(usage.get("promptTokenCount") or 0)
                generated_tokens += int(usage.get("candidatesTokenCount") or 0)
                model_version = result.get("modelVersion") or model_version
                break
            except HTTPError as error:
                detail = error.read(1200).decode("utf-8", errors="replace")
                if error.code != 429 or attempt == 2:
                    raise RuntimeError(
                        f"Gemini invoice API returned HTTP {error.code}: {detail}"
                    ) from error
                try:
                    delay = float(error.headers.get("Retry-After", 2 ** (attempt + 1)))
                except (TypeError, ValueError):
                    delay = float(2 ** (attempt + 1))
                time.sleep(max(1.0, min(delay, 30.0)))
            except (URLError, TimeoutError, json.JSONDecodeError) as error:
                raise RuntimeError(f"Gemini invoice API request failed: {error}") from error

    return {
        "revision": model_version,
        "adapter": None,
        "adapter_revision": None,
        "responses": responses,
        "metrics": {
            "provider": "gemini_api",
            "device": "remote_api",
            "dtype": "remote",
            "load_seconds": 0,
            "inference_seconds": round(elapsed, 2),
            "prompt_tokens": prompt_tokens,
            "generated_tokens": generated_tokens,
            "request_count": len(jobs),
        },
    }
