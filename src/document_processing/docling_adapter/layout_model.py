"""PaddleOCR PP-DocLayout_plus-L adapter for Docling's layout stage."""

from __future__ import annotations

import json
import logging
from typing import ClassVar, Sequence

from pydantic import Field

from docling.datamodel.accelerator_options import AcceleratorOptions
from docling.datamodel.base_models import Cluster, LayoutPrediction, Page
from docling.datamodel.document import ConversionResult
from docling.datamodel.pipeline_options import BaseLayoutOptions
from docling.models.base_layout_model import BaseLayoutModel
from docling.models.factories import get_layout_factory
from docling_core.types.doc import BoundingBox, CoordOrigin, DocItemLabel

_log = logging.getLogger(__name__)

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
    "paragraph_title": DocItemLabel.SECTION_HEADER,
    "section_header": DocItemLabel.SECTION_HEADER,
    "header": DocItemLabel.PAGE_HEADER,
    "page_header": DocItemLabel.PAGE_HEADER,
    "footer": DocItemLabel.PAGE_FOOTER,
    "page_footer": DocItemLabel.PAGE_FOOTER,
    "number": DocItemLabel.PAGE_FOOTER,
    "page_number": DocItemLabel.PAGE_FOOTER,
    "image": DocItemLabel.PICTURE,
    "figure": DocItemLabel.PICTURE,
    "seal": DocItemLabel.PICTURE,
    "chart": DocItemLabel.CHART,
    "formula": DocItemLabel.FORMULA,
    "caption": DocItemLabel.CAPTION,
    "figure_title": DocItemLabel.CAPTION,
    "table_title": DocItemLabel.CAPTION,
    "footnote": DocItemLabel.FOOTNOTE,
    "list": DocItemLabel.LIST_ITEM,
    "list_item": DocItemLabel.LIST_ITEM,
    "code": DocItemLabel.CODE,
    "checkbox_selected": DocItemLabel.CHECKBOX_SELECTED,
    "checkbox_unselected": DocItemLabel.CHECKBOX_UNSELECTED,
    "form": DocItemLabel.FORM,
    "key_value_region": DocItemLabel.KEY_VALUE_REGION,
    "handwritten_text": DocItemLabel.HANDWRITTEN_TEXT,
}


class PPDocLayoutOptions(BaseLayoutOptions):
    """Options for PaddleOCR's PP-DocLayout_plus-L model."""

    kind: ClassVar[str] = "paddle_doclayout_plus_l"
    score_threshold: float = Field(default=0.25, ge=0.0, le=1.0)


class PPDocLayoutModel(BaseLayoutModel):
    """Run PP-DocLayout_plus-L and convert detections into Docling clusters."""

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
                "PP-DocLayout_plus-L requires PaddleOCR and PaddlePaddle; install the document-processing image dependencies."
            ) from error

        requested_device = str(
            getattr(accelerator_options.device, "value", accelerator_options.device)
        ).lower()
        if requested_device.startswith("cuda"):
            if not paddle.is_compiled_with_cuda():
                raise RuntimeError(
                    "CUDA was requested for PP-DocLayout_plus-L, but this image has CPU-only PaddlePaddle."
                )
            device = "gpu:0"
        else:
            device = "cpu"

        self.options = options
        # PaddlePaddle 3.3.1 CPU oneDNN fails on this model's PIR attributes.
        self.model = LayoutDetection(
            model_name="PP-DocLayout_plus-L",
            device=device,
            threshold=options.score_threshold,
            enable_mkldnn=False,
        )

    @classmethod
    def get_options_type(cls) -> type[PPDocLayoutOptions]:
        return PPDocLayoutOptions

    def predict_layout(
        self,
        conv_res: ConversionResult,
        pages: Sequence[Page],
    ) -> Sequence[LayoutPrediction]:
        del conv_res
        import numpy as np

        predictions: list[LayoutPrediction] = []
        for page in pages:
            image = page.get_image(scale=1.0)
            if image is None or page.size is None:
                predictions.append(LayoutPrediction())
                continue

            # PaddleX accepts NumPy image inputs in OpenCV's BGR channel order.
            image_bgr = np.asarray(image.convert("RGB"))[:, :, ::-1].copy()
            result = next(iter(self.model.predict(
                input=image_bgr,
                batch_size=1,
                threshold=self.options.score_threshold,
                layout_nms=True,
            )), None)
            if result is None:
                predictions.append(LayoutPrediction())
                continue

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
                label = _LABELS.get(source_label)
                if label is None:
                    _log.warning(
                        "Unmapped PP-DocLayout_plus-L label %r; keeping region as text.",
                        source_label,
                    )
                    label = DocItemLabel.TEXT
                clusters.append(Cluster(
                    id=index,
                    label=label,
                    confidence=float(box.get("score", 0.0)),
                    bbox=BoundingBox(
                        l=max(0.0, min(x1 * scale_x, float(page.size.width))),
                        t=max(0.0, min(y1 * scale_y, float(page.size.height))),
                        r=max(0.0, min(x2 * scale_x, float(page.size.width))),
                        b=max(0.0, min(y2 * scale_y, float(page.size.height))),
                        coord_origin=CoordOrigin.TOPLEFT,
                    ),
                    cells=[],
                ))
            predictions.append(LayoutPrediction(clusters=clusters))
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
