#!/usr/bin/env python3
"""Score revised evidence labels against unchanged saved vectors/rankings; no encoder."""
import argparse
import copy
import hashlib
import json
from pathlib import Path

import numpy as np
from evaluate_embedding_candidates import ROOT, load_evidence_context, summarize_evidence
from compare_vietstyle_evidence import DEFAULT, CANDIDATES, check, digest
from core.evaluation.evidence_metrics import score_evidence

LABELS = DEFAULT.parent / "evidence-v2/evidence.json"


def check_character_coverage(labels, sources, chunks, actual):
    """Independent set-of-characters check against scorer's interval unions."""
    covered = {}
    for chunk in chunks:
        meta = chunk["metadata"]
        key = (meta["document_id"], meta["source_parser_index"])
        for span in meta["source_spans"]:
            covered.setdefault(key, set()).update(range(span["source_start"], span["source_end"]))
    for sid, result in actual["span_coverage"].items():
        span = labels["spans"][sid]
        key = (span["document_id"], span["source_parser_index"])
        text = sources[key]
        needed = {i for i in range(span["start_char"], span["end_char"]) if not text[i].isspace()}
        found = len(needed & covered.get(key, set()))
        check(result == {"covered_characters": found, "total_characters": len(needed),
                         "fraction": found / len(needed), "complete": found == len(needed)}, "Character coverage differs")



def rescore_reranker(path, labels_raw, previous_raw, context):
    """Rescore saved top10 logits, preserving the original reranker report."""
    from evaluate_vietstyle_reranker import load_experiment
    data = load_experiment(path.parent.parent)
    original_raw = path.read_bytes()
    original = json.loads(original_raw)
    config = original["configuration"]
    audit = json.loads((path.parent / "verification.json").read_text())
    check(digest(original_raw) == audit["results_sha256"], "Changed verified reranker report")
    check(config["provenance"] == data["provenance"] and config["provenance"]["labels_sha256"] == digest(previous_raw),
          "Reranker input/previous-label mismatch")
    score_raw = (path.parent / "scores.npy").read_bytes()
    check(digest(score_raw) == config["scores_sha256"] == audit["scores_sha256"], "Changed reranker scores")
    matrix = np.load(path.parent / "scores.npy")
    check(matrix.shape == (len(data["cases"]),30) and np.isfinite(matrix).all(), "Invalid saved reranker scores")
    check(len(original["results"]) == len(data["cases"]), "Incomplete reranker cases")
    labels = json.loads(labels_raw)
    results = []
    for case,indices,scores,saved in zip(data["cases"],data["candidates"],matrix,original["results"]):
        check(case["id"] == saved["id"], "Reranker case order differs")
        chosen = np.asarray(indices)[np.argsort(-scores,kind="stable")[:10]].tolist()
        ids = [f"{data['rows'][i]['document_id']}::chunk::{data['rows'][i]['chunk_index']}" for i in chosen]
        check(ids == saved["reranked_chunk_ids"], "Reranker ranking differs")
        chunks = [{"text":data["rows"][i]["content"],"metadata":data["rows"][i]["metadata"]} for i in chosen]
        source = context["sources"][case["target_language"]]
        actual = score_evidence(labels,case["intent_id"],case["target_language"],chunks,source,k=10)
        check_character_coverage(labels,source,chunks,actual)
        results.append({"id":case["id"],"intent_id":case["intent_id"],"direction":case["direction"],
                        "ranked_chunk_ids":ids,"evidence":actual})
    return {"evaluation":{"type":"label-only rescore of saved reranker top10; no model or ranking change",
                           "labels_sha256":digest(labels_raw),"previous_evaluation_labels_sha256":digest(previous_raw),
                           "source_results":str(path),"source_results_sha256":digest(original_raw),
                           "limitations":labels["revision_provenance"]["evaluation_warning"]},
            "original_configuration":config,"summary_before":original["summary"]["reranked_top10"],
            "summary":{"by_direction":summarize_evidence(results)},"results":results}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path, default=DEFAULT)
    parser.add_argument("--evidence", type=Path, default=LABELS)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--previous-evidence", type=Path, help="Previous labels when comparing a later revision")
    parser.add_argument("--previous-results-dir", type=Path, help="Prior dense rescore directory; required with --previous-evidence")
    parser.add_argument("--reranker-report", type=Path, help="Also rescore an independently verified saved BGE report")
    args = parser.parse_args()
    if (args.previous_evidence is None) != (args.previous_results_dir is None):
        parser.error("--previous-evidence and --previous-results-dir must be supplied together")
    folder = args.output_dir or args.snapshot / "rescored-evidence-v2"
    if folder.exists():
        parser.error("Output exists; use a fresh --output-dir to preserve label comparisons")
    config = json.loads((args.snapshot / "benchmark-config.json").read_text())
    manifest = json.loads((args.snapshot / "manifest.json").read_text())
    corpus_raw = (args.snapshot / config["indexed_corpus"]).read_bytes()
    case_raw = (args.snapshot / config["cases"]).read_bytes()
    check(digest(corpus_raw) == config["indexed_corpus_sha256"], "Changed corpus")
    check(digest(case_raw) == manifest[config["cases"] + "_sha256"], "Changed cases")
    rows = [json.loads(line) for line in corpus_raw.decode().splitlines()]
    cases = json.loads(case_raw)["cases"]
    old_raw = (ROOT / config["evidence"]["path"]).read_bytes()
    check(digest(old_raw) == config["evidence"]["sha256"], "Changed original labels")
    if args.previous_evidence is not None:
        old_raw = args.previous_evidence.read_bytes()
    old_labels = json.loads(old_raw)
    new_raw = args.evidence.read_bytes()
    labels = json.loads(new_raw)
    check(labels["revision_provenance"]["previous_sha256"] == digest(old_raw), "Wrong parent label version")
    check(labels["sources"] == old_labels["sources"] and labels["question_sources"] == old_labels["question_sources"],
          "Rescoring requires unchanged sources/questions")
    new_config = dict(config, evidence={"path": str(args.evidence.resolve()), "sha256": digest(new_raw)})
    context = load_evidence_context(new_config, cases, rows)
    previous_audit = json.loads((args.snapshot / "replay-verification.json").read_text())
    reports, transitions = {}, []
    for name in CANDIDATES:
        candidate = args.snapshot / "candidates" / name
        original_raw = (candidate / "results.json").read_bytes()
        check(digest(original_raw) == previous_audit["results_sha256"][name], "Original replayed report changed")
        original = json.loads(original_raw)
        recipe = original["configuration"]
        check(recipe["status"] == "completed" and recipe["candidate"] == name
              and recipe["corpus_sha256"] == digest(corpus_raw) and recipe["cases_sha256"] == digest(case_raw)
              and recipe["evidence"] == config["evidence"]
              and recipe["revision"] == config["candidate_revisions"][name], "Original recipe mismatch")
        for filename, field in [("vectors.npy", "vectors_file_sha256"), ("query-vectors.npy", "query_vectors_file_sha256")]:
            check(digest((candidate / filename).read_bytes()) == recipe[field], "Vectors changed")
        vectors = np.load(candidate / "vectors.npy")
        queries = np.load(candidate / "query-vectors.npy")
        check(vectors.shape == (len(rows), recipe["dimensions"]) and queries.shape == (len(cases), recipe["dimensions"]),
              "Wrong vector shape")
        for matrix in (vectors, queries):
            check(np.isfinite(matrix).all() and np.allclose(np.linalg.norm(matrix, axis=1), 1, atol=1e-5), "Invalid vectors")
        check(len(original["results"]) == len(cases), "Incomplete original cases")
        previous = original
        if args.previous_results_dir is not None:
            previous = json.loads((args.previous_results_dir / (name + ".json")).read_text())
            check(previous["evaluation"]["labels_sha256"] == digest(old_raw)
                  and previous["evaluation"]["source_results_sha256"] == digest(original_raw), "Wrong prior label comparison")
        check(len(previous["results"]) == len(cases), "Incomplete prior comparison")
        rescored = []
        for case, query, saved, prior in zip(cases, queries, original["results"], previous["results"]):
            check(prior["id"] == saved["id"] and prior["ranked_chunk_ids"] == saved["ranked_chunk_ids"], "Prior ranking differs")
            check(case["id"] == saved["id"], "Wrong case order")
            allowed = set(case["allowed_roles"])
            eligible = [i for i, row in enumerate(rows) if row["language"] == case["target_language"]
                        and ("admin" in allowed or allowed.intersection(row["allowed_roles"] or []))]
            scores = vectors[eligible] @ query
            chosen = [i for i, score in sorted(zip(eligible, scores), key=lambda pair: -float(pair[1]))[:10]]
            ids = [f"{rows[i]['document_id']}::chunk::{rows[i]['chunk_index']}" for i in chosen]
            check(ids == saved["ranked_chunk_ids"], "Original ranking differs")
            chunks = [{"text": rows[i]["content"], "metadata": rows[i]["metadata"]} for i in chosen]
            actual = score_evidence(labels, case["intent_id"], case["target_language"], chunks,
                                    context["sources"][case["target_language"]], k=10)
            check_character_coverage(labels, context["sources"][case["target_language"]], chunks, actual)
            result = copy.deepcopy(saved)
            result["original_evidence_scoring_ms"] = result.pop("evidence_scoring_ms", None)
            result["evidence"] = actual
            rescored.append(result)
            before = prior["evidence"]["full_evidence_success"]
            after = actual["full_evidence_success"]
            if before != after:
                transitions.append({"model": name, "case_id": case["id"], "direction": case["direction"],
                                    "before": before, "after": after})
        reports[name] = {"evaluation": {"type": "label-only rescore; no model or ranking change",
                                        "labels": str(args.evidence), "labels_sha256": digest(new_raw),
                                        "previous_evaluation_labels_sha256": digest(old_raw),
                                        "source_results": str(candidate / "results.json"), "source_results_sha256": digest(original_raw),
                                        "limitations": labels["revision_provenance"]["evaluation_warning"],
                                        "latency": "Inherited original retrieval latency; no new inference/timing benchmark"},
                         "original_configuration": recipe,
                         "summary_before": previous["summary"]["by_direction"],
                         "summary": {"by_direction": summarize_evidence(rescored)}, "results": rescored}
    if args.reranker_report is not None:
        reranker = rescore_reranker(args.reranker_report,new_raw,old_raw,context)
        reports["e5-bge-reranker-v2-m3"] = reranker
        original_reranker = json.loads(args.reranker_report.read_text())
        for saved, result in zip(original_reranker["results"],reranker["results"]):
            before = saved["reranked_evidence"]["full_evidence_success"]
            after = result["evidence"]["full_evidence_success"]
            if before != after:
                transitions.append({"model":"e5-bge-reranker-v2-m3","case_id":result["id"],
                                    "direction":result["direction"],"before":before,"after":after})
    folder.mkdir(parents=True)
    for name, report in reports.items():
        (folder / (name + ".json")).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    audit = {"label_sha256": digest(new_raw), "original_label_sha256": digest(old_raw),
             "rankings_replayed": sum(len(r["results"]) for r in reports.values()),
             "ranking_and_vector_changes": 0, "independent_character_coverage_check": "passed",
             "transitions": transitions,
             "original_results_sha256": {name: r["evaluation"]["source_results_sha256"] for name, r in reports.items()}}
    (folder / "rescore-verification.json").write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n")
    lines = [f"# {old_labels['dataset_id']} → {labels['dataset_id']}: label-only rescore", "", labels["revision_provenance"]["evaluation_warning"], "",
             "Same top ten chunks, 1,063 shared passages and 80 cases/model from 20 paired intents. No encoder/GPU, translation, reranker, generation or DB run. Q14 remains excluded from full-intent denominator.", "",
             "## Complete-evidence cases: previous → revised", "", "All counts below are out of 19 eligible intents per direction.", "",
             "| Query → documents | " + " | ".join(reports) + " |", "|---|" + "---:|" * len(reports)]
    directions = ["vi->vi", "en->en", "vi->en", "en->vi"]
    for direction in directions:
        cells = []
        for name in reports:
            report = reports[name]
            a = report["summary_before"][direction]["full_evidence_cases_at_10"]
            b = report["summary"]["by_direction"][direction]["full_evidence_cases_at_10"]
            cells.append(f"{a} → {b}")
        lines.append("| " + direction + " | " + " | ".join(cells) + " |")
    lines += ["", "## Required component coverage (revised labels)", "", "Required-component counts are shown explicitly. Label-only score changes do not indicate model improvement.", "",
              "| Query → documents | " + " | ".join(reports) + " |", "|---|" + "---:|" * len(reports)]
    for direction in directions:
        cells = []
        for name in reports:
            value = reports[name]["summary"]["by_direction"][direction]
            cells.append(f"{value['required_met_components']}/{value['required_ready_components']} ({value['required_component_coverage_at_10']:.1%})")
        lines.append("| " + direction + " | " + " | ".join(cells) + " |")
    lines += ["", "## Remaining incomplete VI → VI intents", ""]
    for name, report in reports.items():
        missing = [r["intent_id"] for r in report["results"] if r["direction"] == "vi->vi" and r["evidence"]["full_evidence_success"] is False]
        lines.append("- " + name + ": " + (", ".join(missing) or "none"))
    lines += ["", "Previous label files and scores are preserved. Revised labels are assistant-reviewed, not independently certified; alternative evidence is still non-exhaustive. No generated answers were evaluated. See the revised label folder annotation-changes.json for every before/after component and semantic rationale."]
    (folder / "comparison.md").write_text("\n".join(lines) + "\n")
    print(json.dumps({"output": str(folder), "verified_rankings": audit["rankings_replayed"],
                      "vi_to_vi": {name: report["summary"]["by_direction"]["vi->vi"] for name, report in reports.items()}}, indent=2))


if __name__ == "__main__":
    main()
