"""Prepare a deterministic, template-stratified FATURA benchmark subset."""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
from pathlib import Path
from zipfile import ZipFile


ARCHIVE_ROOT = "invoices_dataset_final/"
IMAGE_RE = re.compile(r"^invoices_dataset_final/images/(Template\d+_Instance\d+\.jpg)$")
ANNOTATION_RE = re.compile(
    r"^invoices_dataset_final/Annotations/Original_Format/(Template\d+_Instance\d+\.json)$"
)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _template_split(archive: ZipFile) -> tuple[set[int], set[int]]:
    split_path = ARCHIVE_ROOT + "Strat2_Split.txt"
    source = archive.read(split_path).decode("utf-8")
    train_match = re.search(r"train_inds\s*=\s*(\[[^\]]+\])", source)
    dev_match = re.search(r"dev_inds\s*=\s*(\[[^\]]+\])", source)
    if not train_match or not dev_match:
        raise ValueError("Could not parse FATURA Strat2 template splits")
    train = set(json.loads(train_match.group(1)))
    # The archive defines test_inds as an alias of dev_inds; use that same
    # template-disjoint group as the benchmark holdout.
    holdout = set(json.loads(dev_match.group(1)))
    if train & holdout or train | holdout != set(range(1, 51)):
        raise ValueError("Strat2 template split is incomplete or overlapping")
    return train, holdout


def prepare(archive_path: Path, output: Path, per_template: int, seed: int) -> dict:
    with ZipFile(archive_path) as archive:
        train_templates, holdout_templates = _template_split(archive)
        images: dict[str, str] = {}
        annotations: dict[str, str] = {}
        for member in archive.namelist():
            image_match = IMAGE_RE.match(member)
            annotation_match = ANNOTATION_RE.match(member)
            if image_match:
                images[image_match.group(1).removesuffix(".jpg")] = member
            elif annotation_match:
                annotations[annotation_match.group(1).removesuffix(".json")] = member

        if images.keys() != annotations.keys():
            raise ValueError(
                f"Image/reference mismatch: {len(images)} images, "
                f"{len(annotations)} references"
            )
        by_template: dict[int, list[str]] = {}
        for key in images:
            template = int(key.split("_", 1)[0].removeprefix("Template"))
            by_template.setdefault(template, []).append(key)

        rng = random.Random(seed)
        selected: list[str] = []
        for template in sorted(by_template):
            candidates = sorted(by_template[template])
            if len(candidates) < per_template:
                raise ValueError(f"Template {template} has only {len(candidates)} samples")
            selected.extend(sorted(rng.sample(candidates, per_template)))

        manifest = {
            "dataset_id": "fatura-template-stratified-v1",
            "source_dataset": "FATURA synthetic invoice dataset",
            "source_record": "https://zenodo.org/records/8261508",
            "license": "CC BY 4.0 (record metadata)",
            "source_archive": archive_path.as_posix(),
            "source_archive_sha256": file_sha256(archive_path),
            "sample_seed": seed,
            "samples_per_template": per_template,
            "sample_count": len(selected),
            "split_policy": (
                "Template-disjoint using Strat2_Split.txt. The source test template "
                "indices are the holdout; remaining source-train templates are "
                "development diagnostics only. No training or tuning is performed."
            ),
            "template_split": {
                "development_diagnostic": sorted(train_templates),
                "template_holdout_test": sorted(holdout_templates),
            },
            "label_provenance": "Dataset-provided synthetic annotations; no human review added.",
            "items": [],
        }
        (output / "inputs").mkdir(parents=True, exist_ok=True)
        (output / "references").mkdir(parents=True, exist_ok=True)
        for key in selected:
            image = archive.read(images[key])
            reference = archive.read(annotations[key])
            item_id = key.lower().replace("_", "-")
            (output / "inputs" / f"{item_id}.jpg").write_bytes(image)
            (output / "references" / f"{item_id}.json").write_bytes(reference)
            template = int(key.split("_", 1)[0].removeprefix("Template"))
            instance = int(key.split("_", 1)[1].removeprefix("Instance"))
            manifest["items"].append(
                {
                    "id": item_id,
                    "template_id": template,
                    "instance_id": instance,
                    "split": (
                        "template_holdout_test"
                        if template in holdout_templates
                        else "development_diagnostic"
                    ),
                    "input": f"inputs/{item_id}.jpg",
                    "input_sha256": sha256(image),
                    "reference": f"references/{item_id}.json",
                    "reference_sha256": sha256(reference),
                    "source_image": images[key],
                    "source_annotation": annotations[key],
                }
            )

    output.mkdir(parents=True, exist_ok=True)
    manifest_path = output / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--per-template", type=int, default=10)
    parser.add_argument("--seed", type=int, default=20261019)
    args = parser.parse_args()
    manifest = prepare(args.archive, args.output, args.per_template, args.seed)
    counts = {
        split: sum(item["split"] == split for item in manifest["items"])
        for split in ("development_diagnostic", "template_holdout_test")
    }
    print(json.dumps({"sample_count": manifest["sample_count"], "split_counts": counts}))
    print(f"Saved {args.output / 'manifest.json'}")


if __name__ == "__main__":
    main()
