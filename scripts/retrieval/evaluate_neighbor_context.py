#!/usr/bin/env python3
"""Offline neighbor-context ablation at fixed token budgets; no encoder or DB."""
import argparse
import json
from pathlib import Path
from statistics import mean
from time import perf_counter

import numpy as np
from evaluate_embedding_candidates import ROOT, MODELS, load_evidence_context, summarize_evidence
from compare_vietstyle_evidence import DEFAULT, check, digest
from rescore_vietstyle_evidence import LABELS, check_character_coverage
from core.evaluation.evidence_metrics import score_evidence


def row_id(row):
    return f"{row['document_id']}::chunk::{row['chunk_index']}"


def render_context(rows):
    return "\n\n".join(f"[{row['document_name']}#{row['chunk_index']}]\n{row['content']}" for row in rows)


def context_candidates(rows, ranked_indices, roles, language, strategy):
    """Immediate final-chunk neighbors; never cross document, language or ACL."""
    check(strategy in ("dense10", "dense30", "neighbors"), "Unknown strategy")
    role_set = set(roles)
    eligible = {i for i,row in enumerate(rows) if row["language"] == language
                and ("admin" in role_set or role_set.intersection(row["allowed_roles"] or []))}
    check(all(i in eligible for i in ranked_indices), "Ranked seeds include unauthorized/wrong-language chunks")
    lookup = {}
    for i in eligible:
        row = rows[i]
        key = (row["document_id"], row["language"], row["chunk_index"])
        check(key not in lookup, "Duplicate chunk identity")
        lookup[key] = i
    candidates, seen = [], set()
    limit = 30 if strategy == "dense30" else 10
    for rank, index in enumerate(ranked_indices[:limit], 1):
        row = rows[index]
        choices = [(index, "seed")]
        if strategy == "neighbors":
            for offset in (-1, 1):
                adjacent = lookup.get((row["document_id"], language, row["chunk_index"] + offset))
                if adjacent is not None:
                    choices.append((adjacent, "previous" if offset < 0 else "next"))
        for chosen, reason in choices:
            if chosen not in seen:
                candidates.append({"index": chosen, "seed_rank": rank, "reason": reason})
                seen.add(chosen)
    return candidates


def pack_context(rows, candidates, count_tokens, budget):
    """Whole chunks only, in candidate order; count the exact rendered context."""
    check(type(budget) is int and budget > 0, "Positive integer context budget required")
    selected, skipped = [], []
    for candidate in candidates:
        attempted = selected + [candidate]
        text = render_context([rows[c["index"]] for c in attempted])
        if count_tokens(text) <= budget:
            selected.append(candidate)
        else:
            skipped.append(candidate)
    tokens = count_tokens(render_context([rows[c["index"]] for c in selected]))
    check(tokens <= budget, "Context budget exceeded")
    return selected, skipped, tokens


def context_summary(results):
    # Reuse component aggregation; context can contain >10 chunks, so rename metrics.
    return {direction: {key.replace("_at_10", "_in_context"): value for key,value in summary.items()}
            for direction,summary in summarize_evidence(results).items()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path, default=DEFAULT)
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    folder = args.output_dir or args.snapshot / "neighbor-context-e5-v1"
    if folder.exists():
        parser.error("Output exists; supply a fresh --output-dir to preserve the experiment")
    config = json.loads((args.snapshot / "benchmark-config.json").read_text())
    manifest = json.loads((args.snapshot / "manifest.json").read_text())
    corpus_raw = (args.snapshot / config["indexed_corpus"]).read_bytes()
    case_raw = (args.snapshot / config["cases"]).read_bytes()
    check(digest(corpus_raw) == config["indexed_corpus_sha256"], "Changed corpus")
    check(digest(case_raw) == manifest[config["cases"] + "_sha256"], "Changed cases")
    rows = [json.loads(line) for line in corpus_raw.decode().splitlines()]
    cases = json.loads(case_raw)["cases"]
    labels_raw = LABELS.read_bytes()
    labels = json.loads(labels_raw)
    label_config = dict(config, evidence={"path": str(LABELS), "sha256": digest(labels_raw)})
    context = load_evidence_context(label_config, cases, rows)
    source_folder = args.snapshot / "candidates/multilingual-e5-base"
    source_raw = (source_folder / "results.json").read_bytes()
    prior = json.loads(source_raw)
    recipe = prior["configuration"]
    audit = json.loads((args.snapshot / "replay-verification.json").read_text())
    check(digest(source_raw) == audit["results_sha256"]["multilingual-e5-base"], "Changed source report")
    check(recipe["corpus_sha256"] == digest(corpus_raw) and recipe["cases_sha256"] == digest(case_raw), "Source recipe mismatch")
    for filename, field in [("vectors.npy", "vectors_file_sha256"), ("query-vectors.npy", "query_vectors_file_sha256")]:
        check(digest((source_folder / filename).read_bytes()) == recipe[field], "Changed saved vectors")
    vectors = np.load(source_folder / "vectors.npy")
    queries = np.load(source_folder / "query-vectors.npy")
    check(vectors.shape == (len(rows),recipe["dimensions"]) and queries.shape == (len(cases),recipe["dimensions"]), "Wrong shape")
    from transformers import AutoTokenizer
    tokenizer = AutoTokenizer.from_pretrained(MODELS["multilingual-e5-base"]["model_id"],
                                             revision=recipe["revision"], local_files_only=True)
    def count_tokens(text):
        return len(tokenizer.encode(text, add_special_tokens=False, truncation=False, verbose=False))
    runs = {"dense10_uncapped": []}
    for budget in (2048, 4096):
        for strategy in ("dense10", "dense30", "neighbors"):
            runs[f"{strategy}_{budget}"] = []
    check(len(prior["results"]) == len(cases), "Incomplete source results")
    for case, query, saved in zip(cases,queries,prior["results"]):
        check(case["id"] == saved["id"], "Wrong case order")
        allowed = set(case["allowed_roles"])
        eligible = [i for i,row in enumerate(rows) if row["language"] == case["target_language"]
                    and ("admin" in allowed or allowed.intersection(row["allowed_roles"] or []))]
        values = vectors[eligible] @ query
        ranked = [i for i,score in sorted(zip(eligible,values),key=lambda pair:-float(pair[1]))]
        check([row_id(rows[i]) for i in ranked[:10]] == saved["ranked_chunk_ids"], "Source ranking mismatch")
        for name, results in runs.items():
            started = perf_counter()
            if name == "dense10_uncapped":
                selected = [{"index": i,"seed_rank":rank,"reason":"seed"} for rank,i in enumerate(ranked[:10],1)]
                skipped, budget = [], None
                tokens = count_tokens(render_context([rows[c["index"]] for c in selected]))
            else:
                strategy, limit = name.rsplit("_",1)
                budget = int(limit)
                candidates = context_candidates(rows,ranked,case["allowed_roles"],case["target_language"],strategy)
                selected,skipped,tokens = pack_context(rows,candidates,count_tokens,budget)
            planning_ms = (perf_counter()-started)*1000
            chosen_rows = [rows[c["index"]] for c in selected]
            chunks = [{"text":row["content"],"metadata":row["metadata"]} for row in chosen_rows]
            evidence = score_evidence(labels,case["intent_id"],case["target_language"],chunks,
                                      context["sources"][case["target_language"]],k=max(1,len(chunks)))
            check_character_coverage(labels,context["sources"][case["target_language"]],chunks,evidence)
            results.append({"id":case["id"],"intent_id":case["intent_id"],"direction":case["direction"],
                "context_token_budget":budget,"context_tokens":tokens,"selected_chunks":len(chosen_rows),
                "candidate_planning_ms":planning_ms,"selected_chunk_ids":[row_id(row) for row in chosen_rows],
                "selection":[dict(c,chunk_id=row_id(rows[c["index"]])) for c in selected],
                "skipped_budget_chunk_ids":[row_id(rows[c["index"]]) for c in skipped],"evidence":evidence})
    # Check that the uncapped replay equals the already-published v2 result.
    previous_raw = (args.snapshot / "rescored-evidence-v2/multilingual-e5-base.json").read_bytes()
    previous = json.loads(previous_raw)
    check(previous["evaluation"]["labels_sha256"] == digest(labels_raw), "Different v2 labels")
    check(previous["evaluation"]["source_results_sha256"] == digest(source_raw), "Different rescore origin")
    for current,saved in zip(runs["dense10_uncapped"],previous["results"]):
        check(current["id"] == saved["id"] and current["evidence"] == saved["evidence"], "Uncapped baseline differs from v2")
    summaries = {}
    for name,results in runs.items():
        summaries[name] = context_summary(results)
        for direction, summary in summaries[name].items():
            selected = [q for q in results if q["direction"] == direction]
            summary.update(mean_context_tokens=mean(q["context_tokens"] for q in selected),
                           max_context_tokens=max(q["context_tokens"] for q in selected),
                           mean_context_chunks=mean(q["selected_chunks"] for q in selected),
                           mean_planning_ms=mean(q["candidate_planning_ms"] for q in selected))
    transitions = []
    for budget in (2048,4096):
        baseline = {q["id"]:q for q in runs[f"dense10_{budget}"]}
        for strategy in ("dense30","neighbors"):
            for result in runs[f"{strategy}_{budget}"]:
                before = baseline[result["id"]]["evidence"]["full_evidence_success"]
                after = result["evidence"]["full_evidence_success"]
                if before != after:
                    transitions.append({"strategy":strategy,"budget":budget,"case_id":result["id"],
                                        "direction":result["direction"],"before":before,"after":after})
    # Language audit uses the same 20 paired question meanings, not mismatched document lengths.
    token_audit = {}
    for model in ("multilingual-e5-base","bge-m3","qwen3-embedding-0.6b"):
        counter = AutoTokenizer.from_pretrained(MODELS[model]["model_id"],revision=config["candidate_revisions"][model],local_files_only=True)
        counts = {language:[len(counter.encode(q["question"][language],add_special_tokens=False,truncation=False,verbose=False))
                           for q in labels["intents"]] for language in ("vi","en")}
        token_audit[model] = {"revision":config["candidate_revisions"][model],"vi_total":sum(counts["vi"]),
                              "en_total":sum(counts["en"]),"vi_en_ratio":sum(counts["vi"])/sum(counts["en"]),
                              "per_intent":[{"id":q["id"],"vi_tokens":vi,"en_tokens":en} for q,vi,en in
                                            zip(labels["intents"],counts["vi"],counts["en"])]}
    report = {"configuration":{"model":"multilingual-e5-base","revision":recipe["revision"],
        "corpus_sha256":digest(corpus_raw),"cases_sha256":digest(case_raw),"labels_sha256":digest(labels_raw),
        "source_results_sha256":digest(source_raw),"v2_baseline_sha256":digest(previous_raw),
        "runner_sha256":digest(Path(__file__).read_bytes()),
        "budgets":[2048,4096],"context_tokenizer":"Pinned E5 tokenizer; proxy, not the generation/chat tokenizer",
        "context_format":"[document_name#chunk_index] + newline + raw chunk; blank line between chunks; no embedding prefixes/special tokens",
        "policy":"Neighbors: each top10 seed then previous and next final chunk in same document/language and ACL; deduplicate; skip whole candidates that do not fit. No partial chunks or gold-label selection.",
        "timing":"Planning/tokenization only, excludes embedding/DB/network/generation and evidence scoring. Does not estimate end-to-end latency.",
        "limitations":"Exploratory post-hoc fixed-budget ablation on 20 paired intents/80 cases; Q14 full-intent excluded. Context evidence coverage can use >10 chunks and is not Recall@10. No generation quality/cost measured. All policy variants predeclared before results, unchanged vectors. Context tokens are not encoder input length and can exceed 512."},
        "verification":{"rankings_replayed":len(cases),"variants_scored":len(runs)*len(cases),
                        "source_baseline_matches_v2":True,"independent_character_coverage":"passed"},
        "summary":summaries,"transitions_vs_budgeted_dense10":transitions,"runs":runs}
    folder.mkdir(parents=True)
    (folder/"results.json").write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n")
    (folder/"language-token-audit.json").write_text(json.dumps({"scope":"20 paired question meanings, raw text only; these are embedding tokenizers, not a ChatGPT billing estimate", "models":token_audit},ensure_ascii=False,indent=2)+"\n")
    lines = ["# E5 neighbor context: fixed-budget ablation", "", "Shared evidence v2, unchanged saved dense vectors; 80 cases reuse 20 paired intents. Not an encoder or generation benchmark. Exact source-provenance coverage; Q14 excluded from full-intent rate.", "",
             "## Vietnamese queries → Vietnamese documents", "", "Full-evidence counts are out of 19; component counts are out of 61. Budgets count the exact rendered context using the E5 tokenizer, not an LLM tokenizer. Uncapped dense10 is diagnostic only.", "",
             "| Strategy | Budget | Complete intents | Components | Mean context tokens | Mean chunks |", "|---|---:|---:|---:|---:|---:|"]
    for name,summary in summaries.items():
        value=summary["vi->vi"]
        lines.append(f"| {name} | {name.rsplit('_',1)[-1]} | {value['full_evidence_cases_in_context']}/19 | {value['required_met_components']}/61 | {value['mean_context_tokens']:.0f} | {value['mean_context_chunks']:.1f} |")
    lines += ["", "## Four directions: complete-evidence counts /19", "", "| Variant | VI→VI | EN→EN | VI→EN | EN→VI |", "|---|---:|---:|---:|---:|"]
    for name,summary in summaries.items():
        lines.append("| "+name+" | "+" | ".join(str(summary[d]["full_evidence_cases_in_context"]) for d in ["vi->vi","en->en","vi->en","en->vi"])+" |")
    lines += ["", "## Vietnamese regressions and gains vs same-budget dense10", ""]
    for budget in (2048,4096):
        for strategy in ("dense30","neighbors"):
            changed=[t for t in transitions if t["budget"]==budget and t["strategy"]==strategy and t["direction"]=="vi->vi"]
            gains=[t["case_id"] for t in changed if t["after"] is True]
            losses=[t["case_id"] for t in changed if t["after"] is False]
            lines.append(f"- {strategy}, {budget}: gained {', '.join(gains) or 'none'}; lost {', '.join(losses) or 'none'}.")
    lines += ["", "## Vietnamese vs English question token counts", "", "Same 20 question intents, raw text without model prefixes/instructions/special tokens. Translation length and tokenizer both affect the ratio; no universal Vietnamese multiplier or conversational-model billing claim.", "",
              "| Tokenizer | VI total | EN total | VI/EN |", "|---|---:|---:|---:|"]
    for name,value in token_audit.items():
        lines.append(f"| {name} | {value['vi_total']} | {value['en_total']} | {value['vi_en_ratio']:.2f}× |")
    lines += ["", "## Method and limits", "", report["configuration"]["policy"], "", report["configuration"]["timing"], "", report["configuration"]["limitations"], "", "Neighbor chunk_index adjacency follows frozen parser serialization, which can separate extracted tables from prose. It is not guaranteed physical page/row adjacency. Production expansion needs persisted document order and ACL/ready/company filters; this offline snapshot cannot validate current database permissions. No production or database changes; old benchmark artifacts unchanged."]
    (folder/"comparison.md").write_text("\n".join(lines)+"\n")
    print(json.dumps({"output":str(folder),"verification":report["verification"],"vi_to_vi":{name:summary["vi->vi"] for name,summary in summaries.items()},"token_ratios":{name:value['vi_en_ratio'] for name,value in token_audit.items()}},indent=2))


if __name__ == "__main__":
    main()
