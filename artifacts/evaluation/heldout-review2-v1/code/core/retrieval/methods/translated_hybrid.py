"""Original-query dense search plus automatically translated EN/VI BM25 fusion."""
from math import isfinite
from time import perf_counter

from openai import APIError

from core.retrieval.retrieval import make_chunk_id


def fuse(rankings, weights, k=60):
    scores = {}
    for ranking, weight in zip(rankings, weights):
        for rank, chunk_id in enumerate(dict.fromkeys(ranking), 1):
            scores[chunk_id] = scores.get(chunk_id, 0.0) + weight / (k + rank)
    return sorted(scores, key=lambda chunk_id: (-scores[chunk_id], chunk_id)), scores


def search(repository, vector, request, get_translator, *, company=None, roles=None,
           document_ids=None, document_languages=None, query_language="auto", metadata_filter=None,
           dense_weight=1.0, bm25_weight=2.0, rrf_k=60):
    if query_language not in {"auto", "en", "vn"}:
        raise ValueError("query_language must be auto, en or vn")
    if len(request.query) > 4000:
        raise ValueError("Translated queries are limited to 4000 characters")
    if (not isfinite(dense_weight) or not isfinite(bm25_weight)
            or min(dense_weight, bm25_weight) < 0 or dense_weight + bm25_weight == 0
            or not isfinite(rrf_k) or rrf_k <= 0):
        raise ValueError("Fusion needs finite nonnegative weights and a positive rrf_k")
    if document_languages is not None:
        if (document_ids is None or not isinstance(document_languages, dict)
                or any(document_languages.get(doc) not in {"en", "vn"} for doc in document_ids)):
            raise ValueError("Language-aware retrieval needs a verified en/vn mapping for every scoped document")
    filters = {"company": company, "roles": roles}
    if document_ids is not None:
        filters["document_ids"] = document_ids
    if metadata_filter:
        filters["metadata_filter"] = metadata_filter
    candidate_k = request.top_k * 10
    dense = repository.similarity_search(
        vector, candidate_k, query=request.query, method="dense", **filters)
    details = {"language_aware": document_languages is not None,
               "document_ids": document_ids, "candidate_k": candidate_k,
               "dense_weight": dense_weight, "bm25_weight": bm25_weight, "rrf_k": rrf_k,
               "lexical_queries": None, "dense_fallback": False,
               "translation_error": None, "effective_method": "translated_hybrid"}
    started = perf_counter()
    try:
        translator = get_translator()
        details["translation_model"] = getattr(translator.llm, "model_name", None)
        queries = translator.translate(request.query, query_language)
    except (APIError, ValueError, RuntimeError) as error:
        details.update(dense_fallback=True, translation_error=type(error).__name__,
                       effective_method="dense")
        return dense[:request.top_k], details
    finally:
        details["translation_latency_ms"] = (perf_counter() - started) * 1000
    details["lexical_queries"] = queries
    indexed = {}
    def ids(chunks):
        ranking = []
        for chunk in chunks:
            key = make_chunk_id(chunk.document_id, chunk.chunk_index)
            indexed[key] = chunk
            ranking.append(key)
        return ranking
    dense_ids = ids(dense)
    lexical = []
    scopes = {}
    for lang in ("en", "vn"):
        scope = document_ids
        if document_languages is not None:
            scope = [doc for doc in document_ids if document_languages[doc] == lang]
        scopes[lang] = scope
        options = dict(filters)
        if scope is not None:
            options["document_ids"] = scope
        lexical.append(ids(repository.similarity_search(
            None, candidate_k, query=queries[lang], method="bm25", **options)))
    details["lexical_document_scopes"] = scopes
    lexical_ids, _ = fuse(lexical, [1.0, 1.0], rrf_k)
    ranking, scores = fuse([dense_ids, lexical_ids[:candidate_k]],
                           [dense_weight, bm25_weight], rrf_k)
    return [indexed[key].model_copy(update={"retrieval_score": scores[key]})
            for key in ranking[:request.top_k]], details
