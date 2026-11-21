"""Experiment 1: re-chunk the VietStyle policy (VN + EN) with one chunking variant and write a corpus file.

  python evaluation/v3/rechunk.py <variant> <chunks.jsonl> <processing_outputs.jsonl> <out.jsonl>

Only the two policy PDFs have parser output; every other document keeps its production chunks and vectors, so a
variant changes exactly the policy chunks. New chunks get E5-base vectors (embedders.py, identical to production).
Variants: C0 production settings, C1 without the "Section:" heading line, C2 fixed strategy, C3 600/80, C4 2000/200.
"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from core.chunking.processor import ChunkingProcessor  # noqa: E402

VARIANTS = {"C0": ({}, True), "C1": ({}, False), "C2": ({"chunking_strategy": "fixed"}, True),
            "C3": ({"chunk_size": 600, "chunk_overlap": 80}, True), "C4": ({"chunk_size": 2000, "chunk_overlap": 200}, True)}
POLICY = {"VietStyle Enterprise Operating Policy v1.0 VN": "VietStyle_Enterprise_Operating_Policy_v1.0_VN.pdf",
          "VietStyle Enterprise Operating Policy v1.0 EN": "VietStyle_Enterprise_Operating_Policy_v1.0_EN.pdf"}
# Document-level metadata copied from the production chunks so ACL, joins and filters behave as in production.
DOC_KEYS = ("document_id", "allowed_roles", "company", "domain", "document_type", "filename", "format", "language", "title",
            "source_type", "knowledge_domains", "synthetic_company_policy")


def main(variant, chunks_path, outputs_path, out_path):
    config, keep_heading = VARIANTS[variant]
    production = [json.loads(line) for line in open(chunks_path, encoding="utf-8")]
    template = {}
    for row in production:
        template.setdefault(row["document_name"], row)
    rows = [row for row in production if row["document_name"] not in POLICY.values()]
    new = []
    next_id = max(r["id"] for r in production) + 1
    for line in open(outputs_path, encoding="utf-8"):
        parsed = json.loads(line)
        name = POLICY.get(parsed["title"])
        if not name:
            continue
        base = template[name]
        for chunk in ChunkingProcessor(config).process(parsed)["chunks"]:
            text = chunk["text"] if keep_heading else re.sub(r"^Section: [^\n]*\n", "", chunk["text"])
            metadata = {**{k: base["metadata"][k] for k in DOC_KEYS if k in base["metadata"]}, **chunk["metadata"]}
            new.append({**base, "id": next_id, "chunk_index": chunk["metadata"]["chunk_index"], "content": text,
                        "metadata": metadata, "embedding": None})
            next_id += 1
    from embedders import Embedder
    vectors = Embedder("e5base").embed_documents([r["content"] for r in new])
    for row, vector in zip(new, vectors):
        row["embedding"] = "[" + ",".join(f"{v:.7g}" for v in vector) + "]"
    with open(out_path, "w", encoding="utf-8") as out:
        for row in rows + new:
            out.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(variant, {name[-6:-4]: sum(1 for r in new if r["document_name"] == name) for name in POLICY.values()},
          "policy chunks; mean chars", round(sum(len(r["content"]) for r in new) / len(new)))


if __name__ == "__main__":
    main(*sys.argv[1:5])
