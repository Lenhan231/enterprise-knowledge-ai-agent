"""Verify the returned Colab experiment and report paired evidence changes."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import zipfile
import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
parser = argparse.ArgumentParser(description=__doc__)
group = parser.add_mutually_exclusive_group()
group.add_argument("--parent-context", action="store_true")
group.add_argument("--parent-plain", action="store_true")
args = parser.parse_args()
parent_run = args.parent_context or args.parent_plain
if parent_run:
    HERE = ROOT / ("artifacts/evaluation/colab-reranker-parent-plain-20261020" if args.parent_plain else "artifacts/evaluation/colab-reranker-parent-20261020")
result_zip = "reranker_parent_plain_results.zip" if args.parent_plain else "reranker_parent_context_results.zip" if parent_run else "reranker_context_results.zip"
input_zip = "reranker_parent_plain_colab_inputs.zip" if args.parent_plain else "reranker_parent_colab_inputs.zip" if parent_run else "reranker_colab_inputs.zip"
OUT = HERE / "colab-results"
with zipfile.ZipFile(HERE / result_zip) as bundle:
    assert bundle.testzip() is None
    assert set(bundle.namelist()) == {"config.json", "results.json", "verification.json",
                                      "rendered-inputs.json", "plain-scores.npy", "context-scores.npy"}
    OUT.mkdir(exist_ok=True)
    bundle.extractall(OUT)
report = json.loads((OUT / "results.json").read_text(encoding="utf-8"))
config = report["configuration"]
with zipfile.ZipFile(HERE / input_zip) as bundle:
    runner = bundle.read("scripts/retrieval/evaluate_reranker_source_context.py")
    assert hashlib.sha256(runner).hexdigest() == config["runner_sha256"]
    key = hashlib.sha256((HERE / input_zip).read_bytes()).hexdigest()[:16]
    input_root = ROOT / ".venv/colab-review-inputs" / key
    input_root.mkdir(parents=True, exist_ok=True)
    assert all((input_root / name).resolve().is_relative_to(input_root.resolve()) for name in bundle.namelist())
    bundle.extractall(input_root)

command = [sys.executable, "-X", "utf8", str(ROOT / "scripts/retrieval/evaluate_reranker_source_context.py"),
           "--input-root", str(input_root), "--output-dir", str(OUT), "--verify-only"]
if parent_run:
    command += ["--context-mode", "parent-plain" if args.parent_plain else "parent"]
subprocess.run(command, cwd=ROOT, check=True)
sys.path.insert(0, str(ROOT / "scripts/retrieval"))
import evaluate_reranker_source_context as experiment

data = experiment.prepare(input_root)
by_id = {experiment.previous.chunk_id(row): row for row in data["rows"]}
historical = {row["id"]: row for row in data["historical"]["results"]}
changes, focused = [], []
for row in report["results"]:
    before = row["plain_evidence"]
    after = row["source_context_evidence"]
    a = {r["id"]: r["complete"] for r in before["requirements"] if r["required"] and r["status"] == "ready"}
    b = {r["id"]: r["complete"] for r in after["requirements"] if r["required"] and r["status"] == "ready"}
    delta = {k: [a[k], b[k]] for k in a if a[k] != b[k]}
    if delta:
        changes.append({"id": row["id"], "direction": row["direction"], "requirements": delta,
                        "full_before": before["full_evidence_success"], "full_after": after["full_evidence_success"]})
    if row["intent_id"] in {"Q13", "Q15"}:
        guards = [cid for cid, source in by_id.items() if source["language"] == "vi"
                  and "02_SOP" in source["document_name"] and source["metadata"]["source_parser_index"] == 4]
        focused.append({"id": row["id"], "required": before["required_ready"],
                        "plain_met": before["required_met"], "context_met": after["required_met"],
                        "missing_before": [k for k, v in a.items() if not v],
                        "missing_after": [k for k, v in b.items() if not v],
                        "vi_guard_rank_plain": next((row["plain_ranking"].index(cid) + 1 for cid in guards if cid in row["plain_ranking"]), None),
                        "vi_guard_rank_context": next((row["source_context_ranking"].index(cid) + 1 for cid in guards if cid in row["source_context_ranking"]), None)})

top10_order_changed = sum(r["plain_ranking"][:10] != r["source_context_ranking"][:10] for r in report["results"])
top10_set_changed = sum(set(r["plain_ranking"][:10]) != set(r["source_context_ranking"][:10]) for r in report["results"])
historical_changed = [r["id"] for r in report["results"] if r["plain_ranking"][:10] != historical[r["id"]]["reranked_chunk_ids"]]
findings = {"summary": report["summary"], "component_changes": changes, "focused_cases": focused,
            "top10_order_changed_cases": top10_order_changed, "top10_set_changed_cases": top10_set_changed,
            "plain_order_differences_from_historical_fp16": historical_changed,
            "paired_inference_seconds": sum(config["paired_case_seconds"])}
if parent_run:
    prior = json.loads((HERE.parent / "colab-reranker-context-20261020/colab-results/results.json").read_text(encoding="utf-8"))
    old = {r["id"]: r for r in prior["results"]}
    findings.pop("plain_order_differences_from_historical_fp16")
    control_arm = "plain" if args.parent_plain else "source_context"
    findings["previous_control_reference"] = "Original plain FP32 Colab run" if args.parent_plain else "Previous metadata-only Colab run"
    findings["control_order_changes_from_previous_run"] = [r["id"] for r in report["results"]
        if r["plain_ranking"][:10] != old[r["id"]][control_arm + "_ranking"][:10]]
    findings["control_evidence_changes_from_previous_run"] = [r["id"] for r in report["results"]
        if r["plain_evidence"] != old[r["id"]][control_arm + "_evidence"]]
    findings["control_mode"] = config["control_mode"]
    findings["context_mode"] = config["context_mode"]
    findings["original_plain_summary"] = prior["summary"]["plain"]
    findings["changes_vs_original_plain"] = [{"id": r["id"],
        "original_plain_complete": old[r["id"]]["plain_evidence"]["full_evidence_success"],
        "parent_complete": r["source_context_evidence"]["full_evidence_success"]}
        for r in report["results"] if old[r["id"]]["plain_evidence"]["full_evidence_success"]
        != r["source_context_evidence"]["full_evidence_success"]]
diagnostics = []
plain_scores, context_scores = [np.load(OUT / name) for name in ("plain-scores.npy", "context-scores.npy")]
for n, row in enumerate(report["results"]):
    changed_ids = {r["id"] for r in changes}
    if row["id"] not in changed_ids and (row["direction"] != "vi->vi" or row["intent_id"] not in {"Q01", "Q13", "Q15"}):
        continue
    changed = set(row["plain_ranking"][:10]) ^ set(row["source_context_ranking"][:10])
    changed |= {cid for cid in row["candidate_chunk_ids"] if "02_SOP" in by_id[cid]["document_name"]
                and by_id[cid]["metadata"]["source_parser_index"] == 4}
    rows = []
    for cid in sorted(changed):
        source = by_id[cid]
        i = row["candidate_chunk_ids"].index(cid)
        rows.append({"document": source["document_name"], "parser_index": source["metadata"]["source_parser_index"],
                     "original_text": source["content"],
                     "plain_rank": row["plain_ranking"].index(cid) + 1,
                     "context_rank": row["source_context_ranking"].index(cid) + 1,
                     "plain_logit": float(plain_scores[n, i]), "context_logit": float(context_scores[n, i])})
    diagnostics.append({"id": row["id"], "changed_top10_or_guard": rows})
findings["diagnostic_passages"] = diagnostics
(HERE / "findings.json").write_text(json.dumps(findings, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(json.dumps({k: v for k, v in findings.items() if k not in {"summary", "diagnostic_passages"}}, ensure_ascii=False, indent=2))
