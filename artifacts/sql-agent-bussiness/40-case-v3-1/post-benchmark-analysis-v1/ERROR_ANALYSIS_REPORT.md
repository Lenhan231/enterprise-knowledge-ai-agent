# Post-benchmark SQL Agent error analysis

**Scope.** Offline analysis of official run `20261122T012821Z`, application `37b5fed55a45fc30a5e46376e9e41d0abb6bb17f`, scorer/protocol `3.3.0`. No SQL Agent, LLM, database, or held-out query was run by this analysis. No frozen input or official result was changed.

## Evidence integrity and denominator

- Freeze status: `FROZEN_WITH_DISCLOSED_REVIEW_PROVENANCE_LIMITATION`; source database fingerprint `dbc14b99acc2920ffaeb4190ba45708982c971f0671b0b9e8114b595f2594028`.
- Manifest-listed artifact hashes: 18/18 verified; all official scoring-input hashes and audit-to-run hashes verified; case-set canonical hash is `36dbd0876167fccb954923dd4ad2f9961a31e6fd05e8d76ec5f99fecf4a012ce`.
- Cohort: 40 unique cases, 30 `execute`, 5 `clarify`, 5 `abstain_without_query`; all 40 attempted and no `NOT_RUN` cases.
- Raw statuses: 19 `executed`, 1 `executed_empty`, 14 `clarification_required`, 1 `unsupported`, 5 `failed` (including unsupported B40-040). Supported no-answer cases: six clarifications and four terminal failures.
- Freeze inputs remain marked draft/provisional at source-file level: the analysis treats the frozen manifest as the evaluation boundary, not proof that Gold SQL/results received an authenticated independent human adjudication. Review provenance for the question cohort is owner-reported; SQL and output audits are AI-assisted and unauthenticated.

## Official v3.3 results (immutable)

| Metric | Official result |
|---|---:|
| Business End-to-End Accuracy | 10/30 (33.33%) |
| Overall Task Success | 18/40 (45.00%) |
| Business Result Accuracy | 11/20 (55.00%) |
| SQL Semantic Accuracy (effective scorer decision) | 14/30 (46.67%) |
| Output Contract Compliance | 13/20 (65.00%) |
| Valid Clarification/Abstention (shape/no-query policy) | 8/10 (80.00%) |
| Unsafe executions | 0 |

These are the saved scorer v3.3.0 values. They are not replaced by the diagnostics below.

## What failed

All 20 supported E2E failures are accounted for: B40-001/003/004/022 are saved-row comparison false negatives; B40-002/011/014/026 end in invalid SQL, a false validator rejection, a semantically wrong query blocked by validation, or malformed clarification; B40-005/009/012/015/028/029 return clarification instead of the frozen execute contract (B40-012 wording needs adjudication); B40-013/021/023/025/027/030 execute or return a result with wrong source dimension, grain, population, inherited date, or snapshot. See the full [`CASE_ERROR_MATRIX.csv`](CASE_ERROR_MATRIX.csv), including exact SQL, parameters, answer, rows, contracts, and audit decisions for every case.

| Primary classification | Cases | Count |
|---|---|---:|
| `CORRECT_PASS` | 12 |
| `DATE_TIME_REPRESENTATION_MISMATCH` | 2 |
| `FALSE_CLARIFICATION_OR_ABSTENTION` | 5 |
| `GENUINE_SEMANTIC_ERROR` | 7 |
| `INSUFFICIENT_EVIDENCE` | 8 |
| `OUTPUT_ALIAS_OR_PROJECTION_MISMATCH` | 2 |
| `RANKING_VALIDATOR_FALSE_NEGATIVE` | 1 |
| `VALIDATION_BLOCKED` | 2 |
| `WRONG_GRAIN_OR_AGGREGATION` | 1 |

### Confirmed comparison false negatives

| Case | Source type / mapping evidence | Saved-row comparison | Official business result | Output contract / E2E |
|---|---|---:|---|---|
| B40-001 | 48/48 | 48/48 | FAIL | PASS | FAIL |
| B40-004 | 12/12 | 12/12 | FAIL | PASS | FAIL |
| B40-003 | 11/11 | 11/11 | FAIL | FAIL | FAIL |
| B40-022 | 47/47 | 47/47 | FAIL | FAIL | FAIL |

B40-001 and B40-004 use `DATE_TRUNC('month', DATE)` without the Gold's `::date`; the serialized outputs are exact `YYYY-MM-01T00:00:00+00:00` values. The comparator converts only an aware zero-offset timestamp at exactly 00:00:00 on day one to its UTC date. It refuses naive timestamps, non-zero offsets, non-midnight values and non-month boundaries. Every non-date cell and duplicate multiplicity is preserved; all saved rows match.

B40-003 uses `COUNT(*) AS return_records` instead of `COUNT(DISTINCT return_id) AS return_count`. The frozen schema contract defines one row per `return_id`, so these counts match at the actual table grain; all 11 result rows match after exact alias and month mapping. B40-022 uses `COUNT(DISTINCT product_id)` over a one-row-per-(snapshot_date, product_id) inventory grain; its non-NULL/NULL partitions match Gold's non-NULL count and filtered NULL count in all 47 rows. These two aliases are outside the frozen output contract. Therefore a verified business-result comparison does **not** waive output-contract or safety review, and neither case becomes E2E PASS here.

### B40-011 — generated SQL is correct; execution is unknown

The saved SELECT projects `commerce.products.cogs AS catalog_cogs`, orders by `p.cogs DESC, p.product_id ASC`, and applies `LIMIT 5`. A SQLGlot AST check against the frozen contract passes all required checks. The raw linked semantic decision is `PASS`, but the scorer applies its own ranking check and downgrades it to `FAIL`; the application validator also rejects the same source expression as a measure/alias mismatch. No repository execution occurred. This is a confirmed ranking-validator false negative and a missed execution opportunity, **not** a result or E2E success.

### Genuine Agent and pipeline failures

- **Invalid generated SQL / execution surface:** B40-002 applies `EXTRACT(EPOCH ...)` to PostgreSQL `DATE - DATE` (integer day count), then fails at the database after one repair. This is an Agent SQL/type error; the database's error is not evidence of a service outage. Static validation failed to catch the operator/type mismatch.
- **Wrong business contract:** B40-013 groups by current `products.segment` instead of snapshot-stored `inventory.segment`; matching rows on one snapshot do not make the query semantically correct. B40-014 substitutes shipment delivery dates for delivered order status/order dates. B40-021 and B40-025 substitute current catalog dimensions for snapshot dimensions; B40-023 returns individual snapshot rows rather than a matched before/after delta; B40-027 drops inherited 2025; B40-030 binds 2024-11-21 rather than inherited snapshot 2025-10-31 and returns empty.
- **False clarification:** B40-005, B40-009, B40-015, B40-028 and B40-029 are clearly answerable from their frozen contracts but stop without SQL. B40-012 asks highest vs lowest; its expected descending ranking is plausible, but the wording does not explicitly say highest, so that item remains a case-definition question rather than a proven Agent error.
- **B40-015 schema-selection trace:** The saved candidate pool contains `commerce.orders`, `commerce.order_items`, and `commerce.products`, but `final_selected_tables` is null. The response says `commerce.orders` is not allowed and asks the user to add it or remove the delivered filter. The evidence confirms a candidate/final-list mismatch and a misleading clarification, but does not identify whether the selector failed to emit a final set or the clarification path misread the candidate list.
- **Recovery/output-format failures:** B40-026 is a contextual monthly COGS follow-up that ends in invalid clarification options after the bounded correction. B40-040 likewise ends in malformed clarification for an unsupported contact-field request. These are failed user-facing outcomes, despite no business SQL execution.

### Clarification and repository-event interpretation

The official 8/10 unsupported clarification/abstention value measures response shape, no SQL, and no execution event; it does not measure semantic adequacy. B40-036 proposes the absent `commerce.campaign_spend` table, B40-037 offers an unsupported invented 10% commission formula/field, and B40-038 returns a generic ranking error despite absent carrier/SLA fields. These shape-valid outputs make the metric potentially optimistic. B40-040 is a malformed terminal failure.

B40-033 returns a safe-sounding unavailability answer naming latest snapshot 2026-11-13, but one approved repository event causes the no-execution abstention check to fail. The raw event has no SQL or result payload. It could represent a `MAX(snapshot_date)` availability lookup rather than the requested current-stock analysis, but that cannot be proved. Keep the official 8/10 unchanged; recover the exact statement/event class before revising policy or scoring.

## Repair-recovery instrumentation

The raw runner reports `calls.sql_repair=1` for 10 cases: B40-002, B40-004, B40-011, B40-014, B40-016, B40-018, B40-022, B40-025, B40-026, B40-040. Nine are supported: B40-002, B40-004, B40-011, B40-014, B40-016, B40-018, B40-022, B40-025, B40-026; two reached official E2E PASS (B40-016 and B40-018), giving a telemetry-derived supported recovery of **2/9 (22.22%)**. The remaining tenth attempt is unsupported B40-040 and should not enter a supported repair-recovery denominator. The official score remains **0/0, NOT MEASURABLE** because scorer v3 reads top-level `repair_count`/`repairs`, while runner v3 emits `calls.sql_repair`. The runner counter is inferred from subsequent bounded `_generate_sql` entries; the raw file does not carry a typed per-generation repair record. See the JSON sensitivity artifact for both 2/9 and non-protocol 2/10.

## Does the scorer underestimate business correctness?

**Within this cohort, yes for a bounded subset; systematic bias beyond this cohort is not established.** Four executed outputs (B40-001, B40-003, B40-004, B40-022) match the saved Gold rows under strict source/type/grain-supported normalization and mapping, while v3.3 reports business-result FAIL. The business-result sensitivity is 15/20 instead of 11/20 (+4 cases) if that explicitly documented equivalence policy is accepted. E2E can rise only to 12/30 (+2: B40-001 and B40-004); B003/B022 retain extra-column safety failures. A fifth issue (B40-011) affects semantic decision only; execution is absent.

This evidence demonstrates material undercount in this 40-case run, not a population-level systematic estimator bias. Conversely, shape-only clarification scoring can overcount semantically weak unsupported responses. The scorer therefore has both false-negative and false-positive risks, each with different evidence.

## Scorer fairness summary

The detailed audit and negative regression examples are in [`SCORER_FAIRNESS_AUDIT.md`](SCORER_FAIRNESS_AUDIT.md). Principal findings: strict literal DATE/timestamp serialization undercounts exact month-boundary rows; exact aliases and SQLGlot lineage are conservative and miss grain-proven count equivalences; B40-011 reveals an incorrect ranking-alias rejection; repair telemetry field names disagree; clarification validity checks shape rather than adequacy; AI-assisted semantic/output audits are unauthenticated. Duplicate-preserving multiset matching, NULL equality, numeric tolerance, execution safety checks and conservative extra-column review are reasonable guardrails and must not be loosened to improve scores.

## Prioritized engineering recommendations

1. **Preserve follow-up state and test it end to end.** The date/metric/snapshot inherited scope is lost in B40-026/027/028/029/030; make context obligations visible to generation and validate every inherited filter/dimension.
2. **Share one typed semantic contract between Agent validation and scorer diagnostics.** Resolve metric aliases to source expressions before ranking checks, while retaining direction, tie-break and TOP-N checks; cover B40-011 and ensure B40-014 remains rejected for its population error.
3. **Validate SQL operator/type combinations before execution.** PostgreSQL DATE arithmetic in B40-002 should be caught locally; repairs must address the exact database/validator error within the existing bound.
4. **Align runner/scorer telemetry with contract tests.** Emit a typed `repair_attempt` event or make scorer consume the existing per-case `calls.sql_repair`; distinguish supported repairs and unsupported formatting corrections.
5. **Add narrowly scoped result equivalence.** Canonicalize dates only for verified DATE-derived month keys and map count aliases only when SQL expression and frozen grain prove equivalence. Keep strict output compliance and extra-column safety separate.
6. **Score semantic clarification quality separately from JSON shape.** Reject suggestions for unavailable schema fields and unsupported formulas; preserve no-query safety.
7. **Retain reviewable execution metadata.** Record statement hash, parameters hash, event purpose/type and success/failure so events such as B40-033 can be classified without retaining sensitive data.
8. **Replace unauthenticated semantic judgments with blinded human adjudication for thesis claims.** Keep original AI decisions as a distinct source and publish disagreements rather than silently overwriting them.

## Reproduction

```bash
uv run --locked --project . python artifacts/sql-agent-bussiness/40-case-v3-1/post-benchmark-analysis-v1/analyze.py
uv run --locked --project . python -m unittest discover -s artifacts/sql-agent-bussiness/40-case-v3-1/post-benchmark-analysis-v1/tests -v
uv run --locked --project . python artifacts/sql-agent-bussiness/40-case-v3-1/post-benchmark-analysis-v1/analyze.py --check
```

The first command verifies frozen hashes and writes only to this new analysis directory. It does not instantiate a SQL Agent, provider, or database connection. The second uses synthetic fixtures; the analysis script separately reads the saved local JSON. The third compares regenerated bytes to committed analysis outputs.
