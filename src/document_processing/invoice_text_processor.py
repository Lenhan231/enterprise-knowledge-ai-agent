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


MODEL_ID = "Qwen/Qwen2.5-0.5B-Instruct"
MODEL_REVISION = "7ae557604adf67be50417f59c2c2f167def9a775"
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


def _is_numbered_column_guide(row: dict[str, Any], columns: list[str]) -> bool:
    """Drop invoice templates' separate 1..N column guide row, not invoice data."""
    values = [str(row.get(column) or "").strip() for column in columns]
    if len(values) < 3 or values[:1] != ["1"]:
        return False
    last_value = values[-1]
    formula_like_amount = bool(
        re.fullmatch(rf"{len(values)}[\d\s=?:x×*\-]+\.?", last_value, flags=re.IGNORECASE)
        and re.search(r"[=?:x×*\-]", last_value, flags=re.IGNORECASE)
    )
    short_cells = all(len(re.sub(r"[^\w]", "", value)) <= 4 for value in values[:-1])
    if formula_like_amount and short_cells:
        return True
    if any(value != str(index) for index, value in enumerate(values[:-1], start=1)):
        return False
    return bool(re.match(rf"{len(values)}.*[x×*]", last_value, flags=re.IGNORECASE))


def _prepare_extraction_input(
    elements: list[dict[str, Any]], tables: list[dict[str, Any]],
) -> dict[str, Any]:
    prepared_tables = []
    for table in tables:
        columns = [str(column) for column in table.get("columns", [])]
        description_column = _find_column(columns, ("tên hàng", "mô tả", "description"))
        quantity_column = _find_column(columns, ("số lượng", "quantity"))
        unit_column = _find_column(columns, ("đvt", "đơn vị", "unit"))
        unit_price_column = _find_column(columns, ("đơn giá", "unit price"))
        amount_column = _find_column(columns, ("thành tiền", "amount"))
        item_rows = []
        summary_rows = []
        for row in table.get("rows", []):
            if not isinstance(row, dict) or _is_numbered_column_guide(row, columns):
                continue
            values = [str(row.get(column) or "").strip() for column in columns]
            row_text = " | ".join(value for value in values if value)
            lowered = row_text.lower()
            summary_kind = _summary_kind(lowered)
            if summary_kind:
                summary_rows.append({
                    "kind": summary_kind,
                    "label": row_text,
                    "amount": str(row.get(amount_column) or "").strip() or None,
                })
                continue
            description = str(row.get(description_column) or "").strip()
            if not description:
                continue
            item_rows.append({
                "description": description,
                "quantity": _cell_text(row, quantity_column),
                "unit": _cell_text(row, unit_column),
                "unit_price": _cell_text(row, unit_price_column),
                "amount": _cell_text(row, amount_column),
            })
        prepared_tables.append({"item_rows": item_rows, "summary_rows": summary_rows})
    return {
        "elements": [
            {
                "element_type": element.get("element_type") or element.get("type"),
                "page_number": (element.get("metadata") or {}).get("page_number"),
                "text": str(element.get("text") or "").strip(),
            }
            for element in elements
            if str(element.get("text") or "").strip()
        ],
        "tables": prepared_tables,
    }


def _find_column(columns: list[str], hints: tuple[str, ...]) -> str | None:
    return next((column for column in columns if any(hint in column.lower() for hint in hints)), None)


def _cell_text(row: dict[str, Any], column: str | None) -> str | None:
    value = str(row.get(column) or "").strip() if column else ""
    return value or None


def _summary_kind(text: str) -> str | None:
    if "tổng tiền" in text or "total" in text:
        return "total_amount"
    if "tiền thuế" in text or "tax amount" in text:
        return "tax_amount"
    if "cộng tiền" in text or "subtotal" in text:
        return "subtotal"
    if "thuế suất" in text or "vat" in text:
        return "tax_summary"
    return None


def _fields_from_tables(tables: list[dict[str, Any]]) -> dict[str, Any]:
    fields: dict[str, Any] = {}
    items = [item for table in tables for item in table["item_rows"]]
    if items:
        fields["items"] = items
    for table in tables:
        for row in table["summary_rows"]:
            if row["kind"] in {"subtotal", "tax_amount", "total_amount"} and row["amount"]:
                fields[row["kind"]] = row["amount"]
    return fields


def _fields_from_labeled_elements(elements: list[dict[str, Any]]) -> dict[str, Any]:
    fields: dict[str, Any] = {}
    for element in elements:
        text = str(element.get("text") or "").strip()
        if not text:
            continue
        buyer = re.search(
            r"(?:tên\s+đơn\s+vị|tên\s+người\s+mua|người\s+mua\s+hàng)\s*:\s*(.+)",
            text, flags=re.IGNORECASE,
        )
        if buyer and buyer.group(1).strip():
            fields["buyer"] = buyer.group(1).strip()
        seller = re.search(r"(?:tên\s+người\s+bán|người\s+bán\s+hàng)\s*:\s*(.+)", text, flags=re.IGNORECASE)
        if seller and seller.group(1).strip():
            fields["seller"] = seller.group(1).strip()
        element_type = element.get("element_type") or element.get("type")
        if element_type == "title" and "công ty" in text.lower():
            fields["seller"] = text
    return fields


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


class InvoiceTextProcessor:
    """Use the isolated CPU model after Docling has extracted page text and tables."""

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
        from document_processing.vintern_processor import resolve_vintern_python

        python_path = resolve_vintern_python(self.config)
        if python_path is None or not python_path.is_file():
            raise RuntimeError(
                "Invoice text extraction needs the isolated Transformers runtime; "
                "set DOCUMENT_PROCESSING_VINTERN_PYTHON."
            )

        prompt = (
            "Trích xuất dữ liệu hóa đơn tiếng Việt từ các vùng OCR và bảng. "
            "Chỉ trả về một JSON object theo schema. Giữ nguyên chuỗi số và cách viết; "
            "không tự tính, không suy đoán trường thiếu, dùng null nếu không thấy. "
            "Các hàng chỉ đánh số cột hoặc ghi công thức mẫu không phải dữ liệu hóa đơn. "
            "Hàng hướng dẫn có thể bị OCR sai, ví dụ 1, tư., ở., 40 đ., 5., 6 - 45.; "
            "Chỉ lấy số lượng/đơn giá khi chúng nằm trong hàng hàng hóa thực tế; "
            "không lấy số thứ tự cột làm dữ liệu và không tự tính bất kỳ số tiền nào. "
            "Các hàng cộng tiền, tiền thuế và tổng thanh toán là số tổng hợp, không phải item.\n"
            f"SCHEMA:\n{json.dumps(SCHEMA, ensure_ascii=False)}\n"
            f"OCR ELEMENTS AND TABLES:\n{json.dumps(ocr_input, ensure_ascii=False)}"
        )
        with tempfile.TemporaryDirectory(prefix="invoice-text-") as temp_dir:
            request_path = Path(temp_dir) / "request.json"
            response_path = Path(temp_dir) / "response.json"
            request_path.write_text(json.dumps({
                "model_id": model_id,
                "revision": revision,
                "prompt": prompt,
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

        raw_response = str(worker_result.get("response", ""))
        fields = _parse_json_response(raw_response) or InvoiceFields().model_dump(mode="json")
        fields.update(_fields_from_tables(ocr_input["tables"]))
        fields.update(_fields_from_labeled_elements(elements))
        return {
            "model": model_id,
            "revision": worker_result.get("revision", revision),
            "schema_version": SCHEMA_VERSION,
            "status": "review_required",
            "review_required": True,
            "fields": fields,
            "raw_response": raw_response,
            "parse_error": None if fields is not None else "Model response did not match invoice.v1",
            "metrics": worker_result.get("metrics", {}),
        }
