"""Collect pooled candidate passages per item for the relevance judge (judge job 2).

  python evaluation/v3/build_pool.py <chunks.jsonl> <runs_dir> <depth> <out.json>

Union of the top <depth> passages from every <set>-<method>.jsonl run, minus passages already in gold and minus
page furniture (headers, footers, the boilerplate ownership table), which is never an answer.
"""
import json
import sys
from pathlib import Path

HERE = Path("artifacts/evaluation/vietstyle-v3")
FURNITURE = ("VSC-OPS-POL-001 ·", "VIETSTYLE COMMERCE | CHÍNH SÁCH", "VIETSTYLE COMMERCE | ENTERPRISE", "TRANG CHÍNH SÁCH",
             "POLICY PAGE", "column_1: Đơn vị chịu trách nhiệm", "column_1: Responsible unit", "column_1: Accountable")


def main(chunks_path, runs_dir, depth, out_path):
    corpus = {(r["document_name"], r["chunk_index"]): r for r in map(json.loads, open(chunks_path, encoding="utf-8"))}
    depth, pool = int(depth), []
    for name in ("dev", "test"):
        items = {i["id"]: i for i in json.load(open(HERE / f"{name}-v3.json", encoding="utf-8"))["items"]}
        candidates = {item_id: {} for item_id in items}
        for run in sorted(Path(runs_dir).glob(f"{name}-*.jsonl")):
            for line in open(run, encoding="utf-8"):
                row = json.loads(line)
                for rank, hit in enumerate(row["ranked"][:depth], 1):
                    candidates[row["id"]].setdefault((hit["document"], hit["chunk_index"]), []).append(f"{row['method']}#{rank}")
        for item_id, item in items.items():
            gold = {(g["document"], g["chunk_index"]) for g in item["gold"]}
            keep = []
            for key, found_by in candidates[item_id].items():
                text = corpus[key]["content"]
                if key in gold or any(marker in text for marker in FURNITURE):
                    continue
                keep.append({"document": key[0], "chunk_index": key[1], "found_by": found_by, "text": text})
            pool.append({"id": item_id, "set": name, "category": item["category"], "role": item["role"],
                         "question": item["question"], "history": item["history"], "expected_outcome": item["expected_outcome"],
                         "reference_answer": item["reference_answer"],
                         "gold": [{"document": g["document"], "chunk_index": g["chunk_index"], "grade": g["grade"]} for g in item["gold"]],
                         "candidates": keep})
    json.dump(pool, open(out_path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    sizes = [len(p["candidates"]) for p in pool]
    print(f"{len(pool)} items, {sum(sizes)} candidates (max {max(sizes)}, mean {sum(sizes) / len(sizes):.1f}) -> {out_path}")


if __name__ == "__main__":
    main(*sys.argv[1:5])
