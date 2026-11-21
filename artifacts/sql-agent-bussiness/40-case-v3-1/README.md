# SQL Agent benchmark v3.1 — post-review draft

**State: NOT FROZEN · 0 human reviewer approvals · held-out SQL Agent not run.**

This revision applies the [2026-11-21 AI-assisted v3 audit](../40-case-v3/AI_ASSISTED_SEMANTIC_REVIEW_2026-11-21.md) without overwriting any original v3 benchmark, review, preflight, or mutation files. It is a **new candidate** requiring independent review and adjudication of its own exact hashes.

## Versioned assets

- `cases_v3_1_draft.json`: 40 questions: 30 execute, 5 clarify, 5 abstain.
- `gold_sql_v3_1_draft.json`: 30 draft Gold SQL definitions.
- `gold_results_v3_1_provisional.json`: 404 provisional reference rows, carrying original snapshot provenance and updated results/column hashes.
- `FREEZE_MANIFEST_V3_1_DRAFT.json`: explicit draft state and content SHA-256 identities.
- `scorer_v3_1.py` and `semantic_audit_v3_1.py`: versioned scorer with SQL/parameter/case hash linkage, independent audit decisions, and conservative AST checks for ranking and TOP-N.
- `PROTOCOL_V3_1.md`: the metric definitions and audit requirements for this revision.
- `runs/technical-validation-v3-1-20261121T114601Z/`: immutable read-only Gold and mutation reruns.
- `tests/sql/test_benchmark_v3_1_contract.py`: no-LLM regression tests for hashes, schema, aliases, ranking, scorer audit gates, and approval state.

## Six case-level corrections

| Case | Decision | Business rationale |
|---|---|---|
| B40-002 | Remove `completed_shipment_count` from required output and Gold projection | Question requests average delivery time plus count of missing dates; it does not ask for denominator. |
| B40-006 | Update intent and required column `commerce.geography.region` → `commerce.geography.city` | Both explicit conditions are city Hai Phong and age_group 25–34. |
| B40-017 | Correct intent to product grouping only | Return date 2023–2025 is a filter, not a grouping dimension. |
| B40-021 | Remove `observed_product_count` from Gold/required output and denominator requirement | Question requests count with `stockout_flag = TRUE` by category only. |
| B40-024 | Remove `observed_products` from Gold/required output | Question requests stock balance totals separately by snapshot, not an item-count denominator. |
| B40-029 | Correct intent to TOP 2 | Question and Gold SQL already use TOP 2; return reasons tie in selected data. |

The three modified Gold SQL queries **B40-002, B40-021, B40-024** were executed again against Supabase FA26AI69; each returned exactly the corresponding stored rows after removal of the previously extra columns (12, 4 and 3 rows respectively). The other 27 Gold SQL definitions and their original reference rows are unchanged. **404/404 is the provisional row-reproducibility record, not human approval or proof of every business formula.**

## Scoring contract

Seven cases require ordered output rows: `B40-011, B40-012, B40-013, B40-014, B40-015, B40-029, B40-030`. The separate ranking contract also applies to B40-005: its returned row sequence is unordered because it has one row, but its TOP-1 selection must use the required rank and tie-break. The v3.1 AST check therefore verifies eight explicit ranking/TOP-N obligations across 30 executable Gold queries; the remaining 22 have no order-sensitive output requirement.

Row order alone cannot fail an unordered case's business result metric. Gold SQL `ORDER BY` remains for deterministic display and result hashing. The TOP-1 entity/month selection contract is checked independently of output row ordering.

The candidate includes **per-case explicit `column_aliases`** for common equivalent semantic names. No aliases are accepted by guesswork, and an alias does not replace the required independent SQL semantic audit. The existing `40-case-v3/scorer_v3.py` supports these two contract fields; the original scorer source is unchanged. Its separate **Strict Result Exact Match** diagnostic still requires literal original column names and row values.

## Database checks and mutation evidence

- Fresh repository preflight verified the allowlisted frozen analytics snapshot and read-only role. Its fingerprint `dbc14b99acc2920ffaeb4190ba45708982c971f0671b0b9e8114b595f2594028` matches the v3.1 provisional references; `commerce.orders.order_date` is PostgreSQL `date`.
- The repository-approved generator executed all 30 v3.1 Gold queries read-only. All 30 SQL/parameter/column/row results exactly match the provisional results (404 rows total). The run is provisional and has zero human approvals.
- All 28 controlled mutations were attempted read-only. Result-based detection is 23/26 (88.46%); three valid mutations were observationally equivalent on this frozen snapshot. Approved-join, join-fanout, and population-contract validator probes each detected 1/1 assigned mutations. This is a newly measured v3.1 result, distinct from the historical v3 evidence.
- No SQL Agent generation calls, held-out execution, or database writes occurred.
- Full run inputs, hashes, output, and limitations are in [the technical validation report](TECHNICAL_VALIDATION_REPORT_2026-11-21.md). Historical v3 files remain unchanged.

## Local automated checks

From repo root, with locked development dependencies installed:

```bash
PYTHONPATH=src uv run --no-sync python -m unittest discover -s tests/sql -p 'test_benchmark_v3_1_contract.py' -v
PYTHONPATH=src uv run --no-sync python -m unittest discover -s tests -t . -v
```

Executed with the repository Python 3.11.16 environment: the v3.1 contract tests passed 21/21, the benchmark package passed 45/45, and all SQL tests passed 544 (10 skipped). The full repository run had one unrelated HEIF encoder error; the preserved v3 artifact suite has one known historical checklist-manifest hash mismatch. Exact commands and outcomes are recorded in the technical validation report. CI discovery includes the new v3.1 tests.

## Remaining freeze blockers

1. Two independent human reviewers must review the exact v3.1 case, Gold, and output-contract hashes; adjudicate any disagreement. The audit-linkage code verifies matching inputs and records reviewer identity/evidence, but does not prove the reviewer is independent or replace human review.
2. Resolve or explicitly accept the full-suite HEIF encoder environment error and the historical v3 checklist hash mismatch. Do not rewrite the archived v3 manifest to hide the mismatch.
3. Keep `FREEZE_MANIFEST_V3_1_DRAFT.json` in draft state until reviews, adjudication, and any required test-environment follow-up are complete.
4. Do not run the 40 held-out SQL Agent cases or mark `FROZEN` before the exact v3.1 contract is independently reviewed and frozen.

**Source-of-truth principle:** Old v3 reference/review is kept immutable. The exact v3.1 content SHA-256 values in the draft manifest identify the new candidate.

## Historical v3 manifest note

The original v3 `FREEZE_MANIFEST.json` records `REVIEW_CHECKLIST.md` SHA-256 `0aa3f33211a0c696a305928f78c4e7c599a53fe7e906a08a0cc43662e234066c`, but the checklist currently hashes to `117b75d2477f3fa1c8519ed0d6c3825a1fb5861bb4b1c667e65cc0bb22540fdf` after the AI review links were appended. The exact original checklist bytes were recovered from Git commit `281aed8c16006280540adc5605b129fc132bf4b6` and archived at [`historical/REVIEW_CHECKLIST_at_v3_manifest.md`](historical/REVIEW_CHECKLIST_at_v3_manifest.md), with the original SHA-256 independently verified. The historical v3 artifact test now verifies this archived snapshot against the original manifest digest, while checking the current checklist separately for the AI review link. **Neither the old manifest nor the current checklist has been rewritten.** The previous failed test run remains an accurate historical record; the revised test's CI result must be checked independently.
