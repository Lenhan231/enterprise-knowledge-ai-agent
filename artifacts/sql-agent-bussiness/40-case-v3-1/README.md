# SQL Agent benchmark v3.1 — post-review draft

**State: NOT FROZEN · 0 human reviewer approvals · held-out SQL Agent not run.**

This revision applies the [2026-11-21 AI-assisted v3 audit](../40-case-v3/AI_ASSISTED_SEMANTIC_REVIEW_2026-11-21.md) without overwriting any original v3 benchmark, review, preflight, or mutation files. It is a **new candidate** requiring independent review and adjudication of its own exact hashes.

## Versioned assets

- `cases_v3_1_draft.json`: 40 questions: 30 execute, 5 clarify, 5 abstain.
- `gold_sql_v3_1_draft.json`: 30 draft Gold SQL definitions.
- `gold_results_v3_1_provisional.json`: 404 provisional reference rows, carrying original snapshot provenance and updated results/column hashes.
- `FREEZE_MANIFEST_V3_1_DRAFT.json`: explicit draft state and content SHA-256 identities.
- `tests/sql/test_benchmark_v3_1_contract.py`: no-LLM regression tests for hashes, schema, aliases, order policy, and pending approval gates.

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

Previous v3 had 26 ordered executable cases. This version requires order-sensitive business scoring only where the question explicitly calls for ranking or TOP-N with ordering:

`B40-011, B40-012, B40-013, B40-014, B40-015, B40-029, B40-030` (7 cases).

The other 23 executable cases use order-insensitive row-multiset scoring. Gold SQL `ORDER BY` remains for deterministic display and result hashing; a different row order alone cannot fail their business result metric. In particular the TOP-1 B40-005 preserves the SQL tie-break selecting a unique month; its single output row needs no sequence constraint.

The candidate includes **per-case explicit `column_aliases`** for common equivalent semantic names. No aliases are accepted by guesswork, and an alias does not replace the required independent SQL semantic audit. The existing `40-case-v3/scorer_v3.py` supports these two contract fields; the original scorer source is unchanged. Its separate **Strict Result Exact Match** diagnostic still requires literal original column names and row values.

## Database checks and mutation evidence

- Rerun 3 changed Gold SQL outputs via Supabase: matched saved results and expected columns.
- Controlled wrong-aggregate on B40-002: missing-date count changes (7 missing in Dec 2025 versus 0 incorrectly).
- Controlled wrong boolean population B40-021: TRUE count changes from 17 total to 97 non-NULL rows.
- Controlled shifted snapshot boundary B40-024: two rows instead of three.
- The **old v3 23/26 mutation result is NOT a newly measured v3.1 detection rate**; full v3.1 mutation probes and repository preflight still need rerunning in the repository runtime. Do not silently carry over 88.46% as a revised-cohort result.
- Original preflight fingerprint `dbc14b99acc2920ffaeb4190ba45708982c971f0671b0b9e8114b595f2594028` is inherited as provenance, not a claim that this connector rerun re-verified the least-privilege executor role. Before freeze, run the approved preflight and reference generator on the exact v3.1 files.

## Local automated checks

From repo root, with locked development dependencies installed:

```bash
PYTHONPATH=src uv run --no-sync python -m unittest discover -s tests/sql -p 'test_benchmark_v3_1_contract.py' -v
PYTHONPATH=src uv run --no-sync python -m unittest discover -s tests -t . -v
```

CI's existing unittest discovery also includes the new regression file.

## Remaining freeze blockers

1. Independent human reviewers must review **this revised version**, each preserving their own record; adjudication resolves objections.
2. Re-run repository-approved read-only preflight, Gold-results generator, structural validator, scorer tests and full mutation set against v3.1 identities; commit new evidence without overwriting v3. 
3. Inspect the benchmark runner: the repository scorer currently trusts a boolean `sql_semantic_valid` supplied by an observation; it does not verify who audited the generated SQL. No production runner that emits cryptographically linked independent semantic-audit evidence was identified in the repository search. Define and enforce a separate SQL audit record (generated SQL hash, case ID, reviewer identity, independent reasoning, decision) before scoring E2E semantics.
4. Do not run the 40 held-out SQL Agent cases or mark `FROZEN` while the above gates are pending.

**Source-of-truth principle:** Old v3 reference/review is kept immutable. The exact v3.1 content SHA-256 values in the draft manifest identify the new candidate.

## Historical v3 manifest note

The original v3 `FREEZE_MANIFEST.json` records `REVIEW_CHECKLIST.md` SHA-256 `0aa3f33211a0c696a305928f78c4e7c599a53fe7e906a08a0cc43662e234066c`, but the checklist now hashes to `117b75d2477f3fa1c8519ed0d6c3825a1fb5861bb4b1c667e65cc0bb22540fdf` after the AI review links were appended. This is an **archival manifest mismatch**, not a mismatch in the v3 case set or Gold SQL/Gold Results. The existing v3 artifact test that verifies historical manifest hashes may fail until this provenance change is reconciled in an explicit follow-up. Do **not** silently update the archived manifest or present its original byte-hash check as passing.
