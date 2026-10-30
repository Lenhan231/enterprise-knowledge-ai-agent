"""Private, single-purpose model and parser runtimes selected by SERVICE_KIND."""
import base64
import binascii
import logging
import os
import secrets
from contextlib import asynccontextmanager
from threading import Lock

from fastapi import Depends, FastAPI, HTTPException, Request
from pydantic import BaseModel, Field

LOCK = Lock()
logger = logging.getLogger(__name__)


def authorize(request: Request):
    token = os.getenv("INTERNAL_SERVICE_TOKEN", "")
    if not token or not secrets.compare_digest(request.headers.get("authorization", ""), "Bearer " + token):
        raise HTTPException(401, "Internal service authentication required")


@asynccontextmanager
async def lifespan(app):
    if not os.getenv("INTERNAL_SERVICE_TOKEN"):
        raise RuntimeError("INTERNAL_SERVICE_TOKEN is required")
    kind = os.environ["SERVICE_KIND"]
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
    else:
        raise RuntimeError("Unsupported SERVICE_KIND")
    logger.info("%s models ready", kind)
    yield


app = FastAPI(lifespan=lifespan, dependencies=[Depends(authorize)])


@app.get("/health")
def health():
    return {"status": "ok"}


class Texts(BaseModel):
    texts: list[str] = Field(min_length=1, max_length=300)
    model_name: str | None = Field(default=None, max_length=255)
    query: str = Field(default="", max_length=32768)


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
    return {"scores": [float(score) for score in scores]}


class Parse(BaseModel):
    filename: str = Field(min_length=1, max_length=255)
    content: str = Field(max_length=70 * 1024 * 1024)
    metadata: dict = Field(default_factory=dict)
    config: dict = Field(default_factory=dict)


@app.post("/parse")
def parse(body: Parse):
    if os.getenv("SERVICE_KIND") != "document-processing":
        raise HTTPException(404)
    try:
        content = base64.b64decode(body.content, validate=True)
        if len(content) > 50 * 1024 * 1024:
            raise HTTPException(413, "Document exceeds 50 MiB")
        from document_processing.document_processor import DocumentProcessor
        with LOCK:
            result = DocumentProcessor(body.config).process(body.filename, content, body.metadata)
        if "page_previews" in result:
            result["page_previews"] = {key: base64.b64encode(value).decode("ascii")
                                       for key, value in result["page_previews"].items()}
        return result
    except (ValueError, binascii.Error) as error:
        raise HTTPException(422, "Invalid document") from error
