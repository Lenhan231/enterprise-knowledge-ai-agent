"""Create a visual review queue from PP-StructureV3 layout proposals."""

from __future__ import annotations

import csv
import argparse
import json
import hashlib
from collections import Counter
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "artifacts/evaluation/document-pipelines"
MANIFEST = BASE / "layout/exploratory/manifest.json"
RAW = BASE / "results/layout-200-pages-v1/pp-structurev3/layout-200-pages-v1/raw_pages"
OUTPUT = BASE / "layout/exploratory-review"
COLORS = {"title": "red", "text": "dodgerblue", "table": "limegreen", "figure": "magenta"}


def category(label: str) -> str | None:
    if label in {"doc_title", "paragraph_title", "table_title", "figure_title", "chart_title"}:
        return "title"
    if label in {"text", "header", "footer", "number", "aside_text", "abstract", "footnote"}:
        return "text"
    if label == "table":
        return "table"
    if label in {"image", "chart", "header_image", "footer_image"}:
        return "figure"
    return None


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=MANIFEST)
    parser.add_argument("--raw-root", type=Path, default=RAW, help="Directory containing PP page JSON files")
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(f"Refusing to overwrite {args.output}")
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    pages = manifest["pages"]
    args.output.mkdir(parents=True)
    (args.output / "overlays").mkdir()
    queue = []
    proposals = []
    for start in range(0, len(pages), 16):
        batch = pages[start : start + 16]
        sheet = Image.new("RGB", (1440, 1720), "white")
        draw_sheet = ImageDraw.Draw(sheet)
        for index, page in enumerate(batch):
            raw_path = args.raw_root / f"{page['id']}-page-001.json"
            payload = json.loads(raw_path.read_text(encoding="utf-8"))["res"] if raw_path.exists() else {}
            raw_boxes = payload.get("layout_det_res", {}).get("boxes", [])
            counts: Counter[str] = Counter()
            image_path = args.manifest.parent / page["page_image"]
            image_sha256 = hashlib.sha256(image_path.read_bytes()).hexdigest()
            image = Image.open(image_path).convert("RGB")
            scale_x = image.width / max(1, int(payload.get("width", image.width)))
            scale_y = image.height / max(1, int(payload.get("height", image.height)))
            draw = ImageDraw.Draw(image)
            reviewed_boxes = []
            for box in raw_boxes:
                label = str(box.get("label", ""))
                mapped = category(label)
                if not mapped:
                    continue
                counts[mapped] += 1
                x0, y0, x1, y1 = box["coordinate"]
                coords = [round(x0 * scale_x, 2), round(y0 * scale_y, 2), round(x1 * scale_x, 2), round(y1 * scale_y, 2)]
                draw.rectangle(coords, outline=COLORS[mapped], width=max(2, image.width // 800))
                reviewed_boxes.append({"class": mapped, "source_label": label, "score": box.get("score"), "bbox_xyxy": coords})
            proposals.append({"page_id": page["id"], "boxes": reviewed_boxes})
            thumb_width, thumb_height = 350, 392
            image.thumbnail((thumb_width, thumb_height))
            col, row = index % 4, index // 4
            x = col * 360 + (360 - image.width) // 2
            y = row * 430 + 28
            sheet.paste(image, (x, y))
            draw_sheet.text((col * 360 + 8, row * 430 + 6), page["id"], fill="black")
            image.close()
            queue.append({
                "page_id": page["id"], "source_file": page["source_file"],
                "source_pdf_sha256": page["source_pdf_sha256"],
                "image_sha256": image_sha256,
                "page_image": page["page_image"],
                "page_number_source": page["page_number_source"], "issuer": page["issuer"],
                "split": page["split"], "is_pilot_page": page.get("is_pilot_page", False),
                "pp_output_found": raw_path.exists(), "title_proposals": counts["title"],
                "text_proposals": counts["text"], "table_proposals": counts["table"],
                "figure_proposals": counts["figure"],
                "review_status": "proposal_only_visual_review_required",
            })
        sheet.save(args.output / "overlays" / f"layout-{start+1:03d}-{start+len(batch):03d}.jpg", quality=88)
        sheet.close()
    with (args.output / "review-queue.csv").open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=list(queue[0]))
        writer.writeheader()
        writer.writerows(queue)
    with (args.output / "pp-proposals.jsonl").open("w", encoding="utf-8") as file:
        for row in proposals:
            file.write(json.dumps(row, ensure_ascii=False) + "\n")
    (args.output / "README.md").write_text(
        f"# Layout visual review queue: {manifest['dataset_id']}\n\n"
        f"Input manifest: `{args.manifest}`. PP-StructureV3 outputs: `{args.raw_root}`.\n\n"
        f"The contact sheets overlay PP-StructureV3 proposals on all {len(pages)} full-page inputs. "
        "Colors are title (red), text (blue), table (green), and figure (magenta). "
        "`pp-proposals.jsonl` stores scaled coordinates in the page-image coordinate system. "
        "Use the page image to independently draw or correct reference boxes before scoring; "
        "model proposals are review aids, not ground truth.\n",
        encoding="utf-8",
    )
    print(json.dumps({"pages": len(queue), "outputs_found": sum(row["pp_output_found"] for row in queue), "sheets": len(list((args.output / "overlays").glob("*.jpg"))), "output": str(args.output)}, indent=2))


if __name__ == "__main__":
    main()
