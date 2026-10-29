"""Run Docling end-to-end on pilot or all currently owner-reviewed pages."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
KERNEL_DIR = ROOT / "kaggle/end-to-end-runner"
DATASET_ID = "letrongnhan/vietnamese-enterprise-e2e-hard-scans"
PILOT_PAGE_IDS = {
    "E2E-LONG-HAU-2008-p6",
    "E2E-LONG-HAU-2008-p8",
    "E2E-LONG-HAU-2008-p17",
    "E2E-BAO-HO-LAO-DONG-2009-p13",
    "E2E-BAO-HO-LAO-DONG-2009-p24",
}
def run(command: list[str], *, capture: bool = False) -> str:
    result = subprocess.run(
        command, cwd=ROOT, check=True, text=True, capture_output=capture,
    )
    return result.stdout if capture else ""


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_reviewed_pages(*, pilot_only: bool) -> list[dict]:
    state = json.loads((ROOT / "data/local-review-state.json").read_text(encoding="utf-8"))
    rows = []
    for review in state.get("reviews", []):
        if review.get("annotation_status") != "owner_reviewed":
            continue
        page = review["page_data"]
        page_id = f"{page['document_id']}-p{int(page['source_page_number'])}"
        if pilot_only and page_id not in PILOT_PAGE_IDS:
            continue
        rows.append((page_id, page))
    rows.sort(key=lambda item: (item[1]["document_id"], int(item[1]["source_page_number"])))
    if pilot_only and {page_id for page_id, _ in rows} != PILOT_PAGE_IDS:
        raise RuntimeError("All five pilot pages must be owner-reviewed")
    if not rows:
        raise RuntimeError("There are no owner-reviewed pages to send to Kaggle")
    if len({page_id for page_id, _ in rows}) != len(rows):
        raise RuntimeError("Review state contains duplicate document/page IDs")
    return [{"reference_id": page_id, "source_page_number_1based": int(page["source_page_number"]), **page} for page_id, page in rows]


def prepare_input_package(destination: Path, pages: list[dict], ocr_engine: str) -> tuple[str, Path]:
    manifest = []
    for page in pages:
        image = (ROOT / "data" / page["source_image"]).resolve()
        image.relative_to((ROOT / "data").resolve())
        if not image.is_file():
            raise FileNotFoundError(image)
        image_hash = sha256(image)
        if image_hash != page.get("source_image_sha256"):
            raise ValueError(f"Source image hash changed: {page['reference_id']}")
        image_name = f"{page['reference_id']}.png"
        shutil.copyfile(image, destination / image_name)
        from PIL import Image

        with Image.open(image) as opened:
            width, height = opened.size
        manifest.append({
            "reference_id": page["reference_id"],
            "document_id": page["document_id"],
            "source_page_number_1based": int(page["source_page_number"]),
            "image_file": image_name,
            "image_sha256": image_hash,
            "width": width,
            "height": height,
        })

    (destination / "shared-html-reviewed-pages.jsonl").write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in manifest),
        encoding="utf-8",
    )
    (destination / "pipeline-config.json").write_text(
        json.dumps({"ocr_engine": ocr_engine}, indent=2) + "\n", encoding="utf-8",
    )
    if ocr_engine == "vietocr":
        for name in ("docling_vietocr.py", "line_detection.py"):
            shutil.copyfile(ROOT / "tools/runners" / name, destination / name)
    (destination / "dataset-metadata.json").write_text(json.dumps({
        "title": "Vietnamese Enterprise End-to-End Hard Scans",
        "id": DATASET_ID,
        "licenses": [{"name": "other"}],
        "isPrivate": True,
    }, indent=2) + "\n")
    (destination / "README.md").write_text(
        "Inference-only images for the private end-to-end pipeline. The manifest has page IDs, "
        "image paths, dimensions, and SHA-256 hashes; it contains no review labels or transcripts.\n",
        encoding="utf-8",
    )
    digest = hashlib.sha256()
    for path in sorted(destination.rglob("*")):
        if not path.is_file():
            continue
        digest.update(path.relative_to(destination).as_posix().encode("utf-8"))
        digest.update(path.read_bytes())
    return digest.hexdigest(), destination / "shared-html-reviewed-pages.jsonl"


def update_dataset_if_needed(package: Path, digest: str, page_count: int) -> None:
    state_path = Path.home() / ".cache/document-pipelines/end-to-end-runner-dataset.sha256"
    previous = state_path.read_text().strip() if state_path.is_file() else None
    if previous == digest:
        print(f"Kaggle input dataset unchanged ({page_count} reviewed pages); skipping upload.", flush=True)
        return
    message = f"Sync {page_count} owner-reviewed end-to-end pages ({digest[:10]})"
    print(f"Updating {DATASET_ID}: {message}", flush=True)
    run(["kaggle", "datasets", "version", "-p", str(package), "-m", message, "-r", "skip"])
    wait_for_dataset(DATASET_ID, 10)
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(digest + "\n")


def wait_for_dataset(dataset_id: str, poll_seconds: int) -> None:
    while True:
        status = run(["kaggle", "datasets", "status", dataset_id], capture=True)
        print(status.strip(), flush=True)
        normalized = status.strip().lower()
        if "ready" in normalized:
            return
        if any(word in normalized for word in ("error", "failed", "denied")):
            raise RuntimeError(f"Kaggle dataset update failed: {status.strip()}")
        time.sleep(poll_seconds)


def wait_for_kernel(kernel_id: str, poll_seconds: int) -> None:
    while True:
        status = run(["kaggle", "kernels", "status", kernel_id], capture=True)
        print(status.strip(), flush=True)
        match = re.search(r"KernelWorkerStatus\.(\w+)", status)
        if not match:
            raise RuntimeError(f"Could not parse Kaggle kernel status: {status.strip()}")
        state = match.group(1)
        if state == "COMPLETE":
            return
        if state in {"ERROR", "CANCEL_ACKNOWLEDGED", "CANCEL_REQUESTED"}:
            logs = run(["kaggle", "kernels", "logs", kernel_id], capture=True)
            print(logs, file=sys.stderr)
            raise RuntimeError(f"Kaggle kernel ended with status {state}")
        time.sleep(poll_seconds)


def register_output(download: Path, run_id: str, kernel_id: str, pages: list[dict], input_digest: str) -> Path:
    raw_root = download / "docling-raw-pages"
    metadata_path = download / "docling-metadata.json"
    if not raw_root.is_dir() or not metadata_path.is_file():
        raise RuntimeError("Kaggle completed without the expected Docling raw pages and metadata")
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    expected_ids = {page["reference_id"] for page in pages}
    raw_files = {path.stem for path in raw_root.glob("*.json")}
    if raw_files != expected_ids:
        raise RuntimeError(
            f"Kaggle returned {len(raw_files)} pages; expected {len(expected_ids)} "
            f"(missing={sorted(expected_ids - raw_files)}, extra={sorted(raw_files - expected_ids)})"
        )

    run_id = f"docling-{run_id}"
    output = ROOT / "results/shared-html" / run_id
    output.mkdir(parents=True, exist_ok=False)
    sys.path.insert(0, str(ROOT / "tools/runners"))
    from run_shared_benchmark import normalize_document

    predictions = []
    for page in pages:
        page_id = page["reference_id"]
        raw = json.loads((raw_root / f"{page_id}.json").read_text(encoding="utf-8"))
        if "error_type" in raw:
            prediction = {
                "schema_version": 1, "engine": metadata["engine"], "run_id": run_id,
                "document_id": page["document_id"],
                "source_page_number_1based": int(page["source_page_number_1based"]),
                "elements": [], "tables": [],
            }
        else:
            prediction = normalize_document(raw, page, metadata["engine"], run_id)
        predictions.append(prediction)

    predictions_path = output / "predictions.jsonl"
    predictions_path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in predictions),
        encoding="utf-8",
    )
    shutil.copytree(raw_root, output / "raw_pages")
    (output / "input-manifest.jsonl").write_text(
        "".join(json.dumps({
            "reference_id": page["reference_id"],
            "image_sha256": page["source_image_sha256"],
        }, ensure_ascii=False) + "\n" for page in pages),
        encoding="utf-8",
    )
    page_status = {item["reference_id"]: item for item in metadata.get("pages", [])}
    inference_seconds = round(sum(metadata.get("page_seconds", {}).values()), 3)
    run_metadata = {
        **metadata,
        "dataset": "shared-html-owner-reviewed",
        "run_id": run_id,
        "source_kernel": kernel_id,
        "input_dataset": DATASET_ID,
        "input_manifest_sha256": input_digest,
        "page_count": len(pages),
        "successful_pages": sum(page_status.get(page_id, {}).get("status") != "failed" for page_id in expected_ids),
        "failed_pages": sum(page_status.get(page_id, {}).get("status") == "failed" for page_id in expected_ids),
        "inference_wall_seconds": inference_seconds,
        "inference_page_seconds": metadata.get("page_seconds", {}),
    }
    (output / "run-metadata.json").write_text(
        json.dumps(run_metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
    )
    command = [
        sys.executable, "tools/evaluators/evaluate_shared_benchmark.py",
        "--predictions", str(predictions_path),
    ]
    for page_id in sorted(expected_ids):
        command.extend(["--page-id", page_id])
    run(command)
    for file in download.iterdir():
        if file.is_file():
            shutil.copyfile(file, output / file.name)
    return output

def main() -> None:
    started_at = datetime.now(timezone.utc)
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--pilot-5", action="store_true", help="Smoke-test pipeline changes on the fixed five-page cohort")
    mode.add_argument("--all-reviewed", action="store_true", help="Run every page currently marked owner_reviewed")
    parser.add_argument("--ocr-engine", choices=("tesseract", "vietocr"), default="tesseract")
    parser.add_argument("--poll-seconds", type=int, default=20)
    args = parser.parse_args()
    pilot_only = args.pilot_5
    pages = load_reviewed_pages(pilot_only=pilot_only)
    run_kind = "pilot-5" if pilot_only else "all-reviewed"
    if args.ocr_engine == "vietocr":
        run_kind += "-vietocr"
    run_id = run_kind + "-" + datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    kernel_metadata = json.loads((KERNEL_DIR / "kernel-metadata.json").read_text())
    kernel_id = kernel_metadata["id"]
    with tempfile.TemporaryDirectory(prefix="end-to-end-input-") as temporary:
        package = Path(temporary)
        input_digest, _ = prepare_input_package(package, pages, args.ocr_engine)
        update_dataset_if_needed(package, input_digest, len(pages))
    print(f"Pushing {kernel_id} with {len(pages)} reviewed pages", flush=True)
    run(["kaggle", "kernels", "push", "-p", str(KERNEL_DIR)])
    wait_for_kernel(kernel_id, max(2, args.poll_seconds))
    with tempfile.TemporaryDirectory(prefix="end-to-end-output-") as temporary:
        download = Path(temporary)
        run(["kaggle", "kernels", "output", kernel_id, "-p", str(download)])
        result = register_output(download, run_id, kernel_id, pages, input_digest)
    finished_at = datetime.now(timezone.utc)
    metadata_path = result / "run-metadata.json"
    run_metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    run_metadata.update({
        "started_at_utc": started_at.isoformat(),
        "finished_at_utc": finished_at.isoformat(),
        "wall_seconds": round((finished_at - started_at).total_seconds(), 3),
        "wall_seconds_scope": "dataset preparation/sync, Kaggle queue/inference, output download, and local result registration",
    })
    metadata_path.write_text(json.dumps(run_metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Saved {len(pages)} reviewed page predictions to {result}", flush=True)
    print("The open Results dashboard discovers the new end-to-end run automatically.", flush=True)


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as error:
        raise SystemExit(error.returncode) from error
