# Discriminative validation, SQL Agent benchmark v3

## Run scope

- Database: frozen analytics snapshot, fingerprint `dbc14b99acc2920ffaeb4190ba45708982c971f0671b0b9e8114b595f2594028`.
- Role: verified read-only; every SQL mutation was submitted through `execute_approved_query`.
- Gold references: 30/30 executed successfully and remain provisional.
- Mutation variants: 28 attempted; zero invalid variants; SQL Agent generation calls: 0; SQL Agent cases executed: 0; database writes: 0.
- The scorer compares business output schema, values, ordering, NULLs, and case tolerances. SQL text inequality is not used as detection evidence.

## Results

| Evidence | Numerator | Denominator | Result |
|---|---:|---:|---:|
| Result-based mutation detection | 23 | 26 executed valid variants | 88.46% |
| Observationally equivalent executed variants | 3 | 26 executed valid variants | 11.54% |
| Approved-relationship validator rejection | 1 | 1 assigned probe | 100% |
| Join-fanout validator rejection | 1 | 1 assigned probe | 100% |
| Business population validator rejection | 1 | 1 assigned probe | 100% |
| Invalid mutations | 0 | 28 attempted | 0% |

The result-based denominator excludes the two SQL variants correctly stopped by the repository's JOIN safety validator. The business population validator is assessed separately from result comparison. Validator results are not folded into the result-based rate.

## Probe coverage and observations

The executable catalog covers missing and wrong filters, missing time scope, a shifted date boundary, aggregation and grouping errors, ranking direction and tie-break, missing or incorrect TOP-N, incorrect join keys, fanout-sensitive aggregation, NULL logic, snapshot selection and direction, and inherited follow-up year/period errors.

| Case | Controlled error | Observation |
|---|---|---|
| B40-002 | Remove year scope; shift end boundary; count non-NULL dates under the NULL predicate | All three result variants differ from Gold. Seven missing delivery dates exist in the 2025 source population. |
| B40-006 | Remove city filter; use age group 35-44; use wrong ZIP join key | Both filter variants change the count. Wrong join key is rejected by the approved-relationship validator. |
| B40-008 | Remove or invert `return_reason IS NOT NULL` | Inversion changes the rows. Removing the filter is observationally equivalent because all selected 2024 reasons are non-NULL. |
| B40-015 | Reverse sort; TOP 5; remove business TOP 3 | Each result differs. The safe executor cap of 200 rows remains in place for the missing-limit probe. |
| B40-017 | Replace SUM with MAX; remove product grouping | Both result variants differ; repeated return rows are combined for 56 product groups in the selected period. |
| B40-021 | Replace `stockout_flag = TRUE` with `IS NOT NULL` | Result differs because the frozen snapshot contains both TRUE and FALSE values. |
| B40-023 | Reverse delta; change after snapshot; remove common-product HAVING | Direction and snapshot changes differ. Removing HAVING is equivalent because the two snapshots have the same 97 products. |
| B40-026 | Use 2025 instead of inherited 2024 | Result differs from the inherited COGS reference. |
| B40-027 | Omit delivered status; change inherited year | Both result variants differ. The production `validate_population_contract` also rejects the missing-status SQL against the adapted follow-up question. |
| B40-028 | Shift 2023 months; remove COGS from gross-profit formula; shorten comparison period | All three result variants differ. No NULL observations were introduced or fabricated. |
| B40-029 | Remove TOP 2; reverse ranking; reverse alphabetical tie-break | Missing TOP 2 and reversed tie-break differ. Reversing numeric ranking is observationally equivalent because all three reasons have equal returned quantity in 2024. |
| B40-030 | Select a different inventory snapshot | Result differs from the inherited snapshot reference. |
| B40-004 | Count joined order rows instead of distinct orders | Rejected by the join-fanout validator before execution; this is reported as validator detection, not result-based detection. |

For missing TOP-N variants the probe replaces the business limit with `LIMIT 200`, the repository's maximum safe bound. The resulting all-category/all-reason set is still bounded and tests whether the requested TOP-N changes the business result.

## Remaining data limitations

- B40-008 cannot test the observable effect of dropping the non-NULL reason filter on this snapshot. Keep the limitation visible; do not fabricate rows.
- B40-023 cannot test different product membership across these two snapshots. It still tests stock movement, delta direction, and exact snapshot choice.
- B40-029 distinguishes TOP 2 and alphabetical tie-break, but descending versus ascending numeric ranking cannot be distinguished while all three grouped quantities tie. Keep the limitation visible.
- B40-020 does not claim NULL shipping-fee coverage because all 728 selected fees are non-NULL.
- B40-028 specifies NULL preservation, but the available paired monthly rows do not create a missing-month NULL edge case.

These results establish that the selected mutations are useful probes on the frozen snapshot; they do not establish general model quality or make the unreviewed Gold oracle authoritative.
