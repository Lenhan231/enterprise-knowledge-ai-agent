# SQL hybrid follow-up — 2026-11-04

**Recommendation: MODIFY; keep production unchanged.** Deterministic field retrieval and the scalar-count correction improve the measured SQL cohort. Broader natural-language coverage, canonical/reference policy disagreements and Report delivery still prevent production readiness. No SQL agent replacement, metric formula, database permission, frozen reference, scoring implementation or judge configuration was changed.

## Implementation and scope

The isolated patch `evaluation/sql_hybrid_deterministic.patch` applies to `62489af`. It uses the existing SQL agent, SQLGlot AST, decoder, RBAC, approved joins, metric validation and read-only repository. Canonical inventory mapping and compilation remain active. Fully parsed field requests now render parameterized SQL directly instead of prompting and repairing a second interpretation. The existing bounded SQL repair remains on the ordinary generated-SQL path. Deterministic rendering makes no provider call and therefore has no LLM repair to perform.

The existing field-contract helper adds a small English/Vietnamese phrase dictionary. It preserves quoted values, exact projections, literal filters, dates, sort direction, stable key ordering and limits. Complex KPI, multi-table, conversational and unmatched-language requests retain the existing pipeline. Recognized but incompletely parsed field clauses clarify instead of dropping constraints. Runtime logic does not contain benchmark IDs or full benchmark question strings. This is a bounded grammar, not general natural-language intent understanding.

The compiler previously always grouped by snapshot_date. For a scalar count this removes the result when no products match. The fix uses the approved distinct-product COUNT without grouping and separately anchors its snapshot projection. Counts remain counts of observed products, not zero inventory balances. For annual inventory totals, the unchanged catalog explicitly permits one snapshot or separate snapshot groups. The candidate now clarifies that policy conflict rather than silently presenting monthly groups as an annual total.

## Root-cause audit

`semantic-audit.json` reviews all **20** zero semantic-equivalence results from the recorded production cohort: **3 genuine mismatches, 1 equivalent query under declared constraints, 14 reference/evaluator ambiguities, and 2 implementation/capability limitations**. These are diagnoses, not revised scores.

- S05: genuine empty-count error, fixed and confirmed against the database.
- S16: genuine requested/output grain mismatch, complicated by the frozen reference asking for a cross-date sum forbidden by the catalog. Now clarified; still scores zero against the untouched reference.
- S14: limited detail anti-existence query lacks stable ordering; remains outside the new parsed-field path and is not fixed.
- S04: fixed-date grouping adds provenance but does not split category totals. Output schema and safety LIMIT differ; do not invent TOP-N to imitate the reference.
- S10/S11: month observations versus a reference that assumes the closing snapshot. These diverge with multiple snapshots; a closing date must not be silently substituted.
- S20: discount_amount is NOT NULL in the commerce schema. COALESCE(discount_amount,0) is redundant under that constraint; no business formula change is justified.
- S23: independently aggregated product-level ratios preserve NULLIF and grain. Extra product enrichment/output naming differs from the reference.
- S27: safe independent aggregates, but a period observation sum differs from a closing-snapshot reference. COALESCE correctly labels order-only categories while the reference can leave that label NULL.
- S28 already counts excess duplicate rows correctly. Existing adversarial fixtures distinguish duplicate groups, excess rows and all participating rows; no new fix was needed.

`clarification-review.json` separately records necessary refusals, unnecessary field-request clarifications fixed by the new path, and uncertain/capability-limited requests. No unavailable supplier/current-stock data is described as an undefined metric, and no user is asked to approve an existing join.

## Fresh paired SQL evaluation

Both variants answered the same **20 predeclared cases**: six prior frozen field fixtures, four separately frozen bilingual paraphrases, three canonical inventory cases, three cross-domain cases and four unsupported requests. The original question/reference items were copied unchanged; new fixtures were committed before generation. Existing Ragas SQLSemanticEquivalence and custom execution/numerical scorers used the unchanged `CodexCLIJudge` gpt-5.6-luna/medium and the same agent provider configuration. All **40 generations and 120 metric records** completed with **zero failed provider attempts and zero evaluator errors**.

| Category | Execution accuracy, production → candidate | Semantic equivalence | Numerical accuracy | LLM calls |
|---|---:|---:|---:|---:|
| Literal fields (6) | 4/6 → 6/6 | 4/6 → 6/6 | 2/4 → 3/3 | 10 → 0 |
| Natural field phrasing (4) | 3/4 → 4/4 | 2/4 → 4/4 | 2/3 → 2/2 | 4 → 0 |
| Canonical inventory (3) | 1/3 → 2/3 | 0/3 → 0/3 | 1/3 → 2/3 | 3 → 3 |
| Cross-domain (3) | 3/3 → 3/3 | 0/3 → 0/3 | 2/2 → 2/2 | 5 → 5 |
| Unsupported (4) | N/A | N/A | N/A | 3 → 0 |
| Overall | **11/16 → 15/16** | **6/16 → 10/16** | **7/12 → 9/10** | **25 → 8** |

The unchanged numerical scorer gives a failed supported request zero before checking numeric applicability. This includes failed metadata requests F01/N04 in the baseline. On the same ten numeric-applicable cases the comparison is **7/10 → 9/10**; official scores above are not rewritten. Four unsupported cases are N/A in these metrics. Manual review finds **4/4 valid refusals in both variants**. S16 remains a frozen-supported failure, not an extra benchmark success for refusing safely.

Successful SQL execution occurred on **13/16 → 15/16 supported requests**; execution accuracy additionally checks result correctness. Overall p50/p95 request latency was **1.870/4.370 s → 1.101/3.532 s**. Literal-field p50/p95 was **1.870/3.765 s → 1.104/1.145 s**. These are small observed samples with different outcomes and occasional retries, not a performance guarantee. The prior 30-case benchmark was not rerun or combined into these denominators. Detailed category results are in `comparison.json`.

Measured SQL application revisions: production source unchanged from `62489af`, candidate `ff5de28270450c89ae39dd17ac535020834b9789`. A subsequent test-only revision `5180522` adjusts an old experiment's assumption that ordinary metadata retrieval must fail outside single-pass mode; it does not change SQL source or scores.

## Regression, security and main integration

**177 focused SQL/Report tests passed** on the SQL candidate. New fixtures cover bilingual constraints, zero model calls, authorization before access, bounded repair on the generated path, NULL preservation, duplicate names, tied rankings, multiple snapshots and the empty scalar count. Existing join/metric suites cover unsafe multi-fact joins, incomplete join keys, wrong aggregates and duplicate counting.

The final SQL-candidate full run had **721 tests, 10 failures, 51 errors, 19 skips**. Compared with the recorded production run of 715 tests, 11 failures and 51 errors, there are no new failure/error identities after correcting the experiment-specific assertion. An unrelated timing test passed this time; no retrieval fix or causal improvement is claimed. The full suite is not green. Later Report-only changes passed **106 focused Report/orchestration tests**, plus the new evidence tests; they were not given another full-suite or full SQL benchmark.

An isolated merge with `main` at `f7ec885` exposed one Report UI conflict. The resolution retains QuocAn's confirmation/resubmission loop and main's session generation/subject guards and 401 handling. **20 integration tests passed**, plus the separate session-change/401 security test. `evaluation/sql_report_main_reconciliation.patch` preserves that reviewed resolution against the pinned main revision. Both Report follow-up patches apply cleanly to the reconciled checkout. This integration work was not merged into production.

GitHub CI already failed on QuocAn (`41813201217`: 777 tests, 6 failures, 53 errors) and main (`41818532150`: 685 tests, 11 failures, 55 errors). One relevant QuocAn failure came from historical ablation tests using git show on a baseline commit absent in shallow checkout. CI now fetches full history. The completed run on `27d2539` (`41835488411`) confirms that error is fixed: **787 tests, 6 failures, 52 errors, 35 skips**, with no new failure/error identities. The ten new experiment-only tests skip in unpatched production discovery and pass in their isolated focused runs. Production Report discovery separately passes **89 tests with 3 experiment-only skips**. See `ci-after.json`.

Other blockers include missing optional Ragas/OCR/UI dependencies, obsolete API imports and unrelated document/retrieval tests. No existing tests were disabled or unrelated dependencies added to make CI appear green. Container/HTTP steps were skipped after unit discovery failed; they are not verified by this experiment.

## Report compatibility: separately versioned live evidence

The three predeclared cases R01, R06 and R16 were run against real database evidence on production and the SQL candidate. First attempts and provider-error retries are retained separately from SQL scores. No Report Ragas scores are claimed in this compatibility probe.

- **R01 inventory health:** both variants produced partial downloads. Candidate evidence validated four facts; narrative citation/format validation failed. This is not an SQL execution failure. Generated prose was rejected, including a fraction/percentage presentation error, rather than accepted as verified.
- **R06 monthly flows:** both variants clarified after the planner emitted units_sold instead of catalog ID inventory_units_sold, sometimes also using forbidden year/month mapping slots. A separate prompt-only trial exposes source fields and valid dimensions (`evaluation/sql_report_planning.patch`, revision `0ffa8f5`). It corrects the dimension context but the fresh R06 trial still uses the wrong metric ID. That trial is **not demonstrated as a solution**; runtime alias recovery would require separate validation.
- **R16 returns/refunds:** the initial quota failure was retried. The next SQL task completed with 200 returned detail rows, but legacy Report collection discarded its single oversized evidence block. An unnecessary Analytics summary call also encountered HTTP 413. This is evidence handling/provider capacity, not failed SQL evidence. The sample query is capped detail, not verified category/reason totals.

A separate Report evidence trial skips the chat summary during collection and splits rows into attributable passages of at most 50 rows with exact included/omitted coverage. Revision `5f6a5ab` retains **100 of 200 returned rows per section context**, but its writer and bounded retry receive HTTP 413. Diagnostics establish a **7,000-token limit versus roughly 9,130 requested tokens**; key rotation cannot fix an oversized request.

The refined trial (`06952c7`, final `evaluation/sql_report_evidence.patch`) reserves room for output using a conservative 10,000-character SQL context allowance. Its **fresh R16 run produces a partial download**, with SQL collection complete, **32/200 rows selected and 168 omitted per section context**, one of three sections complete, and two unavailable/failed. Latency is **26.572 s**, with **11 measured provider attempts including three recovered HTTP 429 attempts**. Summary grounding still rejects an unsupported/ambiguous number. This establishes improved evidence delivery, not complete category/reason totals or semantic correctness of every narrative claim. A later appendix-only change (`388ccc6`) was verified by replaying all eight successful captured responses through the real read-only database, with identical status/coverage and **zero new model API calls**. The downloaded appendix now states included/omitted SQL rows explicitly. No fresh model score or latency is claimed for that rendering-only revision.

Provider diagnostics record status, error code and token-budget numbers without prompts, credentials or source contents. All failed-case attempts are retained; successful partial downloads are not regenerated merely because a recovered provider attempt occurred. The character allowance is a heuristic rather than token accounting, and provider capacity remains a reliability risk.

## Reproduction and remaining limits

Use `evaluation/run_sql_hybrid_followup.py --stage generate|score --mode production|candidate`. SQL fixtures live in `fixtures/` and are hash checked. Apply the SQL patch to `62489af` and use the matching `evaluation/hybrid_field_contract.py` in an isolated worktree. Optional Report trials apply the planning/evidence patches in order, using a new `--output` folder whenever source hashes differ. Manifests prevent changed-source resumption into a scored cohort. Preserve every attempt and frozen input. The first prompt-only Report trial was generated in a nested worktree directory and copied byte-for-byte to the published artifact folder; output paths are now resolved before changing directory.

Keep the variant isolated. Quoted literal filters and supported clause grammar are covered; arbitrary natural-language paraphrases are not. General generated SQL still lacks a universal independent intent proof. Cross-domain/reference ambiguities remain, S14 ordering and S13 delta support remain open, and S15's broad metric request still needs clearer stored/aggregate guidance. Report provider capacity, canonical ID selection and legacy narrative assurance remain blockers. Full integration/container checks and production readiness have not been established.
