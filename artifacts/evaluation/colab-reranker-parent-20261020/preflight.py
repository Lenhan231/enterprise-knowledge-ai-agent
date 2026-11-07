"""Audit the neighbor ablation with the already-cached tokenizer, never model weights."""
import argparse
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--plain-control", action="store_true")
args = parser.parse_args()
if args.plain_control:
    HERE = ROOT / "artifacts/evaluation/colab-reranker-parent-plain-20261020"
    HERE.mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(ROOT / "scripts/retrieval"))
import evaluate_reranker_source_context as experiment
from transformers import AutoTokenizer

data = experiment.prepare()
rows = data["rows"]
metadata = [r["content"] if args.plain_control else experiment.render(rows, i) for i, r in enumerate(rows)]
parent = [experiment.render_parent_plain(rows, i) if args.plain_control else experiment.render_parent(rows, i) for i in range(len(rows))]
if args.plain_control:
    for i, row in enumerate(rows):
        prior = experiment.render_parent(rows, i)
        anchor = experiment.render(rows, i)
        assert (prior != anchor) == (parent[i] != row["content"])
        if prior != anchor:
            assert prior.removesuffix(anchor) == parent[i].removesuffix(row["content"])
tokenizer_path = ROOT / ".venv/benchmark-model-cache/models--BAAI--bge-reranker-v2-m3/snapshots" / experiment.previous.REVISION
tokenizer = AutoTokenizer.from_pretrained(str(tokenizer_path), local_files_only=True)
def pairs(values):
    return [(case["question"], values[i]) for case, indices in zip(data["cases"], data["candidates"]) for i in indices]
control, treatment = pairs(metadata), pairs(parent)
a = experiment.previous.check_pair_lengths(tokenizer, control, 1024)
b = experiment.previous.check_pair_lengths(tokenizer, treatment, 1024)
guard = next(i for i, r in enumerate(rows) if r["language"] == "vi" and "02_SOP" in r["document_name"]
             and r["metadata"]["source_parser_index"] == 4)
before = next(r for r in rows if r["document_id"] == rows[guard]["document_id"] and r["chunk_index"] == rows[guard]["chunk_index"] - 1)
assert parent[guard].startswith("Preceding source passage:\n" + before["content"])
assert parent[guard].endswith(metadata[guard])
audit = {"status": "preflight_passed_not_inference", "source_git_commit": data["provenance"]["source_git_commit"],
         "control_mode": "plain" if args.plain_control else "metadata",
         "context_mode": "parent-plain" if args.plain_control else "parent",
         "labels_sha256": data["provenance"]["labels_sha256"], "model_revision": experiment.previous.REVISION,
         "passages": len(rows), "cases": len(data["cases"]), "pairs_per_condition": len(control),
         "modified_pairs": sum(x != y for x, y in zip(control, treatment)),
         "passages_with_preceding_context": sum(x != y for x, y in zip(metadata, parent)),
         "max_control_pair_tokens": max(a), "max_parent_pair_tokens": max(b),
         "per_pair_limit": 1024, "overlength_pairs": 0, "context_token_budget": None,
         "history_guard_preceding_source_verified": True,
         "limits": "Uses only the cached pinned tokenizer. No reranker weights loaded, no inference or network."}
(HERE / "preflight.json").write_text(json.dumps(audit, indent=2) + "\n", encoding="utf-8")
print(json.dumps(audit, indent=2))
