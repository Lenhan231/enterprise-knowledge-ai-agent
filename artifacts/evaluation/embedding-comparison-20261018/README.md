# VietStyle embedding comparison preparation — 2026-10-18

> Update: the index has now been restored. See [database-restoration.md](database-restoration.md) and benchmark-config.json. The audit below records the state before restoration.

Supabase was inspected using read-only transactions. Only five VietStyle documents
remain: 532 saved parser chunks, 14 structured tables, zero indexed vectors, and
all five document statuses are failed. The status alone does not explain the
failure; it does not prove the tokenizer or embedding provider caused it.

The parser corpus is frozen in parser-corpus.jsonl; manifest.json records its
SHA-256, new document IDs and per-document counts. The old financial-report
corpus is absent. New VietStyle upload IDs replace those in earlier benchmarks.
All 532 parser chunks lack a document language label. No DB writes were made.

The original Downloads CSV is frozen alongside 20 questions copied from An's
committed artifact. Its questions match that artifact exactly. Cases retain
expected source filenames and map available files to the new IDs. README.txt
is absent for Q01/Q18/Q19 and remains explicitly marked unavailable. These are
source-file coverage labels, not gold passages or human answer-quality scores.

## First tokenizer/encoder finding

The ignored local .env selects sentence-transformers/all-MiniLM-L6-v2 with a
configured 512-token limit. Its tokenizer reports 512, but the cached local
Sentence Transformers config defaults to 256. EmbeddingService forwards text
to the local backend without setting its encoder limit to the app's value.
460/532 parser chunks (86.47%) exceed the 256-token default, although none
exceeds 512. This is exposure to truncation if embedded under those defaults,
not an observed answer loss; there are no stored production vectors to inspect.

Our previous multilingual MiniLM baseline is a different model. Its cached
Sentence Transformers default is 128, and 521/532 chunks exceed that default.
For 424 spreadsheet chunks, the repeated headers alone consume at least the
128-token budget, so merely reducing chunk size does not solve table context.
No model settings were changed, no new model weights were downloaded, and
hosted inference behavior was not tested.

The frozen spreadsheet supplies 485/532 parser chunks. Preserve the same data
and questions for each model comparison; report source-document coverage and
any missing expected sources. Before benchmarking, choose and record each
encoder's actual input limit, tokenizer revision, prefixes and normalization.
Keep fixed-chunk model comparisons separate from per-model chunking experiments.

## Reproduce token auditing

```bash
.venv/bin/python scripts/retrieval/audit_embedding_tokens.py \
  --corpus artifacts/evaluation/embedding-comparison-20261018/parser-corpus.jsonl \
  --model sentence-transformers/all-MiniLM-L6-v2 \
  --output artifacts/evaluation/embedding-comparison-20261018/configured-model-native-limit-audit.json
```

This tool reads cached tokenizer/config files only and pins the tokenizer to
the resolved config revision. It does not load model weights or connect to a
provider/database. See configured-model-native-limit-audit.json for the active
model and minilm-native-limit-audit.json for the former multilingual baseline.
The separate configured-model-tokenization-audit.json checks the existing
512-token preparation path and must not be read as a guarantee against encoder
truncation. The existing embedding evaluator still assumes ready indexed
chunks or the old public-manifest corpus, so it cannot directly run this new
parser snapshot without adaptation. No retrieval-quality benchmark ran yet.
