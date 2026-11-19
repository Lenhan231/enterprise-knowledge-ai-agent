"""Normalize image formats for Docling and previews."""

from io import BytesIO
import math
import os
import re
import subprocess
import sys
import xml.etree.ElementTree as ET

from document_processing.formats import (
    MODERN_IMAGE_FORMATS, NORMALIZED_RASTER_FORMATS, matches_signature,
)
from document_processing.worker_runtime import SOURCE_ROOT


_MAX_FRAME_PIXELS = 16_000_000
_MAX_TOTAL_PIXELS = 32_000_000
_MAX_FRAMES = 50


def validate_svg(content: bytes) -> None:
    """Accept self-contained SVG input."""
    try:
        text = content.decode("utf-8-sig")
        if re.search(r"<!\s*(?:DOCTYPE|ENTITY)|<\?xml-stylesheet", text, re.IGNORECASE):
            raise ValueError("SVG document declarations are not supported")
        root = ET.fromstring(text)
    except (UnicodeError, ET.ParseError) as error:
        raise ValueError("File is not an SVG") from error
    if root.tag not in {"{http://www.w3.org/2000/svg}svg", "svg"}:
        raise ValueError("File is not an SVG")
    for node in root.iter():
        if node.tag.rsplit("}", 1)[-1] in {"script", "style", "foreignObject"}:
            raise ValueError("SVG scripts, stylesheets and foreign objects are not supported")
        for name, value in node.attrib.items():
            attribute = name.rsplit("}", 1)[-1].lower()
            if attribute.startswith("on"):
                raise ValueError("SVG scripts, stylesheets and foreign objects are not supported")
            if attribute == "base" or (attribute == "href" and not value.strip().startswith("#")):
                raise ValueError("SVG external references are not supported")
            if re.search(r"url\s*\(\s*['\"]?(?!#)", value, re.IGNORECASE):
                raise ValueError("SVG external references are not supported")


def render_svg(content: bytes) -> bytes:
    """Render a self-contained SVG as PNG."""
    validate_svg(content)
    try:
        import fitz
        with fitz.open(stream=content, filetype="svg") as document:
            page = document[0]
            width, height = page.rect.width, page.rect.height
            if not all(math.isfinite(v) and 0 < v <= 10000 for v in (width, height)):
                raise ValueError("SVG dimensions are invalid")
            scale = min(2.0, 4096 / width, 4096 / height)
            return page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False).tobytes("png")
    except ValueError:
        raise
    except Exception as error:
        raise ValueError("Could not render SVG") from error


def _normalize_raster(content: bytes, suffix: str, *, single_frame: bool = False) -> tuple[bytes, str]:
    from PIL import Image, ImageOps

    expected_format = NORMALIZED_RASTER_FORMATS[suffix]
    if expected_format == "HEIF":
        from pillow_heif import register_heif_opener

        register_heif_opener(thumbnails=False, depth_images=False)

    try:
        with Image.open(BytesIO(content), formats=[expected_format]) as image:
            count = getattr(image, "n_frames", 1)
            if single_frame and count != 1:
                raise ValueError("Expected a single-frame WebP image")
            if count > _MAX_FRAMES:
                raise ValueError(f"Image exceeds the {_MAX_FRAMES}-frame limit")
            frames = []
            pixels = 0
            for index in range(count):
                image.seek(index)
                frame_pixels = image.width * image.height
                pixels += frame_pixels
                if frame_pixels > _MAX_FRAME_PIXELS or pixels > _MAX_TOTAL_PIXELS:
                    raise ValueError("Image exceeds the decoded pixel limit")
                rgba = ImageOps.exif_transpose(image).convert("RGBA")
                frame = Image.new("RGB", rgba.size, "white")
                frame.paste(rgba, mask=rgba.getchannel("A"))
                frames.append(frame)
            output = BytesIO()
            if count == 1:
                frames[0].save(output, format="PNG")
                return output.getvalue(), ".png"
            frames[0].save(output, format="TIFF", save_all=True, append_images=frames[1:],
                           compression="tiff_adobe_deflate")
            return output.getvalue(), ".tiff"
    except ValueError:
        raise
    except (EOFError, OSError, SyntaxError, Image.DecompressionBombError) as error:
        raise ValueError(f"Could not open {expected_format} image") from error


def render_webp(content: bytes) -> bytes:
    """Keep the single-frame WebP input used by invoice and caption uploads."""
    png, _ = _normalize_raster(content, ".webp", single_frame=True)
    return png


def normalize_image(content: bytes, suffix: str) -> tuple[bytes, str]:
    """Return image bytes and the extension consumed by Docling and PyMuPDF."""
    if suffix == ".svg":
        return render_svg(content), ".png"
    if suffix not in NORMALIZED_RASTER_FORMATS:
        return content, suffix
    if not matches_signature(content, suffix):
        raise ValueError(f"File content does not match {suffix}")
    interpreter = os.getenv("DOCUMENT_PROCESSING_IMAGE_PYTHON")
    if suffix not in MODERN_IMAGE_FORMATS or not interpreter:
        return _normalize_raster(content, suffix)

    try:
        converted = subprocess.run(
            [interpreter, "-m", "document_processing.image_input", suffix],
            input=content, capture_output=True, env={"PYTHONPATH": str(SOURCE_ROOT)}, timeout=60,
        )
    except subprocess.TimeoutExpired as error:
        raise ValueError("Image decoding timed out") from error
    except OSError as error:
        raise RuntimeError("Image decoder could not start") from error
    if converted.returncode == 2:
        raise ValueError(converted.stderr.decode("utf-8", errors="replace").strip())
    if converted.returncode:
        raise RuntimeError("Image decoder exited unexpectedly")
    for output_suffix in (".png", ".tiff"):
        if matches_signature(converted.stdout, output_suffix):
            return converted.stdout, output_suffix
    raise RuntimeError("Image decoder returned an invalid format")


if __name__ == "__main__":
    try:
        payload, _ = _normalize_raster(sys.stdin.buffer.read(), sys.argv[1])
    except ValueError as error:
        print(error, file=sys.stderr)
        sys.exit(2)
    sys.stdout.buffer.write(payload)
