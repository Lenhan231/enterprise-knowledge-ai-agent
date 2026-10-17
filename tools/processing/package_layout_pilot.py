"""Package the reviewed enterprise layout manifest as COCO plus its images."""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path
from typing import Any


def package(manifest_path: Path, output_dir: Path) -> dict[str, Any]:
    manifest = json.loads(manifest_path.read_text())
    classes = manifest["annotation_classes"]
    category_ids = {name: index + 1 for index, name in enumerate(classes)}
    coco: dict[str, Any] = {
        "info": {
            "description": manifest["dataset_id"],
            "annotation_status": manifest["status"],
        },
        "licenses": [],
        "categories": [
            {"id": category_ids[name], "name": name, "supercategory": "layout"}
            for name in classes
        ],
        "images": [],
        "annotations": [],
    }

    images_dir = output_dir / "images"
    images_dir.mkdir(parents=True, exist_ok=True)
    annotation_id = 1
    for image_id, page in enumerate(manifest["pages"], 1):
        source_image = Path(page["image_file"])
        relative_image = Path("images") / source_image.name
        shutil.copy2(source_image, output_dir / relative_image)
        coco["images"].append(
            {
                "id": image_id,
                "file_name": relative_image.as_posix(),
                "width": page["width_px"],
                "height": page["height_px"],
                "source_page_id": page["id"],
            }
        )
        for region in page["annotations"]:
            x1, y1, x2, y2 = region["bbox_xyxy"]
            width, height = x2 - x1, y2 - y1
            coco["annotations"].append(
                {
                    "id": annotation_id,
                    "image_id": image_id,
                    "category_id": category_ids[region["class"]],
                    "bbox": [x1, y1, width, height],
                    "area": width * height,
                    "iscrowd": 0,
                }
            )
            annotation_id += 1

    (output_dir / "pilot-coco.json").write_text(
        json.dumps(coco, ensure_ascii=False, indent=2) + "\n"
    )
    (output_dir / "dataset-metadata.json").write_text(
        json.dumps(
            {
                "title": "Vietnamese Enterprise Layout Pilot v1",
                "id": "ltrngnhn/vietnamese-enterprise-layout-pilot-v1",
                "licenses": [{"name": "other"}],
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n"
    )
    return coco


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    coco = package(args.manifest, args.output_dir)
    print(
        json.dumps(
            {
                "images": len(coco["images"]),
                "annotations": len(coco["annotations"]),
                "output_dir": str(args.output_dir),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
