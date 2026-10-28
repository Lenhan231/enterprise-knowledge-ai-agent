"""Lazy, pinned BGE cross-encoder; original chunks retain their citation identity."""
import math
import os
from functools import lru_cache
from threading import Lock
from time import perf_counter
from core.latency import measure

MODEL_ID = "BAAI/bge-reranker-v2-m3"
REVISION = "953dc6f6f85a1b2dbfca4c34a2796e7dde08d41e"
_INFERENCE_LOCK = Lock()


@lru_cache(maxsize=1)
def _load_model():
    import torch
    from sentence_transformers import CrossEncoder
    return CrossEncoder(
        MODEL_ID, revision=REVISION, max_length=1024,
        device=os.getenv("RERANKER_DEVICE", "cpu"),
        local_files_only=os.getenv("RERANKER_ALLOW_DOWNLOAD", "0") != "1",
        model_kwargs={"torch_dtype": torch.float32},
    )


class BGEReranker:
    def __init__(self, model=None):
        self.model = model

    @measure("reranking")
    def rerank(self, query, chunks, top_k):
        details = {"reranker_model": MODEL_ID, "reranker_revision": REVISION,
                   "reranker_candidate_count": len(chunks), "reranker_max_pair_tokens": 1024,
                   "reranker_score_type": "raw_logit", "reranker_applied": False}
        if not chunks:
            return [], details
        started = perf_counter()
        if self.model is None and os.getenv("RERANKER_URL"):
            from core.services.client import post
            scores = post(os.environ["RERANKER_URL"], "/rerank", {
                "query": query, "texts": [chunk.content for chunk in chunks],
            })["scores"]
        else:
            import torch
            with _INFERENCE_LOCK:
                if self.model is None:
                    try:
                        self.model = _load_model()
                    except OSError as exc:
                        raise RuntimeError(
                            "BGE reranker is not cached. Provision the pinned model first or explicitly "
                            "set RERANKER_ALLOW_DOWNLOAD=1 on the compute host.") from exc
                scores = self.model.predict(
                    [(query, chunk.content) for chunk in chunks], batch_size=4,
                    show_progress_bar=False, convert_to_numpy=True,
                    activation_fn=torch.nn.Identity(),
                )
        details["reranker_latency_ms"] = (perf_counter() - started) * 1000
        scores = [float(score) for score in scores]
        if len(scores) != len(chunks) or not all(math.isfinite(score) for score in scores):
            raise ValueError("Reranker returned invalid scores")
        # Python's stable sort retains fused candidate order for equal logits.
        order = sorted(range(len(chunks)), key=lambda index: -scores[index])[:top_k]
        details["reranker_applied"] = True
        return [chunks[index].model_copy(update={"retrieval_score": scores[index]})
                for index in order], details
