# Knowledge and invoice evaluation — 2026-11-10

The isolated branch **`eval/knowledge-invoice-20261110`** integrates main
`cae083c` into local QuocAn `43f4446` through merge `f0d5d25`. Production
Knowledge, retrieval, SQL and Report code matches the reviewed main revision.
No production data was changed and nothing was merged or pushed to main.

## New completed cohorts

| Cohort / measure | Result | Applicability |
|---|---:|---|
| Knowledge: RAGAS Faithfulness | **95.00%** | 24 answers; six abstentions N/A |
| Knowledge: RAGAS Answer Relevancy | **75.24%** | All 30 questions, including abstentions |
| Knowledge: RAGAS Context Precision | **88.25%** | All 30 questions |
| Knowledge: correct unsupported abstentions | **5/5** | Five operational lookups absent from policy |
| Knowledge: unnecessary supported abstentions | **1/25** | K17 |
| Knowledge: valid citation IDs | **24/24 answered cases** | Structural check; no unknown IDs |
| Knowledge: expected-page citation precision | **81.67%** | Macro mean over 24 answered cases |
| Knowledge: request latency p50 / p95 | **13.487s / 19.257s** | Preloaded local models; startup excluded |
| Invoice: exact reference-result accuracy | **9/10 (90%)** | Ten attempted/executed SQL requests |
| Invoice: numerical accuracy | **4/5 (80%)** | Five applicable cases; five N/A |
| Invoice: request latency p50 / p95 | **2.198s / 4.961s** | Ten requests |

Knowledge has 30 saved generations and **90 complete metric records**. Invoice
has ten generations and **20 complete metric records**. Neither cohort has a
provider-failed generation, evaluator error or missing score. All first recorded
outputs and low scores are retained. Six Knowledge responses abstained: the five
intended cases and K17. Statement-free refusals are N/A for Faithfulness, while
their zero relevancy scores remain in the 30-case mean.

Knowledge source/evaluator SHA:
`6bf2f73f2eb32940571dcfb424f20a6d336b56f2` (v3).
Invoice source/evaluator SHA:
`fe53b21f4e76907e90db6f8398eb3bcc119e7ffe` (v2).
These remain **separate cohorts**. The generic v3 summary's unattempted invoice
section is intentional: the complete invoice measurements are in v2, not copied
into a differently configured run.

## Findings

- **Invoice I05 fails:** the model treats the word "approved" as a buyer name,
  adding `WHERE LOWER(buyer) = LOWER($1)` with parameter `approved`. The requested
  buyer grouping over all published invoices instead returns no rows. The failure
  was not repaired or replaced. All other strict result comparisons pass.
- **Knowledge K17 misses evidence:** the question requests cycle-count evidence
  fields from policy page 31 (physical page 33), but the five retrieved physical
  pages are 2, 18, 7, 32 and 38. The agent safely abstains on this supported request.
- Faithfulness is not uniformly perfect: the saved judgment gives K04 **0.5**
  and other cases also retain partial credit. Valid source IDs alone do not prove
  that each citation entails its attached claim. Expected-page precision is a
  location proxy; RAGAS Faithfulness uses the actual supplied retrieved passages.
- The cold-start diagnostic in v2 times out at **60.014s** while initializing
  models. The independent v3 cohort records model loading separately: **68.553s**
  for the smoke process and **30.305s** for the remaining-generation process.
  Warm request latencies do not establish cold-start or deployed-service latency.

## Historical SQL / Report comparison

| Preserved measurement | Existing result | Relationship to this work |
|---|---|---|
| SQL original 30-case full improved run | Execution 82.1%; numerical 79.2%; semantic 32.1% | Unchanged historical revision |
| SQL three-case incremental update | Execution 89.3%; numerical 87.5%; semantic 32.1% | Existing mixed-revision aggregate; not rerun |
| Report original 30-case baseline | Faithfulness 84.5% on four cases; factual correctness 6.9%; completeness 9.2%; one complete and three partial downloads | Preserved; no new Report benchmark |

All **754 existing agent-evaluation files** in the preservation manifest remain
byte-identical. Existing SQL/Report baseline and improved results were not
overwritten, rejudged, selectively replaced or pooled with these new datasets.
There is no compatible pre-integration 30-question Knowledge run in this task,
so these results establish a new integrated baseline, **not a measured improvement
attributable to Huy's changes**. The ten invoice questions also cannot be ranked
against the older, different 30-question commerce SQL benchmark.

## Integrity, cost and limits

The datasets were frozen before generation. Read-only Supabase schema, data and corpus snapshots match before/after. Invoice coverage is limited to one published invoice and four items, with some NULL monetary references; it does not establish multi-invoice or multi-currency generalization. Policy references are author-reviewed, not externally certified held-out gold.

The recorded configuration uses qwen/qwen3.8-27b at temperature 0, pinned E5/BGE CPU int8, and the existing RAGAS fork plus CodexCLIJudge(gpt-5.6-luna, medium). Optional multiquery and claim verification remain off. Full SHAs, versions and hashes are in the manifests and runtime-environment.json.

Cost records show 30 answer calls, 30 successful translation tasks, 11 invoice planning calls and 222 cached successful structured judgments, plus the CLI readiness smoke. Translation tokens, HTTP retries and dollar billing were not instrumented. The two scoring partitions verify identical source, package, configuration, dataset and generation hashes; no failed score was replaced.

Focused Report/invoice/integrity checks passed 87 tests. Knowledge runtime checks ran 85 tests with three failures already present on main; broad discovery also retains incompatible historical experiment expectations. Compilation and JavaScript syntax passed. No green full-suite, production deployment, data-writing publication test or fresh historical SQL/Report rerun is claimed.

## Artifacts

- [Knowledge per-question CSV](knowledge/per-question.csv),
  [raw scores](knowledge/scores.jsonl), [generations](knowledge/generations.jsonl),
  [frozen dataset](knowledge/dataset.json), [aggregate metrics](summary.json).
- [Invoice per-question CSV](../knowledge-invoice-2026-11-10-v2/invoice/per-question.csv),
  [raw scores](../knowledge-invoice-2026-11-10-v2/invoice/scores.jsonl),
  [frozen dataset](../knowledge-invoice-2026-11-10-v2/invoice/dataset.json),
  [aggregate metrics](../knowledge-invoice-2026-11-10-v2/summary.json).
- [Reproduction commands](README.md), [manifest](manifest.json),
  [integration verification](integration-verification.json),
  [supplemental metrics](supplemental-metrics.json), and before/after snapshots.
- Runner: `evaluation/run_knowledge_invoice_benchmark.py`; fixture definitions:
  `evaluation/knowledge_invoice_cases.py`; protocol:
  `evaluation/KNOWLEDGE_INVOICE_PROTOCOL.md`. Pin the recorded source revision
  and environment and use a new folder for any new experiment.
