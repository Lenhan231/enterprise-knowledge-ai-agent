"""Replay exact saved BGE scores with preceding context disabled for structured tables."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import zipfile

import numpy as np
import evaluate_reranker_source_context as experiment

ROOT = experiment.ROOT
SOURCE = ROOT / "artifacts/evaluation/colab-reranker-parent-plain-20261020"
OUT = ROOT / "artifacts/evaluation/reranker-narrative-context-20261020"


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def main():
    experiment.previous.check(not (OUT / "results.json").exists(), "Completed output exists; preserve it")
    source = SOURCE / "colab-results"
    report = load(source / "results.json")
    recipe = report["configuration"]
    with zipfile.ZipFile(SOURCE / "reranker_parent_plain_colab_inputs.zip") as bundle:
        check = experiment.previous.check
        check(hashlib.sha256(bundle.read("scripts/retrieval/evaluate_reranker_source_context.py")).hexdigest()
              == recipe["runner_sha256"], "Source inference runner differs")
        key = experiment.digest((SOURCE / "reranker_parent_plain_colab_inputs.zip").read_bytes())[:16]
        inputs = ROOT / ".venv/colab-review-inputs" / key
        inputs.mkdir(parents=True, exist_ok=True)
        check(all((inputs / name).resolve().is_relative_to(inputs.resolve()) for name in bundle.namelist()), "Invalid input archive")
        bundle.extractall(inputs)
    check(recipe["context_mode"] == "parent-plain" and recipe["control_mode"] == "plain", "Wrong source experiment")
    check(recipe["revision"] == experiment.previous.REVISION and recipe["context_token_budget"] is None, "Wrong model/limit")
    # Verify all original saved scores, renderings and evidence before reusing any.
    subprocess.run([sys.executable, "-X", "utf8", str(Path(experiment.__file__)), "--input-root", str(inputs),
                    "--output-dir", str(source), "--context-mode", "parent-plain", "--verify-only"], check=True)
    data = experiment.prepare(inputs)
    rows = data["rows"]
    plain = np.load(source / "plain-scores.npy", allow_pickle=False)
    parent = np.load(source / "context-scores.npy", allow_pickle=False)
    mask = np.asarray([[experiment.is_structured_table(rows[i]) for i in indices] for indices in data["candidates"]])
    scores = np.where(mask, plain, parent)
    rendered = [experiment.render_narrative_parent(rows, i) for i in range(len(rows))]
    source_inputs = load(source / "rendered-inputs.json")
    check(len(source_inputs) == len(rows), "Incomplete scored-input list")
    for i, (row, saved) in enumerate(zip(rows, source_inputs)):
        expected = saved["original"] if experiment.is_structured_table(row) else saved["context_input"]
        check(rendered[i] == expected, "Policy input was not scored by source experiment")
    # Independent per-element score lineage check.
    for n, indices in enumerate(data["candidates"]):
        for j, i in enumerate(indices):
            expected = plain[n, j] if experiment.is_structured_table(rows[i]) else parent[n, j]
            check(scores[n, j] == expected, "Score lineage differs")
    records, summary = experiment.summarize(data, plain, scores)
    OUT.mkdir(exist_ok=True)
    np.save(OUT / "plain-scores.npy", plain)
    np.save(OUT / "context-scores.npy", scores)
    (OUT / "rendered-inputs.json").write_text(json.dumps([
        {"chunk_id": experiment.previous.chunk_id(r), "original": r["content"], "context_input": text}
        for r, text in zip(rows, rendered)], ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    changed = sum(rendered[i] != rows[i]["content"] for indices in data["candidates"] for i in indices)
    disabled = sum(experiment.is_structured_table(rows[i]) and experiment.render_parent_plain(rows, i) != rows[i]["content"]
                   for indices in data["candidates"] for i in indices)
    config = {"status": "completed", "context_mode": "narrative-parent", "control_mode": "plain",
        "execution": "offline exact-score policy replay; no new inference", "device": "cpu saved-score replay",
        "dtype": "float32", "model": recipe["model"], "revision": recipe["revision"],
        "candidate_k": 30, "final_k": 10, "context_token_budget": None, "max_pair_tokens": 1024,
        "source_preflight_max_pair_tokens": recipe["max_observed_pair_tokens"], "truncated_pairs": 0,
        "short_passage_max_chars": experiment.SHORT_CHARS, "cases_completed": len(records),
        "changed_pairs": changed, "table_context_pairs_disabled": int(disabled),
        "provenance": data["provenance"], "source_results_sha256": experiment.digest((source / "results.json").read_bytes()),
        "source_scores_sha256": {"plain": recipe["plain_scores_sha256"], "parent": recipe["context_scores_sha256"]},
        "source_inference_gpu": recipe["gpu_name"], "source_inference_dtype": recipe["dtype"],
        "source_inference_runner_sha256": recipe["runner_sha256"],
        "runner_sha256": experiment.digest(Path(__file__).read_bytes()),
        "plain_scores_sha256": experiment.digest((OUT / "plain-scores.npy").read_bytes()),
        "context_scores_sha256": experiment.digest((OUT / "context-scores.npy").read_bytes()),
        "rendered_inputs_sha256": experiment.digest((OUT / "rendered-inputs.json").read_bytes()),
        "limits": "Post-hoc policy on 20 paired intents, not held-out. Every input/logit already exists in one same-runtime Colab experiment. Original anchors alone earn evidence. No production change."}
    (OUT / "config.json").write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
    (OUT / "results.json").write_text(json.dumps({"configuration": config, "summary": summary, "results": records},
                                               ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    subprocess.run([sys.executable, "-X", "utf8", str(Path(experiment.__file__)), "--input-root", str(inputs),
                    "--output-dir", str(OUT), "--context-mode", "narrative-parent", "--verify-only"], check=True)
    lineage = {"cases": len(records), "matrix_entries_checked": int(scores.size),
               "each_policy_input_matches_original_or_parent_input": True,
               "each_score_matches_its_recorded_input": True, "new_model_calls": 0,
               "source_results_sha256": config["source_results_sha256"],
               "policy_scores_sha256": config["context_scores_sha256"]}
    (OUT / "score-lineage.json").write_text(json.dumps(lineage, indent=2) + "\n", encoding="utf-8")
    changes = []
    for before, after in zip(report["results"], records):
        old = before["source_context_evidence"]
        new = after["source_context_evidence"]
        a = {r["id"]: r["complete"] for r in old["requirements"] if r["required"] and r["status"] == "ready"}
        b = {r["id"]: r["complete"] for r in new["requirements"] if r["required"] and r["status"] == "ready"}
        delta = {k: [a[k], b[k]] for k in a if a[k] != b[k]}
        if delta:
            changes.append({"id": after["id"], "components": delta, "complete_before": old["full_evidence_success"],
                            "complete_after": new["full_evidence_success"]})
    (OUT / "changes-vs-parent.json").write_text(json.dumps(changes, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"summary": summary, "changes_vs_parent": changes, "config": config}, indent=2))


if __name__ == "__main__":
    main()
