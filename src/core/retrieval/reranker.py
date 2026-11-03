"""Lazy, pinned BGE cross-encoder; original chunks retain their citation identity."""
import math
import os
from functools import lru_cache
from threading import Lock
from time import perf_counter
from core.latency import measure

MODELS = {  # name -> (model id, pinned revision, max pair tokens)
    "bge": ("BAAI/bge-reranker-v2-m3", "953dc6f6f85a1b2dbfca4c34a2796e7dde08d41e", 1024),
    # ~5x smaller; VietStyle 80-case top-5 evidence 182 vs 183 for BGE, ~1.5x faster than BGE int8 on CPU.
    "mminilm": ("cross-encoder/mmarco-mMiniLMv2-L12-H384-v1", "1427fd652930e4ba29e8149678df786c240d8825", 512),
}
MODEL_ID, REVISION, MAX_LENGTH = MODELS[os.getenv("RERANKER_MODEL", "bge")]
_INFERENCE_LOCK = Lock()


@lru_cache(maxsize=1)
def _load_model():
    import torch
    from sentence_transformers import CrossEncoder
    quantize, device = os.getenv("RERANKER_QUANTIZE", ""), os.getenv("RERANKER_DEVICE", "cpu")
    if quantize not in ("", "int8") or (quantize and device != "cpu"):
        raise ValueError("RERANKER_QUANTIZE supports only int8 on cpu")
    model = CrossEncoder(
        MODEL_ID, revision=REVISION, max_length=MAX_LENGTH, device=device,
        local_files_only=os.getenv("RERANKER_ALLOW_DOWNLOAD", "0") != "1",
        model_kwargs={"torch_dtype": torch.float32},
    )
    if quantize:
        # ~1.75x faster on the 6-core VPS; 80-case VietStyle eval: full@10 57 vs 55 fp32.
        # shortcut: torch.ao quantize_dynamic is deprecated (pytorch/ao#2259), move to torchao when torch drops it.
        torch.ao.quantization.quantize_dynamic(model, {torch.nn.Linear}, dtype=torch.qint8, inplace=True)
    return model


class BGEReranker:
    def __init__(self, model=None):
        self.model = model

    @measure("reranking")
    def rerank(self, query, chunks, top_k):
        details = {"reranker_model": MODEL_ID, "reranker_revision": REVISION,
                   "reranker_candidate_count": len(chunks), "reranker_max_pair_tokens": MAX_LENGTH,
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
