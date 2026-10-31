#!/usr/bin/env python3
"""Freeze shared provenance-bearing chunks and 4-direction cases; no encoder or DB."""
import argparse
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path

from evaluate_embedding_candidates import ROOT, MODELS, inputs_for, token_lengths, load_evidence_context
from validate_vietstyle_evidence import FOLDER, validate
from core.tokenization.embedding_chunker import build_embedding_chunks
from core.tokenization.token_counter import TokenCounter

CANDIDATES = ("multilingual-e5-base", "bge-m3", "qwen3-embedding-0.6b")
DEFAULT = FOLDER.parent / "dense-evidence-benchmark-v1"


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT)
    args = parser.parse_args()
    if args.output_dir.exists():
        parser.error("Output directory exists; choose a fresh --output-dir to preserve snapshots")
    raw = (FOLDER / "evidence.json").read_bytes()
    evidence = json.loads(raw)
    validate(evidence)
    revisions = {name: json.loads((ROOT / "artifacts/evaluation/embedding-comparison-20261018/candidates"
                                  / name / "config.json").read_text())["revision"] for name in CANDIDATES}
    from transformers import AutoTokenizer
    # One common chunk set for all models; reject overflow after model-specific prefixes.
    counter = TokenCounter.__new__(TokenCounter)
    chunk_model = "qwen3-embedding-0.6b"
    counter.tokenizer = AutoTokenizer.from_pretrained(MODELS[chunk_model]["model_id"],
                                                    revision=revisions[chunk_model], local_files_only=True)
    rows, questions = [], {}
    for language, source in evidence["sources"].items():
        parents = [json.loads(line) for line in (ROOT / source["path"]).read_text().splitlines()]
        documents = defaultdict(list)
        for parent in parents:
            documents[parent["document_id"]].append(parent)
        for doc_id, doc_parents in documents.items():
            parent = doc_parents[0]
            name = parent.get("document_name", parent["metadata"].get("filename"))
            roles = parent["allowed_roles"]
            chunks = build_embedding_chunks(doc_parents, counter, 512, MODELS[chunk_model]["model_id"])
            for chunk in chunks:
                meta = dict(chunk["metadata"], document_id=doc_id)
                rows.append({"document_id": doc_id, "document_name": name, "language": language,
                             "chunk_index": meta["chunk_index"], "content": chunk["text"],
                             "metadata": meta, "allowed_roles": roles})
        questions[language] = {q["id"]: q for q in json.loads(
            (ROOT / evidence["question_sources"][language]["path"]).read_text())["cases"]}
    cases = []
    for target in ("vi", "en"):
        for query in ("vi", "en"):
            for intent in evidence["intents"]:
                qid = intent["id"]
                expected = questions[target][qid]
                cases.append({"id": qid + "-" + query + "-to-" + target, "intent_id": qid,
                              "question": questions[query][qid]["question"], "query_language": query,
                              "target_language": target, "direction": query + "->" + target,
                              "allowed_roles": expected["allowed_roles"],
                              "expected_sources": expected["expected_sources"],
                              "unavailable_expected_sources": expected["unavailable_expected_sources"]})
    config = {"indexed_corpus": "indexed-corpus.jsonl", "cases": "cases.json",
              "document_ids": sorted({r["document_id"] for r in rows}), "candidate_revisions": revisions,
              "evidence": {"path": str((FOLDER / "evidence.json").relative_to(ROOT)), "sha256": digest(raw)}}
    load_evidence_context(config, cases, rows)
    audit = {}
    for name in CANDIDATES:
        tokenizer = AutoTokenizer.from_pretrained(MODELS[name]["model_id"], revision=revisions[name], local_files_only=True)
        passages, queries = inputs_for(MODELS[name], rows, cases)
        audit[name] = {"revision": revisions[name], "max_passage_tokens": max(token_lengths(tokenizer, passages, 512)),
                       "max_query_tokens": max(token_lengths(tokenizer, queries, 512)), "truncated_inputs": 0}
    corpus = "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows).encode()
    case_raw = (json.dumps({"cases": cases}, ensure_ascii=False, indent=2) + "\n").encode()
    config["indexed_corpus_sha256"] = digest(corpus)
    manifest = {"cases.json_sha256": digest(case_raw), "indexed-corpus.jsonl_sha256": digest(corpus),
                "sources": evidence["sources"], "question_sources": evidence["question_sources"],
                "evidence": config["evidence"], "chunks": len(rows), "cases": len(cases),
                "chunks_by_language": dict(Counter(r["language"] for r in rows)),
                "directions": dict(Counter(c["direction"] for c in cases)),
                "chunking": {"tokenizer_model": MODELS[chunk_model]["model_id"], "revision": revisions[chunk_model],
                             "max_tokens": 512, "method": "Shared build_embedding_chunks with exact source_spans; unchanged across encoders"},
                "scope": "All five documents in target language compete. Target-language restriction is experimental, not production language detection. Gold labels never filter/rank chunks.",
                "metric": "Required ready component coverage and complete-intent evidence success in top ten chunks; Q14 full-intent excluded",
                "independent_intents": 20,
                "code_sha256": {path: digest((ROOT / path).read_bytes()) for path in
                    ["scripts/retrieval/prepare_vietstyle_evidence_benchmark.py", "src/core/tokenization/embedding_chunker.py",
                     "src/core/tokenization/token_counter.py", "src/core/evaluation/evidence_metrics.py"]}}
    args.output_dir.mkdir(parents=True)
    (args.output_dir / "indexed-corpus.jsonl").write_bytes(corpus)
    (args.output_dir / "cases.json").write_bytes(case_raw)
    for filename, value in [("benchmark-config.json",config),("manifest.json",manifest),("all-model-token-preflight.json",audit)]:
        (args.output_dir / filename).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"output": str(args.output_dir), "chunks": len(rows), "cases": len(cases), "token_audit": audit}, indent=2))


if __name__ == "__main__":
    main()
