"""Invoice image preparation and dispatch to the isolated Vintern runtime."""

from __future__ import annotations

import ast
from io import BytesIO
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from typing import Any

from PIL import Image, ImageOps, ImageSequence


_IMAGE_FORMATS = {".png", ".jpg", ".jpeg", ".tif", ".tiff"}
_MODEL_ID = "5CD-AI/Vintern-1B-v2"
_MODEL_REVISION = "5ec005391798968cd62f41cb71b22c1cee0b13d8"
_PROMPT = """Trích xuất hóa đơn trong ảnh thành đúng một JSON object, không markdown.
Giữ nguyên chuỗi số và cách viết số tiền trên ảnh; không tự suy đoán giá trị bị mờ.
Dùng null nếu không đọc được. Dùng các khóa sau:
{"ten_cua_hang":null,"dia_chi":null,"ma_so_thue":null,"so_hoa_don":null,
"ngay":null,"gio":null,"nguoi_mua":null,"mat_hang":[],"tam_tinh":null,
"giam_gia":null,"thue":null,"tong_cong":null,"tien_khach_tra":null,
"tien_thua":null,"phuong_thuc_thanh_toan":null}
Mỗi mat_hang là object có ten, so_luong, don_vi, don_gia, thanh_tien."""


def resolve_vintern_python(config: dict[str, Any] | None = None) -> Path | None:
    """Find an explicitly configured or project-local isolated Vintern Python."""
    configured = (config or {}).get("vintern_python") or os.environ.get(
        "DOCUMENT_PROCESSING_VINTERN_PYTHON"
    )
    if configured:
        return Path(str(configured)).expanduser()
    local_python = Path(__file__).resolve().parents[3] / ".venv-vintern" / "bin" / "python"
    return local_python if local_python.is_file() else None


class VinternInvoiceProcessor:
    """Run the receipt VLM in a separate environment from the Docling stack."""

    def __init__(self, config: dict[str, Any]):
        self.config = config

    def process(
        self, filename: str, content: bytes, metadata: dict[str, Any]
    ) -> dict[str, Any]:
        suffix = Path(filename).suffix.lower()
        if suffix != ".pdf" and suffix not in _IMAGE_FORMATS:
            raise ValueError("Invoice intent currently supports PDF and image files only.")

        python_path = resolve_vintern_python(self.config)
        if python_path is None:
            raise RuntimeError(
                "Invoice intent needs an isolated Vintern Python environment. Set "
                "DOCUMENT_PROCESSING_VINTERN_PYTHON or create .venv-vintern; "
                "see src/document_processing/README.md."
            )
        if not python_path.is_file():
            raise RuntimeError(
                f"Vintern Python executable does not exist: {python_path}"
            )

        model_id = str(
            self.config.get("vintern_model")
            or os.environ.get("DOCUMENT_PROCESSING_VINTERN_MODEL")
            or _MODEL_ID
        )
        device = str(
            self.config.get("vintern_device")
            or self.config.get("device")
            or self.config.get("docling_device")
            or "cpu"
        ).lower()

        with tempfile.TemporaryDirectory(prefix="document-invoice-") as temp_dir:
            work_dir = Path(temp_dir)
            pages = self._prepare_pages(suffix, content, work_dir)
            request_path = work_dir / "request.json"
            response_path = work_dir / "response.json"
            request_path.write_text(
                json.dumps({
                    "model_id": model_id,
                    "revision": self.config.get("vintern_revision") or (
                        _MODEL_REVISION if model_id == _MODEL_ID else None
                    ),
                    "device": device,
                    "prompt": _PROMPT,
                    "pages": [
                        {"page_number": page["page_number"], "image_path": page["image_path"]}
                        for page in pages
                    ],
                }, ensure_ascii=False),
                encoding="utf-8",
            )
            env = os.environ.copy()
            source_root = str(Path(__file__).resolve().parents[2])
            env["PYTHONPATH"] = os.pathsep.join(filter(None, [source_root, env.get("PYTHONPATH", "")]))
            timeout = int(
                self.config.get(
                    "vintern_timeout_seconds",
                    os.environ.get("DOCUMENT_PROCESSING_VINTERN_TIMEOUT_SECONDS", 1800),
                )
            )
            completed = subprocess.run(
                [str(python_path), "-m", "document_processing.invoice.vintern_worker",
                 str(request_path), str(response_path)],
                capture_output=True,
                text=True,
                env=env,
                timeout=timeout,
                check=False,
            )
            if completed.returncode != 0:
                details = (completed.stderr or completed.stdout).strip()[-3000:]
                raise RuntimeError(
                    "Vintern invoice extraction failed in its isolated runtime. "
                    f"{details or f'Worker exited with code {completed.returncode}.'}"
                )
            try:
                worker_result = json.loads(response_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as error:
                raise RuntimeError("Vintern worker returned invalid output.") from error

            extracted_pages = []
            elements = []
            for page in worker_result.get("pages", []):
                raw_response = str(page.get("response", "")).strip()
                fields = _parse_fields(raw_response)
                page_number = int(page["page_number"])
                extracted_page = {
                    "page_number": page_number,
                    "fields": fields,
                    "raw_response": raw_response,
                    "review_required": True,
                }
                extracted_pages.append(extracted_page)
                searchable_value = fields if fields is not None else {"raw_response": raw_response}
                elements.append({
                    "text": json.dumps(searchable_value, ensure_ascii=False),
                    "element_type": "text",
                    "metadata": {
                        "page_number": page_number,
                        "element_type": "text",
                        "layout_type": "text",
                        "parser": "vintern_invoice",
                        "text_extraction_method": "vintern_invoice_extraction",
                        "review_required": True,
                    },
                })

            if not extracted_pages:
                raise RuntimeError("Vintern returned no invoice page results.")

            page_previews = {
                str(page["page_number"]): page["preview_png"]
                for page in pages
            }
            page_sizes = {
                str(page["page_number"]): page["size"]
                for page in pages
            }
            return {
                "elements": elements,
                "tables": [],
                "invoice_extraction": {
                    "model": model_id,
                    "status": "review_required",
                    "review_required": True,
                    "pages": extracted_pages,
                },
                "page_previews": page_previews,
                "page_sizes": page_sizes,
                "metadata": {
                    "pipeline_id": "vintern_invoice",
                    "parser_engine": "vintern_invoice",
                    "intent": "invoice",
                    "invoice_model": model_id,
                    "invoice_model_revision": worker_result.get("revision"),
                    "invoice_review_required": True,
                },
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
        else:
            with Image.open(BytesIO(content)) as source:
                images.extend(
                    ImageOps.exif_transpose(frame).convert("RGB").copy()
                    for frame in ImageSequence.Iterator(source)
                )

        pages = []
        for page_number, source_image in enumerate(images, start=1):
            image = ImageOps.exif_transpose(source_image).convert("RGB")
            image_path = work_dir / f"page-{page_number}.png"
            image.save(image_path, format="PNG")
            preview = BytesIO()
            image.save(preview, format="PNG")
            pages.append({
                "page_number": page_number,
                "image_path": str(image_path),
                "preview_png": preview.getvalue(),
                "size": {"width": image.width, "height": image.height},
            })
        return pages


def _parse_fields(response: str) -> dict[str, Any] | None:
    text = response.strip()
    if text.startswith("```"):
        text = text.strip("`").removeprefix("json").strip()
    start = text.find("{")
    if start < 0:
        return None
    candidate = text[start:]
    try:
        value, _ = json.JSONDecoder().raw_decode(candidate)
    except json.JSONDecodeError:
        try:
            value = ast.literal_eval(candidate)
        except (SyntaxError, ValueError):
            return None
    return value if isinstance(value, dict) else None
