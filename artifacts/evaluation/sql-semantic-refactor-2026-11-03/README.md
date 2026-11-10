# SQL interpretation evaluation — November 3, 2026

This is a separate experiment over the frozen [November 2 benchmark](../agent-benchmarks-2026-11-02/README.md). Its questions, reference SQL/results, identity counts, scoring code, Groq model settings and Codex Ragas judge configuration are retained. No reference answers were changed to accommodate the implementation.

Read [AUDIT.md](AUDIT.md) for the case-specific root causes and evidence limits. Final measurements are in `comparison.json`; raw attempts and metric judgments are separated by variant. Report compatibility is covered by regression tests; this experiment does not re-score Report or Knowledge.

## Resumed SQL comparison ? November 3

Report benchmarking was stopped at the user's request. SQL generation and scoring are complete for all 30 questions: 44 attempts including bounded quota retries, 90 current metric records, no evaluator errors or pending SQL scores.

| Metric | November 2 | Resumed November 3 | Change |
|---|---:|---:|---:|
| Execution accuracy (28 scored) | 21.4% | 46.4% | +25.0 percentage points |
| SQL semantic equivalence (28 scored) | 14.3% | 17.9% | +3.6 points |
| Numerical accuracy (27 scored) | 22.3% | 44.8% | +22.5 points |

The same questions, frozen references, model and judge configuration were used. All three configured Groq keys produced successful responses during the resumed SQL run. Nine latest case outcomes still failed on quota limits, so this is an operational result under provider constraints, not a clean estimate of algorithm-only improvement. Query execution increased from 11 to 17; clarification responses decreased from 14 to 3, with several failures now caused by quotas instead.

Machine-readable comparison: [resumed-comparison.json](resumed-comparison.json). Report's interrupted run and per-key quota diagnostic are retained separately in `../report-rebenchmark-2026-11-03/`; it is not a completed Report evaluation.

## Measured results and release coverage

The earlier **complete live cohort without final provider failures** is revision **`6ed9a19`**. It precedes the final standalone transaction-routing change, explicit unreviewed-alias protection and deterministic missing-dimension guard. These later changes have regression coverage; do not attribute the following full-cohort measurements to them.

| Metric | Frozen November 2 | Fresh baseline `3ba340d` | Complete live `6ed9a19` |
|---|---:|---:|---:|
| Execution accuracy | 21.4% (28 scored) | 25.0% (28) | 53.6% (28) |
| SQL semantic equivalence | 14.3% (28) | 14.3% (28) | 25.0% (28) |
| Numerical accuracy, inherited method | 22.3% (27) | 26.0% (27) | 52.2% (26) |

All cohorts above have 30 questions and zero evaluator errors. The fresh baseline and `6ed9a19` each have zero final provider failures. Their variation from November 2 demonstrates that temperature zero does not make repeated generations and judgments identical.

The inherited numerical scorer gives a failed supported request zero before checking whether the gold output contains numerical measures. Identifier/name-only S14 changes from zero to N/A when it executes. S25 and S26 are also identifier-only requests. **Supplementary fixed-applicability comparison:** excluding identifier/date-only references in both cohorts gives **29.2% → 56.6% over the same 24 cases**. The inherited score files and primary metrics remain unchanged.

| Operational measure, 30 questions | Fresh baseline | Complete live `6ed9a19` |
|---|---:|---:|
| Executed queries, including empty results | 11 | 21 |
| Supported-question clarifications | 13/28 | 7/28 |
| Non-clarification validation failures | 5/30 | 0/30 |
| p50 request latency | 2.598 s | 2.238 s |
| p95 request latency | 4.257 s | 3.952 s |
| Instrumented generation attempts | 61 (2.03/request) | 48 (1.60/request) |
| Reported input/output tokens | 102,264 / 7,535 | 72,824 / 5,146 |

These timing samples are descriptive, not a statistical performance guarantee. Pipeline-call reduction for accepted inventory mappings is additionally verified with mocks. Provider refusals before an underlying generation attempt can yield zero counted calls; the quota-limited sample is unsuitable for call/latency comparisons.

The subsequent **`95aa2b3`** run is retained in `quota-95aa2b3/`: **5/30 cases attempted, 1 executed and 4 daily-quota failures**, after exhausting primary, backup and `GROQ_API_KEY_RAGAS`. The other 25 were not scheduled. Its small-sample scores are not an overall accuracy estimate. The final-revision `combined/` rerun was subsequently resumed with all three keys; its completed results are shown above. The separate [scope smoke](unsupported-scope-smoke.json) initialized the real least-privilege repository and verified S30's deterministic supported alternative with **zero provider calls and zero request-time database queries**; this was not a staging HTTP test.

| Focused ablation, audited 10 cases | Execution | Semantic | Numerical | Final quota failures |
|---|---:|---:|---:|---:|
| Fresh baseline | 0% | 0% | 0% | 0 |
| Temporal only | 40% | 0% | 40.5% | 0 |
| Ontology only | 0% | 0% | 0% | 0 |
| Schema context only | 0% | 0% | 0% | 0 |
| Compiler only | 0% | 0% | 0% | 6 |
| Combined `6ed9a19` | 50% | 20% | 45.0% (9 scored) | 0 |

Temporal normalization has a directly observed independent effect on result accuracy. Schema/candidate changes alone do not resolve the earlier validation failures. The compiler-only ablation is confounded by six daily-quota failures and cannot establish the compiler's standalone effect. Combined results support an interaction between temporal validation, compilation and structural-query support; they do not isolate each component's marginal benefit.

Verified root causes include redundant identical snapshot ends, a valid product-period query rejected before a bad repair, the writer's month boundary error, and an overly narrow outer-join predicate rule. No incorrect alias selection was proved in the original ten traces. Final transaction routing, unreviewed-metric protection and the new scope guard are verified through regression tests, not a complete final live cohort.

## Changes

| File | Behavior |
|---|---|
| `src/core/analytics/metric_mapping.py` | Normalize an identical snapshot end, check explicit period contracts, treat executable inventory aliases as candidates, and share the deterministic inventory compiler. Unresolved/draft requirements remain protected. |
| `src/core/analytics/metric_validation.py` | Recognize explicit English/Vietnamese months, quarters and years as ranges; accept DATE casts; allow product observations across dates without forcing GROUP BY. Key-only inventory diagnostics do not approve business measures or hidden measure predicates. |
| `src/core/analytics/text_to_sql.py` | Select relevant schema context with primary keys/grain; retain bridge tables and approved joins. Permit date predicates beside an approved join key. Backend authorization and the full SQL allowlist remain independent of prompt selection. |
| `src/core/agents/sql_analytics_agent.py` | Compile accepted inventory mappings without a second SQL LLM call. Standalone transaction-only requests skip the inventory interpreter. Check known unavailable dimensions against the full approved schema before provider calls and offer a supported alternative. Expose execution status, output column units and validated inventory scope through existing result metadata. |
| `src/core/reports/planning.py` | Reuse the shared compiler and normalized period bounds. Rendering, confirmations and narrative grounding are retained. |

No metric formulas, approval statuses, schema permissions, database migrations, models, dependencies or unrelated analytics routes changed. Context-aware follow-ups still use the existing inventory conversation contract. Non-inventory canonical alias handling and arbitrary multi-grain calculations have not been redesigned.

## Experiment design

The complete comparison uses all 30 SQL questions. Focused ablations use the ten audited cases: S02, S03, S04, S10, S11, S14, S23, S26, S27 and S28.

| Variant | Changes relative to application baseline `3ba340d` |
|---|---|
| baseline | Historical application modules loaded directly from Git. |
| temporal | Period/date normalization, DATE equivalence, and product-period grain validation. |
| ontology | Inventory alias candidacy and key-only observation diagnostics. |
| schema | Relevant schema context and primary-key/grain information; no join-validator relaxation. |
| compiler | Deterministic inventory compilation while retaining the old interpretation and temporal rules. |
| combined | All final application changes, including safe join-side dates and standalone transaction routing. |

Application module hashes are recorded per variant. Historical modules are loaded only in the evaluation process; production has one SQL agent implementation. Full Git history containing `3ba340d` is required to reproduce ablations.

Frozen working input copies are ignored by Git and rebuilt by `prepare()` from the existing November 2 directory. Each manifest records the original input hashes and directory; only new generation/score records and metadata are committed here.

The read-only repeatable-read preflight re-executed all 28 supported reference queries and matched every frozen result. This verifies reference outcomes at preflight, not an exported or permanently pinned database snapshot. The account and repository keep their existing least-privilege checks and five-second statement timeout.

Generation runs are sequential with ten seconds between requests outside the measured request duration. Agent generation calls use primary Groq, numbered backups and `GROQ_API_KEY_RAGAS` as the last fallback. The judge remains `CodexCLIJudge`, `gpt-5.6-luna`, reasoning `medium`. Failed attempts are retained. Calls mean logical provider generation invocations, including pacing-level retries; internal key-level HTTP attempts are not separately counted. Token totals include successful response usage, with missing usage counted separately.

`exploratory-*` folders preserve superseded application revisions and the stopped concurrent runs. They are excluded from final comparisons. `live-6ed9a19/` preserves the complete measured revision, and `quota-95aa2b3/` preserves the later interrupted quota-limited sample. The concurrent runs contended for shared quotas and are not performance evidence. Sequential runs are also unrandomized live measurements; provider cooldowns are included in request latency, so latency differences do not prove a fixed production speedup.

## Reproduction

Run generation variants sequentially. Keep the same `.env`, model and database contents. Do not regenerate reference files.

```powershell
uv run python -m evaluation.run_sql_semantic_ablation --stage verify
uv run python -m evaluation.run_sql_semantic_ablation --variant baseline --stage generate
uv run python -m evaluation.run_sql_semantic_ablation --variant combined --stage generate
uv run python -m evaluation.run_sql_semantic_ablation --variant temporal --stage generate --ids S02 S03 S04 S10 S11 S14 S23 S26 S27 S28
# Repeat the focused command with ontology, schema and compiler.
uv run python -m evaluation.run_sql_semantic_ablation --variant baseline --stage score
# Repeat scoring with combined, temporal, ontology, schema and compiler.
uv run python -m evaluation.run_sql_semantic_ablation --stage comparison
```

Successful generation checkpoints are reused. To reproduce an independent new sample, use a separate output directory in the runner instead of overwriting recorded attempts. Source hashes prevent accidentally scoring an existing variant against changed application code.

## Assurance and remaining limits

Execution and numerical matches do not establish equivalent SQL semantics. In particular, empty/count-zero cases and a partial detail sample can match by coincidence. Inspect semantic scores and query scope alongside result comparison.

Supported-question clarifications are reported as a proxy; they are not all certified unnecessary. S15's unspecified collection of metrics and S28's duplicate-row convention need care. No trusted per-case clarification labels were supplied in the dataset. Unsupported-only cases S29/S30 retain N/A accuracy scores and require manual refusal review; nonexecution alone does not establish a helpful or correct refusal explanation.

Manual review of the complete live cohort: S29's interpretation-error explanation is unhelpful, and S30 incorrectly claims delivery-date columns are absent even though shipment dates are approved. Neither supplies a useful supported alternative. Both avoid unsupported numerical answers, but that is not a successful refusal-quality result. The final full-schema guard fixes S30 deterministically; S29's explanation remains a limitation.

Semantic-equivalence failures have several distinct causes: S03 adds the required as-of date; S04 invents a top-10 limit; S10/S11 use a month range instead of the oracle's sole month-end observation, and S11 also returns only ten products. S20 lacks the oracle's NULL-discount-as-zero convention, which needs business review; S28 counts duplicate groups instead of excess rows. Current-result equality is insufficient to establish the same meaning under changed data. References and judge outputs were not adjusted to improve these scores.

S23 and S27 still need a proven contract for independently aggregated fact joins. S26 needs a supported cross-domain existence plan. Source availability is not the same as implemented semantic support. Product-name ambiguity, exact output scope/ranking limits, period-flow totals, unsupported-date explanations and model interpretation errors can remain. Free-form text is not proved correct by SQL validation.

The complete repository suite has known failures outside the affected paths; see [validation.json](validation.json). No failing tests were disabled and no unrelated failures were repaired.
