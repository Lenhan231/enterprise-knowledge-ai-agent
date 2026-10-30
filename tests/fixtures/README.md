# Dense retrieval fixture

`ranked_dense_retrieval.json` is a synthetic, complete `RetrievalResponse` for
context/citation development. Text, scores, latency, and URLs are examples, not
retrieved evidence or measured performance. The second result demonstrates
unknown page and section values. The Markdown source illustrates the contract,
not support for Markdown ingestion in the current pipeline.

Import contracts from `core.retrieval.retrieval` with `src` on the Python path:

```python
from pathlib import Path
from core.retrieval.retrieval import RetrievalResponse

response = RetrievalResponse.model_validate_json(
    Path("tests/fixtures/ranked_dense_retrieval.json").read_text(encoding="utf-8")
)
for chunk in response.results:
    print(chunk.rank, chunk.source, chunk.location.page_number, chunk.text)
```

`source` is the repository's `document_name`; title and official URL stay in
metadata. Public `document_id` must match the non-empty ID in ingested metadata.
Missing IDs are validation errors, never substituted filenames or generated UUIDs.

Use `make_chunk_id(document_id, chunk_index)` for the transitional format
`{document_id}::chunk::{chunk_index}`. It remains stable only while the document ID
and chunking/index do not change. Persistent ingestion/database IDs are future work.

`RetrievedChunk` is an internal repository model with no rank or latency.
`RankedChunk` is the public service result. The repository returns `RetrievedChunk`;
the single public `RetrievalService.retrieve(RetrievalRequest(...))` returns
`RetrievalResponse`. RAG and the retrieval checkpoint script consume this contract.
Database order is cosine distance ascending, then row `id` ascending for ties.
The service preserves that order and assigns ranks starting at 1. The tie-break
is deterministic for unchanged rows; row IDs can change after re-ingestion.

Requests accept nonblank queries and integer `top_k` from 1 through 100 (default 5).
All models reject unknown fields; metadata dictionary keys remain unrestricted.
Text, query, identifiers, and extra metadata are preserved, not trimmed or truncated.
Dense score means `1 - cosine_distance`, with higher scores ranked first; it is not
a probability. The service measures embedding, repository search, and result mapping
with a monotonic clock and reports elapsed milliseconds as `latency_ms`.
