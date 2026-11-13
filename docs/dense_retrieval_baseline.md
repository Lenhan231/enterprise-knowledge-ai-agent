# Dense retrieval baseline

Run date: 2026-09-21  
Embedding model: `sentence-transformers/all-MiniLM-L6-v2`  
Top-K: 5  
Queries: 5

## Results

| Metric | K=1 | K=3 | K=5 |
|---|---:|---:|---:|
| Document-level Hit@K | 1.000 | 1.000 | 1.000 |
| Document-level Recall@K | 1.000 | 1.000 | 1.000 |

- Mean request latency: 1084.7 ms
- Median request latency: 427.9 ms
- No warm-up query was excluded. The first measured request was 3836.1 ms.
- `RetrievalResponse.latency_ms` includes query embedding, pgvector search and
  result mapping. It excludes service/model construction.

This is a small, manually verified document-level baseline, not a production
benchmark. Three labels were verified by existing grounded-QA evidence. The two
procurement labels were verified against their Supabase document metadata and
matching chunk content. Only five labels could be verified without inventing
ground truth, so the fixture intentionally contains fewer than ten questions.

Every current query has one expected document, so Hit@K and Recall@K have the
same measured value. Unit tests cover multiple expected documents, where Hit@K
means at least one expected document was retrieved and Recall@K is the fraction
of expected documents retrieved. Retrieved document IDs are deduplicated before
both metrics, and aggregate Recall@K is the macro-average across queries.

## Provenance compatibility

Each ranked retrieval result provides enough data for an answer layer to map:

- `chunk_id`
- `document_id`
- `location.chunk_index`
- `source` as the canonical source document
- `location.page_number`
- `location.section_title`
- `metadata.official_url`
- full `text`
- `score`

Missing page, section and official URL values remain `null`; the evaluator does
not infer fallbacks or truncate content. `chunk_id` and `document_id` are
retrieval identities. Answer-local IDs such as `S1` are not created by the
evaluator and are not persistent source identities.

The transitional chunk ID format is
`{document_id}::chunk::{chunk_index}`. It is stable only while the document ID
and chunking/index remain unchanged, not across re-chunking.

## Answer-layer compatibility audit

`src/core/agents/knowledge_agent.py` currently expects
`context["citation_id"]`, while `RAGService` supplies `source_id`. It would raise
`KeyError` for non-empty contexts. `RAGService` also does not currently copy
retrieval `chunk_id` into its context dictionaries, so `KnowledgeAgent` cannot
preserve that identity in evidence. `document_id`, source document, page,
section and official URL remain available through the context metadata/source.

These answer-layer mappings are owned by the answer/evidence work and were not
changed in this checkpoint.

## Run

With `DATABASE_URL` configured:

```bash
uv run python scripts/check_apple_retrieval.py
```

The run also writes the machine-readable result to
`artifacts/review1/dense_retrieval_baseline.json`. Use `--output` to select a
different path.

The evaluator uses `RetrievalService`, requests exactly five ranked chunks,
sets the existing PostgreSQL connection to read-only, does not call Groq and
does not write database data. Low recall is reported as a baseline rather than
treated as a program failure. Invalid fixtures, retrieval failures and
structurally invalid responses return a non-zero exit code.
