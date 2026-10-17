"""Parse PDFs through MinerU Basic."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any

import fitz


def process(
    runtime: Any,
    pdf_bytes: bytes,
    document: dict[str, Any],
    *,
    force_ocr: bool | None = None,
    page_range: str | None = None,
) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="upload-test-mineru-") as temporary_dir:
        work_dir = Path(temporary_dir)
        input_pdf = work_dir / "input.pdf"
        output_dir = work_dir / "output"
        input_pdf.write_bytes(pdf_bytes)
        runtime.run([
            "parse", str(input_pdf), "--output", str(output_dir),
            "--pages", (page_range if page_range is not None else runtime.config.get("mineru_page_range")) or "all",
            "--tier", "basic", "--format", "middle_json",
            "--ocr-mode", "ocr" if (
                runtime.config.get("mineru_force_ocr") if force_ocr is None else force_ocr
            ) else "auto",
            "--disable-image-analysis",
        ])
        outputs = list(output_dir.rglob("*.json")) if output_dir.exists() else []
        if len(outputs) != 1:
            raise RuntimeError(f"Local MinerU produced {len(outputs)} parsed JSON files; expected one")
        try:
            payload = json.loads(outputs[0].read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise RuntimeError("Local MinerU produced invalid Middle JSON") from error

    version = (payload.get("metadata") or {}).get("producer", {}).get("version")
    return runtime.result_mapper.to_parser_result(payload, pdf_bytes, version)
