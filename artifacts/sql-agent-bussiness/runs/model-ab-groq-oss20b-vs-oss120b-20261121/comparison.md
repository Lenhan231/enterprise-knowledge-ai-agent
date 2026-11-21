# SQL Agent model comparison: Groq OSS-20B vs OSS-120B

Status: exploratory pilot comparison, not a model-selection result.

This comparison uses the existing five-case development pilot. It does not run
or score the 40-case held-out cohort. The selected paced runs use the same
question-set hash, gold-reference hash, frozen database fingerprint, SQL source
hashes, prompt hashes, Python version, repair budget, and case delay. The app
revision metadata and benchmark runner hashes differ, so this is not a fully
controlled model-only experiment.

## Results

| Metric | Groq `openai/gpt-oss-20b` | Groq `openai/gpt-oss-120b` |
|---|---:|---:|
| Business end-to-end accuracy | 4/4 (100%) | 3/4 (75%) |
| SQL semantic accuracy | 4/4 (100%) | 4/4 (100%) |
| Business result accuracy, executed cases | 4/4 (100%) | 3/3 (100%) |
| Strict exact match | 2/4 (50%) | 2/4 (50%) |
| Supported noncompletion | 0/4 (0%) | 1/4 (25%) |
| Safe unsupported abstention | 1/1 (100%) | 1/1 (100%) |
| Unsafe executions | 0 | 0 |
| Repair recovery | N/A (0 applicable) | 0/1 |
| SQL-generation provider submissions | 2 | 3 |
| Local Codex fallback calls | 0 | 0 |
| Latency p50 / p95 | 9.23 / 10.34 s | 9.26 / 11.33 s |

The 120B run did not complete P03. Its recorded failure class is
`provider_failure`; the SQL semantic checks passed, but the query was not
executed. The one-case completion difference therefore does not establish
that 20B has better SQL reasoning. For cases that executed, both models matched
the business results. Both had the same strict exact-match rate.

## Interpretation

On this single paced pilot run, OSS-20B completed all four supported cases and
OSS-120B completed three. SQL semantic accuracy was 4/4 for both. This is too
small and not sufficiently controlled to select a winner. The practical signal
is to repeat a paired comparison with identical app and benchmark revisions,
alternate model order, and record provider failures separately from SQL
quality. These pilot questions are development examples, not held-out test
data.

## Reproducibility

| Item | OSS-20B | OSS-120B |
|---|---|---|
| Run | [`oss20b-paced`](oss20b-paced/report.md) | [`oss120b-paced-final`](oss120b-paced-final/report.md) |
| Experiment | `20261121T030504Z` | `20261121T032033Z` |
| Application revision | `2f00c5b199ebdb8671ad76d641c0d9fc46054c49` | `a5a2169727d6397b96e6bfc21ea7a8e70165f9a5` |
| SQL source fingerprint | `5feb222132233fa2bd8ee010eac42b804a64bb0d0f13ad80b7252c3b0728a57d` | same |
| Case-set SHA-256 | `ddade2d597b30a6bb4c74fc7b997dfe9a617e6c5348cd8b64bf7016463d100c4` | same |
| Gold-reference SHA-256 | `295c53652e5fe3a7fc8c3c35cffb9ecf4f6bc23e44b6db861955e369d0932a17` | same |
| Database fingerprint | `dbc14b99acc2920ffaeb4190ba45708982c971f0671b0b9e8114b595f2594028` | same |
| Repair budget / case delay | 1 / 60 s | 1 / 60 s |
| Schema-selection model | `perplexity/pplx-decider-flash-v1.3:free` | same |

Each run directory contains the raw observations (`data.json`), deterministic
scoring (`scores.json`), and full report. Earlier attempts are retained beside
these selected runs; they are not pooled into the table above.
