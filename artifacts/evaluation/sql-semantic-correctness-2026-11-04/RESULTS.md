# SQL semantic correctness results

Current benchmark update (2026-11-06): [S13/S15/S17 incremental results](../sql-three-case-followup-2026-11-06/README.md), [updated 30-case aggregate](../sql-three-case-followup-2026-11-06/merged/paired-summary.json). Only those three cases were rerun; the other 27 records are retained. The original full-run results below remain unchanged.

The full 30-question comparison measures archived application `153e5d5` against live application `f53c56f`. It includes earlier fixes already present on QuocAn as well as this work. Frozen questions/references and the Ragas judge (`gpt-5.6-luna`, medium) and scorers are unchanged.

| Measure | Before: 153e5d5 | After: f53c56f |
|---|---:|---:|
| Execution accuracy | 20/28 (71.4%) | 23/28 (82.1%) |
| SQL semantic equivalence | 6/28 (21.4%) | 9/28 (32.1%) |
| Numerical accuracy, inherited applicability | 18/26 (69.2%) | 19/24 (79.2%) |
| Numerical accuracy, common applicable cases | 18/24 (75.0%) | 19/24 (79.2%) |
| SQL executed, including empty results | 23/30 | 25/30 |
| Latest-attempt provider failures | 0/30 | 0/30 |
| Historical provider-failed attempts | 10/40 total attempts | 0/30 total attempts |
| Evaluator errors / pending scores | 0 / 0 | 0 / 0 |
| Final-attempt latency p50 / p95 | 2.420s / 7.467s | 2.194s / 4.571s |

The common numerical row uses the intersection of applicable cases; it does not change scoring. SQL execution does not imply correct semantics. Latencies are descriptive, not a controlled speed comparison. The full run contains 35 provider calls with no recorded call failures. All 28 supported reference results still matched the read-only database before generation.

The semantic gains are **S14, S17 and S28**. There were no semantic-score changes on identical bound SQL. S08 now correctly excludes NULLs, and S23/S25 now execute and match the frozen result comparison, but their strict semantic scores remain zero because output/schema or bounded ordering differs. This audit does not override those scores.

## Separate latest-revision S27 follow-up

The full run rejected S27 because the model invented a cancelled-order exclusion. The validator correctly preserved the requested population. Revision `a287d53` improves the prompt and makes the repair diagnostic identify the unrequested filter; it also prevents “most recent” from becoming a ranking instruction.

One separate live S27 request at `a287d53` used the original frozen question/reference and the same Ragas judge. It **executed**, scored **execution 1.0**, **numerical 1.0**, **semantic 0.0**, and had **zero provider/evaluator errors**. It took 7.210s, with two provider calls: the first omitted the safety LIMIT and the existing repair added it. No cancellation filter was present. Its semantic zero reflects full-month inventory observations and preserved FULL JOIN category labels versus the frozen closing-snapshot reference.

This result is in `followup/` and is **not substituted into the 30-case aggregate**. The full aggregate is not a claim about all 30 questions at the later revision.

## Audit and remaining mismatches

[failure-audit.json](failure-audit.json) classifies all 22 baseline semantic failures: six genuine mismatches, one equivalent query, ten reference/evaluator ambiguities, and five execution/data/capability limitations. [remaining-failures.json](remaining-failures.json) classifies all 19 full-run failures and records the S27 follow-up separately.

- **S04:** category totals agree; a constant snapshot provenance column and safety ceiling differ from the reference output schema.
- **S10/S11:** retain the approved full-period/separate-snapshot policy. Multiple monthly observations distinguish it from a closing-date reference. Do not silently equate a month with its final day.
- **S20:** direct discount subtraction equals COALESCE under the approved NOT NULL schema. The formula and evaluator context were left unchanged.
- **S23:** independently grouped complete operands, matching periods, NUMERIC division, NULLIF, stable rank and strict missing-value handling now execute. The extra product name still changes the strict output schema.
- **S27:** the unrequested population filter is repaired in the measured follow-up; the remaining temporal/reference ambiguity is preserved.
- **S28:** safe qualification/scalar bounding plus the verified excess-row formula now pass all three metrics. Synthetic duplicate fixtures distinguish excess rows from group counts even though production keys currently have no duplicates.
- **S05:** empty filtered observations still produce an empty grouped result instead of a scalar zero count. **S12/S16:** requested month/year rollups exceed approved snapshot-grain behavior. **S13:** no verified intersection/delta contract. **S15:** “snapshot metrics” does not specify a unique field set and now requests clarification. These remain unresolved.
- Product names, snapshot provenance and alternate bounded ordering still cause strict equivalence failures, even where execution/numerical comparisons pass. Exhaustive equivalence and general natural-language intent correctness are not established.

On the two unsupported gold cases, manual review finds **1/2 valid refusals before, 2/2 after**: S29 now verifies MAX(snapshot_date) and explains that 2026 current stock is unavailable rather than giving a vague period error; S30 explains absent supplier dimensions. These are manual validity judgments, not automatic Ragas scores. Supported-case failures are not counted as valid refusals.

## Tests and reproduction

The initial focused suite passed **246 tests** at `f53c56f`. At `a287d53`, the two affected suites passed **10 + 30 tests**; the full suite ran **688 tests: 11 failures, 51 errors, 15 skips**. There are no new failure/error names versus the previous QuocAn run or the recorded main baseline. The full suite is not green. Raw full-suite failure names are in [final-full-tests.json](final-full-tests.json); [regression-comparison.json](regression-comparison.json) records baseline revisions and counts.

The existing Pydantic semantic models, compiler and AST validators were strengthened; no new semantic model hierarchy was added. Tests cover NULL populations, tied ranks, wrong metric/date/filter/grain, hidden filters, incomplete join keys, unequal fact multiplicities, zero denominators, missing category measures and duplicate-count conventions. SQL safety, RBAC, metric formulas, approved joins, permissions and read-only execution remain intact.

Use an authenticated environment with the same database snapshot and existing keys. Checkout the application revision matching the chosen output manifest; the generation runner rejects changed application bytes. Frozen working input copies are intentionally ignored by Git and are recreated from the original benchmark folder. Run:

```powershell
uv run python -m unittest discover -s tests -p "test_sql_semantic*.py"
uv run python -m unittest discover -s tests -p "test_report*.py"
uv run python -m evaluation.run_sql_contract_benchmark --stage verify --output artifacts/evaluation/sql-semantic-correctness-2026-11-04/paired
uv run python -m evaluation.run_sql_contract_benchmark --stage generate --output artifacts/evaluation/sql-semantic-correctness-2026-11-04/paired --retry-provider-errors
uv run python -m evaluation.run_sql_contract_benchmark --stage score --output artifacts/evaluation/sql-semantic-correctness-2026-11-04/paired --retry-provider-errors
uv run python -m evaluation.summarize_sql_semantic_pair --before artifacts/evaluation/sql-semantic-contracts-2026-11-03/final --after artifacts/evaluation/sql-semantic-correctness-2026-11-04/paired
```

For the separate follow-up, use `a287d53`, `--output artifacts/evaluation/sql-semantic-correctness-2026-11-04/followup --ids S27` for generate/score. Existing completed generations/scores are retained. A genuinely new experiment needs a separate output directory. Git checkouts may normalize line endings; source-byte guards require matching manifest bytes or a separately recorded verified reproduction checkout, never silently replacing the original hashes.

The runner's legacy `comparison.json` uses an older baseline and Report context and is excluded here. Use [paired/paired-summary.json](paired/paired-summary.json) for this comparison. [PROTOCOL.md](PROTOCOL.md) records boundaries and assurance limits. Report live benchmarking remains paused.
