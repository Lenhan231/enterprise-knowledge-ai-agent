"""Run Xiaomi-OCR-0 over invoice page images in an isolated Transformers runtime."""

from __future__ import annotations

from io import BytesIO
import json
import logging
import os
from pathlib import Path
import re
import subprocess
import tempfile
import time
from typing import Any

from PIL import Image, ImageOps, ImageSequence

from document_processing.invoice_text_processor import (
    InvoiceFields,
    SCHEMA,
    SCHEMA_VERSION,
    _merge_job_fields,
)


MODEL_ID = "xiaomi-research/Xiaomi-OCR-0"
_LOGGER = logging.getLogger(__name__)
_IMAGE_FORMATS = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".webp"}
_PROMPT = """Extract the Vietnamese invoice from this image. Return exactly one JSON object matching this schema:
{schema}
All non-null leaf values must be strings. Preserve the original Vietnamese spelling, digits, separators, and line order exactly as printed. Do not infer, calculate, normalize, or repair text. Use null when a value is absent or unreadable, and [] when there are no line items. Map each item from its row and column headings: description, quantity, unit, unit_price, amount. Keep invoice totals separate from line amounts. Return JSON only, without markdown or explanation."""


def resolve_xiaomi_python(config: dict[str, Any] | None = None) -> Path | None:
    configured = (config or {}).get("xiaomi_python") or os.environ.get(
        "DOCUMENT_PROCESSING_XIAOMI_PYTHON"
    )
    if configured:
        return Path(str(configured)).expanduser()
    local_python = Path(__file__).resolve().parents[2] / ".venv-xiaomi" / "bin" / "python"
    return local_python if local_python.is_file() else None


def _parse_xiaomi_response(response: str) -> dict[str, Any] | None:
    text = response.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.IGNORECASE)
    start = min((index for index in (text.find("{"), text.find("[")) if index >= 0), default=-1)
    if start < 0:
        return None
    try:
        value, _ = json.JSONDecoder().raw_decode(text[start:])
        if isinstance(value, list):
            value = next((item for item in value if isinstance(item, dict)), None)
        if not isinstance(value, dict):
            return None
        return InvoiceFields.model_validate(value).model_dump(mode="json")
    except (ValueError, TypeError):
        return None


class XiaomiOCRInvoiceProcessor:
    """Extract invoice fields directly from the original PDF or image pages."""

    def __init__(self, config: dict[str, Any] | None = None):
        self.config = config or {}

    def process(
        self, filename: str, content: bytes, *, reference_id: str | None = None,
    ) -> dict[str, Any]:
        started = time.perf_counter()
        model_id = str(
            self.config.get("xiaomi_invoice_model")
            or os.environ.get("DOCUMENT_PROCESSING_XIAOMI_MODEL")
            or MODEL_ID
        )
        revision = str(
            self.config.get("xiaomi_invoice_revision")
            or os.environ.get("DOCUMENT_PROCESSING_XIAOMI_REVISION")
            or "main"
        )
        device = str(self.config.get("xiaomi_device") or os.environ.get(
            "DOCUMENT_PROCESSING_XIAOMI_DEVICE", "auto",
        ))
        python_path = resolve_xiaomi_python(self.config)
        if python_path is None or not python_path.is_file():
            raise RuntimeError(
                "Xiaomi-OCR-0 needs an isolated Transformers runtime; set "
                "DOCUMENT_PROCESSING_XIAOMI_PYTHON or create .venv-xiaomi."
            )

        with tempfile.TemporaryDirectory(prefix="invoice-xiaomi-") as temp_dir:
            work_dir = Path(temp_dir)
            pages = self._prepare_pages(Path(filename).suffix.lower(), content, work_dir)
            if not pages:
                raise ValueError("No pages were found in the invoice source")
            request_path = work_dir / "request.json"
            response_path = work_dir / "response.json"
            request_path.write_text(json.dumps({
                "model_id": model_id,
                "revision": revision,
                "device": device,
                "prompt": _PROMPT.format(schema=json.dumps(SCHEMA, ensure_ascii=False)),
                "max_new_tokens": int(self.config.get("xiaomi_max_new_tokens", 4096)),
                "pages": [
                    {"page_number": page["page_number"], "image_path": page["image_path"]}
                    for page in pages
                ],
            }, ensure_ascii=False), encoding="utf-8")

            env = os.environ.copy()
            source_root = str(Path(__file__).resolve().parents[1])
            env["PYTHONPATH"] = os.pathsep.join(filter(None, [source_root, env.get("PYTHONPATH", "")]))
            timeout = int(self.config.get(
                "xiaomi_timeout_seconds",
                os.environ.get("DOCUMENT_PROCESSING_XIAOMI_TIMEOUT_SECONDS", 1800),
            ))
            try:
                completed = subprocess.run(
                    [str(python_path), "-m", "document_processing.xiaomi_ocr_worker",
                     str(request_path), str(response_path)],
                    capture_output=True, text=True, env=env, timeout=timeout, check=False,
                )
            except subprocess.TimeoutExpired as error:
                raise RuntimeError(f"Xiaomi-OCR-0 exceeded the {timeout}s timeout") from error
            if completed.returncode != 0:
                details = (completed.stderr or completed.stdout).strip()[-3000:]
                raise RuntimeError(
                    "Xiaomi-OCR-0 inference failed in its isolated runtime. "
                    f"{details or f'Worker exited with code {completed.returncode}.'}"
                )
            try:
                worker_result = json.loads(response_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as error:
                raise RuntimeError("Xiaomi-OCR-0 worker returned invalid output") from error

        parsed_jobs = []
        invalid_pages = []
        responses = worker_result.get("pages", [])
        if len(responses) != len(pages):
            invalid_pages.append(
                f"worker returned {len(responses)} page results for {len(pages)} pages"
            )
        for page, result in zip(pages, responses):
            parsed = _parse_xiaomi_response(str(result.get("response", "")))
            if parsed is None:
                invalid_pages.append(f"page {page['page_number']}")
                continue
            parsed_jobs.append(({"kind": "document"}, parsed))
        fields, conflicts = _merge_job_fields(parsed_jobs)
        model_revision = worker_result.get("revision", revision)
        raw_response = json.dumps(responses, ensure_ascii=False)
        parse_error = (
            "Invalid JSON/schema from: " + ", ".join(invalid_pages)
            if invalid_pages else None
        )
        metrics = {
            **(worker_result.get("metrics") or {}),
            "page_count": len(pages),
            "invalid_pages": invalid_pages,
            "elapsed_seconds": round(time.perf_counter() - started, 2),
        }
        _LOGGER.info("XIAOMI_INVOICE_EXTRACTION %s", json.dumps({
            "invoice_id": reference_id,
            "model": model_id,
            "revision": model_revision,
            "page_count": len(pages),
            "elapsed_seconds": metrics["elapsed_seconds"],
        }, separators=(",", ":")))
        return {
            "model": model_id,
            "revision": model_revision,
            "adapter": None,
            "adapter_revision": None,
            "schema_version": SCHEMA_VERSION,
            "status": "review_required",
            "review_required": True,
            "fields": fields,
            "raw_response": raw_response,
            "parse_error": parse_error,
            "field_conflicts": conflicts,
            "metrics": metrics,
        }

    @staticmethod
    def _prepare_pages(suffix: str, content: bytes, work_dir: Path) -> list[dict[str, Any]]:
        images: list[Image.Image] = []
        if suffix == ".pdf":
            import fitz

            with fitz.open(stream=content, filetype="pdf") as pdf:
                for page in pdf:
                    pixmap = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
                    images.append(Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples))
        elif suffix in _IMAGE_FORMATS:
            with Image.open(BytesIO(content)) as source:
                images.extend(
                    ImageOps.exif_transpose(frame).convert("RGB").copy()
                    for frame in ImageSequence.Iterator(source)
                )
        else:
            raise ValueError(f"Xiaomi-OCR-0 does not support invoice format: {suffix or 'unknown'}")

        pages = []
        for page_number, source_image in enumerate(images, start=1):
            image = ImageOps.exif_transpose(source_image).convert("RGB")
            image_path = work_dir / f"page-{page_number}.png"
            image.save(image_path, format="PNG")
            pages.append({"page_number": page_number, "image_path": str(image_path)})
        return pages
