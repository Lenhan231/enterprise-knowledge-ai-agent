"""PaddleOCR PP-DocLayoutV3 adapter for Docling's layout stage."""

from __future__ import annotations

import json
import logging
import time
from typing import ClassVar, Sequence

from pydantic import Field

from docling.datamodel.accelerator_options import AcceleratorOptions
from docling.datamodel.base_models import Cluster, LayoutPrediction, Page
from docling.datamodel.document import ConversionResult
from docling.datamodel.pipeline_options import BaseLayoutOptions
from docling.models.base_layout_model import BaseLayoutModel
from docling.models.factories import get_layout_factory
from docling_core.types.doc import BoundingBox, CoordOrigin, DocItemLabel
from .orientation import (
    detect_paddle_orientation,
    OrientedPageBackend,
)

_log = logging.getLogger(__name__)

# PP-DocLayoutV3 inference.yml label_list.
PADDLE_LAYOUT_LABELS = frozenset({
    "abstract", "algorithm", "aside_text", "chart", "content", "display_formula",
    "doc_title", "figure_title", "footer", "footer_image", "footnote",
    "formula_number", "header", "header_image", "image", "inline_formula",
    "number", "paragraph_title", "reference", "reference_content", "seal",
    "table", "text", "vertical_text", "vision_footnote",
})

_LABELS = {
    "table": DocItemLabel.TABLE,
    "document_index": DocItemLabel.DOCUMENT_INDEX,
    "text": DocItemLabel.TEXT,
    "content": DocItemLabel.TEXT,
    "abstract": DocItemLabel.TEXT,
    "aside_text": DocItemLabel.TEXT,
    "reference": DocItemLabel.TEXT,
    "algorithm": DocItemLabel.TEXT,
    "paragraph": DocItemLabel.TEXT,
    "doc_title": DocItemLabel.TITLE,
    "title": DocItemLabel.TITLE,
    "title_table": DocItemLabel.TITLE,
    "table_title": DocItemLabel.CAPTION,
    "diagram_title": DocItemLabel.CAPTION,
    "paragraph_title": DocItemLabel.SECTION_HEADER,
    "section_header": DocItemLabel.SECTION_HEADER,
    "header": DocItemLabel.PAGE_HEADER,
    "page_header": DocItemLabel.PAGE_HEADER,
    "footer": DocItemLabel.PAGE_FOOTER,
    "page_footer": DocItemLabel.PAGE_FOOTER,
    "number": DocItemLabel.PAGE_FOOTER,
    "page_number": DocItemLabel.PAGE_FOOTER,
    "image": DocItemLabel.PICTURE,
    "header_image": DocItemLabel.PICTURE,
    "footer_image": DocItemLabel.PICTURE,
    "figure": DocItemLabel.PICTURE,
    "seal": DocItemLabel.PICTURE,
    # Docling 2.129's layout postprocessor/page assembler do not support CHART.
    # Keep chart detections as picture clusters and retain their source boxes below.
    "chart": DocItemLabel.PICTURE,
    "formula": DocItemLabel.FORMULA,
    "display_formula": DocItemLabel.FORMULA,
    "inline_formula": DocItemLabel.FORMULA,
    "formula_number": DocItemLabel.TEXT,
    "caption": DocItemLabel.CAPTION,
    "figure_title": DocItemLabel.CAPTION,
    "footnote": DocItemLabel.FOOTNOTE,
    "vision_footnote": DocItemLabel.FOOTNOTE,
    "vertical_text": DocItemLabel.TEXT,
    "list": DocItemLabel.LIST_ITEM,
    "list_item": DocItemLabel.LIST_ITEM,
    "code": DocItemLabel.CODE,
    "checkbox_selected": DocItemLabel.CHECKBOX_SELECTED,
    "checkbox_unselected": DocItemLabel.CHECKBOX_UNSELECTED,
    "form": DocItemLabel.FORM,
    "key_value_region": DocItemLabel.KEY_VALUE_REGION,
    "handwritten_text": DocItemLabel.HANDWRITTEN_TEXT,
    "reference_content": DocItemLabel.TEXT,
}


class PPDocLayoutOptions(BaseLayoutOptions):
    """Options for PaddleOCR's PP-DocLayoutV3 model."""

    kind: ClassVar[str] = "paddle_doclayout_v3"
    score_threshold: float = Field(default=0.25, ge=0.0, le=1.0)
    cpu_threads: int = Field(default=2, ge=1, le=16)


class PPDocLayoutModel(BaseLayoutModel):
    """Run PP-DocLayoutV3 and convert detections into Docling clusters."""

    def __init__(
        self,
        *,
        options: PPDocLayoutOptions,
        accelerator_options: AcceleratorOptions,
        **_: object,
    ) -> None:
        try:
            import paddle
            from paddleocr import LayoutDetection
        except ImportError as error:
            raise RuntimeError(
                "PP-DocLayoutV3 requires PaddleOCR and PaddlePaddle; install the document-processing image dependencies."
            ) from error

        requested_device = str(
            getattr(accelerator_options.device, "value", accelerator_options.device)
        ).lower()
        if requested_device.startswith("cuda"):
            if not paddle.is_compiled_with_cuda():
                _log.warning(
                    "CUDA requested for PP-DocLayoutV3, but PaddlePaddle is CPU-only; "
                    "running layout detection on CPU. Other Docling stages may still use CUDA."
                )
                device = "cpu"
            else:
                device = "gpu:0"
        else:
            device = "cpu"

        self.options = options
        self.chart_regions: list[dict[str, object]] = []
        self.layout_detections: list[dict[str, object]] = []
        self.page_orientation_corrections: dict[int, int] = {}
        self.current_reference_id: str | None = None
        # PaddlePaddle 3.3.1 CPU oneDNN fails on this model's PIR attributes.
        self.model = LayoutDetection(
            model_name="PP-DocLayoutV3",
            device=device,
            threshold=options.score_threshold,
            enable_mkldnn=False,
            cpu_threads=options.cpu_threads,
        )

    @classmethod
    def get_options_type(cls) -> type[PPDocLayoutOptions]:
        return PPDocLayoutOptions

    def warmup(self) -> None:
        """Run one forward pass so the first invoice does not pay model cold-start cost."""
        import numpy as np

        image = np.full((800, 800, 3), 255, dtype=np.uint8)
        started = time.perf_counter()
        next(iter(self.model.predict(
            input=image,
            batch_size=1,
            threshold=self.options.score_threshold,
            layout_nms=True,
        )), None)
        _log.info("DOCLING_LAYOUT_WARMUP %s", json.dumps({
            "elapsed_ms": round((time.perf_counter() - started) * 1000, 2),
        }, separators=(",", ":")))

    def predict_layout(
        self,
        conv_res: ConversionResult,
        pages: Sequence[Page],
    ) -> Sequence[LayoutPrediction]:
        del conv_res
        import numpy as np

        if pages and int(pages[0].page_no) == 1:
            self.chart_regions.clear()
            self.layout_detections.clear()
            self.page_orientation_corrections.clear()

        predictions: list[LayoutPrediction] = []
        for page in pages:
            page_started = time.perf_counter()
            timings_ms: dict[str, float] = {}
            stage_started = time.perf_counter()
            image = page.get_image(scale=1.0)
            timings_ms["page_render"] = round((time.perf_counter() - stage_started) * 1000, 2)
            if image is None or page.size is None:
                predictions.append(LayoutPrediction())
                _log.info("DOCLING_LAYOUT_COMPONENT_TIMING %s", json.dumps({
                    "invoice_id": self.current_reference_id,
                    "page_number": int(page.page_no),
                    "box_count": 0,
                    "timings_ms": {
                        **timings_ms,
                        "total": round((time.perf_counter() - page_started) * 1000, 2),
                    },
                }, separators=(",", ":")))
                continue

            stage_started = time.perf_counter()
            try:
                correction, _, _ = detect_paddle_orientation(image)
            except Exception:
                # Orientation classification is an optional correction stage.
                # If Paddle fails, keep the source orientation and continue
                # layout detection so one bad classifier call cannot drop a page.
                _log.warning(
                    "Page orientation detection failed for page %s; "
                    "continuing without rotation correction.",
                    page.page_no,
                    exc_info=True,
                )
                correction = 0
            timings_ms["page_orientation"] = round((time.perf_counter() - stage_started) * 1000, 2)
            self.page_orientation_corrections[int(page.page_no)] = correction
            if correction:
                stage_started = time.perf_counter()
                page._backend = OrientedPageBackend(page._backend, correction)
                page.size = page._backend.get_size()
                page._image_cache.clear()
                image = page.get_image(scale=1.0)
                timings_ms["page_rotation"] = round((time.perf_counter() - stage_started) * 1000, 2)
            layout_image = image
            # PaddleX accepts NumPy image inputs in OpenCV's BGR channel order.
            stage_started = time.perf_counter()
            image_bgr = np.asarray(layout_image.convert("RGB"))[:, :, ::-1].copy()
            timings_ms["model_input_prepare"] = round((time.perf_counter() - stage_started) * 1000, 2)
            stage_started = time.perf_counter()
            result = next(iter(self.model.predict(
                input=image_bgr,
                batch_size=1,
                threshold=self.options.score_threshold,
                layout_nms=True,
            )), None)
            timings_ms["layout_model_inference"] = round((time.perf_counter() - stage_started) * 1000, 2)
            if result is None:
                predictions.append(LayoutPrediction())
                _log.info("DOCLING_LAYOUT_COMPONENT_TIMING %s", json.dumps({
                    "invoice_id": self.current_reference_id,
                    "page_number": int(page.page_no),
                    "box_count": 0,
                    "timings_ms": {
                        **timings_ms,
                        "total": round((time.perf_counter() - page_started) * 1000, 2),
                    },
                }, separators=(",", ":")))
                continue

            stage_started = time.perf_counter()
            payload = result.json
            if isinstance(payload, str):
                payload = json.loads(payload)
            raw = payload.get("res", payload)
            image_width, image_height = image.size
            scale_x = float(page.size.width) / image_width
            scale_y = float(page.size.height) / image_height
            clusters = []
            for index, box in enumerate(raw.get("boxes", [])):
                coordinates = box.get("coordinate", [])
                if len(coordinates) != 4:
                    continue
                x1, y1, x2, y2 = map(float, coordinates)
                source_label = str(box.get("label", "text")).strip().lower()
                score = float(box.get("score", 0.0))
                label = _LABELS.get(source_label)
                if label is None:
                    _log.warning(
                        "Unmapped PP-DocLayoutV3 label %r; keeping region as text.",
                        source_label,
                    )
                    label = DocItemLabel.TEXT
                bbox = BoundingBox(
                    l=max(0.0, min(x1 * scale_x, float(page.size.width))),
                    t=max(0.0, min(y1 * scale_y, float(page.size.height))),
                    r=max(0.0, min(x2 * scale_x, float(page.size.width))),
                    b=max(0.0, min(y2 * scale_y, float(page.size.height))),
                    coord_origin=CoordOrigin.TOPLEFT,
                )
                self.layout_detections.append({
                    "page_number": int(page.page_no),
                    "label": source_label,
                    "score": score,
                    "bbox": [bbox.l, bbox.t, bbox.r, bbox.b],
                    "bbox_coordinate_system": "docling_page_coordinate",
                    "bbox_coordinate_origin": "TOPLEFT",
                })
                if source_label == "chart":
                    self.chart_regions.append({
                        "page_no": page.page_no,
                        "bbox": (bbox.l, bbox.t, bbox.r, bbox.b),
                    })
                clusters.append(Cluster(
                    id=index,
                    label=label,
                    confidence=score,
                    bbox=bbox,
                    cells=[],
                ))
            predictions.append(LayoutPrediction(clusters=clusters))
            timings_ms["detection_mapping"] = round((time.perf_counter() - stage_started) * 1000, 2)
            timings_ms["total"] = round((time.perf_counter() - page_started) * 1000, 2)
            _log.info("DOCLING_LAYOUT_COMPONENT_TIMING %s", json.dumps({
                "invoice_id": self.current_reference_id,
                "page_number": int(page.page_no),
                "box_count": len(raw.get("boxes", [])),
                "timings_ms": timings_ms,
            }, separators=(",", ":")))
        return predictions


def register_pp_doclayout() -> None:
    """Register this in-process model without enabling third-party plugins."""
    factory = get_layout_factory(allow_external_plugins=False)
    if PPDocLayoutOptions not in factory.classes:
        factory.register(
            PPDocLayoutModel,
            plugin_name="document_processing",
            plugin_module_name=__name__,
        )
