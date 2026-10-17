"""PDF page OCR, orientation recovery, and OCR text helpers."""

from __future__ import annotations

import logging
import math
import re
import statistics
import subprocess
import unicodedata
from difflib import SequenceMatcher
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import fitz
import numpy as np

from core.document_processing.scanned.ocr.image_ocr import (
    exclude_table_words,
    looks_like_numeric_table,
    recognize_image_text,
    recognize_image_words,
    words_to_text,
)

logger = logging.getLogger(__name__)


class PDFOCRProcessor:
    """Run Tesseract and prepare page OCR text and word boxes."""

    def __init__(self, config: dict[str, Any], tessdata_dir: Path | None, available: bool):
        self.config = config
        self.tesseract_data_dir = tessdata_dir
        self.ocr_available = available

    @staticmethod
    def _needs_ocr(page, native_text: str) -> bool:
        """OCR sparse pages and mixed pages dominated by a large raster image."""
        if len(native_text) < 50:
            return True
        if len(native_text) >= 500:
            return False

        image_area = sum(
            fitz.Rect(image["bbox"]).intersect(page.rect).get_area()
            for image in page.get_image_info()
        )
        return image_area / max(page.rect.get_area(), 1) >= 0.25

    @staticmethod
    def _embedded_image_regions(page):
        """Return a small set of large raster regions on otherwise text-rich pages."""
        regions = []
        seen = set()
        page_area = max(page.rect.get_area(), 1)
        for image in page.get_image_info():
            rect = fitz.Rect(image.get("bbox", (0, 0, 0, 0))).intersect(page.rect)
            key = tuple(round(value, 1) for value in rect)
            if (
                key in seen
                or rect.width < 96
                or rect.height < 48
                or rect.get_area() / page_area < 0.10
            ):
                continue
            seen.add(key)
            regions.append(rect)
        # ponytail: OCR only the two largest embedded images per text-rich page;
        # expand after a labeled fixture shows that smaller images carry needed text.
        return sorted(regions, key=lambda rect: rect.get_area(), reverse=True)[:2]

    @staticmethod
    def _ocr_words_to_text(words) -> str:
        return words_to_text(words)

    @staticmethod
    def _exclude_table_words(words, tables):
        return exclude_table_words(words, tables)

    @staticmethod
    def _remove_ocr_duplicates(native_text: str, ocr_text: str) -> str:
        """Drop OCR lines and sentences already represented by native PDF text."""
        def fragments(text: str) -> list[tuple[str, str]]:
            result = []
            for line in text.splitlines() or [text]:
                for fragment in re.split(r"(?<=[.!?])\s+", " ".join(line.split())):
                    normalized = "".join(
                        character for character in unicodedata.normalize("NFD", fragment.casefold())
                        if unicodedata.category(character) != "Mn" and character.isalnum()
                    )
                    if normalized:
                        result.append((fragment, normalized))
            return result

        native_fragments = fragments(native_text)
        native_exact = {normalized for _, normalized in native_fragments if len(normalized) >= 8}
        if not native_fragments:
            return ocr_text

        kept = []
        for sentence, normalized in fragments(ocr_text):
            duplicate = normalized in native_exact or (len(normalized) >= 30 and any(
                min(len(normalized), len(native)) / max(len(normalized), len(native)) >= 0.65
                and SequenceMatcher(None, normalized, native, autojunk=False).ratio() >= 0.82
                for _, native in native_fragments
            ))
            if not duplicate:
                kept.append(sentence)
        return " ".join(kept)

    @staticmethod
    def _has_meaningful_ocr_additions(native_text: str, ocr_text: str) -> bool:
        """Ignore OCR noise when little of the OCR token stream is new to native text."""
        pattern = re.compile(r"(?u)\b(?:\d{2,}(?:[.,]\d+)*|[^\W\d_][\w-]{2,})\b")
        native_tokens = set(pattern.findall(native_text.casefold()))
        ocr_tokens = pattern.findall(ocr_text.casefold())
        new_tokens = [token for token in ocr_tokens if token not in native_tokens]
        return len(set(new_tokens)) >= 3 and len(new_tokens) / max(len(ocr_tokens), 1) >= 0.08

    @staticmethod
    def _looks_like_numeric_table(text: str) -> bool:
        return looks_like_numeric_table(text)

    def _ocr_table_metadata(
        self, orientation_correction_degrees: int = 0,
        deskew_correction_degrees: float = 0.0,
        mean_word_confidence: Optional[float] = None,
    ) -> Dict[str, Any]:
        metadata = {
            "engine": "tesseract",
            "language": self.config.get("ocr_language", "vie+eng"),
            "table_psm": self.config["tesseract_table_psm"],
            "render_scale": self.config["ocr_table_render_scale"],
        }
        if orientation_correction_degrees:
            metadata["orientation_correction_degrees"] = orientation_correction_degrees
        if deskew_correction_degrees:
            metadata["deskew_correction_degrees"] = deskew_correction_degrees
        if mean_word_confidence is not None:
            metadata["mean_word_confidence"] = mean_word_confidence
        return metadata

    def _detect_ocr_rotation(self, pixmap) -> int:
        """Return a confident Tesseract OSD quarter-turn correction, if any."""
        if not self.config.get("ocr_orientation_detection", True) or not self.ocr_available:
            return 0
        try:
            output = recognize_image_text(
                pixmap.tobytes("png"), self.config, page_segmentation_mode=0,
                language="osd", timeout=30, tessdata_dir=self.tesseract_data_dir,
                include_config=False,
            )
        except (OSError, subprocess.SubprocessError) as error:
            logger.debug("Tesseract orientation detection unavailable: %s", error)
            return 0

        rotation = re.search(r"^Rotate:\s*(\d+)\s*$", output, re.MULTILINE)
        confidence = re.search(r"^Orientation confidence:\s*([\d.]+)\s*$", output, re.MULTILINE)
        if not rotation or not confidence:
            return 0
        degrees = int(rotation.group(1))
        if degrees not in {90, 180, 270} or float(confidence.group(1)) < 2.5:
            return 0
        return degrees

    def _estimate_ocr_skew(self, pixmap) -> float:
        """Estimate small page skew from horizontal text-line projections."""
        from PIL import Image

        try:
            with Image.open(BytesIO(pixmap.tobytes("png"))) as source:
                image = source.convert("L")
                image.thumbnail((420, 600), Image.Resampling.LANCZOS)

            def projection_score(angle: float) -> float:
                rotated = image.rotate(
                    angle, resample=Image.Resampling.BILINEAR,
                    expand=False, fillcolor=255,
                )
                pixels = np.asarray(rotated, dtype=np.uint8)
                row_ink = np.count_nonzero(pixels < 190, axis=1).astype(np.float64)
                return float(np.square(row_ink - row_ink.mean()).sum())

            baseline = projection_score(0.0)
            if baseline <= 0:
                return 0.0
            coarse = max(
                ((projection_score(float(angle)), float(angle))
                 for angle in np.arange(-6.0, 6.01, 0.5)),
                key=lambda item: item[0],
            )[1]
            best_score, correction = max(
                ((projection_score(float(angle)), float(angle))
                 for angle in np.arange(coarse - 0.5, coarse + 0.501, 0.1)),
                key=lambda item: item[0],
            )
            if abs(correction) < 0.5 or best_score < baseline * 1.1:
                return 0.0
            return round(correction, 1)
        except (OSError, ValueError):
            return 0.0

    @staticmethod
    def _rotate_ocr_pixmap_by_angle(pixmap, correction_degrees: float):
        """Apply a small counterclockwise correction without changing raster bounds."""
        from PIL import Image

        with Image.open(BytesIO(pixmap.tobytes("png"))) as image:
            corrected = image.rotate(
                correction_degrees, resample=Image.Resampling.BICUBIC,
                expand=False, fillcolor=(255, 255, 255),
            ).convert("RGB")
            output = BytesIO()
            corrected.save(output, format="PNG")
        return fitz.Pixmap(output.getvalue())

    @staticmethod
    def _rotate_ocr_pixmap(pixmap, clockwise_degrees: int):
        """Rotate a rendered page to the orientation reported by Tesseract OSD."""
        from PIL import Image

        with Image.open(BytesIO(pixmap.tobytes("png"))) as image:
            upright = image.rotate(-clockwise_degrees, expand=True).convert("RGB")
            output = BytesIO()
            upright.save(output, format="PNG")
        return fitz.Pixmap(output.getvalue())

    def _recover_sparse_landscape_orientation(self, page, pixmap, ocr_text: str):
        """Try sideways candidates only when OSD and upright OCR yield little text."""
        if (
            not self.config.get("ocr_orientation_detection", True)
            or not self.ocr_available
            or pixmap.width <= pixmap.height
            or sum(character.isalnum() for character in ocr_text) >= 40
        ):
            return 0, pixmap, ocr_text
        from PIL import Image, ImageStat

        try:
            with Image.open(BytesIO(pixmap.tobytes("png"))) as image:
                thumbnail = image.convert("L")
                thumbnail.thumbnail((48, 48))
                if ImageStat.Stat(thumbnail).stddev[0] <= 1.5:
                    return 0, pixmap, ocr_text
        except (OSError, ValueError) as error:
            logger.debug("Could not inspect sparse OCR page for rotation: %s", error)
            return 0, pixmap, ocr_text

        def score(text):
            return (
                int(self._looks_like_numeric_table(text)),
                sum(character.isalpha() for character in text),
                sum(character.isdigit() for character in text),
            )

        best_score = score(ocr_text)
        best = (0, pixmap, ocr_text)
        for degrees in (90, 270):
            try:
                candidate_pixmap = self._rotate_ocr_pixmap(pixmap, degrees)
            except (OSError, ValueError) as error:
                logger.debug("Could not try %d-degree OCR rotation: %s", degrees, error)
                continue
            candidate_text = self._ocr_page(page, candidate_pixmap, timeout=30).strip()
            candidate_score = score(candidate_text)
            if candidate_score > best_score and (
                self._looks_like_numeric_table(candidate_text)
                or sum(character.isalpha() for character in candidate_text) >= 24
            ):
                best_score = candidate_score
                best = (degrees, candidate_pixmap, candidate_text)
        return best

    @staticmethod
    def _oriented_page_rect(page_rect, clockwise_degrees: int):
        if clockwise_degrees in {90, 270}:
            return fitz.Rect(0, 0, page_rect.height, page_rect.width)
        return fitz.Rect(0, 0, page_rect.width, page_rect.height)

    def _ocr_page(self, page, pixmap=None, *, timeout: int = 90) -> str:
        """
        Perform OCR on a PDF page.

        Args:
            page: PyMuPDF page object

        Returns:
            Extracted text from OCR
        """
        if not self.ocr_available:
            return ""

        try:
            if pixmap is None:
                render_scale = self.config["ocr_render_scale"]
                pixmap = page.get_pixmap(
                    matrix=fitz.Matrix(render_scale, render_scale), alpha=False,
                )
            return recognize_image_text(
                pixmap.tobytes("png"), self.config,
                page_segmentation_mode=self.config["tesseract_psm"],
                timeout=timeout, tessdata_dir=self.tesseract_data_dir,
            )
        except (OSError, subprocess.SubprocessError) as e:
            logger.error("OCR error: %s", str(e))
            return ""

    def _ocr_page_words(
        self, page, pixmap=None, *, page_rect=None,
    ) -> List[Tuple[float, float, float, float, str, int, int, int, float]]:
        """Return Tesseract word boxes in PDF points for scanned-table layout."""
        if not self.ocr_available:
            return []
        if pixmap is None:
            render_scale = self.config["ocr_render_scale"]
            pixmap = page.get_pixmap(
                matrix=fitz.Matrix(render_scale, render_scale), alpha=False,
            )
        coordinate_rect = page_rect or page.rect
        return recognize_image_words(
            pixmap.tobytes("png"), self.config,
            page_segmentation_mode=self.config["tesseract_table_psm"],
            image_size=(pixmap.width, pixmap.height),
            coordinate_rect=tuple(coordinate_rect),
            tessdata_dir=self.tesseract_data_dir,
        )
