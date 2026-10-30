# Embeddings and tokenization

## Active configuration

`EmbeddingService` reads `EMBEDDING_MODEL` (default
`sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`) and
`EMBEDDING_BACKEND` (`local` by default). The current model emits 384-element
vectors stored in PostgreSQL `vector(384)` columns. Document passages and
queries must use the same model and vector dimension.

- `local` loads Hugging Face Sentence Transformers in the API process. The
  model weights consume local RAM and are cached by the runtime. When
  `HUGGINGFACE_API_KEY` is configured, the same token authenticates Hub model
  downloads; local embedding text stays on the app's machine.
- `huggingface_inference` calls the hosted feature-extraction API and requires
  server-side `HUGGINGFACE_API_KEY`. It avoids loading those weights locally,
  but sends document/query text to the provider and depends on network and
  account limits. Ingestion batches at most 16 passages per request.

`TokenCounter` loads the selected model's Hugging Face tokenizer. The configured
`EMBEDDING_MAX_SEQUENCE_LENGTH` defaults to 512 tokens. Chunking records actual
token counts and splits overlength text before embedding; character limits are
not a substitute because tokenization varies by model and language. See
[chunking](../../src/core/chunking/README.md) for the processing order and settings.

Changing the embedding model or vector dimension requires re-embedding all
passages that will be searched. Do not compare vectors from different models
or mix them in one model-specific search. Model experiments belong in the
offline evaluators and must use the same source snapshot and query labels.

## Code and checks

- Implementation: `src/core/embeddings/embedding_service.py`
- Tokenizer boundary: `src/core/tokenization/token_counter.py`
- Retrieval evaluation: `tools/retrieval/evaluate_embeddings.py`
- Configuration example: `.env.example`

```bash
PYTHONPATH=src .venv/bin/python -m unittest \
  tests.test_embedding_service tests.test_text_processor_chunking -q
```

Hosted inference has a different privacy, latency, and quota profile from the
local backend. Verify the selected backend and model in the local environment
before an ingestion or benchmark run; do not infer production configuration
from an ignored `.env` file or a stale evaluation artifact.
