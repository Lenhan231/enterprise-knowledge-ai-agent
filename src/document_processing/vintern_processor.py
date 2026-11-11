"""Run invoice extraction or image captioning through the isolated Vintern runtime."""

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


_IMAGE_FORMATS = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".webp", ".svg"}
_MODEL_ID = "5CD-AI/Vintern-1B-v2"
_MODEL_REVISION = "5ec005391798968cd62f41cb71b22c1cee0b13d8"
_INVOICE_PROMPT = """Trích xuất hóa đơn trong ảnh thành đúng một JSON object, không markdown.
Giữ nguyên chuỗi số và cách viết trên ảnh; không suy đoán, dùng null nếu không đọc được.
Dùng các khóa sau:
{"loại":null,"số":null,"ngày":null,"người bán":null,"mã số thuế":null,
"người mua":null,"mặt hàng":[{"hàng hóa":null,"số lượng":null,"đơn giá":null}],
"thuế":null,"tổng tiền":null}
Mỗi phần tử mặt hàng là một dòng hàng. Dùng đúng các khóa này; nếu không đọc được thì điền null."""
_IMAGE_CAPTION_PROMPT = """Quan sát ảnh và viết một caption ngắn bằng tiếng Việt mô tả nội dung chính, đối tượng và bố cục nhìn thấy. Nếu ảnh có sơ đồ hoặc biểu đồ, nêu luồng/quan hệ và các nhãn dễ đọc. Không suy đoán chi tiết không nhìn rõ; chỉ trả về caption, không thêm lời dẫn."""


def resolve_vintern_python(config: dict[str, Any] | None = None) -> Path | None:
    """Find an explicitly configured or project-local isolated Vintern Python."""
    configured = (config or {}).get("vintern_python") or os.environ.get(
        "DOCUMENT_PROCESSING_VINTERN_PYTHON"
    )
    if configured:
        return Path(str(configured)).expanduser()
    local_python = Path(__file__).resolve().parents[2] / ".venv-vintern" / "bin" / "python"
    return local_python if local_python.is_file() else None


class VinternProcessor:
    """Run one page-level Vintern task in an isolated environment."""

    def __init__(self, config: dict[str, Any]):
        self.config = config

    def process(
        self, filename: str, content: bytes, metadata: dict[str, Any]
    ) -> dict[str, Any]:
        suffix = Path(filename).suffix.lower()
        intent = str(metadata.get("intent") or self.config.get("intent") or "invoice").lower()
        if intent not in {"invoice", "image_caption"}:
            raise ValueError(f"Unsupported Vintern intent: {intent}")
        if suffix != ".pdf" and suffix not in _IMAGE_FORMATS:
            raise ValueError("Vintern intents support PDF and image files only.")
        if suffix == ".svg":
            from document_processing.document_processor import render_svg

            content = render_svg(content)
            suffix = ".png"

        python_path = resolve_vintern_python(self.config)
        if python_path is None:
            raise RuntimeError(
                "Vintern intent needs an isolated Python environment. Set "
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

        with tempfile.TemporaryDirectory(prefix=f"document-{intent}-") as temp_dir:
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
                    "prompt": _INVOICE_PROMPT if intent == "invoice" else _IMAGE_CAPTION_PROMPT,
                    "pages": [
                        {"page_number": page["page_number"], "image_path": page["image_path"]}
                        for page in pages
                    ],
                }, ensure_ascii=False),
                encoding="utf-8",
            )
            env = os.environ.copy()
            source_root = str(Path(__file__).resolve().parents[1])
            env["PYTHONPATH"] = os.pathsep.join(filter(None, [source_root, env.get("PYTHONPATH", "")]))
            timeout = int(
                self.config.get(
                    "vintern_timeout_seconds",
                    os.environ.get("DOCUMENT_PROCESSING_VINTERN_TIMEOUT_SECONDS", 1800),
                )
            )
            completed = subprocess.run(
                [str(python_path), "-m", "document_processing.vintern_worker",
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
                    f"Vintern {intent} processing failed in its isolated runtime. "
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
                page_number = int(page["page_number"])
                if intent == "invoice":
                    fields = _parse_fields(raw_response)
                    extracted_page = {"page_number": page_number, "fields": fields, "raw_response": raw_response, "review_required": True}
                    searchable_value = json.dumps(fields if fields is not None else {"raw_response": raw_response}, ensure_ascii=False)
                    layout_type = "text"
                else:
                    extracted_page = {"page_number": page_number, "caption": raw_response, "raw_response": raw_response, "review_required": True}
                    searchable_value = raw_response
                    layout_type = "figure_caption"
                extracted_pages.append(extracted_page)
                elements.append({
                    "text": searchable_value,
                    "element_type": "text",
                    "metadata": {
                        "page_number": page_number,
                        "element_type": "text",
                        "layout_type": layout_type,
                        "parser": f"vintern_{intent}",
                        "text_extraction_method": f"vintern_{intent}_extraction",
                        "review_required": True,
                    },
                })

            if not extracted_pages:
                raise RuntimeError(f"Vintern returned no {intent} page results.")

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
                f"{intent}_extraction": {
                    "model": model_id,
                    "status": "review_required",
                    "review_required": True,
                    "pages": extracted_pages,
                },
                "page_previews": page_previews,
                "page_sizes": page_sizes,
                "metadata": {
                    "pipeline_id": f"vintern_{intent}",
                    "parser_engine": f"vintern_{intent}",
                    "intent": intent,
                    f"{intent}_model": model_id,
                    f"{intent}_model_revision": worker_result.get("revision"),
                    f"{intent}_review_required": True,
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
