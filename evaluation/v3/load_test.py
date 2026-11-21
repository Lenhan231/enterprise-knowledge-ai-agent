"""Experiment 12: Knowledge response time and throughput at 1, 2, 4 and 8 concurrent users (isolated copy, never prod).

  CUDA_VISIBLE_DEVICES= DATABASE_URL=<local eval db> GROQ_BASE_URL=<self-hosted> GROQ_API_KEY=<its key> \
    python evaluation/v3/load_test.py <out_dir> [levels=1,2,4,8] [reps=2]

Each simulated user takes the next dev-v3 question and calls RAGService.generate_answer exactly as KnowledgeAgent.run
does: through runtime.run_sync (the production pool of 8 worker slots) with the production deadline (90 s with
multiquery). Settings come from the production .env via answer.load_settings. Each level gets its own 15 questions
in a repetition; the second repetition rotates the slices. Writes requests.jsonl (one row per request) and samples.jsonl
(CPU/RAM of this process every 2 s; LLM server queue and GPU from vLLM /metrics and nvidia-smi every 15 s).
"""
import asyncio
import contextvars
import json
import os
import re
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from answer import ROOT, load_settings  # noqa: E402

request_id = contextvars.ContextVar("request_id", default=None)
spans = {}  # request id -> [first retrieval start, last retrieval end]


def timed_retrieval(original):
    def wrapper(*args, **kwargs):
        start = time.perf_counter()
        try:
            return original(*args, **kwargs)
        finally:
            span = spans.setdefault(request_id.get(), [start, start])
            span[0], span[1] = min(span[0], start), max(span[1], time.perf_counter())
    return wrapper


def cpu_ticks():
    fields = open("/proc/stat").readline().split()[1:]
    values = list(map(int, fields))
    return sum(values), values[3] + values[4]  # total, idle + iowait


def qwen_container():
    try:
        rows = json.loads(subprocess.run([os.environ["MODAL_BIN"], "container", "list", "--json"], capture_output=True,
                                         text=True, timeout=60).stdout or "[]")
        return next((r["container_id"] for r in rows if "qwen" in r.get("app_name", "")), None)
    except Exception:
        return None


def sampler(path, stop, base_url):
    """Process CPU and RSS every 2 s; vLLM queue and KV cache every 15 s; GPU utilization via nvidia-smi on Modal."""
    clock = os.sysconf("SC_CLK_TCK")
    last_proc, last_wall, (last_total, last_idle) = sum(os.times()[:2]), time.time(), cpu_ticks()
    container = None
    next_llm = 0.0
    with open(path, "a", encoding="utf-8") as out:
        while not stop.is_set():
            now = time.time()
            proc = sum(os.times()[:2])
            total, idle = cpu_ticks()
            rss = int(re.search(r"VmRSS:\s+(\d+)", open("/proc/self/status").read()).group(1)) // 1024
            row = {"t": round(now, 1), "level": current_level[0],
                   "process_cpu_pct": round(100 * (proc - last_proc) / (now - last_wall), 1),
                   "system_cpu_pct": round(100 * (1 - (idle - last_idle) / max(1, total - last_total)), 1),
                   "rss_mb": rss}
            last_proc, last_wall, last_total, last_idle = proc, now, total, idle
            if now >= next_llm:
                next_llm = now + 15
                try:
                    text = urllib.request.urlopen(base_url.rsplit("/v1", 1)[0] + "/metrics", timeout=10).read().decode()
                    for name in ("num_requests_running", "num_requests_waiting", "kv_cache_usage_perc", "gpu_cache_usage_perc"):
                        m = re.search(rf"^vllm:{name}\{{[^}}]*\}} ([0-9.e+-]+)", text, re.M)
                        if m:
                            row["llm_" + name] = float(m.group(1))
                except Exception as error:
                    row["llm_metrics_error"] = type(error).__name__
                if not container:
                    container = qwen_container()
                if container:
                    try:
                        smi = subprocess.run([os.environ["MODAL_BIN"], "container", "exec", "--no-pty", container, "--", "nvidia-smi",
                                              "--query-gpu=utilization.gpu,memory.used", "--format=csv,noheader,nounits"],
                                             capture_output=True, text=True, timeout=30).stdout.strip().splitlines()
                        if smi:
                            util, mem = smi[-1].split(",")
                            row["gpu_util_pct"], row["gpu_mem_mb"] = float(util), float(mem)
                    except Exception:
                        pass
            out.write(json.dumps(row) + "\n")
            out.flush()
            stop.wait(2)


current_level = [0]


async def one_request(rag, item, level, rep, out):
    from core.agents.runtime import deadline, remaining, run_sync
    multiquery = os.getenv("KNOWLEDGE_MULTIQUERY_ENABLED", "0") == "1"
    timeout = 90.0 if multiquery else 60.0  # KnowledgeAgent.run
    rid = f"{rep}-{level}-{item['id']}"
    request_id.set(rid)
    token = deadline.set(time.monotonic() + remaining(timeout))
    started, status, outcome = time.perf_counter(), "ok", None
    try:
        result = await run_sync(rag.generate_answer, item["question"], decompose=multiquery,
                                verify_claims=os.getenv("KNOWLEDGE_CLAIM_VERIFICATION_ENABLED", "0") == "1",
                                _timeout=timeout, roles=[item["role"]], retrieval_method="translated_hybrid_rerank")
        outcome = (result.verification.status if result.verification else
                   "not_covered" if result.insufficient_context else "answered")
    except (asyncio.TimeoutError, TimeoutError):
        status = "timeout"
    except Exception as error:
        status = f"error:{type(error).__name__}"
    finally:
        deadline.reset(token)
    total = time.perf_counter() - started
    span = spans.pop(rid, None)
    row = {"rep": rep, "level": level, "id": item["id"], "status": status, "outcome": outcome,
           "total_s": round(total, 2), "retrieval_s": round(span[1] - span[0], 2) if span else None,
           "started": round(time.time() - total, 1)}
    out.write(json.dumps(row) + "\n")
    out.flush()
    print(rid, status, outcome, f"{total:.1f}s", flush=True)


async def run_level(rag, items, level, rep, out):
    queue = asyncio.Queue()
    for item in items:
        queue.put_nowait(item)

    async def user():
        while not queue.empty():
            await one_request(rag, queue.get_nowait(), level, rep, out)

    started = time.perf_counter()
    await asyncio.gather(*(user() for _ in range(level)))
    return time.perf_counter() - started


async def main(out_dir, levels="1,2,4,8", reps="2"):
    load_settings()
    from core.rag import rag_service
    from core.rag.rag_service import RAGService
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    items = json.load(open(ROOT / "artifacts/evaluation/vietstyle-v3/dev-v3.json", encoding="utf-8"))["items"]
    levels = [int(x) for x in levels.split(",")]
    rag = RAGService()
    rag.retrieve_contexts = timed_retrieval(rag.retrieve_contexts)
    stop = threading.Event()
    threading.Thread(target=sampler, args=(out_dir / "samples.jsonl", stop, os.environ["GROQ_BASE_URL"]),
                     daemon=True).start()
    summary = []
    try:
        with open(out_dir / "requests.jsonl", "a", encoding="utf-8") as out:
            await run_level(rag, items[-2:], 1, 0, out)  # warm-up: models loaded, LLM awake; not scored
            for rep in (1, 2):
                if rep > int(reps):
                    break
                for n, level in enumerate(levels):
                    part = (n + rep - 1) % len(levels)
                    current_level[0] = level
                    wall = await run_level(rag, items[part * 15:(part + 1) * 15], level, rep, out)
                    summary.append({"rep": rep, "level": level, "wall_s": round(wall, 1)})
                    print("level", level, "rep", rep, f"wall {wall:.0f}s", flush=True)
                    current_level[0] = 0
                    await asyncio.sleep(20)
    finally:
        stop.set()
        rag.close()
        (out_dir / "levels.json").write_text(json.dumps(summary, indent=1))


if __name__ == "__main__":
    asyncio.run(main(*sys.argv[1:]))
