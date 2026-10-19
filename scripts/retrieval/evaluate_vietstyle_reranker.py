#!/usr/bin/env python3
"""E5 top30 -> multilingual cross-encoder -> top10, with frozen evidence v2."""
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean, median
from time import perf_counter

import numpy as np
from evaluate_embedding_candidates import ROOT, load_evidence_context, summarize_evidence
from evaluate_rerankers import MODELS
from compare_vietstyle_evidence import DEFAULT, check, digest
from rescore_vietstyle_evidence import LABELS, check_character_coverage
from core.evaluation.evidence_metrics import score_evidence

MODEL_KEY = "bge-reranker-v2-m3"
REVISION = "953dc6f6f85a1b2dbfca4c34a2796e7dde08d41e"


def chunk_id(row):
    return f"{row['document_id']}::chunk::{row['chunk_index']}"


def dense_candidates(rows, vectors, query, case, k=30):
    roles = set(case["allowed_roles"])
    eligible = [i for i,row in enumerate(rows) if row["language"] == case["target_language"]
                and ("admin" in roles or roles.intersection(row["allowed_roles"] or []))]
    check(bool(eligible), "No eligible candidates")
    scores = vectors[eligible] @ query
    return [i for i,score in sorted(zip(eligible,scores), key=lambda pair:-float(pair[1]))[:k]]


def rerank_candidates(indices, scores, top_k=10):
    """Higher raw logits first; score ties retain dense candidate order."""
    values = np.asarray(scores)
    check(type(top_k) is int and top_k > 0, "top_k must be a positive integer")
    check(bool(indices) and len(indices) == len(set(indices)), "Empty or duplicate candidates")
    check(values.shape == (len(indices),) and np.isfinite(values).all(), "Invalid reranker scores")
    order = sorted(range(len(indices)), key=lambda i:-float(values[i]))
    return [indices[i] for i in order[:top_k]]


def check_pair_lengths(tokenizer, pairs, limit):
    lengths = [len(ids) for ids in tokenizer([q for q,p in pairs], [p for q,p in pairs],
               add_special_tokens=True, truncation=False, padding=False, verbose=False)["input_ids"]]
    over = [(i,n) for i,n in enumerate(lengths) if n > limit]
    check(not over, f"Pairs exceed per-input model limit {limit}: {over[:5]}; no silent truncation")
    return lengths


def evidence_for(data, case, indices):
    chunks = [{"text":data["rows"][i]["content"],"metadata":data["rows"][i]["metadata"]} for i in indices]
    sources = data["context"]["sources"][case["target_language"]]
    result = score_evidence(data["context"]["data"],case["intent_id"],case["target_language"],chunks,sources,k=len(chunks))
    check_character_coverage(data["context"]["data"],sources,chunks,result)
    return result


def load_experiment(snapshot):
    config = json.loads((snapshot / "benchmark-config.json").read_text())
    manifest = json.loads((snapshot / "manifest.json").read_text())
    corpus_raw = (snapshot / config["indexed_corpus"]).read_bytes()
    case_raw = (snapshot / config["cases"]).read_bytes()
    labels_raw = LABELS.read_bytes()
    check(digest(corpus_raw) == config["indexed_corpus_sha256"], "Changed corpus")
    check(digest(case_raw) == manifest[config["cases"]+"_sha256"], "Changed cases")
    rows = [json.loads(line) for line in corpus_raw.decode().splitlines()]
    cases = json.loads(case_raw)["cases"]
    context = load_evidence_context(dict(config,evidence={"path":str(LABELS),"sha256":digest(labels_raw)}),cases,rows)
    folder = snapshot / "candidates/multilingual-e5-base"
    original_raw = (folder / "results.json").read_bytes()
    original = json.loads(original_raw)
    recipe = original["configuration"]
    audit = json.loads((snapshot / "replay-verification.json").read_text())
    check(digest(original_raw) == audit["results_sha256"]["multilingual-e5-base"], "Changed original results")
    check(recipe["status"] == "completed" and recipe["corpus_sha256"] == digest(corpus_raw)
          and recipe["cases_sha256"] == digest(case_raw)
          and recipe["revision"] == config["candidate_revisions"]["multilingual-e5-base"], "Wrong dense recipe")
    check(recipe["row_order_sha256"] == digest(json.dumps([(r["document_id"],r["chunk_index"]) for r in rows]).encode()),
          "Wrong dense row order")
    for filename,field in [("vectors.npy","vectors_file_sha256"),("query-vectors.npy","query_vectors_file_sha256")]:
        check(digest((folder / filename).read_bytes()) == recipe[field], "Changed saved vectors")
    vectors, queries = np.load(folder / "vectors.npy"), np.load(folder / "query-vectors.npy")
    check(vectors.shape == (len(rows),recipe["dimensions"]) and queries.shape == (len(cases),recipe["dimensions"]), "Wrong dense shape")
    for matrix in (vectors,queries):
        check(np.isfinite(matrix).all() and np.allclose(np.linalg.norm(matrix,axis=1),1,atol=1e-5), "Invalid dense vectors")
    baseline_raw = (snapshot / "rescored-evidence-v2/multilingual-e5-base.json").read_bytes()
    baseline = json.loads(baseline_raw)
    check(baseline["evaluation"]["labels_sha256"] == digest(labels_raw)
          and baseline["evaluation"]["source_results_sha256"] == digest(original_raw), "Wrong v2 baseline")
    check(len(original["results"]) == len(baseline["results"]) == len(cases), "Incomplete source cases")
    data = {"rows":rows,"cases":cases,"context":context,"candidates":[],"baseline":baseline["results"],
            "provenance":{"corpus_sha256":digest(corpus_raw),"cases_sha256":digest(case_raw),
                          "labels_sha256":digest(labels_raw),"dense_results_sha256":digest(original_raw),
                          "dense_vectors_sha256":recipe["vectors_file_sha256"],
                          "query_vectors_sha256":recipe["query_vectors_file_sha256"],
                          "v2_baseline_sha256":digest(baseline_raw)}}
    for case,query,saved,v2 in zip(cases,queries,original["results"],baseline["results"]):
        check(case["id"] == saved["id"] == v2["id"], "Case order mismatch")
        indices = dense_candidates(rows,vectors,query,case)
        check(len(indices) == 30, "Expected 30 eligible candidates")
        check([chunk_id(rows[i]) for i in indices[:10]] == saved["ranked_chunk_ids"], "Dense baseline ranking differs")
        check(evidence_for(data,case,indices[:10]) == v2["evidence"], "Dense v2 evidence differs")
        data["candidates"].append(indices)
    data["provenance"]["candidate_order_sha256"] = digest(json.dumps(data["candidates"]).encode())
    return data


def summaries(results, field):
    values = [{"direction":r["direction"],"evidence":r[field]} for r in results]
    result = summarize_evidence(values)
    if field == "candidate_evidence":
        result = {d:{k.replace("_at_10","_at_30"):v for k,v in row.items()} for d,row in result.items()}
    return result


def verify(folder, data):
    raw = (folder / "results.json").read_bytes()
    report = json.loads(raw)
    config = report["configuration"]
    check(config["status"] == "completed" and config["provenance"] == data["provenance"], "Changed experiment inputs")
    check(config == json.loads((folder / "config.json").read_text()), "Configuration mismatch")
    check(config["scores_sha256"] == digest((folder / "scores.npy").read_bytes()), "Changed reranker scores")
    matrix = np.load(folder / "scores.npy")
    check(matrix.shape == (len(data["cases"]),30) and np.isfinite(matrix).all(), "Invalid saved score matrix")
    check(len(report["results"]) == len(data["cases"]), "Incomplete reranker results")
    for case,candidates,scores,saved in zip(data["cases"],data["candidates"],matrix,report["results"]):
        check(saved["id"] == case["id"], "Wrong saved case order")
        # Independent np stable sort, distinct from inference helper's Python sort.
        selected = np.asarray(candidates)[np.argsort(-scores,kind="stable")[:10]].tolist()
        check(saved["reranked_chunk_ids"] == [chunk_id(data["rows"][i]) for i in selected], "Reranker score replay differs")
        check(saved["candidate_chunk_ids"] == [chunk_id(data["rows"][i]) for i in candidates], "Candidate pool differs")
        for field,indices in [("dense_evidence",candidates[:10]),("candidate_evidence",candidates),("reranked_evidence",selected)]:
            check(saved[field] == evidence_for(data,case,indices), f"Evidence replay differs: {field}")
    for name,field in [("dense_top10","dense_evidence"),("candidate_pool30","candidate_evidence"),("reranked_top10","reranked_evidence")]:
        check(report["summary"][name] == summaries(report["results"],field), "Summary replay differs")
    audit = {"cases_verified":len(data["cases"]),"scores_verified":int(matrix.size),
             "candidate_retrieval_replayed":True,"independent_stable_score_sort":"passed",
             "all_three_evidence_views_replayed":"passed","independent_character_coverage":"passed",
             "results_sha256":digest(raw),"scores_sha256":digest((folder / "scores.npy").read_bytes())}
    (folder / "verification.json").write_text(json.dumps(audit,indent=2)+"\n")
    print(json.dumps(audit,indent=2),flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot",type=Path,default=DEFAULT)
    parser.add_argument("--output-dir",type=Path)
    parser.add_argument("--device",choices=("cpu","cuda"),default="cuda")
    parser.add_argument("--batch-size",type=int,default=2)
    parser.add_argument("--max-pair-tokens",type=int,default=1024,help="Per question-passage model input limit, not a context budget")
    parser.add_argument("--verify-only",action="store_true")
    args = parser.parse_args()
    folder = args.output_dir or args.snapshot / "reranker-bge-v2-m3-v1"
    if not args.verify_only and folder.exists():
        parser.error("Output exists; use a fresh --output-dir")
    if args.batch_size < 1 or args.max_pair_tokens < 8:
        parser.error("Positive batch size and pair limit >=8 required")
    data = load_experiment(args.snapshot)
    if args.verify_only:
        verify(folder,data)
        return
    from huggingface_hub import snapshot_download
    from transformers import AutoConfig, AutoTokenizer
    model_path = snapshot_download(MODELS[MODEL_KEY],revision=REVISION,local_files_only=True,
        allow_patterns=["config.json","model.safetensors","tokenizer.json","tokenizer_config.json",
                        "special_tokens_map.json","sentencepiece.bpe.model"])
    tokenizer = AutoTokenizer.from_pretrained(model_path,local_files_only=True)
    pairs = [(case["question"],data["rows"][i]["content"]) for case,indices in zip(data["cases"],data["candidates"]) for i in indices]
    lengths = check_pair_lengths(tokenizer,pairs,args.max_pair_tokens)
    pretrained = AutoConfig.from_pretrained(model_path,local_files_only=True)
    check(pretrained.num_labels == 1 and pretrained.model_type == "xlm-roberta", "Unexpected reranker architecture/head")
    check(args.max_pair_tokens <= pretrained.max_position_embeddings-2, "Pair limit exceeds model positions")
    config = {"status":"preflight","model_key":MODEL_KEY,"model_id":MODELS[MODEL_KEY],"revision":REVISION,
              "device":args.device,"dtype":"float16" if args.device == "cuda" else "float32", "batch_size":args.batch_size,
              "candidate_k":30,"final_k":10,"context_token_budget":None,"max_pair_tokens":args.max_pair_tokens,
              "max_observed_pair_tokens":max(lengths),"truncated_pairs":0,"pairs":len(pairs),"cases":len(data["cases"]),
              "provenance":data["provenance"],"runner_sha256":digest(Path(__file__).read_bytes()),
              "created_at":datetime.now(timezone.utc).isoformat(),"score_type":"raw relevance logits; higher is better, dense order breaks ties",
              "model_card":"https://huggingface.co/BAAI/bge-reranker-v2-m3",
              "scoring_scope":"80 cases reuse20 paired intents across4 directions,5 target-language documents compete. No translation/generation/hybrid/neighbor expansion.",
              "limitations":"Small post-hoc assistant-reviewed evidence v2, not an independent held-out test. Candidate pool coverage is availability, not a top10 oracle. No context-token budget; final chunk lengths may differ. Local rerank timing excludes model loading, dense retrieval, preflight and evidence scoring. No end-to-end answer latency or quality evaluated."}
    folder.mkdir(parents=True)
    def save_config():
        (folder / "config.json").write_text(json.dumps(config,indent=2)+"\n")
    save_config()
    try:
        import torch
        from sentence_transformers import CrossEncoder
        check(args.device != "cuda" or torch.cuda.is_available(), "CUDA requested but unavailable; no CPU fallback")
        started = perf_counter()
        model = CrossEncoder(model_path,max_length=args.max_pair_tokens,device=args.device,
                             model_kwargs={"torch_dtype":torch.float16 if args.device == "cuda" else torch.float32})
        config.update(model_load_seconds=perf_counter()-started,
                      gpu_name=torch.cuda.get_device_name() if args.device == "cuda" else None)
        # Warm-up is recorded separately from the per-query 30-pair timings.
        started = perf_counter()
        model.predict(pairs[:1],batch_size=1,show_progress_bar=False,activation_fn=torch.nn.Identity(),convert_to_numpy=True)
        if args.device == "cuda":
            torch.cuda.synchronize()
            torch.cuda.reset_peak_memory_stats()
        config.update(warmup_seconds=perf_counter()-started,status="reranking")
        save_config()
        results,all_scores = [],[]
        for case,indices in zip(data["cases"],data["candidates"]):
            inputs = [(case["question"],data["rows"][i]["content"]) for i in indices]
            if args.device == "cuda":torch.cuda.synchronize()
            started = perf_counter()
            scores = np.asarray(model.predict(inputs,batch_size=args.batch_size,show_progress_bar=False,
                                activation_fn=torch.nn.Identity(),convert_to_numpy=True),dtype=np.float32).reshape(-1)
            if args.device == "cuda":torch.cuda.synchronize()
            elapsed = (perf_counter()-started)*1000
            chosen = rerank_candidates(indices,scores)
            dense,available,reranked = [evidence_for(data,case,picks) for picks in (indices[:10],indices,chosen)]
            check(reranked["required_met"] <= available["required_met"], "Selection exceeds candidate evidence coverage")
            results.append({"id":case["id"],"intent_id":case["intent_id"],"direction":case["direction"],
                "query_language":case["query_language"],"target_language":case["target_language"],
                "candidate_chunk_ids":[chunk_id(data["rows"][i]) for i in indices],
                "dense_top10_chunk_ids":[chunk_id(data["rows"][i]) for i in indices[:10]],
                "reranked_chunk_ids":[chunk_id(data["rows"][i]) for i in chosen],
                "dense_evidence":dense,"candidate_evidence":available,"reranked_evidence":reranked,"rerank_latency_ms":elapsed})
            all_scores.append(scores)
            config["cases_completed"] = len(results)
            save_config()
            print(case["id"],f"dense={dense['full_evidence_success']} reranked={reranked['full_evidence_success']} {elapsed:.0f}ms",flush=True)
        np.save(folder / "scores.npy",np.asarray(all_scores,dtype=np.float32))
        config.update(status="completed",scores_sha256=digest((folder / "scores.npy").read_bytes()),
                      peak_gpu_allocated_mib=torch.cuda.max_memory_allocated()/1024**2 if args.device == "cuda" else None)
        save_config()
        report = {"configuration":config,"summary":{
            "dense_top10":summaries(results,"dense_evidence"),"candidate_pool30":summaries(results,"candidate_evidence"),
            "reranked_top10":summaries(results,"reranked_evidence"),
            "mean_rerank_latency_ms":mean(r["rerank_latency_ms"] for r in results),
            "median_rerank_latency_ms":median(r["rerank_latency_ms"] for r in results)},"results":results}
        (folder / "results.json").write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n")
        verify(folder,data)
        lines = ["# E5 top30 → BGE reranker → top10", "", "Evidence v2; unchanged E5 vectors/candidate scope. No total context-token cap. Both baseline and reranker return10 chunks; evidence availability in all30 candidates is diagnostic only. Q14 remains excluded from full-intent denominator.", "",
                 "| Query → document | Dense top10 | Reranked top10 | Evidence available in top30 |", "|---|---:|---:|---:|"]
        for direction in ["vi->vi","en->en","vi->en","en->vi"]:
            a=report["summary"]["dense_top10"][direction];b=report["summary"]["reranked_top10"][direction];c=report["summary"]["candidate_pool30"][direction]
            lines.append(f"| {direction} | {a['full_evidence_cases_at_10']}/19 | {b['full_evidence_cases_at_10']}/19 | {c['full_evidence_cases_at_30']}/19 |")
        lines += ["", "## Required evidence components /61", "", "| Direction | Dense top10 | Reranked top10 | Candidate top30 |", "|---|---:|---:|---:|"]
        for direction in ["vi->vi","en->en","vi->en","en->vi"]:
            a,b,c=[report["summary"][field][direction]["required_met_components"] for field in ["dense_top10","reranked_top10","candidate_pool30"]]
            lines.append(f"| {direction} | {a}/61 | {b}/61 | {c}/61 |")
        lines += ["", "## Gains and regressions", ""]
        for direction in ["vi->vi","en->en","vi->en","en->vi"]:
            gains=[r["intent_id"] for r in results if r["direction"] == direction and r["dense_evidence"]["full_evidence_success"] is False and r["reranked_evidence"]["full_evidence_success"] is True]
            losses=[r["intent_id"] for r in results if r["direction"] == direction and r["dense_evidence"]["full_evidence_success"] is True and r["reranked_evidence"]["full_evidence_success"] is False]
            lines.append(f"- {direction}: gained {', '.join(gains) or 'none'}; lost {', '.join(losses) or 'none'}.")
        lines += ["",f"Local30-pair reranking: mean {report['summary']['mean_rerank_latency_ms']:.0f}ms, median {report['summary']['median_rerank_latency_ms']:.0f}ms. Device {config['gpu_name']}; dtype {config['dtype']}; batch{args.batch_size}. Load/warmup excluded.","",
                  f"Per-pair preflight: max{max(lengths)} tokens, model limit configured{args.max_pair_tokens}, zero truncated inputs. This per-pair limit is not a context-token budget.","",config["limitations"],"", "All saved scores, candidate retrieval and evidence views independently replayed by --verify-only. No production retrieval, embedding service, database/index or LLM changes."]
        (folder / "comparison.md").write_text("\n".join(lines)+"\n")
        print(json.dumps({"output":str(folder),"summary":report["summary"]},indent=2),flush=True)
    except Exception as error:
        config.update(status="failed",error_type=type(error).__name__)
        save_config()
        raise


if __name__ == "__main__":
    main()
