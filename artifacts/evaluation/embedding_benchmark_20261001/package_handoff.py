"""Package the completed CPU runs with the exact inputs for the GPU PC."""

import hashlib
import json
from pathlib import Path
import time
import zipfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
INPUTS = ROOT / "data/evaluation/embedding_benchmark_20261001"

if __name__ == "__main__":
    while not (HERE / "bge-m3.json").exists():
        time.sleep(5)
    baseline = json.loads((HERE / "baseline.json").read_text(encoding="utf-8"))
    bge = json.loads((HERE / "bge-m3.json").read_text(encoding="utf-8"))
    manifest = json.loads((INPUTS / "manifest.json").read_text(encoding="utf-8"))
    for name, provenance in manifest["files"].items():
        assert hashlib.sha256((INPUTS / name).read_bytes()).hexdigest() == provenance["sha256"]
    for field in ("case_file_sha256", "corpus_file_sha256", "sampled_corpus_sha256", "case_count", "corpus_chunks"):
        assert baseline[field] == bge[field], field
    assert bge["model_id"] == "BAAI/bge-m3" and bge["model_revision"]
    assert bge["all_corpus_chunks_included"] and bge["corpus_chunks"] == manifest["chunk_count"]
    assert bge["corpus_file_sha256"] == manifest["files"]["corpus.jsonl"]["sha256"]
    assert bge["case_file_sha256"] == manifest["files"]["cases.json"]["sha256"]
    evaluator = ROOT / "scripts/retrieval/evaluate_embeddings.py"
    assert hashlib.sha256(evaluator.read_bytes()).hexdigest() == manifest["evaluator_sha256"]
    manifest["run_plan"]["bge-m3"] = "laptop CPU, complete"
    manifest["gpu_handoff"] = {"gpu": "RTX 2060", "os": "Windows with WSL 2"}
    (INPUTS / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    paths = list(INPUTS.iterdir()) + [
        evaluator, ROOT / "src/core/evaluation/retrieval_metrics.py",
        ROOT / "data/vietnam_enterprises/manifest.json",
    ] + [HERE / name for name in (
        "baseline.json", "bge-m3.json", "summarize.py", "GPU_HANDOFF.md",
        "regression.log", "changes.patch",
    )]
    output = HERE / "embedding_benchmark_20261001_gpu.zip"
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as bundle:
        for path in paths:
            assert path.is_file(), path
            bundle.write(path, path.relative_to(ROOT).as_posix())
    with zipfile.ZipFile(output) as bundle:
        for name, provenance in manifest["files"].items():
            relative = (INPUTS / name).relative_to(ROOT).as_posix()
            assert hashlib.sha256(bundle.read(relative)).hexdigest() == provenance["sha256"]
        assert bundle.testzip() is None
    print(json.dumps({"bundle": str(output), "bge_metrics": bge["aggregate"]}, indent=2))
