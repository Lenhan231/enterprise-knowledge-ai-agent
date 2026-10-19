#!/usr/bin/env python3
"""Replay saved dense vectors and evidence characters without encoders; write comparison."""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from evaluate_embedding_candidates import ROOT, load_evidence_context, summarize_evidence

DEFAULT = ROOT / "artifacts/evaluation/vietstyle-bilingual-20261019/dense-evidence-benchmark-v1"
CANDIDATES = ("multilingual-e5-base", "bge-m3", "qwen3-embedding-0.6b")


def check(ok, message):
    if not ok:
        raise ValueError(message)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path, default=DEFAULT)
    args = parser.parse_args()
    config = json.loads((args.snapshot / "benchmark-config.json").read_text())
    manifest = json.loads((args.snapshot / "manifest.json").read_text())
    raw = (args.snapshot / config["indexed_corpus"]).read_bytes()
    check(digest(raw) == config["indexed_corpus_sha256"], "Changed corpus")
    rows = [json.loads(line) for line in raw.decode().splitlines()]
    case_raw = (args.snapshot / config["cases"]).read_bytes()
    check(digest(case_raw) == manifest[config["cases"] + "_sha256"], "Changed cases")
    cases = json.loads(case_raw)["cases"]
    context = load_evidence_context(config, cases, rows)
    labels = context["data"]
    intents = {q["id"]: q for q in labels["intents"]}
    reports = {}
    for name in CANDIDATES:
        folder = args.snapshot / "candidates" / name
        report = json.loads((folder / "results.json").read_text())
        recipe = report["configuration"]
        check(recipe["status"] == "completed" and recipe["candidate"] == name, "Incomplete candidate")
        check(recipe == json.loads((folder / "config.json").read_text()), "Recipe disagreement")
        check(recipe["corpus_sha256"] == digest(raw) and recipe["cases_sha256"] == digest(case_raw)
              and recipe["evidence"] == config["evidence"], "Candidate inputs differ")
        check(recipe["revision"] == config["candidate_revisions"][name], "Candidate revision differs")
        check(recipe["row_order_sha256"] == digest(json.dumps([(r["document_id"],r["chunk_index"]) for r in rows]).encode()),
              "Candidate vector row order differs")
        for filename, key in [("vectors.npy","vectors_file_sha256"),("query-vectors.npy","query_vectors_file_sha256")]:
            check(digest((folder / filename).read_bytes()) == recipe[key], "Changed vectors")
        vectors, queries = np.load(folder / "vectors.npy"), np.load(folder / "query-vectors.npy")
        check(vectors.shape == (len(rows),recipe["dimensions"]) and queries.shape == (len(cases),recipe["dimensions"]),
              "Wrong vector shape")
        for matrix in (vectors,queries):
            check(np.isfinite(matrix).all() and np.allclose(np.linalg.norm(matrix,axis=1),1,atol=1e-5), "Invalid vectors")
        check(len(report["results"]) == len(cases), "Incomplete cases")
        for case, query, saved in zip(cases,queries,report["results"]):
            check(saved["id"] == case["id"], "Case order differs")
            # Independent ranking: stable Python sort instead of runner's np.argsort.
            allowed = set(case["allowed_roles"])
            eligible = [i for i,r in enumerate(rows) if r["language"] == case["target_language"]
                        and ("admin" in allowed or allowed.intersection(r["allowed_roles"] or []))]
            scores = vectors[eligible] @ query
            selected = [i for i,score in sorted(zip(eligible,scores),key=lambda pair:-float(pair[1]))[:10]]
            ids = [f"{rows[i]['document_id']}::chunk::{rows[i]['chunk_index']}" for i in selected]
            check(ids == saved["ranked_chunk_ids"], f"Ranking differs {name} {case['id']}")
            # Independent coverage: explicit character sets, not scorer's interval union.
            covered = {}
            for i in selected:
                meta = rows[i]["metadata"]
                key = (rows[i]["document_id"],meta["source_parser_index"])
                for span in meta["source_spans"]:
                    covered.setdefault(key,set()).update(range(span["source_start"],span["source_end"]))
            actual = saved["evidence"]
            for sid, span_result in actual["span_coverage"].items():
                span = labels["spans"][sid]
                check(span["language"] == case["target_language"], "Wrong-language evidence")
                key = (span["document_id"],span["source_parser_index"])
                source = context["sources"][case["target_language"]][key]
                needed = {i for i in range(span["start_char"],span["end_char"]) if not source[i].isspace()}
                found = len(needed & covered.get(key,set()))
                check(span_result == {"covered_characters": found,"total_characters": len(needed),
                                      "fraction": found/len(needed),"complete": found == len(needed)}, "Coverage differs")
            ready, met = 0, 0
            intent = intents[case["intent_id"]]
            check(len(actual["requirements"]) == len(intent["requirements"]), "Missing requirement")
            for requirement, result in zip(intent["requirements"],actual["requirements"]):
                check(requirement["id"] == result["id"], "Requirement order differs")
                if requirement["status"] == "ready":
                    bundles = requirement["evidence_by_language"][case["target_language"]]["alternatives"]
                    complete = any(all(actual["span_coverage"][sid]["complete"] for sid in b["all_of"]) for b in bundles)
                    check(result["complete"] == complete, "Alternative bundle differs")
                    if requirement["required"]:
                        ready += 1
                        met += complete
            full_eligible = all(q["status"] == "ready" for q in intent["requirements"] if q["required"])
            check(actual["required_ready"] == ready and actual["required_met"] == met
                  and actual["required_coverage"] == met/ready and actual["full_intent_eligible"] == full_eligible
                  and actual["full_evidence_success"] == (met == ready if full_eligible else None), "Case metric differs")
        check(summarize_evidence(report["results"]) == report["summary"]["by_direction"], "Summary differs")
        reports[name] = report
    audit = {"verified_models": list(reports),"verified_rankings": sum(len(r["results"]) for r in reports.values()),
             "method": "Saved normalized vectors; independent stable dense ranking and explicit source-character set coverage; no encoder/GPU/API/DB",
             "results_sha256": {name: digest((args.snapshot / "candidates" / name / "results.json").read_bytes()) for name in reports}}
    (args.snapshot / "replay-verification.json").write_text(json.dumps(audit,indent=2)+"\n")
    lines = ["# VietStyle dense evidence benchmark v1", "", "20 paired intents, 80 cases per model, 4 directions. Each case searches all five documents in the target language. Shared 1,063 chunks (532 VI, 531 EN); no truncation, translation, hybrid, reranker or generation.", "",
             "## Complete evidence in top 10", "", "Q14 excluded from the full-intent denominator because required approval-role labels remain unresolved. Each direction has 19 eligible intents.", "",
             "| Query → document | E5 multilingual base | BGE-M3 | Qwen3 0.6B |", "|---|---:|---:|---:|"]
    directions = ["vi->vi","en->en","vi->en","en->vi"]
    def cell(name,direction,kind):
        value = reports[name]["summary"]["by_direction"][direction]
        if kind == "full":
            return f"{value['full_evidence_cases_at_10']}/{value['full_intent_eligible_cases']} ({value['full_evidence_success_rate_at_10']:.1%})"
        return f"{value['required_met_components']}/{value['required_ready_components']} ({value['required_component_coverage_at_10']:.1%})"
    for direction in directions:
        lines.append("| "+direction+" | "+" | ".join(cell(name,direction,"full") for name in CANDIDATES)+" |")
    lines += ["", "## Required component coverage in top 10", "", "Includes ready components of Q14; pending and optional components excluded. This is binary completeness per annotated component, not raw character fraction or generated answer accuracy.", "",
              "| Query → document | E5 multilingual base | BGE-M3 | Qwen3 0.6B |", "|---|---:|---:|---:|"]
    for direction in directions:
        lines.append("| "+direction+" | "+" | ".join(cell(name,direction,"component") for name in CANDIDATES)+" |")
    lines += ["", "## Cases missing complete evidence", "", "Q14 is excluded below; inspect candidate results.json for each missing component and alternative span.", ""]
    for direction in directions:
        lines.append("### "+direction)
        lines.append("")
        for name,report in reports.items():
            missing = [r["intent_id"] for r in report["results"] if r["direction"] == direction and r["evidence"]["full_evidence_success"] is False]
            lines.append("- "+name+": "+(", ".join(missing) or "none"))
        lines.append("")
    lines += ["## Interpretation and limits", "", "Exact annotated evidence coverage is stricter than the previous expected-file metric; percentages are not comparable directly. Alternate valid evidence may be unlabelled. English files, queries and evidence are assistant-curated simulations, not independently certified. Four directions reuse the same 20 intents and are not 80 independent questions. This test isolates dense encoders within a target-language corpus; it does not evaluate production language selection or a mixed-language index. Q09/Q10 calculation inputs also come from the question; Q18 is unavailable-data abstention. These scores do not measure generated-answer correctness. The label validator and independent replay verified all 240 rankings and their span/component scores.", "",
              "Production embedding service, live database/index, retrieval ranking and translation settings are unchanged. New outputs preserve the old benchmark artifacts."]
    (args.snapshot / "comparison.md").write_text("\n".join(lines)+"\n")
    print(json.dumps(audit,indent=2))


if __name__ == "__main__":
    main()
