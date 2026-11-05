"""Extract compact invoice JSON from existing OCR elements and table cells."""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
from typing import Any

from pydantic import BaseModel, ConfigDict, StrictStr


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
        ocr_input = {
            "elements": [
                {
                    "element_type": element.get("element_type"),
                    "page_number": (element.get("metadata") or {}).get("page_number"),
                    "text": str(element.get("text") or "").strip(),
                }
                for element in elements
                if str(element.get("text") or "").strip()
            ],
            "tables": [
                {"columns": table.get("columns", []), "rows": table.get("rows", [])}
                for table in tables
            ],
        }
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
            "Bỏ qua số thứ tự/chú thích mẫu dưới tiêu đề cột; mỗi hàng hóa thực tế là một item.\n"
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
        fields = _parse_json_response(raw_response)
        return {
            "model": model_id,
            "revision": worker_result.get("revision", revision),
            "schema_version": SCHEMA_VERSION,
            "status": "review_required",
            "review_required": True,
            "fields": fields or InvoiceFields().model_dump(mode="json"),
            "raw_response": raw_response,
            "parse_error": None if fields is not None else "Model response did not match invoice.v1",
            "metrics": worker_result.get("metrics", {}),
        }
