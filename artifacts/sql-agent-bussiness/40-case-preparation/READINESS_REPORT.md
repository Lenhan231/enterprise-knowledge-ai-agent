# 40-case preparation readiness

**Verdict: READY_FOR_HUMAN_REVIEW**

**READY_FOR_40_CASE_EXECUTION = NO**

## Prepared cohort

- Original design plan remains unchanged and is still `DESIGN_ONLY_NOT_FROZEN`.
- V2 case-set SHA-256: `a759615f58dbb843296ce3d54642be3576374309a3bf4451546f771ebc2641a4`; source-plan canonical SHA-256: `77a2487a275ff678c82d693d0be35c55bad834f169895fc0f5d67dfc6eafaa43`.
- Distribution: 30 execute, 5 clarify, 5 abstain without query. Candidate structural validator: `PASS_STRUCTURAL_DRAFT` with 0 errors.
- Every original candidate is audited in `CANDIDATE_AUDIT.md`; pilot overlap dispositions are in `DUPLICATE_REVIEW.md`. Replacements with no original rationale are called out for reviewer decision.

## Frozen database evidence

- Database classification: `frozen-analytics-snapshot`; read-only role and host allowlist verified.
- Fingerprint: `dbc14b99acc2920ffaeb4190ba45708982c971f0671b0b9e8114b595f2594028`; preflight captured `2026-11-21T05:51:51.334549+00:00`.
- Approved live schema: 15 tables; 47 inventory snapshots; 0 required candidate columns missing. `commerce.orders.order_date` is `DATE`.
- Snapshot facts: stock_on_hand follows the approved NOT NULL contract; days_of_supply is all NULL on 2025-10-31; current geography has only East. The fresh preflight records targeted category, geography, sales-filter and NULL checks.
- Information schema exposed no PK/FK metadata; relationship/key checks rely on the approved migration contract. This remains a reviewer-visible limitation.

## Gold SQL and provisional references

- Gold SQL: 30/30 authored independently by Codex from the question/schema/metric contract; SQL Agent outputs used: 0.
- Gold structural validation: `PASS_STRUCTURAL_DRAFT`, 30/30 pass, 0 errors. Checks include approved sources/columns/joins, output contract, bound parameters, date predicates, ranking direction/order and TOP-N.
- Frozen read-only reference execution: 30/30 completed, 0 failures, 0 empty results, 395 rows stored. All statuses remain `PROVISIONAL_NOT_APPROVED`; SQL Agent generation calls: 0; held-out Agent executed: `False`.
- Reference consistency validation: `PASS_PROVISIONAL_REFERENCE`, 30/30 pass. Per-case result hashes are stored in `gold_results_provisional.json`.
- Provisional result file SHA-256: `56dbddbf953d411c538bb0b7eef3db15cbb23358a5d56221463f50decd9b60bb`. Gold SQL definition SHA-256: `484a2dcd77b4352eec1dee30e56b0dd79690f74b829c1b0ed516832b25ba9fe6`.

## Human review and remaining gates

- Reviewer 1 approvals: 0; Reviewer 2 approvals: 0; adjudications: 0. No signatures or independent approvals are claimed.
- `FREEZE_MANIFEST.json` is `PENDING_REVIEW` with freeze state `DRAFT`; no case, oracle or cohort is marked `APPROVED` or `FROZEN`.
- Reviewers must accept/reject all question substitutions, metric formulas, semantic overlap dispositions, gold SQL/results and tolerances.
- B40-026–030 use typed frozen-context injection but no live conversation adapter is implemented or verified; these are not yet reproducible live multi-turn cases.
- No 40-case SQL Agent evaluation and no new model comparison were run.

The package is ready for human semantic review. It is not ready for held-out execution until all freeze gates and the follow-up adapter are approved.

## Test and static-check evidence

| Suite/check | Passed | Failed | Skipped | Status |
|---|---:|---:|---:|---|
| Preparation dataset/gold/result tests | 21 | 0 | 0 | PASS |
| Existing SQL benchmark package tests | 43 | 0 | 0 | PASS |
| SQL semantic contracts | 44 | 0 | 0 | PASS |
| JOIN duplication checks | 18 | 0 | 0 | PASS |
| Inventory integration | 13 | 0 | 0 | PASS |
| Inventory snapshot contracts | 5 | 0 | 0 | PASS |
| Python syntax compilation | — | 0 | — | PASS |
| `git diff --check` and new-artifact whitespace scan | — | 0 | — | PASS |

Tests ran with Python 3.11.16. The preparation and benchmark suites are offline; the only live database work was the approved read-only preflight and author-written reference SQL execution described above.
