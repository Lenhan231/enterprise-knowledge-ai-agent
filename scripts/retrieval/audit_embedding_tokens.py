#!/usr/bin/env python3
"""Audit a frozen parser corpus against its tokenizer and packaged encoder defaults.

Reads cached tokenizer/config files only; runtime encoder overrides are not measured.
No model weights, inference or DB writes.
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=Path, required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--revision")
    parser.add_argument("--configured-limit", type=int, default=512)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.configured_limit < 1:
        parser.error("--configured-limit must be positive")
    from huggingface_hub import hf_hub_download
    from transformers import AutoTokenizer
    from core.tokenization.token_counter import TokenCounter
    from core.tokenization.embedding_chunker import _context_prefix
    config_path = Path(hf_hub_download(args.model, "sentence_bert_config.json",
                                      revision=args.revision, local_files_only=True))
    revision = config_path.parent.name
    native = json.loads(config_path.read_text())["max_seq_length"]
    counter = TokenCounter.__new__(TokenCounter)
    counter.tokenizer = AutoTokenizer.from_pretrained(
        args.model, revision=revision, use_fast=True, local_files_only=True)
    special = counter.tokenizer.num_special_tokens_to_add(pair=False)
    raw = args.corpus.read_bytes()
    rows = [json.loads(line) for line in raw.decode().splitlines() if line.strip()]
    if not rows:
        parser.error("Corpus is empty")
    report = {"model_id": args.model, "cached_revision": revision,
              "corpus_sha256": hashlib.sha256(raw).hexdigest(),
              "tokenizer_model_max_length": counter.tokenizer.model_max_length,
              "app_configured_limit": args.configured_limit,
              "sentence_transformers_default_limit": native, "special_tokens": special,
              "documents": [], "limitations": "Exposure to truncation under local encoder defaults; not an answer-loss benchmark or verification of hosted inference behavior. No application settings or database records changed."}
    for doc in sorted({row["document_id"] for row in rows}):
        subset = [row for row in rows if row["document_id"] == doc]
        counts = [counter.count(row["content"]) + special for row in subset]
        prefixes = [counter.count(_context_prefix(row["content"])[0]) + special for row in subset]
        report["documents"].append({
            "document_id": doc, "title": subset[0].get("document_title"),
            "parser_chunks": len(subset), "over_native_limit": sum(n > native for n in counts),
            "over_app_limit": sum(n > args.configured_limit for n in counts),
            "max_tokens_including_special": max(counts),
            "headers_alone_exceed_native_limit": sum(n >= native for n in prefixes)})
    report["total_chunks"] = len(rows)
    report["over_native_limit"] = sum(row["over_native_limit"] for row in report["documents"])
    report["over_native_percent"] = round(100 * report["over_native_limit"] / len(rows), 2)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({key: report[key] for key in
                      ("model_id", "sentence_transformers_default_limit", "total_chunks",
                       "over_native_limit", "over_native_percent")}, indent=2))


if __name__ == "__main__":
    main()
