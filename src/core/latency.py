"""Request-local stage timings, including work propagated through asyncio.to_thread."""

from contextlib import contextmanager
from contextvars import ContextVar
from time import perf_counter

latency_events: ContextVar[list[dict] | None] = ContextVar("latency_events", default=None)
STAGES = (
    "routing", "embedding", "database_retrieval", "retrieval_fusion",
    "query_translation", "reranking", "answer_generation", "sql_planning",
    "sql_execution", "answer_synthesis", "retrieval_total", "agent_workflow",
)


@contextmanager
def measure(stage: str):
    events = latency_events.get()
    if events is None:
        yield
        return
    started = perf_counter()
    status = "failed"
    try:
        yield
        status = "completed"
    finally:
        events.append({"stage": stage, "elapsed_ms": (perf_counter() - started) * 1000,
                       "status": status})


def snapshot() -> dict:
    events = [dict(event) for event in (latency_events.get() or [])]
    stages = {stage: None for stage in STAGES}
    for event in events:
        stage = event["stage"]
        stages[stage] = (stages.get(stage) or 0.0) + event["elapsed_ms"]
    return {"stages_ms": stages, "events": events}
