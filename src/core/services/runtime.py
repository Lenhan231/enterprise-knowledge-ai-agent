"""Private, single-purpose model and parser runtimes selected by SERVICE_KIND."""
import base64
import binascii
import json
import logging
import os
import secrets
import time
from contextlib import asynccontextmanager
from pathlib import Path
from queue import Queue
from typing import Literal
from threading import Lock, Thread

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from document_processing.diagnostics import PageLimitExceeded, component_errors, document_log_context

LOCK = Lock()
logger = logging.getLogger(__name__)


def _invoice_provider_is_remote(config):
    provider = str(
        config.get("invoice_provider")
        or os.environ.get("DOCUMENT_PROCESSING_INVOICE_PROVIDER")
        or "gemini"
    ).strip().lower()
    return provider in {"gemini", "groq"}


def authorize(request: Request):
    token = os.getenv("INTERNAL_SERVICE_TOKEN", "")
    if not token or not secrets.compare_digest(request.headers.get("authorization", ""), "Bearer " + token):
        raise HTTPException(401, "Internal service authentication required")


@asynccontextmanager
async def lifespan(app):
    if not os.getenv("INTERNAL_SERVICE_TOKEN"):
        raise RuntimeError("INTERNAL_SERVICE_TOKEN is required")
    kind = os.environ["SERVICE_KIND"]
    retrieval_service = None
    logger.info("Loading %s models before accepting requests", kind)
    if kind == "embeddings":
        from core.embeddings.embedding_service import _shared_backend
        from core.embeddings.settings import DEFAULT_EMBEDDING_MODEL
        app.state.encoder = _shared_backend(DEFAULT_EMBEDDING_MODEL, "local")
    elif kind == "reranker":
        from core.retrieval.reranker import _load_model
        app.state.encoder = _load_model()
    elif kind == "document-processing":
        from document_processing.docling_adapter.processor import DoclingProcessor
        DoclingProcessor({}).preload()
    elif kind == "retrieval":
        from core.retrieval.retrieval_service import RetrievalService
        retrieval_service = RetrievalService()
        app.state.retrieval_service = retrieval_service
    else:
        raise RuntimeError("Unsupported SERVICE_KIND")
    logger.info("%s models ready", kind)
    try:
        yield
    finally:
        if retrieval_service is not None:
            retrieval_service.close()


app = FastAPI(lifespan=lifespan, dependencies=[Depends(authorize)])


@app.get("/health")
def health():
    return {"status": "ok"}


class Texts(BaseModel):
    texts: list[str] = Field(min_length=1, max_length=300)
    model_name: str | None = Field(default=None, max_length=255)
    query: str = Field(default="", max_length=32768)


class Retrieve(BaseModel):
    query: str = Field(min_length=1, max_length=4000)
    top_k: int = Field(default=5, ge=1, le=100)
    company: str | None = Field(default=None, max_length=255)
    roles: list[str] = Field(min_length=1, max_length=16)
    method: Literal["dense", "bm25", "hybrid", "parent", "translated_hybrid", "translated_hybrid_rerank"] = "translated_hybrid_rerank"
    dense_weight: float = Field(default=1.0, ge=0)
    bm25_weight: float = Field(default=2.0, ge=0)
    rrf_k: int = Field(default=60, ge=1)
    document_ids: list[str] | None = Field(default=None, max_length=500)
    metadata_filter: dict | None = None
    query_language: Literal["auto", "en", "vn"] = "auto"
    document_languages: dict[str, str] | None = None


@app.post("/retrieve")
def retrieve(body: Retrieve, stream: bool = False):
    if os.getenv("SERVICE_KIND") != "retrieval":
        raise HTTPException(404)
    if not stream:
        return _run_retrieval(body, [])
    # NDJSON: one {"stage", "state", "elapsed_ms"} line per stage as it happens, then {"result"} or {"error"}.
    lines: Queue = Queue()
    events: list[dict] = []

    def notify(stage: str, state: str):
        line = {"stage": stage, "state": state}
        if state != "started" and events and events[-1]["stage"] == stage:
            line["elapsed_ms"] = events[-1]["elapsed_ms"]  # measure() records the event before notifying
        lines.put(line)

    def work():
        try:
            lines.put({"result": _run_retrieval(body, events, notify).model_dump(mode="json")})
        except Exception:
            logger.exception("Streaming retrieval failed")
            lines.put({"error": "Retrieval failed"})
        finally:
            lines.put(None)

    Thread(target=work, daemon=True).start()
    return StreamingResponse((json.dumps(line) + "\n" for line in iter(lines.get, None)),
                             media_type="application/x-ndjson")


def _run_retrieval(body: Retrieve, events: list[dict], notify=None):
    from core.latency import latency_events, stage_listener
    from core.retrieval.retrieval import RetrievalRequest
    from core.retrieval.retrieval import RetrievalResponse

    # Stage timings would otherwise stay in this process; the caller replays them (remote_service.py).
    token, listener_token = latency_events.set(events), stage_listener.set(notify)
    try:
        result = app.state.retrieval_service.retrieve(
            RetrievalRequest(query=body.query, top_k=body.top_k),
            company=body.company,
            roles=body.roles,
            method=body.method,
            dense_weight=body.dense_weight,
            bm25_weight=body.bm25_weight,
            rrf_k=body.rrf_k,
            document_ids=body.document_ids,
            metadata_filter=body.metadata_filter,
            query_language=body.query_language,
            document_languages=body.document_languages,
        )
    finally:
        latency_events.reset(token)
        stage_listener.reset(listener_token)
    response = RetrievalResponse.model_validate(result)
    response.retrieval_details["stage_events"] = events
    return response


@app.post("/embed")
def embed(body: Texts):
    if os.getenv("SERVICE_KIND") != "embeddings":
        raise HTTPException(404)
    if len(body.texts) > 32 or any(len(text) > 32768 for text in body.texts):
        raise HTTPException(413, "Embedding batch exceeds limit")
    from core.embeddings.settings import DEFAULT_EMBEDDING_MODEL
    if body.model_name is not None and body.model_name != DEFAULT_EMBEDDING_MODEL:
        raise HTTPException(409, "Embedding model does not match configured service")
    with LOCK:
        vectors = app.state.encoder.embed_documents(body.texts)
    return {"vectors": vectors}


@app.post("/rerank")
def rerank(body: Texts):
    if os.getenv("SERVICE_KIND") != "reranker":
        raise HTTPException(404)
    if any(len(text) > 131072 for text in body.texts):
        raise HTTPException(413, "Reranker text exceeds limit")
    import torch
    with LOCK:
        scores = app.state.encoder.predict(
            [(body.query, text) for text in body.texts], batch_size=4,
            show_progress_bar=False, convert_to_numpy=True, activation_fn=torch.nn.Identity())
    from core.retrieval.reranker import MAX_LENGTH, MODEL_ID, REVISION
    # The caller's own env does not say which model this service loaded, so report it.
    return {"scores": [float(score) for score in scores], "model": MODEL_ID, "revision": REVISION,
            "max_pair_tokens": MAX_LENGTH, "quantize": os.getenv("RERANKER_QUANTIZE", "")}


class Parse(BaseModel):
    filename: str = Field(min_length=1, max_length=255)
    content: str = Field(max_length=70 * 1024 * 1024)
    metadata: dict = Field(default_factory=dict)
    config: dict = Field(default_factory=dict)


@app.post("/parse")
def parse(body: Parse):
    if os.getenv("SERVICE_KIND") != "document-processing":
        raise HTTPException(404)
    request_started = time.perf_counter()
    timings_ms = {}
    invoice_id = body.metadata.get("invoice_id")
    source_format = str(body.metadata.get("format") or Path(body.filename).suffix.lstrip(".") or "unknown").lower()
    log_context = document_log_context(body.metadata, source_format=source_format)
    result_status = "failed"
    try:
        stage_started = time.perf_counter()
        with component_errors(logger, "base64_decode", **log_context):
            content = base64.b64decode(body.content, validate=True)
        timings_ms["base64_decode"] = round((time.perf_counter() - stage_started) * 1000, 2)
        if len(content) > 50 * 1024 * 1024:
            raise HTTPException(413, "Document exceeds 50 MiB")
        from document_processing.document_processor import DocumentProcessor
        processor = DocumentProcessor(body.config)
        remote_invoice = (
            str(body.config.get("intent", "document")).strip().lower() == "invoice"
            and _invoice_provider_is_remote(body.config)
        )
        if remote_invoice:
            timings_ms["queue_lock_wait"] = 0.0
            stage_started = time.perf_counter()
            try:
                result = processor.process(
                    body.filename,
                    content,
                    body.metadata,
                    invoice_docling_lock=LOCK,
                    on_invoice_docling_lock_wait=lambda wait_ms: timings_ms.__setitem__(
                        "queue_lock_wait", round(wait_ms, 2)
                    ),
                )
            finally:
                timings_ms["document_processor"] = round((time.perf_counter() - stage_started) * 1000, 2)
        else:
            lock_started = time.perf_counter()
            LOCK.acquire()
            timings_ms["queue_lock_wait"] = round((time.perf_counter() - lock_started) * 1000, 2)
            try:
                stage_started = time.perf_counter()
                try:
                    result = processor.process(body.filename, content, body.metadata)
                finally:
                    timings_ms["document_processor"] = round((time.perf_counter() - stage_started) * 1000, 2)
            finally:
                LOCK.release()
        if "page_previews" in result:
            stage_started = time.perf_counter()
            with component_errors(logger, "preview_base64_encode", **log_context):
                result["page_previews"] = {key: base64.b64encode(value).decode("ascii")
                                           for key, value in result["page_previews"].items()}
            timings_ms["preview_base64_encode"] = round((time.perf_counter() - stage_started) * 1000, 2)
        result_status = "completed"
        return result
    except PageLimitExceeded as error:
        raise HTTPException(422, str(error)) from error
    except (ValueError, binascii.Error) as error:
        raise HTTPException(422, "Invalid document") from error
    finally:
        logger.info(
            "DOCUMENT_PARSE_REQUEST_TIMING %s",
            json.dumps(
                {
                    "invoice_id": invoice_id,
                    "filename_extension": source_format,
                    "content_bytes": len(content) if "content" in locals() else None,
                    "status": result_status,
                    "timings_ms": timings_ms,
                    "total_ms": round((time.perf_counter() - request_started) * 1000, 2),
                },
                separators=(",", ":"),
            ),
        )
