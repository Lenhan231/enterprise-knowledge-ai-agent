# Cross-domain SQL semantics — 2026-11-04

**Recommendation: keep isolated.** The experiment closes demonstrated validation gaps and improves Report provenance, without replacing the SQL agent or changing a business formula. It does not settle S26's output-grain choice or S27's cross-snapshot business approval. Production `src`, database schema/permissions, metric catalog, frozen questions/references and existing Ragas scorers remain unchanged.

## Per-case root causes

| Case | Generated SQL versus frozen reference | Assessment | Minimal fix / remaining decision |
|---|---|---|---|
| S23: annual returned units / ordered units by product | Both sides independently sum their own 2022 fact populations, join product keys, use a numeric numerator and NULLIF denominator, and rank descending with a stable ID tie-break. Baseline adds product_name through the approved unique products key; reference does not. Candidate selects the ordered aggregate's product_id rather than the return aggregate's equal key. | Baseline calculation is a valid alternative under the declared FK/PK constraints. Extra enrichment and alias/output shape explain the judge disagreement. This is an explicit unit ratio, not canonical order-based return_rate. | Require product_id in output as well as both operands; ordering by an ID that is not projected does not identify duplicate-name products to the user. Preserve exact source windows, all order statuses and denominator protection. No formula/reference rewrite. |
| S26: stockout observations plus orders in December | Candidate selects product/snapshot records across December, requiring correlated EXISTS on December orders. Reference restricts inventory to December 31 and omits snapshot_date. Multiple snapshots can produce several records per product. | Temporal scope and output-grain ambiguity, not proof of erroneous monthly filtering. The single December snapshot in current data hides this disagreement. A closing snapshot must not be inferred from the word December. | Reject hidden inventory/category and order-status filters, invented outer TOP-N, and incomplete stable observation ordering. Keep SQLGlot's existing correlation protections. Explicitly disclose product_snapshot output rather than imply a deduplicated roster. Business decision: unique products with any qualifying December observation, per-snapshot observations, or a named closing snapshot. |
| S27: category inventory observations versus ordered quantities | Both sources aggregate independently by category. Candidate sums all December observations, full joins categories and uses both keys in COALESCE. Reference uses only December 31 inventory and selects the inventory-side category, leaving order-only category labels NULL. | Candidate matches an explicit recorded-observation-sum interpretation; reference is a closing-snapshot interpretation. COALESCE of both keys is necessary for complete category labeling. However, the catalog's canonical inventory metric is per snapshot and does not establish approval or non-overlap for a period rollup. | Verify both aggregate aliases survive in the category label and stable sort; reject inner truncation, output restrictions, zero substitutions and an invented outer TOP-N. Add calculation provenance/approval metadata and carry it to Report facts. Business approval of a cross-snapshot movement rollup remains `not_established`. |

The audit verifies return_date versus order_date independently, product versus product_snapshot versus category-period grain, complete source populations, inner-join observed ratio operands, and NULL preservation on absent full-join sides. Approved order_items.quantity is NOT NULL and positive, so a zero annual denominator is not a valid source fixture; the defensive NULLIF guard is still required and tested. Inventory's composite key prevents duplicate rows at one date but does not prove that movement observations at different dates describe disjoint business events.

`ambiguity-fixture-results.json` executes the untouched references against adversarial data. With a product flagged mid-month but not at closing, S26's period interpretation returns product IDs **{1,2}** while the closing reference returns **{2}**. S27's category A observation sum is **13**, versus **9** at closing. An order-only category is correctly labeled **D** by the candidate, while the reference leaves its category NULL. These probes demonstrate material scope/output differences; they do not authorize selecting a business interpretation or repairing the frozen reference.

## What changed

The final patch changes **three existing runtime modules: 88 additions and 14 deletions**. No new agent, schema, Pydantic model, mandatory mapping stage, routing layer or dependency is introduced.

- Existing contract population validation now admits only the exact verified correlation/flag equality in addition to date predicates for the narrow presence contract. This blocks hidden category and order-status restrictions.
- Ratio results must project a verified product ID; independent aggregates, complete join keys, inspectable operands and ratio ordering remain mandatory.
- Category output and ordering must use keys from both independently aggregated scopes. Source-lineage normalization alone previously accepted COALESCE of the inventory key twice, losing order-only category names.
- Complete presence/category contracts retain the 200-row safety ceiling and stable complete keys. The ceiling is not an inferred user TOP-N. New filtered/ranked variants outside these narrow contracts still need a verified scope rather than silently dropping constraints.
- The existing decoder normalizes a unique ORDER BY output alias into its position before qualification, preserving PostgreSQL quoted-name semantics. Duplicate aliases and aliases used illegally in WHERE still fail. Qualified SQLGlot/schema/join checks still run afterward.
- Period-observation calculations retain the original catalog definition but add separate calculation scope, formula and unestablished approval metadata. Report facts use that calculation provenance instead of falsely inheriting the canonical snapshot formula/approval.
- Annual EXTRACT validation no longer returns early and ignores narrower date bounds. Every additional date predicate must be independently verified; unsupported date expressions cannot silently narrow an otherwise correct period. An annual EXTRACT alone remains valid.

SQLGlot already rejected the uncorrelated and wrong-product EXISTS examples. Those are retained controls, not claimed new fixes. Valid reversed correlation, redundant DISTINCT on complete observation keys, reversed COALESCE argument order and unique ORDER BY aliases have positive tests. Frozen SQL is not changed to accommodate the stricter contract.

## Fresh paired evaluation

Exactly S23, S26 and S27 were run using the same frozen questions/references and existing Ragas judge configuration (`CodexCLIJudge`, gpt-5.6-luna, medium). Production source is unchanged from b9ee699. The initial candidate at `d4def4e` was preserved in `candidate/`. Review then exposed the additional temporal gap, so the final candidate at **`c37afeeddbaa1ec0979c1bc757aaf1d14698345e`** received a new three-case generation/scoring run in `candidate-final/`; the unchanged baseline was reused. Results below compare that baseline with the **final fresh candidate**, not unit-only changes. This scoped candidate is the production cross-domain path with the published patch, not an adoption of the entire earlier hybrid. Other hybrid features do not affect these paths.

| Metric | Baseline | Candidate |
|---|---:|---:|
| Execution accuracy | 3/3 | 3/3 |
| Ragas SQL semantic equivalence | 0/3 | 1/3 |
| Numerical accuracy | 2/2, one N/A | 2/2, one N/A |
| Requests completing SQL execution | 3/3 | 3/3 |
| LLM calls, including SQL repair | 4 | 3 |
| Failed provider attempts / evaluator errors | 0 / 0 | 0 / 0 |
| Observed p50 / p95 request seconds | 3.666 / 9.130 | 2.612 / 6.994 |

The judge accepted the candidate's S23 output; S26 and S27 remained zero. The baseline's extra product-name projection was not a business calculation bug, so the semantic-score change is not evidence that its ratio became more mathematically correct. Three requests are too few to establish a latency improvement. No unsupported questions were included: valid-refusal rate is **N/A, denominator 0**, not 100%. There were no provider-error cases requiring retries. Across the baseline, initial and final candidate, all **nine generations and 27 metric records** are retained; no original scorer or denominator was edited. `comparison-final.json` contains the final comparison; `comparison.json` preserves the initial one.

## Separate intent and business-rule checks

These checks supplement the frozen scores; they do not replace them or count uncertainty as a pass. Expected calculations are independently accumulated in Python from synthetic source rows, then compared with generated SQL executed against that dataset. Repeated product names, unequal return/order cardinalities, cancelled orders, out-of-period rows, multiple snapshots and one-sided categories make silent counting/population errors observable. SQLite's test-only REAL division models PostgreSQL numeric division; production execution remains PostgreSQL.

| Supplemental check | Baseline | Candidate |
|---|---:|---:|
| Fixture calculation/population matches | 3/3 | 3/3 |
| Intent fidelity | 2 pass, 1 uncertain | 2 pass, 1 uncertain |
| Business-rule compliance | 2 pass, 1 uncertain | 2 pass, 1 uncertain |
| Adversarial mutations rejected | 11/19 | 19/19 |
| Additional temporal regression cases rejected | 0/2 | 2/2 |

S26 is the uncertain intent decision; S27 is the uncertain business-rule approval. The eight previously accepted mutations were missing ratio output identity, hidden stockout/category and order-status restrictions, incomplete presence-key ordering, invented presence limit, repeated same-side category labeling, missing category ordering and invented category limit. The two additional, separately disclosed temporal cases expose ignored narrowing filters after annual EXTRACT or alongside valid date bounds. A separate November-return fixture demonstrates the changed result. Original fixture data and frozen benchmark references remain unchanged. Existing guards continue to reject wrong denominators, zero substitution, wrong periods, raw multi-fact joins, missing categories and truncated inner aggregates. These finite checks do not prove all natural-language intent or all SQL equivalences.

## Regression and Report compatibility

The final focused SQL/security and Report suites ran **183 tests: no failures/errors, three unrelated experiment-only skips**. This includes the new synthetic fixtures and the existing metric/join/RBAC/read-only suites. A final full candidate run executed **739 tests: 11 failures, 51 errors, 29 skips**. Failure/error identities match the recorded 715-test source-equivalent pre-experiment run; no unrelated fixes or test disabling were used to claim a green suite. See `regression-comparison-final.json`; the initial test results are also retained and the repository's existing full-suite/CI blockers remain.

Fresh real SQL results were replayed through Report fact conversion without new provider calls: **800 S23 facts, 600 S26 facts and 12 S27 facts**. Every S27 inventory-rollup fact carries `approval_status=not_established` and the explicit observation-calculation formula, rather than the approved snapshot formula. No Report narrative correctness score or fresh full Report provider benchmark is claimed. Returned detail hitting 200 rows is a bounded query result, not an exhaustive dataset export.

## Reproduce and adoption limits

`PROTOCOL.md` and source hashes record the predeclared method. Apply `evaluation/sql_cross_domain_fidelity.patch` to b9ee699 in an isolated checkout. Run `evaluation/run_sql_hybrid_followup.py --stage generate|score --ids S23 S26 S27`, separate baseline/candidate `--output` directories, and the candidate `--worktree` path. Use `evaluation/check_cross_domain_fidelity.py --application <checkout> --generations <generations.jsonl> --output <sidecar.json>` for the independent checks. Existing manifests prevent changed-source resumption into a scored cohort. Tests use `SQL_CROSS_DOMAIN_ROOT` only to select the isolated application; production discovery skips candidate-only contract assertions and still runs the independent fixture truth tests.

Keep the fixes isolated until the two business decisions are resolved and normal integration gates pass. Qualified source/grouping forms remain deliberately narrow; not every SQL-standard equivalent form or newly requested source population is supported. No asymmetric source-period contract, event-level overlap proof, new approval, production migration, permission change or broad hybrid rollout is established by this experiment.
