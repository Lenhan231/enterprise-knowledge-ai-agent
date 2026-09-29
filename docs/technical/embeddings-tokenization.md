# Embeddings and tokenization

## Active configuration

- Environment settings: `EMBEDDING_MODEL`, `EMBEDDING_BACKEND`.
- Input cap: `EMBEDDING_MAX_SEQUENCE_LENGTH` (default `512`, including special
  tokens required by the model).
- Default in `.env.example` and `EmbeddingService`:
  `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`.
- `EMBEDDING_BACKEND=local` (default) uses local Hugging Face Sentence
  Transformers weights. `EMBEDDING_BACKEND=huggingface_inference` calls the
  Hugging Face Inference API with `HUGGINGFACE_API_KEY`, avoiding those weights
  in app RAM. Both document passages and queries use the selected backend.
- PostgreSQL stores `vector(384)` and ranks cosine distance with pgvector.
- `TokenCounter` loads `AutoTokenizer` for the same model and records token
  counts in chunk metadata. It does not truncate or reject overlength text.

The configured model is the only model currently used by the app. A read-only
hosted/local compatibility check on one public Vinamilk chunk produced 384
dimensions, cosine similarity 1.00000012, and maximum component difference
4.2e-7, so the hosted backend can query existing vectors without re-embedding.
The app has been switched locally through the ignored `.env`; `.env.example`
still defaults to local. The hosted backend sends uploaded document text and
question text to Hugging Face, so use it only when that data transfer is
permitted. It has no silent local fallback: authentication, provider outages,
or rate limits surface as errors. Hosted inference reduces model-weight RAM,
but adds network latency and account usage; local inference avoids sending
text to that provider but loads the model into RAM.

The one-case hosted retrieval smoke reproduced the exact ranked document and
passage IDs for the FY2024 financial question from three existing local runs;
document MRR is 1.0 and passage MRR is 0.125 on the manually pooled labels.
Hosted retrieval took 15.2 seconds for that request. This is a compatibility
smoke, not a broad quality or latency benchmark. See the
[`hosted-backend retrieval report`](../../artifacts/evaluation/vinamilk-hosted-embedding-retrieval-smoke-20260928.json).

The embedding module now imports `HuggingFaceEmbeddings` only for the local
backend. Before that change, the local-model dependency import alone raised a
fresh process from 14.6 to 590 MiB RSS. On the same one-query smoke, hosted
peak RSS fell from 576.2 to 76.7 MiB (86.7%); local mode remained at 1,480.5
MiB. Hosted and local vectors still match (cosine 0.9999999999998066,
maximum component difference 4.92e-7). The restarted Uvicorn explicitly loads
`.env` with `EMBEDDING_BACKEND=huggingface_inference`; after one authenticated
analyst ask returned HTTP 200 with a citation, its process high-water RSS was
185,012 KiB and no local embedding model mappings were present. These are
single-query resource checks, not a steady-state or concurrency benchmark;
provider latency is not compared. See the [post-change artifact](../../artifacts/evaluation/vinamilk-embedding-hosted-lazy-import-20260928.json) and [pre-change reference](../../artifacts/evaluation/vinamilk-embedding-backend-resource-parity-20260928.json).

The configured model is the only model currently used by the app. Proposal
models are evaluated offline by `scripts/retrieval/evaluate_embeddings.py`; its
same-sample smoke reports live under `artifacts/evaluation/` and do not change
the production vectors. Changing the app model requires matching vector
dimensions and re-embedding every stored chunk before search.

The original three-model paired smoke uses 38 of 3,785 ready Vinamilk chunks
(up to three per document). An expanded paired run uses 93 chunks (up to eight
per document); all models share the same corpus SHA-256 and nine-case hash.
On CPU, corpus embedding took 103 s for BGE-M3, 1,325 s for Qwen3 Embedding
0.6B, and 134 s for e5-large-v2. Mean query time was 171, 1,355 and 219 ms,
respectively; peak RSS was 2,434, 2,637 and 2,189 MiB. Scores and limits are in
the expanded-run artifacts linked from the [evaluation matrix](agents-and-evaluation.md).
Batch sizes were 1/8/4, so measured throughput reflects each recorded CPU
configuration and is not a batch-controlled speed ranking.

A separate e5-large-v2 scaling run uses 181 chunks (up to 16 per document):
peak RSS 2,228 MiB, corpus embedding 236 s, mean query 207 ms. Its ranking
scores are not directly comparable with the paired runs because the sample
differs. All these runs are nine-query, document-level smoke evaluations; none
uses the full ready corpus or passage-level judgments.

### Refreshed 12-case embedding comparison

After adding three governance queries, BGE-M3 and e5-large-v2 were rerun on the
same 173 evenly sampled chunks across all 25 ready documents, with the same
case hash, CPU, batch 8 and 512-token input limit. BGE/e5 MRR is 0.606/0.706,
Recall@3 is 0.750/0.833, and nDCG@3 is 0.616/0.719. Corpus embedding took
223/281 seconds; mean query encoding/scoring took 187/224 ms. The sample is 173
of 4,750 chunks, so this is not full-corpus model selection. Qwen3-Embedding
did not complete on this CPU: its first batch took about 200 seconds. Full
metrics, case-level ranks, hashes and this limitation are in
[`vinamilk-embedding-three-model-expanded-25docs-12cases-20260927.json`](../../artifacts/evaluation/vinamilk-embedding-three-model-expanded-25docs-12cases-20260927.json).

### Cloud run on the full public corpus

The local evaluator now accepts `--corpus` JSONL as well as the live database.
`uv run python scripts/retrieval/export_public_embedding_corpus.py` exports only ready
document IDs present in the public manifest, preserves their `allowed_roles`,
and writes a SHA-256 metadata sidecar. The committed 2026-09-27 snapshot has
4,750 passages from 25 public Vinamilk sources; no database credential is
needed in a hosted runtime. The loader rejects any document ID outside the
manifest allowlist. Attach the private Kaggle dataset
[vinamilk-proposal-benchmark-assets](https://www.kaggle.com/datasets/ltrngnhn/vinamilk-proposal-benchmark-assets).
`notebooks/kaggle_embedding_benchmark.ipynb` runs BGE-M3,
Qwen3-Embedding-0.6B and e5-large-v2 separately on the exact same complete
corpus and twelve cases with CUDA and batch size 4. It records each model
revision, data hashes, peak RAM/VRAM and per-case rankings. This is a larger
paired smoke benchmark, not final selection: the twelve document-level labels
remain sparse and do not replace passage-level judgments or human QA review.

The completed run is summarized in
[`vinamilk-embedding-three-model-full-corpus-t4-20260927.json`](../../artifacts/evaluation/vinamilk-embedding-three-model-full-corpus-t4-20260927.json);
the three original Kaggle JSON reports and their SHA-256 values are retained
under `artifacts/evaluation/embedding-full-corpus-t4/`. A later local hash replay
is recorded in
[`vinamilk-embedding-three-model-full-corpus-hash-verified-20260928.json`](../../artifacts/evaluation/vinamilk-embedding-three-model-full-corpus-hash-verified-20260928.json).
It verifies the exact case hash `554f9837…f21270b1a`, source corpus hash
`149b531c…eca984a7`, and sampled corpus hash `a7418846…f7fd8cd8` against the
committed JSONL and case file. The replay reproduces all 4,750 selected chunks:
the largest of 25 documents has 452 chunks, below the reported 1,000-per-document
cap. Thus full-corpus coverage is verified. The raw reports still carry a stale
`sample_strategy` value claiming evenly spaced sampling and a stale limitation
sentence claiming a smaller sample; these source files remain unchanged, and
the audit artifact records both the discrepancy and the hash proof. On those
reported rankings, BGE-M3/Qwen3/e5 MRR is 0.7759/0.8028/0.7583,
Recall@5 is 0.9167/0.9167/0.9167 and nDCG@5 is 0.8041/0.8239/0.7917. Mean query
time is 28.3/64.5/25.2 ms; corpus embedding time is 266/782/336 seconds.
These single-run measurements on sparse document-level labels are not a
production winner or passage-level answer-quality result. The raw Kaggle
reports contain a stale generated limitation sentence about sampling, and their
sample-strategy field conflicts with the recorded counts. Raw reports remain
unchanged; the hash audit proves the selected data and flags the stale metadata. The local evaluator
now describes the sampling strategy based on the actual included/full counts.
The notebook resolves Kaggle's attached dataset mount from its project files,
installs the lockfile-matched `sentence-transformers` version, and checks CUDA
before launching the three model runs.

## Input-length constraint

The model reports a 512-token maximum sequence length. Seed PDF chunks target
1,200 characters and upload chunks 1,100; character limits do not guarantee a
token limit, especially for Vietnamese text. `TokenCounter.split_text` now
splits overlength chunks before embedding and stores the recalculated token
count. The 11-report corpus has been re-ingested with this guard; a read-only
database check found no stored report chunk above the configured sequence limit.

Useful source: `src/core/embeddings/embedding_service.py`,
`src/core/utils/token_counter.py`, `.env.example`, and
`supabase/migrations/20260922000000_initial_knowledge_schema.sql`.
