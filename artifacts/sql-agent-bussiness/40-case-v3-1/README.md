# SQL Agent benchmark v3.1 case set — v3.3 scorer draft

**State: NOT FROZEN · Reviewers 1 and 2 recorded 40/40 APPROVE · adjudication pending · held-out SQL Agent not run.**

The v3.1 case set and Gold artifacts remain unchanged. Scorer/protocol v3.3.0 retains canonical hybrid result matching and separate business/output-contract metrics, and permits E2E PASS when unapproved extra columns have complete linked safety-review evidence and are the only output-contract deviation. Unreviewed or unverifiable extra columns become `REVIEW_REQUIRED`. No original v3 benchmark, review, preflight, mutation file, or historical score was overwritten.

## Versioned assets

- `SEMANTIC_REVIEW_V3_1.html`: local review UI for the 40 cases, 30 Gold SQL queries/results, independent reviewer decisions, and adjudication. From this directory run `python3 -m http.server 8765 --bind 127.0.0.1`, then open `http://127.0.0.1:8765/SEMANTIC_REVIEW_V3_1.html`. Autosave is only in that browser's localStorage; it does not write a JSON file into this folder or sync to another browser. Export the completed reviewer JSON and verify the download before closing the page.
- `review_v3_1_reviewer_1_Lenhan231_complete.json`: Reviewer 1's 40/40 APPROVE record, logged from the user's confirmation after the HTML failed to leave a recoverable export. Its timestamp is when the record was logged, not the original per-case review time; no original rationales were provided.
- `review_v3_1_reviewer_2_user_reported_complete.json`: Reviewer 2's 40/40 APPROVE record from the user's report that their friend completed the review before the HTML reset. The reviewer's actual identity and original per-case timestamps/rationales were not supplied; the record labels this provenance explicitly.
- `cases_v3_1_draft.json`: 40 questions: 30 execute, 5 clarify, 5 abstain.
- `gold_sql_v3_1_draft.json`: 30 draft Gold SQL definitions.
- `gold_results_v3_1_provisional.json`: 404 provisional reference rows, carrying original snapshot provenance and updated results/column hashes.
- `FREEZE_MANIFEST_V3_1_DRAFT.json`: explicit draft state and content SHA-256 identities.
- `scorer_v3_1.py`, `semantic_audit_v3_1.py`, and `output_safety_audit_v3_3.py`: scorer v3.3.0 with canonical column mapping, decimal-aware row matching, separate output-contract metrics, independent SQL audit linkage, additional-output safety review linkage, and conservative ranking/TOP-N AST checks.
- `PROTOCOL_V3_1.md`: scoring v3.3 metric definitions and audit requirements for the unchanged v3.1 case set.
- `runs/technical-validation-v3-1-20261121T114601Z/`: immutable read-only Gold and mutation reruns.
- `tests/sql/test_benchmark_v3_1_contract.py`: no-LLM regression tests for hashes, all 30 Gold outputs, canonical alignment, row matching, output contract, audit linkage/export, ranking, and approval state.

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

Canonical matching accepts exact field names, case-specific aliases, or identical SQL projection expressions with resolvable source-column lineage. Ambiguous mappings become `REVIEW_REQUIRED`; fuzzy matching is disabled. Business Result Accuracy compares row content by an explicit case business key or duplicate-preserving multiset. Output Contract Compliance separately checks unexpected columns, row limits, and order-sensitive output. E2E requires an independent SQL audit PASS, business result PASS, and runner security evidence. An extra column only avoids E2E failure after a separate reviewer decision is linked to the exact SQL, parameters, case/set, complete result and column values; the Output Contract metric still fails. Missing evidence is `REVIEW_REQUIRED`. The plain JSON review record is unauthenticated and does not prove reviewer identity or independence. Neither metric substitutes for the required independent SQL semantic audit. The historical v3 scorer remains unchanged.

For independent SQL review, create a `sql-semantic-audit-decisions.v1` JSON file and use the exporter documented in [`PROTOCOL_V3_1.md`](PROTOCOL_V3_1.md). For additional output, create a separate `sql-agent-additional-output-safety-decisions.v1` file with all seven evidenced checks and use `output_safety_audit_v3_3.py`. Neither exporter decides safety or semantic correctness. Records are not signed or identity-authenticated; they do not create or prove human review.

## Database checks and mutation evidence

- Fresh repository preflight verified the allowlisted frozen analytics snapshot and read-only role. Its fingerprint `dbc14b99acc2920ffaeb4190ba45708982c971f0671b0b9e8114b595f2594028` matches the v3.1 provisional references; `commerce.orders.order_date` is PostgreSQL `date`.
- The repository-approved generator executed all 30 v3.1 Gold queries read-only. All 30 SQL/parameter/column/row results exactly match the provisional results (404 rows total). The run remains provisional; two approval records are logged, and adjudication is pending.
- All 28 controlled mutations were attempted read-only. Result-based detection is 23/26 (88.46%); three valid mutations were observationally equivalent on this frozen snapshot. Approved-join, join-fanout, and population-contract validator probes each detected 1/1 assigned mutations. This is a newly measured v3.1 result, distinct from the historical v3 evidence.
- No SQL Agent generation calls, held-out execution, or database writes occurred.
- Full run inputs, hashes, output, and limitations are in [the technical validation report](TECHNICAL_VALIDATION_REPORT_2026-11-21.md). Historical v3 files remain unchanged.

## Local automated checks

From repo root, with locked development dependencies installed:

```bash
PYTHONPATH=src uv run --no-sync python -m unittest discover -s tests/sql -p 'test_benchmark_v3_1_contract.py' -v
PYTHONPATH=src uv run --no-sync python -m unittest discover -s tests -t . -v
```

The v3.3 contract run is recorded in `TECHNICAL_VALIDATION_REPORT_2026-11-21.md`; it exercises all 30 stored reference result sets without calling the SQL Agent. Re-run the focused test after any scorer or protocol change. Synthetic audit fixtures are not real reviewer records. The v3.1 reviewer 2 record remains user-reported and hash-linked; the case cohort stays unfrozen until adjudication and formal gates are complete.

## Remaining freeze blockers

1. Adjudicate the two 40/40 approval records against the exact v3.1 case, Gold, and output-contract hashes. Reviewer 2's decision is user-reported; obtain a direct identity/export if the formal process requires it. The audit-linkage code binds records to inputs but does not prove reviewer independence.
2. Resolve or explicitly accept the full-suite HEIF encoder environment error. The historical v3 checklist test now checks the archived original bytes; do not rewrite the archived v3 manifest to hide the mismatch.
3. Keep `FREEZE_MANIFEST_V3_1_DRAFT.json` in draft state until reviews, adjudication, and any required test-environment follow-up are complete.
4. Do not run the 40 held-out SQL Agent cases or mark `FROZEN` before the exact v3.1 contract is independently reviewed and frozen.

**Source-of-truth principle:** Old v3 reference/review is kept immutable. The exact v3.1 content SHA-256 values in the draft manifest identify the new candidate.

## Historical v3 manifest note

The original v3 `FREEZE_MANIFEST.json` records `REVIEW_CHECKLIST.md` SHA-256 `0aa3f33211a0c696a305928f78c4e7c599a53fe7e906a08a0cc43662e234066c`, but the checklist currently hashes to `117b75d2477f3fa1c8519ed0d6c3825a1fb5861bb4b1c667e65cc0bb22540fdf` after the AI review links were appended. The exact original checklist bytes were recovered from Git commit `281aed8c16006280540adc5605b129fc132bf4b6` and archived at [`historical/REVIEW_CHECKLIST_at_v3_manifest.md`](historical/REVIEW_CHECKLIST_at_v3_manifest.md), with the original SHA-256 independently verified. The historical v3 artifact test now verifies this archived snapshot against the original manifest digest, while checking the current checklist separately for the AI review link. **Neither the old manifest nor the current checklist has been rewritten.** The previous failed test run remains an accurate historical record; the revised test's CI result must be checked independently.
