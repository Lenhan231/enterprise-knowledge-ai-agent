# Invoice benchmark and cold-start Knowledge diagnostic

Measured application/evaluator: `fe53b21f4e76907e90db6f8398eb3bcc119e7ffe`.
Dataset: `commerce-invoice-10-v1`; agent `qwen/qwen3.8-27b`, temperature 0.

| Invoice measure | Result |
|---|---:|
| Questions attempted / SQL executed | 10 / 10 |
| Exact reference-result accuracy | 9/10 (90%) |
| Numerical accuracy, applicable cases | 4/5 (80%) |
| Evaluator errors / pending metrics | 0 / 0 |
| Request latency p50 / p95 | 2.198s / 4.961s |
| Recorded SQL-planning calls | 11 |

I05 misinterprets "approved" as a buyer value and adds
`LOWER(buyer) = LOWER($1)` with parameter `approved`. The requested grouping over
all published invoices therefore returns no rows. The failure was not repaired,
rerun or rescored. Strict output names were requested before generation.

The live population has one approved invoice and four items. Some monetary
references are NULL; numerical applicability is only five cases. These data do
not establish multi-invoice or multi-currency correctness, arbitrary equivalence,
or a valid comparison with the historical 30-question SQL benchmark. The
existing deterministic SQL result/numerical helpers were reused; no LLM SQL judge
or inferred currency/amount was added. Both snapshots match, including data and
schema hashes, and the reader connection reports read-only transactions.

The separate Knowledge cold-start smoke attempted only K01. Model initialization
exceeded the application's 60-second deadline (60.014s; no answer-model call).
That failure remains in `knowledge/generations.jsonl`. It has no published RAGAS
scores and is not combined with the subsequent startup-profiled Knowledge cohort.

See `manifest.json`, `database-before.json`, `database-after.json`,
`invoice/dataset.json`, `invoice/generations.jsonl`, `invoice/scores.jsonl` and
`summary.json`. The frozen question/reference inputs were authored before any
generation. Reproduction requires this source revision and the recorded package
environment; changed inputs, source or data require a new cohort folder.
