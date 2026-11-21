"""Summarise an experiment-12 run (load_test.py): one row per concurrency level, both repetitions pooled.

  python evaluation/v3/load_summary.py <out_dir>
"""
import json
import statistics
import sys
from pathlib import Path


def pct(values, q):
    values = sorted(values)
    return values[min(len(values) - 1, round(q * (len(values) - 1)))] if values else None


def main(out_dir):
    out = Path(out_dir)
    reqs = [json.loads(l) for l in open(out / "requests.jsonl") if l.strip() and json.loads(l)["rep"] > 0]
    samples = [json.loads(l) for l in open(out / "samples.jsonl") if l.strip()]
    walls = json.load(open(out / "levels.json"))
    rows = []
    for level in sorted({r["level"] for r in reqs}):
        mine = [r for r in reqs if r["level"] == level]
        ok = [r for r in mine if r["status"] == "ok"]
        wall = sum(w["wall_s"] for w in walls if w["level"] == level)
        s = [x for x in samples if x["level"] == level]
        get = lambda k: [x[k] for x in s if x.get(k) is not None]
        rows.append({
            "users": level, "requests": len(mine), "ok": len(ok),
            "timeouts": sum(r["status"] == "timeout" for r in mine),
            "errors": sum(r["status"].startswith("error") for r in mine),
            "median_s": round(statistics.median([r["total_s"] for r in ok]), 1) if ok else None,
            "p95_s": round(pct([r["total_s"] for r in ok], 0.95), 1) if ok else None,
            "retrieval_median_s": round(statistics.median([r["retrieval_s"] for r in ok if r["retrieval_s"]]), 1) if ok else None,
            "throughput_per_min": round(60 * len(ok) / wall, 2) if wall else None,
            "cpu_mean_pct": round(statistics.mean(get("system_cpu_pct")), 0) if get("system_cpu_pct") else None,
            "rss_max_mb": max(get("rss_mb")) if get("rss_mb") else None,
            "gpu_util_mean_pct": round(statistics.mean(get("gpu_util_pct")), 0) if get("gpu_util_pct") else None,
            "gpu_util_max_pct": max(get("gpu_util_pct")) if get("gpu_util_pct") else None,
            "llm_running_max": max(get("llm_num_requests_running")) if get("llm_num_requests_running") else None,
            "kv_cache_max_pct": round(100 * max(get("llm_kv_cache_usage_perc")), 1) if get("llm_kv_cache_usage_perc") else None,
        })
    cols = list(rows[0])
    print(" | ".join(cols))
    for r in rows:
        print(" | ".join(str(r[c]) for c in cols))
    (out / "summary.json").write_text(json.dumps(rows, indent=1))


if __name__ == "__main__":
    main(sys.argv[1])
