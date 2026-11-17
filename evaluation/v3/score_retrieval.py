"""Score retrieval runs against a v3 set (SPEC.md "Metrics").

  python evaluation/v3/score_retrieval.py <dev|test> <run.jsonl> [<run.jsonl> ...] [--json out.json]

Answer items (expected_outcome "answer"): Hit@K and Recall@K, Precision@K and MRR on grade-2 passages; nDCG@K on graded
gold (gain 2^grade - 1). RBAC denial items: leak rate = a forbidden document appears in the top 10. Latency p50/p95.
"""
import json
import math
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parents[2] / "artifacts/evaluation/vietstyle-v3"
KS = (1, 5, 10)


def item_metrics(ranked, gold):
    grades = {(g["document"], g["chunk_index"]): g["grade"] for g in gold}
    relevant = {key for key, grade in grades.items() if grade == 2}
    keys = [(r["document"], r["chunk_index"]) for r in ranked]
    first = next((rank for rank, key in enumerate(keys, 1) if key in relevant), None)
    out = {"mrr": 1 / first if first else 0.0}
    ideal = sorted((2 ** g - 1 for g in grades.values()), reverse=True)
    for k in KS:
        top = keys[:k]
        found = sum(1 for key in top if key in relevant)
        out[f"hit@{k}"] = float(found > 0)
        out[f"recall@{k}"] = found / len(relevant)
        out[f"precision@{k}"] = found / k
        dcg = sum((2 ** grades.get(key, 0) - 1) / math.log2(rank + 1) for rank, key in enumerate(top, 1))
        idcg = sum(gain / math.log2(rank + 1) for rank, gain in enumerate(ideal[:k], 1))
        out[f"ndcg@{k}"] = dcg / idcg if idcg else 0.0
    return out


def percentile(values, q):
    values = sorted(values)
    return values[min(len(values) - 1, int(round(q * (len(values) - 1))))] if values else None


def score(set_name, run_path):
    items = {i["id"]: i for i in json.load(open(HERE / f"{set_name}-v3.json", encoding="utf-8"))["items"]}
    rows = [json.loads(line) for line in open(run_path, encoding="utf-8")]
    overall, by_category, leaks, denials, latency = defaultdict(list), defaultdict(lambda: defaultdict(list)), 0, 0, []
    for row in rows:
        item = items[row["id"]]
        latency.append(row["latency_ms"])
        if item["forbidden_documents"]:
            denials += 1
            leaks += any(r["document"] in item["forbidden_documents"] for r in row["ranked"][:10])
        if item["expected_outcome"] != "answer" or not any(g["grade"] == 2 for g in item["gold"]):
            continue
        for name, value in item_metrics(row["ranked"], item["gold"]).items():
            overall[name].append(value)
            by_category[item["category"]][name].append(value)
    mean = lambda values: round(sum(values) / len(values), 4) if values else None
    return {"run": Path(run_path).stem, "items": len(rows), "scored": len(overall["mrr"]),
            "metrics": {k: mean(v) for k, v in overall.items()},
            "by_category": {c: {k: mean(v) for k, v in m.items() if k in ("hit@5", "mrr", "ndcg@10")} for c, m in sorted(by_category.items())},
            "rbac_leak_rate": leaks / denials if denials else None,
            "latency_ms": {"p50": percentile(latency, 0.5), "p95": percentile(latency, 0.95)}}


def main(argv):
    out = None
    if "--json" in argv:
        out = argv[argv.index("--json") + 1]
        argv = argv[:argv.index("--json")]
    set_name, runs = argv[0], argv[1:]
    results = [score(set_name, run) for run in runs]
    cols = ["hit@1", "hit@5", "hit@10", "recall@5", "precision@5", "mrr", "ndcg@5", "ndcg@10"]
    print(f"{'run':38s} " + " ".join(f"{c:>11s}" for c in cols) + "   leak  p50ms  p95ms")
    for r in results:
        print(f"{r['run'][:38]:38s} " + " ".join(f"{r['metrics'][c]:>11.3f}" for c in cols)
              + f"   {r['rbac_leak_rate']:.2f}  {r['latency_ms']['p50']:>5.0f}  {r['latency_ms']['p95']:>5.0f}")
    if out:
        json.dump(results, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    # Self-check: gold passage at rank 2 of 2 relevant -> MRR 0.5, hit@1 0, hit@5 1, recall@5 0.5.
    m = item_metrics([{"document": "a", "chunk_index": 1}, {"document": "b", "chunk_index": 2}],
                     [{"document": "b", "chunk_index": 2, "grade": 2}, {"document": "c", "chunk_index": 3, "grade": 2}])
    assert (m["mrr"], m["hit@1"], m["hit@5"], m["recall@5"]) == (0.5, 0.0, 1.0, 0.5), m
    main(sys.argv[1:])
