# Inventory-only SQL integration evaluation

**Recommendation: keep isolated; modify before merging.** The SQL agent is a usable inventory-only rehearsal candidate, but the full-suite and CI gates are red. Report benchmarking is deferred by the user's explicit instruction; no Report benchmark results are published here.

Implementation branch: `inventory-demo-integration-2026-11-04`. Measured candidate: `3564c0638d0c9654240d222638e02b1ea8b057c5`; baseline: `1a6470b84443d6f9819b242357e76435eb329ce5`. Production source on `QuocAn` remains unchanged. Runs occurred on 2026-11-05; the directory retains the task's 2026-11-04 name.

## Measured results

| Measure | Baseline | Candidate |
|---|---:|---:|
| Execution accuracy: frozen result match | 40/50 (80%) | 49/50 (98%) |
| Ragas SQL semantic equivalence | 21/50 (42%) | 34/50 (68%) |
| Numerical accuracy, applicable cases | 31/37 (83.8%) | 34/35 (97.1%) |
| Numerical accuracy, common 35-case applicability | 31/35 | 34/35 |
| Supported requests executed | 46/50 | 50/50 |
| Unnecessary supported clarifications | 3/50 | 0/50 |
| Audited valid refusals | 6/9 | 9/9 |
| LLM calls across 60 requests | 62 | 46 |
| Request latency p50 / p95 | 2.094s / 2.742s | 2.169s / 3.647s |
| Unrecovered provider failures | 0/60 | 0/60 |
| Evaluator errors | 0/180 scores | 0/180 scores |

Calls fell 25.8%; latency did **not** improve. These sequentially executed cohorts are descriptive measurements, not a controlled performance guarantee. Timing excludes ten-second inter-request pacing and excludes web/Auto routing overhead.

The frozen set has 50 primary requests and 10 paraphrases. Fifty records have supported SQL references. Nine are genuine unsupported/ambiguous requests. P47 incorrectly points to an unsupported turnover reference instead of the stock-comparison reference: its frozen record is retained and excluded from audited refusal denominators. See [fixture errata](fixture-errata.json). Oracles are independently authored and author-reviewed, not externally certified gold.

Ragas, its original metrics, and `CodexCLIJudge(gpt-5.6-luna, medium)` were retained. Agent model/temperature, package versions, source hashes, all three authorized Groq-key routing, and attempts are recorded in cohort manifests. Successful requests were not retried for higher scores. All SQL provider-error checks finished before Report was stopped/deferred.

## What changed

The existing SQL agent now uses deterministic rendering for fully parsed raw-field requests. Inventory measures retain canonical mapping and compilation. The shared SQL boundary permits only `commerce.inventory` and `commerce.products`; RBAC, approved joins, SQLGlot, read-only execution and the 200-row ceiling remain enforced.

Two-snapshot stock comparisons use exact observations, product intersection and after-minus-before values. Missing rows are excluded from intersection; NULL operands remain NULL. PostgreSQL-native date binding covers selected date casts and snapshot IN lists. Scalar counts preserve zero for empty filtered populations. Explicit separate-snapshot totals are accepted; unapproved combined annual totals are clarified.

## Audit and limits

- [Capability matrix](capability-matrix.md), [semantic audit](semantic-audit.json), [clarification audit](clarification-audit.json), [S12/S13/S16 audit](temporal-audit.json).
- [Paired results](final/paired-summary.json), [legacy paired results](legacy-final/paired-summary.json), [real PostgreSQL repair probes](postgres-repair-probes.json), [database keys/FK verification](data-assurance.json).
- Remaining strict result failure I49 is an extra reference product-name column absent from the question; product IDs and requested numerical values match. The 16 remaining semantic-score failures include valid FK/PK equivalences, output-provenance differences and an ambiguous NULL-ranking reference. Scores were not overridden.
- Identical SQL changed semantic scores for I19/I32. Legacy S12 has identical SQL **and rows**, but execution/numerical scores changed because column alignment is LLM-driven. Do not attribute this evaluator variation to code changes.
- Period rollups, operational reorder quantities, safety stock, live stock and cross-domain analytics remain unavailable without appropriate definitions/data. The parser supports bounded complete field clauses, not arbitrary natural-language syntax. Detail results remain capped at 200.

## Regression gates

194 focused tests ran: 191 passed and three experiment-only cases skipped. Final full suite: 752 tests, 36 failures, 96 errors, 39 skips; baseline: 739 tests, 11 failures, 51 errors, 39 skips. The 70 added failure identities exercise removed broad-domain contracts; existing unrelated failures remain. See [comparison](regression-comparison.json).

[GitHub CI](https://github.com/Lenhan231/enterprise-knowledge-ai-agent/actions/runs/41959184878) passed compilation but failed the full test suite (814 tests, 31 failures, 97 errors, 45 skips). Later container/HTTP checks were skipped. Obsolete comparison expectations and inventory smoke probes were updated; the remaining broad-domain tests were left visible rather than filtered out. Interactive web/Streamlit and authenticated staging HTTP were not exercised.

The `report/` directories inside SQL cohorts contain unchanged historical reference inputs used by the existing SQL scorer, not Report generations. Interrupted Report checkpoints remain local and are not part of this SQL delivery.

## Reproduction

Check out the measured revision and use the existing configured read-only database and provider environment. Do not rerun `freeze_inventory_demo.py` over these fixtures.

```powershell
uv run python -m evaluation.run_sql_hybrid_followup --mode candidate --worktree . --fixtures artifacts/evaluation/inventory-demo-2026-11-04/fixtures --output artifacts/evaluation/inventory-demo-reproduction --stage generate
uv run python -m evaluation.run_sql_hybrid_followup --mode candidate --worktree . --fixtures artifacts/evaluation/inventory-demo-2026-11-04/fixtures --output artifacts/evaluation/inventory-demo-reproduction --stage score
```

Use the same commands with `--mode production --production-root <baseline-checkout>` for the baseline. Reuse completed checkpoints; retry only provider failures. [Cohort index](cohorts.json) identifies interrupted/superseded diagnostic runs separately from the final measurements.
