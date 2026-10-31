"""Verify all four frozen-input runs and write their comparison."""

import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
INPUTS = HERE.parents[2] / "data/evaluation/embedding_benchmark_20261001"
manifest = json.loads((INPUTS / "manifest.json").read_text(encoding="utf-8"))
cases = json.loads((INPUTS / "cases.json").read_text(encoding="utf-8"))["cases"]
keys = ("baseline", "bge-m3", "qwen3-embedding", "e5-large-v2")
reports = {key: json.loads((HERE / f"{key}.json").read_text(encoding="utf-8")) for key in keys}
expected_models = {
    "baseline": manifest["baseline_model"], "bge-m3": "BAAI/bge-m3",
    "qwen3-embedding": "Qwen/Qwen3-Embedding-0.6B", "e5-large-v2": "intfloat/e5-large-v2",
}
for name, provenance in manifest["files"].items():
    assert hashlib.sha256((INPUTS / name).read_bytes()).hexdigest() == provenance["sha256"], name
first = reports["baseline"]
for key, report in reports.items():
    assert report["model_key"] == key and report["model_id"] == expected_models[key]
    for field in ("case_file_sha256", "corpus_file_sha256", "sampled_corpus_sha256", "case_count", "corpus_chunks"):
        assert report[field] == first[field], (key, field)
    assert report["case_file_sha256"] == manifest["files"]["cases.json"]["sha256"]
    assert report["corpus_file_sha256"] == manifest["files"]["corpus.jsonl"]["sha256"]
    assert report["all_corpus_chunks_included"] and report["corpus_chunks"] == manifest["chunk_count"]
    assert report["model_revision"], key
    assert [row["id"] for row in report["results"]] == [case["id"] for case in cases]
    for row, case in zip(report["results"], cases):
        assert row["relevant_document_ids"] == sorted(case["relevant_document_ids"])
    assert [row["eligible_chunks"] for row in report["results"]] == [row["eligible_chunks"] for row in first["results"]]
    assert report["configuration"]["device"] in {"cpu", "cuda"}
    assert report["configuration"]["batch_size"] == manifest["batch_size"]

vi_ids = set(manifest["vietnamese_case_ids"])
models = []
for key, report in reports.items():
    vi_rows = [row for row in report["results"] if row["id"] in vi_ids]
    models.append({
        "key": key, "model_id": report["model_id"], "revision": report["model_revision"],
        "sequence_limit": report["max_sequence_length"], "aggregate": report["aggregate"],
        "environment": report["environment"],
        "vietnamese_aggregate": {metric: round(sum(row["metrics"][metric] for row in vi_rows) / len(vi_rows), 4)
                                  for metric in report["aggregate"]},
        "timing_seconds": report["timing_seconds"],
    })
summary = {"input_hashes_verified": True, "manifest": manifest, "models": models}
(HERE / "comparison.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
lines = ["# Frozen embedding benchmark — 2026-10-01", "",
         "All four reports use the same verified input hashes: 4,750 saved chunks, 25 documents,",
         "and 12 labeled questions (five Vietnamese). All chunks were included; none were rechunked.", "",
         "The configured baseline is `sentence-transformers/all-MiniLM-L6-v2`, using the local backend.", "",
         "## All 12 questions", "",
         "| Model | Device | Recall@1 | Recall@5 | MRR | nDCG@5 | Corpus embedding seconds | Mean query ms |",
         "|---|---|---:|---:|---:|---:|---:|---:|"]
for model in models:
    a, t = model["aggregate"], model["timing_seconds"]
    lines.append(f"| {model['key']} | {model['environment']['device']} | {a['recall@1']:.4f} | {a['recall@5']:.4f} | {a['mrr']:.4f} | {a['ndcg@5']:.4f} | {t['corpus_embeddings']:.2f} | {t['mean_query'] * 1000:.2f} |")
lines += ["", "## Five Vietnamese questions", "",
          "| Model | Recall@1 | Recall@5 | MRR | nDCG@5 |", "|---|---:|---:|---:|---:|"]
for model in models:
    a = model["vietnamese_aggregate"]
    lines.append(f"| {model['key']} | {a['recall@1']:.4f} | {a['recall@5']:.4f} | {a['mrr']:.4f} | {a['ndcg@5']:.4f} |")
lines += ["", "## Verification and limits", "",
          "Prior handoff regression suite: 487 tests, exit code 0, 10 skips. See `regression.log`.",
          "The initial merged checkout failed; corrections restore main's RAG test mock,",
          "update the moved Apple evaluator import/root and explicit dense selection, and",
          "handle Windows resource telemetry, permissions and optional source fixtures.",
          "Tests ran in UTF-8 mode with a test-only authentication secret; `.env` was not changed.", "",
          "This measures role-filtered dense document retrieval using maximum chunk cosine per",
          "document. It does not measure hybrid search, year boosting, reranking, passage relevance,",
          "or generated answers. The labels are inherited from a small demo set, not independent review.", "",
          "The baseline retains its native 256-token limit; the other runs cap their limits at 512.",
          "All receive identical saved text, but model tokenizers, truncation and recommended prefixes",
          "differ. All runs use four compute threads and batch size eight. Qwen3/e5 completed",
          "on an RTX 2060 in WSL: accuracy can be compared on the frozen inputs, but CPU/GPU",
          "timings are not a controlled speed comparison. Model loading may include downloads",
          "and differs with cache state. No database embeddings were modified.", "",
          "Input provenance and reproduction commands: `data/evaluation/embedding_benchmark_20261001/README.md`."]
(HERE / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
print(json.dumps({"verified": True, "models": models}, indent=2))
