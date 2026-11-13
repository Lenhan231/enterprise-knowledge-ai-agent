#!/usr/bin/env python3
"""Rebuild complete old PDFs locally; retain page labels, never stale chunk IDs."""
import collections
import concurrent.futures
import hashlib
import json
import os
import re
import subprocess
import unicodedata
from pathlib import Path

import fitz

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "artifacts/evaluation/four-direction-20261018"
SOURCES = {"annual_report": ("AnnualReport_2008.pdf", "en"),
           "long_hau_fs": ("2.BCTC da kiem toan 2008 (V).pdf", "vi")}

def digest(data):
    return hashlib.sha256(data).hexdigest()

def tokens(text):
    plain = "".join(c for c in unicodedata.normalize("NFD", text.lower()) if unicodedata.category(c) != "Mn")
    return set(re.findall(r"[a-z0-9]+", plain))

def extract_page(job):
    source, filename, language, number = job
    with fitz.open(ROOT / "data/raw/benchmark_data" / filename) as pdf:
        page = pdf[number - 1]
        text = page.get_text()
        method = "pymupdf"
        if not text.strip():
            image = page.get_pixmap(dpi=200).tobytes("png")
            text = subprocess.run(["tesseract", "stdin", "stdout", "-l", "vie+eng" if language == "vi" else "eng", "--psm", "3"],
                                  input=image, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True,
                                  timeout=180, env={**os.environ, "OMP_THREAD_LIMIT": "1"}).stdout.decode()
            method = "tesseract-5.3.4-200dpi-psm3"
    print(source, number, method, len(text), flush=True)
    return {"document_id": source, "document_name": filename, "language": language,
            "page_number": number, "content": text, "extraction": method}

def main():
    OUT.mkdir(parents=True, exist_ok=True)
    pages_path = OUT / "pages.jsonl"
    if pages_path.exists():
        pages = [json.loads(x) for x in pages_path.read_text().splitlines()]
    else:
        jobs = []
        for source, (filename, language) in SOURCES.items():
            with fitz.open(ROOT / "data/raw/benchmark_data" / filename) as pdf:
                jobs.extend((source, filename, language, n + 1) for n in range(len(pdf)))
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            pages = list(pool.map(extract_page, jobs))
        pages_path.write_text("".join(json.dumps(p, ensure_ascii=False) + "\n" for p in pages))
    assert len(pages) == 118
    rows = []
    indices = collections.Counter()
    for page in pages:
        words = list(re.finditer(r"\S+", page["content"]))
        for start in range(0, len(words), 48):
            end = min(start + 60, len(words))
            text = page["content"][words[start].start():words[end - 1].end()]
            source = page["document_id"]
            rows.append({"document_id": source, "document_name": page["document_name"],
                         "chunk_index": indices[source], "content": text, "allowed_roles": ["admin"],
                         "metadata": {"document_id": source, "page_number": page["page_number"],
                                      "language": page["language"], "word_start": start, "word_end": end}})
            indices[source] += 1
            if end == len(words):
                break
    paired = {lang: json.loads((ROOT / "data/evaluation" / name).read_text()) for lang, name in
              [("vi", "long_hau_2008_cases.json"), ("en", "long_hau_2008_cases_en.json")]}
    assert len(paired["vi"]) == len(paired["en"]) == 24
    cases = []
    for vi, en in zip(paired["vi"], paired["en"]):
        assert vi["id"] == en["id"] and vi["evidence"] == en["evidence"]
        for lang, original in [("vi", vi), ("en", en)]:
            sources = {e["source"] for e in original["evidence"]}
            target = SOURCES[next(iter(sources))][1] if len(sources) == 1 else "mixed"
            gold = sorted({e["source"] + "::page::" + str(e["page_number"]) for e in original["evidence"]})
            cases.append({"id": original["id"] + "-" + lang, "intent_id": original["id"],
                          "question": original["question"], "query_language": lang, "direction": lang + "->" + target,
                          "allowed_roles": ["admin"], "expected_sources": sorted(SOURCES[s][0] for s in sources),
                          "unavailable_expected_sources": [], "gold_pages": gold, "original_evidence": original["evidence"]})
    # Validate all candidate tokenizers before spending GPU time on any model.
    import os
    os.environ["HF_HUB_OFFLINE"] = "1"
    from transformers import AutoTokenizer
    from evaluate_embedding_candidates import MODELS, inputs_for, token_lengths
    token_audit = {}
    prior = ROOT / "artifacts/evaluation/embedding-comparison-20261018/candidates"
    for name in ["multilingual-e5-base", "bge-m3", "qwen3-embedding-0.6b"]:
        revision = json.loads((prior / name / "config.json").read_text())["revision"]
        tokenizer = AutoTokenizer.from_pretrained(MODELS[name]["model_id"], revision=revision, local_files_only=True)
        passages, queries = inputs_for(MODELS[name], rows, cases)
        token_audit[name] = {"revision": revision, "max_passage_tokens": max(token_lengths(tokenizer, passages, 512)),
                             "max_query_tokens": max(token_lengths(tokenizer, queries, 512)), "truncated_inputs": 0}
    (OUT / "all-model-token-preflight.json").write_text(json.dumps(token_audit, indent=2))
    indexed_pages = {p["document_id"] + "::page::" + str(p["page_number"]): p for p in pages}
    for c in cases:
        assert all(g in indexed_pages and indexed_pages[g]["content"].strip() for g in c["gold_pages"])
    # Saved original evidence is used for page validation only, never to build/rank chunks.
    saved = json.loads((OUT / "retained-original-contexts.json").read_text())
    oldids = {"annual_report": "UPLOAD-11e62199551047c0a1ddcd5e6684a1c1", "long_hau_fs": "UPLOAD-5149fb823530440da1a2f09704c695d6"}
    old = {(source, x["chunk_index"]): x for source, doc in oldids.items() for x in saved[doc]}
    checks = []
    for c in paired["vi"]:
        for e in c["evidence"]:
            oldrow = old[(e["source"], e["chunk_index"])]
            assert oldrow.get("page_number", oldrow.get("metadata", {}).get("page_number", e["page_number"])) == e["page_number"]
            page = indexed_pages[e["source"] + "::page::" + str(e["page_number"])]
            a, b = tokens(oldrow["content"]), tokens(page["content"])
            checks.append({"id": c["id"], **e, "old_evidence_token_coverage": len(a & b) / len(a),
                           "old_evidence_excerpt": oldrow["content"][:500]})
    (OUT / "evidence-validation.json").write_text(json.dumps(checks, ensure_ascii=False, indent=2))
    corpus = "".join(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n" for r in rows).encode()
    case_bytes = (json.dumps({"cases": cases}, ensure_ascii=False, indent=2) + "\n").encode()
    (OUT / "indexed-corpus.jsonl").write_bytes(corpus)
    (OUT / "cases.json").write_bytes(case_bytes)
    (OUT / "benchmark-config.json").write_text(json.dumps({"indexed_corpus": "indexed-corpus.jsonl", "indexed_corpus_sha256": digest(corpus),
                                                          "cases": "cases.json", "document_ids": list(SOURCES)}, indent=2))
    manifest = {"cases.json_sha256": digest(case_bytes), "pages_sha256": digest(pages_path.read_bytes()),
                "original_pdf_sha256": {name: digest((ROOT / "data/raw/benchmark_data" / name).read_bytes()) for name, _ in SOURCES.values()},
                "chunks": len(rows), "pages": len(pages), "chunks_by_document": dict(indices), "chunking": "60 whitespace words, 12-word overlap, page boundaries preserved",
                "directions": dict(collections.Counter(c["direction"] for c in cases)), "empty_pages": [k for k, p in indexed_pages.items() if not p["content"].strip()],
                "metric": "gold evidence page coverage among top 10 chunks; page labels retained, old chunk indices not reused",
                "scope": "Both complete reports compete for every question; language/gold labels never restrict ranking"}
    (OUT / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2))
    print(json.dumps(manifest, indent=2)); print("MIN_EVIDENCE_COVERAGE", min(c["old_evidence_token_coverage"] for c in checks))

if __name__ == "__main__":
    main()
