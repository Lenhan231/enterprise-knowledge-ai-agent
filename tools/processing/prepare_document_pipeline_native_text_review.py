"""Build a prediction-blind review packet for native-text pilot references."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import fitz

from prepare_document_pipeline_human_review import render_pdf, write_review_page


ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "artifacts/evaluation/document-pipelines"
MANIFEST = BASE / "pilot-v1/manifest.json"
OUTPUT = BASE / "human-review/native-text-pilot-v2"


def native_text(pdf_path: Path) -> str:
    with fitz.open(pdf_path) as document:
        if len(document) != 1:
            raise ValueError(f"Expected one-page PDF, got {len(document)}: {pdf_path}")
        return document[0].get_text("text")


def build(manifest_path: Path, output: Path) -> int:
    if output.exists():
        raise FileExistsError(f"Refusing to overwrite review packet: {output}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    items = []
    for page in manifest["pages"]:
        pdf_path = manifest_path.parent / page["input_pdf"]
        image = f"images/{page['id']}.jpg"
        render_pdf(pdf_path, output / image)
        items.append({
            "id": page["id"],
            "split": page.get("source_type", "unknown"),
            "dataset_id": manifest["dataset_id"],
            "image": image,
            "reviewed_source_type": page.get("source_type", "unknown"),
            "reviewed_native_text": native_text(pdf_path),
        })
    write_review_page(
        output / "review.html",
        "Native PDF text and source-type review",
        "native-text",
        items,
        [
            ("reviewed_source_type", "Verified type: born_digital, mixed, physical_scan, or image_only"),
            (
                "reviewed_native_text",
                "Correct transcript to visible reading order; keep table text row-major",
            ),
        ],
    )
    return len(items)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=MANIFEST)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    count = build(args.manifest, args.output)
    print(json.dumps({"status": "review_packet_created", "pages": count, "output": str(args.output)}))


if __name__ == "__main__":
    main()
