#!/usr/bin/env python3
"""One-folder benchmark: verify, review, prepare, run, verify-run.

No network/model calls in verify/review/verify-run. prepare explicitly opts in to
question-only Groq calls plus read-only PG lexeme extraction. run reuses saved
translations and document vectors; local cache only unless --allow-download.
"""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import itertools
import json
import os
from pathlib import Path
import sys
from time import perf_counter, sleep

HOME = Path(__file__).resolve().parent
sys.path.insert(0, str(HOME / "code"))
import numpy as np
from core.evaluation.evidence_metrics import score_evidence
from core.evaluation.retrieval_metrics import precision_at_k, recall_at_k, reciprocal_rank, ndcg_at_k
from core.retrieval.methods import translated_hybrid
from core.retrieval.retrieval import RetrievalRequest, RetrievedChunk, make_chunk_id
from fresh_translated_candidates import FrozenRepository, SavedTranslator


def read(path):
    return json.loads(Path(path).read_text())


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def check(condition, message):
    if not condition:
        raise ValueError(message)


def load():
    manifest = read(HOME / "manifest.json")
    for name, digest in manifest["files"].items():
        check(sha(HOME / name) == digest, "Changed frozen input/code: " + name)
    data = {"protocol": read(HOME / "protocol.json"), "labels": read(HOME / "evidence.json"),
            "questions": read(HOME / "questions.json")["intents"], "cases": read(HOME / "cases.json")["cases"]}
    data["rows"] = [json.loads(line) for line in (HOME / "inputs/corpus.jsonl").read_text().splitlines()]
    data["vectors"] = np.load(HOME / "inputs/document_vectors.npy", allow_pickle=False)
    data["sources"] = {lang: {(r["document_id"], r.get("parser_chunk_index", r.get("chunk_index"))): r["content"]
                              for r in map(json.loads, (HOME / f"inputs/parser_{lang}.jsonl").read_text().splitlines())}
                       for lang in ("vi", "en")}
    data["byid"] = {make_chunk_id(r["document_id"], r["chunk_index"]): r for r in data["rows"]}
    check(len(data["byid"]) == len(data["rows"]) == 1063, "Invalid corpus identities")
    check(data["vectors"].shape == (1063,768) and np.isfinite(data["vectors"]).all()
          and np.allclose(np.linalg.norm(data["vectors"], axis=1), 1, atol=1e-5), "Invalid E5 vectors")
    check(all(r["metadata"].get("fiscal_year") is None for r in data["rows"]),
          "Frozen adapter assumes no fiscal-year priority; use a new protocol for changed corpus")
    return data


def evidence(data, case, ranking):
    rows = [data["byid"][key] for key in ranking]
    return score_evidence(data["labels"], case["intent_id"], case["target_language"],
        [{"text": r["content"], "metadata": r["metadata"]} for r in rows],
        data["sources"][case["target_language"]], k=max(1,len(rows)))


def gold(data):
    answer = {}; audit = []
    for intent in data["questions"]:
        for lang in ("vi", "en"):
            case = next(c for c in data["cases"] if c["intent_id"] == intent["id"] and c["target_language"] == lang)
            eligible = [make_chunk_id(r["document_id"], r["chunk_index"]) for r in data["rows"] if r["language"] == lang]
            check(evidence(data, case, eligible)["full_evidence_success"], "Full corpus cannot answer " + case["id"])
            check(not evidence(data, case, [])["full_evidence_success"], "Empty evidence passed " + case["id"])
            relevant = [key for key in eligible if any(v["covered_characters"] > 0 for v in evidence(data, case, [key])["span_coverage"].values())]
            check(relevant, "No mapped gold chunks")
            if intent["category"] == "multi_chunk":
                check(not any(evidence(data, case, [key])["full_evidence_success"] for key in relevant),
                      "Claimed multi-chunk question is answerable from one chunk: " + case["id"])
                check(any(evidence(data, case, list(pair))["full_evidence_success"] for pair in itertools.combinations(relevant,2)),
                      "Multi-chunk label requires more than the planned two chunks: " + case["id"])
            answer[(intent["id"],lang)] = set(relevant)
            audit.append({"intent_id":intent["id"],"target_language":lang,"relevant_chunks":relevant,
                          "multi_chunk_checked":intent["category"] == "multi_chunk"})
    return answer, audit


def values(data, case, ranking, qrels):
    top = ranking[:10]
    check(len(top) == len(set(top)), "Duplicate ranked chunk IDs")
    check(all(key in data["byid"] and data["byid"][key]["language"] == case["target_language"] for key in ranking),
          "Ranking violates target-language corpus scope")
    score = evidence(data, case, top)
    return {"precision_at_10":precision_at_k(qrels,top,10),"recall_at_10":recall_at_k(qrels,top,10),
            "mrr_at_10":reciprocal_rank(qrels,top),"ndcg_at_10":ndcg_at_k(qrels,top,10),
            "full_evidence_at_10":float(score["full_evidence_success"]),
            "component_coverage_at_10":score["required_coverage"],"required_met":score["required_met"],
            "required_total":score["required_ready"],"missing_components":[r["id"] for r in score["requirements"] if r["required"] and not r["complete"]]}


def verify(data):
    cases = data["cases"]
    check(len(data["questions"]) == 20 and len(cases) == 80 and len({c["id"] for c in cases}) == 80, "Expected 20 intents/80 unique cases")
    check(Counter(q["category"] for q in data["questions"]) == dict.fromkeys(["narrative","table_numeric","multi_chunk","paraphrase_terminology"],5), "Wrong category balance")
    check(len({(c["query_language"],c["question"]) for c in cases}) == 40, "Expected40 question texts")
    check(Counter(c["direction"] for c in cases) == dict.fromkeys(["vi->vi","vi->en","en->vi","en->en"],20), "Wrong direction balance")
    _, mapped = gold(data)
    report = {"status":"passed","intents":20,"question_texts":40,"cases":80,
        "requirements":sum(len(i["requirements"]) for i in data["labels"]["intents"]),"spans":len(data["labels"]["spans"]),
        "full_and_empty_oracle_pairs":40,"multi_chunk_two_anchor_checks":10,"source_mapping":"exact hash/character coverage validated",
        "human_review":read(HOME / "review-status.json") if (HOME / "review-status.json").exists() else "pending",
        "model_inference":False,"external_api_calls":False}
    save(HOME / "validation.json",report)
    save(HOME / "gold-chunk-map.json",mapped)
    print(json.dumps(report,indent=2))


def prepare(data, allow_groq):
    check(allow_groq,"Explicit --allow-groq required: sends only40 simulated question texts to Groq, not labels or documents")
    from dotenv import load_dotenv
    from core.llm.groq_provider import GroqProvider
    from core.retrieval.query_translator import QueryTranslator
    from core.retrieval.methods.common import lexical_tsquery
    import psycopg
    load_dotenv()
    folder=HOME / "prepared"
    check(not (folder / "manifest.json").exists(),"Prepared inputs already frozen; reuse them, do not regenerate after seeing results")
    texts=[q["question"][lang] for q in data["questions"] for lang in ("vi","en")]
    path=folder / "translations.json"
    previous=read(path) if path.exists() else {"records":[],"questions_sha256":sha(HOME/"questions.json")}
    check(previous["questions_sha256"]==sha(HOME/"questions.json"),"Questions changed during translation preparation")
    llm=GroqProvider()
    check(llm.model_name==data["protocol"]["translation_model"],"Use the pinned protocol GROQ_MODEL")
    translator=QueryTranslator(llm);records=previous["records"]
    try:
        for question in texts:
            if any(r["question"]==question for r in records):continue
            start=perf_counter();llm.last_usage=None
            try:queries=translator.translate(question,"auto");error=None
            except Exception as exc:queries=None;error=type(exc).__name__
            records.append({"question":question,"queries":queries,"error":error,"api_seconds":perf_counter()-start,"usage":llm.last_usage})
            save(path,{"model":llm.model_name,"questions_sha256":sha(HOME/"questions.json"),"operator_opt_in":"--allow-groq; only original question text sent","records":records})
            print(f"Translations {len(records)}/40: {error or 'ok'}",flush=True)
            sleep(2)
    finally:llm.close()
    check(len(records)==40 and any(r["queries"] for r in records),"Incomplete/all-failed translations")
    alltexts=list(dict.fromkeys(texts+[t for r in records if r["queries"] for t in r["queries"].values()]))
    sql="SELECT d.ordinality-1, coalesce((SELECT jsonb_object_agg(t.lexeme,cardinality(t.positions)) FROM unnest(to_tsvector('simple',d.text)) AS t(lexeme,positions,weights)), '{}'::jsonb) FROM unnest(%s::text[]) WITH ORDINALITY AS d(text,ordinality) ORDER BY d.ordinality"
    with psycopg.connect(os.environ["DATABASE_URL"],connect_timeout=15) as conn:
        conn.execute("SET TRANSACTION READ ONLY")
        results=conn.execute(sql,([lexical_tsquery(t) for t in alltexts],)).fetchall()
        version=conn.execute("SELECT version()").fetchone()[0]
        conn.rollback()
    save(folder/"query_terms.json",{"query_terms":{text:list(row[1]) for text,row in zip(alltexts,results,strict=True)},"postgres_version":version,"readonly":True})
    save(folder/"manifest.json",{"dataset_manifest_sha256":sha(HOME/"manifest.json"),"files":{n:sha(folder/n) for n in ["translations.json","query_terms.json"]},"translation_failures":sum(r["error"] is not None for r in records)})
    print("Prepared inputs frozen. Reuse for every method/rerun; do not correct translations based on outcomes.")


class SQLRepository:
    def __init__(self,conn):self.conn=conn
    def similarity_search(self,vector,limit,*,query,method,**filters):
        from core.retrieval.methods import dense,bm25
        if method=="dense":return dense.search(self,vector,limit,query=query,**filters)
        if method=="bm25":return bm25.search(self,limit,query=query,**filters)
        raise ValueError("Unexpected method")


def sql_repository(data):
    import psycopg
    from psycopg.types.json import Jsonb
    from pgvector.psycopg import register_vector
    from dotenv import load_dotenv
    load_dotenv()
    conn=psycopg.connect(os.environ["DATABASE_URL"],connect_timeout=15)
    try:
        register_vector(conn)
        conn.execute("SET LOCAL statement_timeout='30s'")
        conn.execute("CREATE TEMP TABLE documents (document_id text PRIMARY KEY, document_type text, title text, source_url text, fiscal_year text, company text, allowed_roles text[], processing_status text, knowledge_base_active boolean) ON COMMIT DROP")
        conn.execute("CREATE TEMP TABLE document_chunks (id bigint PRIMARY KEY, document_name text, chunk_index int, content text, metadata jsonb, embedding vector(768)) ON COMMIT DROP")
        docs={r["document_id"]:(r["document_id"],r["metadata"].get("document_type"),r["document_name"],r["metadata"].get("source_url"),None,r["metadata"].get("company"),r["allowed_roles"],"ready",True) for r in data["rows"]}
        with conn.cursor() as cursor:
            cursor.executemany("INSERT INTO documents VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",list(docs.values()))
            cursor.executemany("INSERT INTO document_chunks VALUES (%s,%s,%s,%s,%s,%s)",[(i+1,r["document_name"],r["chunk_index"],r["content"],Jsonb(r["metadata"]),data["vectors"][i]) for i,r in enumerate(data["rows"])])
        namespace=conn.execute("SELECT n.nspname FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE c.oid='document_chunks'::regclass").fetchone()[0]
        check(namespace.startswith("pg_temp_"),"Refusing non-temporary benchmark table")
        conn.execute("ANALYZE documents");conn.execute("ANALYZE document_chunks")
        return SQLRepository(conn),conn
    except Exception:
        conn.rollback();conn.close();raise


def summaries(records):
    fields=["precision_at_10","recall_at_10","mrr_at_10","ndcg_at_10","full_evidence_at_10","component_coverage_at_10"]
    result={}
    for method in records[0]["methods"]:
        result[method]={}
        for group in ["all"]+sorted({r["direction"] for r in records})+sorted({r["category"] for r in records}):
            rows=[r["methods"][method] for r in records if group in ("all",r["direction"],r["category"])]
            item={"cases":len(rows),**{f:float(np.mean([r[f] for r in rows])) for f in fields},
                  "complete_cases":sum(r["full_evidence_at_10"] for r in rows),"components_met":sum(r["required_met"] for r in rows),"components_total":sum(r["required_total"] for r in rows)}
            if all("latency_ms" in r for r in rows):
                timings=[r["latency_ms"] for r in rows]
                item.update(mean_latency_ms=float(np.mean(timings)),median_latency_ms=float(np.median(timings)),p95_latency_ms=float(np.quantile(timings,.95)))
            result[method][group]=item
    return result


def run(data,args):
    prepared=read(HOME/"prepared/manifest.json")
    check(prepared["dataset_manifest_sha256"]==sha(HOME/"manifest.json"),"Prepared inputs belong to a different dataset")
    for name,digest in prepared["files"].items():check(sha(HOME/"prepared"/name)==digest,"Changed prepared input: "+name)
    output=(HOME/"runs"/(args.name or datetime.now(timezone.utc).strftime("run-%Y%m%dT%H%M%SZ")))
    check(output.resolve().is_relative_to((HOME/"runs").resolve()),"Output must remain under this package runs/")
    check(not output.exists(),"Run exists; choose a new --name to preserve results")
    import torch
    from sentence_transformers import SentenceTransformer,CrossEncoder
    check(torch.cuda.is_available(),"CUDA required; no automatic CPU fallback")
    torch.set_num_threads(4);torch.manual_seed(data["protocol"]["seed"])
    torch.backends.cuda.matmul.allow_tf32=False;torch.backends.cudnn.allow_tf32=False
    protocol=data["protocol"]
    e5=SentenceTransformer(protocol["e5_model"],revision=protocol["e5_revision"],device="cuda",local_files_only=not args.allow_download,model_kwargs={"torch_dtype":torch.float32})
    e5.max_seq_length=512
    texts=list(dict.fromkeys(c["question"] for c in data["cases"]))
    check(max(len(e5.tokenizer.encode("query: "+q)) for q in texts)<=512,"Question truncation would occur")
    e5.encode(["query: warmup"],normalize_embeddings=True,prompt="",show_progress_bar=False)
    unique={};encoding_ms={}
    for q in texts:
        torch.cuda.synchronize();start=perf_counter()
        unique[q]=e5.encode(["query: "+q],normalize_embeddings=True,prompt="",show_progress_bar=False,convert_to_numpy=True)[0]
        torch.cuda.synchronize();encoding_ms[q]=(perf_counter()-start)*1000
    vectors=np.asarray([unique[c["question"]] for c in data["cases"]],dtype=np.float32)
    del e5
    import gc
    gc.collect();torch.cuda.empty_cache()
    model=CrossEncoder(protocol["reranker_model"],revision=protocol["reranker_revision"],device="cuda",max_length=1024,local_files_only=not args.allow_download,model_kwargs={"torch_dtype":torch.float32})
    model.predict([(texts[0],data["rows"][0]["content"])],show_progress_bar=False,activation_fn=torch.nn.Identity())
    translation=read(HOME/"prepared/translations.json")
    translator=SavedTranslator({r["question"]:r for r in translation["records"]},translation["model"])
    terms=read(HOME/"prepared/query_terms.json")["query_terms"]
    doc_terms=read(HOME/"inputs/document_terms.json")["document_terms"]
    conn=None
    repository=FrozenRepository(data["rows"],data["vectors"],doc_terms,terms)
    if args.backend=="sql":repository,conn=sql_repository(data)
    output.mkdir()
    np.save(output/"query_vectors.npy",vectors)
    qrels,mapping=gold(data);save(output/"gold-chunk-map.json",mapping)
    config={"status":"running","dataset_manifest_sha256":sha(HOME/"manifest.json"),"prepared_manifest_sha256":sha(HOME/"prepared/manifest.json"),"backend":args.backend,"protocol":protocol,"gpu":torch.cuda.get_device_name(0),"torch_version":torch.__version__,"external_api_calls":0,"document_vectors_reused":True,"persistent_database_writes":False,"timing":"warm stages; shared fresh query encoding per case; cached translator; excludes API translation/generation/model startup; raw translated-hybrid timing is its pre-rerank stage","review_status":read(HOME/"review-status.json") if (HOME/"review-status.json").exists() else "assistant_prepared_pending_human_review","cases_completed":0}
    records=[];matrices={m:np.full((80,30),np.nan,dtype=np.float32) for m in ["dense_bge","translated_hybrid_bge"]}
    language_map={r["document_id"]:"vn" if r["language"]=="vi" else "en" for r in data["rows"]}
    rng=np.random.default_rng(protocol["seed"])
    try:
        for n,(case,vector) in enumerate(zip(data["cases"],vectors)):
            scope=sorted({r["document_id"] for r in data["rows"] if r["language"]==case["target_language"]})
            filters={"roles":case["allowed_roles"],"document_ids":scope}
            record={**case,"methods":{}}
            for arm in rng.permutation(["dense","dense_bge","translated_hybrid_bge"]):
                torch.cuda.synchronize();start=perf_counter()
                if arm=="translated_hybrid_bge":
                    chunks,details=translated_hybrid.search(repository,vector,RetrievalRequest(query=case["question"],top_k=30),lambda:translator,document_languages={d:language_map[d] for d in scope},**filters)
                else:chunks=repository.similarity_search(vector,30,query=case["question"],method="dense",**filters);details={}
                candidate_ms=(perf_counter()-start)*1000
                candidates=[make_chunk_id(c.document_id,c.chunk_index) for c in chunks]
                check(len(candidates)==30,"Expected30 candidates")
                ranking=candidates;rerank_ms=0.0
                if arm!="dense":
                    pairs=[(case["question"],c.content) for c in chunks]
                    check(max(map(len,model.tokenizer([a for a,b in pairs],[b for a,b in pairs],truncation=False)["input_ids"]))<=1024,"Pair truncation would occur")
                    torch.cuda.synchronize();start=perf_counter()
                    scores=np.asarray(model.predict(pairs,batch_size=4,show_progress_bar=False,activation_fn=torch.nn.Identity(),convert_to_numpy=True),dtype=np.float32).reshape(-1)
                    torch.cuda.synchronize();rerank_ms=(perf_counter()-start)*1000
                    check(scores.shape==(30,) and np.isfinite(scores).all(),"Incomplete reranker scores")
                    matrices[str(arm)][n]=scores
                    ranking=[candidates[i] for i in np.argsort(-scores,kind="stable")]
                result=values(data,case,ranking,qrels[(case["intent_id"],case["target_language"])])
                result.update(candidates=candidates,ranking=ranking,query_ms=encoding_ms[case["question"]],candidate_ms=candidate_ms,rerank_ms=rerank_ms,latency_ms=encoding_ms[case["question"]]+candidate_ms+rerank_ms,retrieval_details=details)
                record["methods"][str(arm)]=result
                if arm=="translated_hybrid_bge":
                    raw=values(data,case,candidates,qrels[(case["intent_id"],case["target_language"])])
                    raw.update(ranking=candidates,candidates=candidates,latency_ms=encoding_ms[case["question"]]+candidate_ms)
                    record["methods"]["translated_hybrid_raw"]=raw
            # Canonical method order independent of randomized timing order.
            record["methods"]={m:record["methods"][m] for m in ["dense","dense_bge","translated_hybrid_raw","translated_hybrid_bge"]}
            records.append(record);config["cases_completed"]=len(records)
            for arm,matrix in matrices.items():np.save(output/(arm+"-scores.npy"),matrix)
            save(output/"config.json",config);save(output/"results.json",{"configuration":config,"results":records})
            print(f"{n+1}/80 {case['id']}",flush=True)
        config.update(status="completed",cuda_peak_allocated_bytes=torch.cuda.max_memory_allocated(),output_hashes={name:sha(output/name) for name in ["query_vectors.npy","dense_bge-scores.npy","translated_hybrid_bge-scores.npy"]})
        save(output/"config.json",config)
        save(output/"results.json",{"configuration":config,"summary":summaries(records),"results":records})
        import csv
        summary=summaries(records)
        with (output/"metrics.csv").open("w",newline="") as stream:
            first_group = next(iter(next(iter(summary.values())).values()))
            fields=["method","group",*first_group.keys()]
            writer=csv.DictWriter(stream,fieldnames=fields);writer.writeheader()
            for method,groups in summary.items():
                for group,v in groups.items():writer.writerow({"method":method,"group":group,**v})
        verify_run(data,output)
        print(str(output))
    except Exception as exc:
        config.update(status="failed",error_type=type(exc).__name__,error=str(exc));save(output/"config.json",config)
        raise
    finally:
        if conn is not None:conn.rollback();conn.close()


def verify_run(data,folder):
    report=read(folder/"results.json");config=read(folder/"config.json")
    check(report["configuration"]==config and config["status"]=="completed" and len(report["results"])==80,"Incomplete run")
    check(config["dataset_manifest_sha256"]==sha(HOME/"manifest.json"),"Wrong input version")
    check(config["prepared_manifest_sha256"]==sha(HOME/"prepared/manifest.json"),"Prepared inputs changed")
    for name,digest in read(HOME/"prepared/manifest.json")["files"].items():
        check(sha(HOME/"prepared"/name)==digest,"Changed prepared input: "+name)
    for name,digest in config["output_hashes"].items():check(sha(folder/name)==digest,"Changed output "+name)
    qrels,_=gold(data)
    matrices={m:np.load(folder/(m+"-scores.npy"),allow_pickle=False) for m in ["dense_bge","translated_hybrid_bge"]}
    query_vectors=np.load(folder/"query_vectors.npy",allow_pickle=False)
    check(query_vectors.shape==(80,768) and np.isfinite(query_vectors).all() and np.allclose(np.linalg.norm(query_vectors,axis=1),1,atol=1e-5),"Bad saved query vectors")
    for n,(case,record) in enumerate(zip(data["cases"],report["results"],strict=True)):
        check(case["id"]==record["id"],"Case order changed")
        check(set(record["methods"]) == {"dense","dense_bge","translated_hybrid_raw","translated_hybrid_bge"}, "Missing benchmark method")
        for method,result in record["methods"].items():
            expected=result["candidates"]
            if method in matrices:
                scores=matrices[method][n];check(scores.shape==(30,) and np.isfinite(scores).all(),"Incomplete logits")
                expected=[expected[i] for i in np.argsort(-scores,kind="stable")]
            check(expected==result["ranking"],"Ranking/logit replay mismatch")
            computed=values(data,case,expected,qrels[(case["intent_id"],case["target_language"])])
            check(computed=={k:result[k] for k in computed},"Metric/evidence replay mismatch")
    check(summaries(report["results"])==report["summary"],"Summary replay mismatch")
    save(folder/"verification.json",{"status":"passed","cases":80,"reranked_score_entries":4800,"metric_rank_evidence_replay":True,"limits":"Checks stored artifacts, not a fresh model inference or generated-answer accuracy"})
    print("Saved rankings/logits/metrics/evidence verified.")


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest="command",required=True)
    sub.add_parser("verify")
    review=sub.add_parser("review");review.add_argument("--reviewer",required=True)
    prep=sub.add_parser("prepare");prep.add_argument("--allow-groq",action="store_true")
    execution=sub.add_parser("run");execution.add_argument("--name");execution.add_argument("--backend",choices=["sql","offline"],default="sql");execution.add_argument("--allow-download",action="store_true")
    replay=sub.add_parser("verify-run");replay.add_argument("folder",type=Path)
    args=parser.parse_args();data=load()
    if args.command=="verify":verify(data)
    elif args.command=="review":
        check(bool(args.reviewer.strip()),"Reviewer must not be blank")
        save(HOME/"review-status.json",{"reviewer":args.reviewer,"status":"operator_confirmed_reviewed","manifest_sha256":sha(HOME/"manifest.json"),"note":"Operator self-reports reviewing VI/EN questions, source evidence and overlap audit; not independently certified."})
    elif args.command=="prepare":prepare(data,args.allow_groq)
    elif args.command=="run":run(data,args)
    else:verify_run(data,args.folder)


if __name__=="__main__":main()
