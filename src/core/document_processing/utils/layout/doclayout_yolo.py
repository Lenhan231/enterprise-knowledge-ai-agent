"""Optional DocLayout-YOLO layout detections for isolated Upload Test runs."""

from __future__ import annotations

import hashlib
from io import BytesIO

MODEL_REPO = "juliozhao/DocLayout-YOLO-DocStructBench"
MODEL_REVISION = "8c3299a30b8ff29a1503c4431b035b93220f7b11"
MODEL_FILENAME = "doclayout_yolo_docstructbench_imgsz1024.pt"
MODEL_SHA256 = "9a2ee0220fe3d9ad31b47e1d9f1282f46959a54e4618fce9cffcc9715b8286e2"
CLASS_MAP = {
    "title": "title",
    "plain text": "text",
    "figure": "figure",
    "table": "table",
    "formula": "formula",
    "isolate_formula": "formula",
    "signature": "signature",
}


def detect_layout(page_previews: list[bytes], *, image_size: int, threshold: float) -> list[dict]:
    """Return normalized page-local boxes; this does not perform OCR."""
    import torch
    from PIL import Image
    from doclayout_yolo import YOLOv10
    from huggingface_hub import hf_hub_download

    checkpoint = hf_hub_download(
        repo_id=MODEL_REPO,
        filename=MODEL_FILENAME,
        revision=MODEL_REVISION,
    )
    digest = hashlib.sha256()
    with open(checkpoint, "rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    if digest.hexdigest() != MODEL_SHA256:
        raise RuntimeError("Downloaded DocLayout-YOLO checkpoint failed SHA-256 verification")

    device = "cuda:0" if torch.cuda.is_available() else "cpu"
    detector = YOLOv10(checkpoint)
    pages = []
    for page_number, preview in enumerate(page_previews, start=1):
        with Image.open(BytesIO(preview)) as image:
            image = image.convert("RGB")
            width, height = image.size
            result = detector.predict(
                image,
                imgsz=image_size,
                conf=threshold,
                iou=0.7,
                device=device,
                verbose=False,
            )[0]
        regions = []
        if result.boxes is not None:
            for box, class_id, score in zip(
                result.boxes.xyxy.tolist(),
                result.boxes.cls.tolist(),
                result.boxes.conf.tolist(),
            ):
                label = str(result.names[int(class_id)]).casefold()
                mapped_label = CLASS_MAP.get(label)
                if mapped_label:
                    x1, y1, x2, y2 = map(float, box)
                    regions.append({
                        "class": mapped_label,
                        "bbox": [x1 / width, y1 / height, x2 / width, y2 / height],
                        "score": float(score),
                    })
        pages.append({"page_number": page_number, "width": width, "height": height, "regions": regions})
    return pages
