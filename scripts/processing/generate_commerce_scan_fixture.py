#!/usr/bin/env python3
"""Create a degraded image-only copy of the explicitly synthetic Commerce OCR fixture."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path
import random

import fitz
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageOps


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "data/evaluation/ocr/commerce_synthetic_policy_scan_demo.pdf"
OUTPUT = ROOT / "data/evaluation/ocr/commerce_synthetic_degraded_scan_demo.pdf"
RENDER_SCALE = 2.5
NOISE_SEED = 20261004


def main() -> None:
    source = fitz.open(SOURCE)
    output = fitz.open()
    noise = random.Random(NOISE_SEED)
    for index, page in enumerate(source):
        pixmap = page.get_pixmap(matrix=fitz.Matrix(RENDER_SCALE, RENDER_SCALE), alpha=False)
        image = Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples)
        image = ImageOps.grayscale(image)
        image = ImageEnhance.Contrast(image).enhance(0.78)
        image = ImageEnhance.Brightness(image).enhance(1.05)
        image = image.filter(ImageFilter.GaussianBlur(radius=0.28))
        # Mimic a slightly skewed, low-contrast office scan with light sensor noise.
        image = image.rotate(-0.65 if index == 0 else 0.85, resample=Image.Resampling.BICUBIC,
                             expand=False, fillcolor=248)
        speckles = ImageDraw.Draw(image)
        for _ in range(360):
            x = noise.randrange(image.width)
            y = noise.randrange(image.height)
            speckles.point((x, y), fill=noise.choice((175, 205, 230)))
        encoded = BytesIO()
        image.save(encoded, format="JPEG", quality=78, optimize=True)
        output_page = output.new_page(width=page.rect.width, height=page.rect.height)
        output_page.insert_image(output_page.rect, stream=encoded.getvalue())
    output.set_metadata({
        "title": "Synthetic degraded scan for OCR pipeline testing",
        "subject": "Invented test-only content; not company policy or business evidence",
        "creator": "generate_commerce_scan_fixture.py",
    })
    output.save(OUTPUT, garbage=4, deflate=True, no_new_id=True)
    print(f"created {OUTPUT.relative_to(ROOT)} ({OUTPUT.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
