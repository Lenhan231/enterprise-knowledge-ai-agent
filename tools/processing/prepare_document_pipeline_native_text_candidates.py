"""Package source-preserving dev/validation PDFs with extractable text layers."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import defaultdict
from pathlib import Path

import fitz


ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "artifacts/evaluation/document-pipelines"
DEFAULT_MANIFEST = BASE / "layout/inputs/manifest.json"
DEFAULT_OUTPUT = BASE / "results/follow-up-metrics/native-text-candidates-v1"
MIN_NATIVE_TEXT_CHARS = 100
ALLOWED_SPLITS = {"development", "validation"}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def build(manifest_path: Path, output: Path) -> dict:
    if output.exists():
        raise FileExistsError(f"Refusing to overwrite candidate set: {output}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    source_root = ROOT
    grouped: dict[str, list[dict]] = defaultdict(list)
    for row in manifest["pages"]:
        if row.get("split") in ALLOWED_SPLITS:
            grouped[row["source_file"]].append(row)

    output_inputs = output / "inputs"
    output_inputs.mkdir(parents=True)
    pages = []
    source_hashes = {}
    seen_source_pages = set()
    for source_file in sorted(grouped):
        source_path = source_root / source_file
        if not source_path.is_file():
            raise FileNotFoundError(source_path)
        actual_source_hash = sha256(source_path)
        expected_hashes = {row["source_pdf_sha256"] for row in grouped[source_file]}
        if expected_hashes != {actual_source_hash}:
            raise ValueError(f"Source hash mismatch for {source_path}")
        with fitz.open(source_path) as source:
            for row in sorted(grouped[source_file], key=lambda item: item["page_number_source"]):
                source_page_number = int(row["page_number_source"])
                source_key = (actual_source_hash, source_page_number)
                if source_key in seen_source_pages:
                    raise ValueError(f"Duplicate source page in manifest: {source_file} p{source_page_number}")
                seen_source_pages.add(source_key)
                if not 1 <= source_page_number <= len(source):
                    raise ValueError(f"Source page out of range: {source_file} p{source_page_number}")

                source_text = source[source_page_number - 1].get_text("text").strip()
                if len(source_text) < MIN_NATIVE_TEXT_CHARS:
                    continue

                page_id = row["id"]
                relative_pdf = f"inputs/{page_id}.pdf"
                target = fitz.open()
                target.insert_pdf(source, from_page=source_page_number - 1, to_page=source_page_number - 1)
                target.save(output / relative_pdf, garbage=4, deflate=True)
                target.close()

                with fitz.open(output / relative_pdf) as packaged:
                    if len(packaged) != 1:
                        raise ValueError(f"Expected one page in {relative_pdf}")
                    packaged_text = packaged[0].get_text("text").strip()
                if "".join(packaged_text.split()) != "".join(source_text.split()):
                    raise ValueError(f"Text layer changed while packaging {source_file} p{source_page_number}")

                pages.append({
                    "id": page_id,
                    "input_pdf": relative_pdf,
                    "input_pdf_sha256": sha256(output / relative_pdf),
                    "source_file": source_file,
                    "source_pdf_sha256": actual_source_hash,
                    "source_page_number": source_page_number,
                    "source_page_id": page_id,
                    "issuer": row["issuer"],
                    "split": row["split"],
                    "native_text_char_count": len(source_text),
                    "candidate_source_type": "text_layer_present_unreviewed",
                })
                source_hashes[source_file] = actual_source_hash

    split_counts = {
        split: sum(page["split"] == split for page in pages)
        for split in sorted(ALLOWED_SPLITS)
    }
    result = {
        "dataset_id": "vietnam-enterprise-native-text-candidates-v1",
        "status": "candidate_inputs_only_source_type_and_references_unreviewed",
        "source_manifest": str(manifest_path.relative_to(ROOT)),
        "selection_rule": f"Development/validation pages with at least {MIN_NATIVE_TEXT_CHARS} extractable characters in the original source PDF.",
        "locked_test_included": False,
        "page_count": len(pages),
        "split_counts": split_counts,
        "source_pdf_count": len(source_hashes),
        "issuer_count": len({page["issuer"] for page in pages}),
        "preserves_original_text_layer": True,
        "pages": pages,
        "source_pdfs": source_hashes,
    }
    (output / "manifest.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    result = build(args.manifest, args.output)
    print(json.dumps({key: result[key] for key in (
        "status", "page_count", "split_counts", "source_pdf_count", "issuer_count", "locked_test_included"
    )} | {"output": str(args.output)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
