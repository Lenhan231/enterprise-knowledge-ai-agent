# Optional translated hybrid + BGE reranker

## Before / after

Previously `translated_hybrid` returned its fused candidates directly. New method
`translated_hybrid_rerank` reuses that implementation, retrieves at least 30 fused
candidates, then scores original-question/original-chunk pairs with
`BAAI/bge-reranker-v2-m3` revision `953dc6f6f85a1b2dbfca4c34a2796e7dde08d41e`.
BGE uses FP32, batches of 4, a 1024-token pair cap, and raw logits. Equal scores
retain fusion order. For the normal knowledge-agent request, 30 candidates become
10 passages. Requests above 30 retain their larger candidate/output limit.
Existing `hybrid` remains the default. Existing methods do not load BGE.

## Select it

Choose **Translated Hybrid + BGE Reranker** in the app retrieval selector, or send
this body to the existing authenticated question endpoint:

```json
{"question": "What evidence is required for damaged deliveries?", "retrieval_method": "translated_hybrid_rerank"}
```

For a benchmark script using the shared service:

```python
response = service.retrieve(
    RetrievalRequest(query=question, top_k=10),
    method="translated_hybrid_rerank",
    company=company, roles=trusted_roles,
    document_ids=verified_document_ids,
    document_languages=verified_document_languages,
)
```

`document_languages` maps real document IDs to `en` or `vn`. Supply all scoped
IDs when providing a map. The HTTP request does not accept a language map;
trusted server-side callers can use the service or RAG parameters shown above.
Without a verified map, both BM25 queries search the same authorized corpus;
`retrieval_details.language_aware` reports false. No document language is guessed
and no database schema change is required. ACL/company/document/metadata filters
remain applied inside each candidate search, before reranking.

## Compute-host preparation

Install the project's existing dependencies. Set these in the server environment
before starting the app:

```bash
export RERANKER_DEVICE=cuda  # use cpu on a host without CUDA
export RERANKER_ALLOW_DOWNLOAD=1  # explicitly permit downloading the pinned model
```

Default is CPU and cached files only. First use loads the model; first-use timing
includes loading. Provision/cache it on the compute host, then unset download
permission if desired. No weights were downloaded during integration/testing.
Groq translation uses the existing translator/provider configuration. Translation
sends the question text externally; reranking scores passages on the compute host.
Translation failure uses scoped dense candidates and still reranks them; details
report `dense_fallback=true` and `effective_method=dense_rerank`. Missing weights
or invalid reranker output raise an error, rather than silently skipping reranking.

## Limits and benchmark interpretation

Production was migrated on 2026-10-21 from `sentence-transformers/all-MiniLM-L6-v2`
(384 dimensions) to `intfloat/multilingual-e5-base` (768 dimensions), revision
`d128750597153bb5987e10b1c3493a34e5a4502a`. The active `document_chunks` table now
uses E5 exclusively; no parallel MiniLM index is maintained. Set this explicitly in
any existing local/server `.env` (pulling code does not overwrite an old `.env`):

```bash
EMBEDDING_MODEL=intfloat/multilingual-e5-base
EMBEDDING_BACKEND=local
EMBEDDING_MAX_SEQUENCE_LENGTH=512
```

Restart the app after updating the environment. Code supplies `query: ` and
`passage: ` prefixes, pins the local encoder/tokenizer revision, and normalizes
768-dimensional vectors. Do not add prefixes manually. Future upload chunking
reserves four prefix tokens within the encoder's 512-token limit. MiniLM-configured
clients are incompatible with this migrated database and must update before use.
See [E5 rollout](e5-production-rollout.md) for verification and migration details.

BGE may truncate question/passage pairs above 1024 tokens. Generation retains the
existing 5000-character prompt-context cap: top-10 retrieval does not guarantee all
10 passages fit into the final LLM prompt. No total retrieval token budget added.
The small frozen development benchmark measures evidence retrieval, not production
answer accuracy. Live model latency and end-to-end generation still need testing
on the team's compute host and compatible index.

## Validation

```bash
PYTHONPATH=src:tests HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 .venv/bin/python -m unittest test_translated_hybrid_rerank test_translated_hybrid test_retrieval_service test_document_scope test_parser_chunking_integration test_embedding_chunker test_token_counter test_evidence_metrics
```

Mocks replace translation, database, and CrossEncoder inference. Tests cover stable
ranking/raw scores, original content and source identity, all trusted search filters,
language scopes, dense fallback provenance, default-method isolation, missing weights,
invalid scores, empty results, RAG/knowledge-agent dispatch, and API request acceptance.
Legacy `test_app_request_models` fails import because it still expects the removed
`CandidateReviewRequest`; it is not part of this passing targeted suite.
