# Scorer fairness audit — v3.3.0

This is an offline review of scorer v3.3.0 and the saved official run. It is not a new scorer, rescore, or change to official results. Source hashes are pinned in `REPRODUCIBILITY_MANIFEST.json`.

| Dimension | Current behavior and evidence | Fairness finding | Safe correction proposal | Negative regression / risk | Policy vs implementation |
|---|---|---|---|---|---|
| DATE/TIMESTAMP outputs | Business rows are compared literally. B40-001 and B40-004 use verified `DATE` source columns and return exact UTC month-start timestamps; strict comparison proves B40-001, B40-004 rows match. | Confirmed false negatives for calendar-month display values. | In a future version, normalize only known DATE-derived month keys at exact UTC 00:00 on day one; reject timezone shifts, non-boundaries and unknown source types. | Must fail if timestamp is non-UTC, non-midnight, not first-of-month, or any non-date cell/multiplicity differs. | Implementation measurement gap; no official policy changed here. |
| Case-insensitive aliases | Scorer folds labels with `strip().casefold()` and accepts case-specific aliases. | Reasonable exact-name behavior; safe against case-only serialization drift. | Keep normalization exact and deterministic. | No fuzzy/substring mapping; duplicate canonical mapping remains failure/review. | Existing policy is sound. |
| SQLGlot projection lineage | Maps unknown labels only when normalized parsed projection expressions resolve to identical fully-qualified source columns. It does not prove filters/joins/grain. | Conservative by design; does not recognize COUNT(*) vs COUNT(DISTINCT PK) or grain-equivalent expressions. | Permit semantic mapping only with verified expression plus frozen source grain/constraints; keep output contract separately strict. B40-003/B40-022 are cohort-supported examples (B40-003, B40-022). | Wrong expression, join fanout, duplicate grain, changed NULL predicate, or wrong filter must fail. | Current limitation is intentional conservatism; case-sensitive business-result undercount is supported, generic equivalence needs reviewed policy. |
| Equivalent SQL expressions | No general theorem prover; structural lineage only. | Safe false negatives possible when SQL formulations differ but source grain proves equivalence. | Narrow evidence-backed equivalence rules and synthetic positive/negative tests; do not broaden from alias text alone. | Same totals on one dataset do not prove same semantics; B40-013 is a counterexample (matching rows, wrong historical dimension). | Policy/implementation boundary; do not change v3.3. |
| Duplicate-preserving row matching | Uses maximum bipartite matching for unordered rows, preserving duplicates and Decimal tolerances. | Avoids greedy mispairing; reasonable. | Retain. | A Counter/set-only replacement would collapse duplicate rows and create false positives; analysis tests keep multiplicity. | Correct existing policy/implementation. |
| Numeric tolerance | Decimal comparison; exact identifier/count columns; case-specific absolute/relative tolerance. | Appropriate if tolerance is frozen per case. | Keep current tolerance and publish tolerance per case. | Float rounding, tolerance applied to counts/IDs, NaN/Infinity or bool-as-number must fail. | Correct; do not widen to improve result rate. |
| NULL behavior | NULL matches only NULL; never zero. | Correct for this domain and task. | Keep. | NULL↔0 and NULL↔empty string must fail. | Correct existing implementation. |
| Ordering and TOP-N | Unordered contracts use multiset rows; ordered contracts and explicit ranking are checked separately. | B40-011 source expression `p.cogs` is rejected although projection alias is `catalog_cogs`; direct AST contract check: True. | Resolve the ordered expression against the canonical projected metric, then validate direction, tie-break and limit. Share interpretation with application ranking validator. | Wrong ASC/DESC, wrong tie-break, wrong metric, or LIMIT !=5 must fail. Never infer output values without execution. | Confirmed scorer and application validator false negative for this statement; no E2E correction without execution. |
| Cardinality and grain | Business row matching requires full multiset match; output contract checks limits and required fields. | Correctly exposes B21 (3 vs4) and B23 (194 vs97); do not call same-value subsets correct. | Retain exact row cardinality and grain obligations. | Duplicates, dropped groups, fanout and wrong snapshot must remain failures. | Correct existing policy. |
| Harmless extra columns | Extra columns fail strict output compliance; E2E may permit only `unexpected_extra_columns` with linked per-column safety PASS. All 6 extra-output cases in this run remain REVIEW_REQUIRED. | Conservative and appropriate given authorization/sensitivity uncertainty; may understate user usefulness, but not proven false negative. | Human policy review per exact SQL/result and column; do not auto-approve names. | Sensitive values, changed grain/population, misleading extras, or missing linkage must remain unresolved/fail. | Policy choice, not implementation defect. |
| Semantic audit dependency | E2E requires a linked semantic audit PASS; run has 23 AI-assisted records (15 raw PASS/8 FAIL), unauthenticated. Scorer's ranking rule changes B40-011 raw PASS to effective FAIL; overall effective decisions are 14 PASS/9 FAIL/7 indeterminate. | “Independent” is computationally separate from Agent output but not an authenticated human review. Accuracy is not a human-ground-truth estimate. | Label as AI-assisted and obtain blinded human review/adjudication for thesis claims. | Never trust Agent's own semantic-valid boolean; retain linkage hashes. | Measurement provenance limitation. |
| Execution security evidence | Requires approved/unverified repository event with `security_validated: true`; raw run unsafe executions=0. B40-033 event has no statement/result payload. | Fail-closed safety is proper; event provenance is too coarse to distinguish metadata lookup from business query. | Record redacted statement/parameter hashes and typed event purpose, with no sensitive result content. | Missing, malformed or failed security evidence must not pass. | Instrumentation gap. |
| Clarification / abstention | `_valid_unsupported_response` checks non-empty answer, <=3 non-empty string options, no SQL/event/provider failure. It does not check semantic relevance. Official 8/10 therefore is schema/no-query validity, not semantic adequacy. | Potential false positives: B36 suggests absent `campaign_spend`, B37 offers unsupported 10% commission, B38 gives a generic rank error. B33 safe-looking answer is excluded due opaque execution event; B40 fails schema. | Keep response-schema metric; add separately adjudicated semantic-adequacy metric in a future protocol. Do not change current v3.3. | Valid JSON that cites unavailable fields or invents formulas must fail semantic adequacy; malformed JSON must fail schema metric. | Measurement definition gap; no v3.4 implemented. |
| Repair recovery | Runner emits `calls.sql_repair`; scorer v3 reads top-level `repair_count` or `repairs`. Official result becomes 0/0 although raw runner has ten repair cases. | Confirmed telemetry contract mismatch. | Make scorer and runner agree on a typed repair event and explicitly exclude unsupported cases from supported recovery denominator. | A non-repair second generation or unsupported clarification correction must not enter supported denominator. | Implementation defect; official 0/0 remains historical. |

## Minimal reproducible examples

### DATE/TIMESTAMP false negative (B40-001, B40-004)

```json
{"month": "2024-01-01"}
{"month": "2024-01-01T00:00:00+00:00"}
```

v3.3 literal row comparison returns `FAIL`. The frozen source month fields are PostgreSQL `DATE`; every saved output row is the exact UTC first-of-month boundary and every non-date field and duplicate count matches. The analysis-only comparator returns a full multiset match. It must still reject `2024-01-01T01:00:00+00:00`, a nonzero offset, a naive timestamp, a non-first day, or any mismatching measure.

### Explicit count alias and grain equivalence (B40-003, B40-022)

```json
{"return_count": 7}
{"return_records": 7}
```

The v3.3 business-result decision is `FAIL`; only an explicit observed-to-Gold alias map is allowed in this diagnostic. B40-003's `COUNT(*)` is equivalent to `COUNT(DISTINCT return_id)` only under the frozen one-row-per-return-id constraint. B40-022's count expressions are equivalent only under one inventory row per snapshot/product and matching NULL predicates. Wrong values, duplicate grain, fanout, or a missing NULL filter must fail. Output Contract and E2E remain failed pending policy/safety review.

### Ranking validator false negative (B40-011)

```sql
SELECT p.product_id AS product_id, p.cogs AS catalog_cogs
FROM commerce.products AS p
ORDER BY p.cogs DESC, p.product_id ASC
LIMIT 5;
```

The linked raw semantic audit says `PASS`; the v3.3 ranking path and application validator reject the metric expression because the selected expression is `p.cogs` while the contract uses alias `catalog_cogs`. The direct AST check verifies source, projections, no added population filter/join/grouping, direction, tie-break, and limit. Wrong metric, order direction, tie-break, limit, or population mutation fails the synthetic tests. No result exists; E2E remains failed.

### Repair telemetry mismatch

```json
{"calls": {"sql_repair": 1}}
```

The runner emits this nested counter; scorer v3.3 reads top-level `repair_count` or `repairs`, yielding official `0/0`. Saved observations show nine supported repair cases and two E2E recoveries (`2/9`) if the runner counter is accepted as a bounded-generation proxy. Unsupported B40-040 is excluded from the supported denominator. Because the counter is not a typed repair event, this remains a diagnostic, not an official revised metric.

### Shape-valid but semantically weak clarification

```json
{"status": "clarification_required", "answer": "Choose whether to use the unavailable campaign_spend field.", "options": ["Use campaign_spend"], "sql": null, "execution_events": []}
```

The response-shape check accepts this type of object; it does not establish semantic adequacy or schema availability. Existing examples B40-036 through B40-038 are counted in the official shape metric despite suggesting unavailable fields/formulas or omitting the blocker. A future semantic-adequacy metric needs independently reviewed positives and negatives. Keep the current shape metric and E2E/abstention result unchanged.

## Synthetic regression expectations

The accompanying `tests/test_analysis.py` exercises the analysis-only comparator and direct ranking check, without touching scorer v3.3. It requires:

- exact UTC month-boundary representation to match; non-zero offset, naive timestamp, non-midnight, non-first-day and mismatched non-date value to fail;
- duplicate rows to retain multiplicity;
- B003/B022 alias mapping only under explicit mapping and matching values;
- the B40-011 source metric/direction/tie-break/TOP-N AST to pass and mutations to fail;
- a shape-valid but semantically unsupported clarification to remain a scorer shape pass while being flagged for human adequacy review.

No scorer code, Gold, official score, or Agent logic is changed.
