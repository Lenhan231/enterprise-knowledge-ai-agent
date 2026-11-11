# Incremental SQL benchmark: S13, S15, S17

Current incremental update to the original 30-question benchmark, published 2026-11-06. Only S13, S15 and S17 were regenerated and scored. The other 27 generations and 81 metric records are unchanged. The original full run remains in `../sql-semantic-correctness-2026-11-04/paired/`.

Final measured application: `f4c9ec1b086591ed340dc5250d161513cbc4d020` on QuocAn. Retained cases use `f53c56fada9892f433a9609c4d9e5a8df98ee1b6`. This is a benchmark containing measurements from two revisions, not a fresh measurement of all 30 cases at the latest revision. [Merged results](merged/paired-summary.json) and [per-case source/revision provenance](merged/manifest.json) are authoritative for this update.

| Case | Previous execution / semantic / numerical | Updated execution / semantic / numerical |
|---|---|---|
| S13: stock change between two snapshots | 0 / 0 / 0 | 1 / 0 / 1 |
| S15: stored inventory snapshot metrics | 0 / 0 / 0 | 1 / 0 / 1 |
| S17: top 20 ordered quantities, excluding cancellations | 1 / 1 / 1 | 1 / 1 / 1 |

| Aggregate | Original 30-case run | Updated incremental benchmark |
|---|---:|---:|
| Execution accuracy | 23/28 (82.1%) | 25/28 (89.3%) |
| SQL semantic equivalence | 9/28 (32.1%) | 9/28 (32.1%) |
| Numerical accuracy | 19/24 (79.2%) | 21/24 (87.5%) |
| Requests executing SQL, including empty results | 25/30 | 27/30 |
| Evaluator errors / pending scores | 0 / 0 | 0 / 0 |

## Changes and checks

S13 now uses the existing isolated candidate's conditional-observation approach within the shared inventory mapping/compiler. It selects products observed on both exact dates and subtracts earlier stock from later stock. Missing products are excluded; observed NULL stock remains NULL. The original catalog formula is preserved. Dates and product filters remain parameterized; shared SQL validation, RBAC, approved relationships and read-only repository execution apply. Results remain capped at 200 products. Comparison snapshot dates are carried in metadata.

For S15, the phrase "inventory snapshot metrics" now requests the catalog's ten approved stored measures in product representation. It does not request aggregate fill rate or invent a numeric filter. The compiler returns the full stored bundle and product/date identity. The mapping prompt specifies integer product IDs, boolean indicators and explicit output dimensions. S17 needed no SQL logic change and passed again.

All three final frozen oracle results were checked against the live read-only database before generation; all matched. Final provider generations took 3.971 s, 2.623 s and 2.664 s for S13/S15/S17, respectively, with one LLM call each and zero provider failures. These are observed request times, not a controlled performance comparison. The mixed aggregate latency is not evidence of a latest-revision speed improvement.

The questions, references, Ragas metrics, agent model `qwen/qwen3.8-27b`, temperature 0, and `CodexCLIJudge(gpt-5.6-luna, medium)` were retained. The final subset has three generations and nine completed metric records. Raw records are in `final/sql_analytics/`. The legacy runner's `comparison.json` uses a different historical baseline and is excluded from this publication.

## Semantic audit

The semantic judge assigned zero to S13 and S15. Its reasons are retained in the score records; scores were not overridden or rejudged.

For S13, it cited possible duplicate rows within a snapshot and missing/duplicate products in the extra products join. The verified database declares `inventory PRIMARY KEY(snapshot_date, product_id)`, `products PRIMARY KEY(product_id)`, and the inventory-to-products foreign key. The read-only check also found zero duplicate inventory keys and zero orphan products. Those counterexamples are outside the verified schema/population. Conditional MAX preserves the unique observation and its NULL value. Execution and numerical metrics both pass.

For S15, it cited the same products join, different column order/aliases, ordering, and a date-cast difference. The verified keys/FK preserve its single product/date row; native date binding is used. The requested stored values all match, while the strict semantic score remains zero. This audit establishes the stated constraints and tested cases; it does not certify arbitrary SQL equivalence. See [data assurance](data-assurance.json).

## Tests and retained diagnostic run

The final focused run passed **211 tests** across SQL generation, inventory mapping, semantic validation, joins, follow-ups, benchmark tooling, Report planning/inventory/facts, and analytics callers. New regression tests exercise intersection, subtraction direction, NULL/missing observations, native date binding, full snapshot fields, strict filter types, execution through the shared agent, and the incremental benchmark merge.

The separate legacy financial suite `tests.test_sql_analytics` has the same **1 failure and 7 errors in 14 tests** at baseline `e297839` and after the changes. The full repository suite was not rerun. See [verification](focused-tests.json).

`fresh/` preserves the initial diagnostic attempt at `ba560e1`: S13/S17 executed, but S15's model interpretation supplied product_id as the string "8" and strict validation rejected it. That observation prompted the typed-filter/output guidance change. The final cohort was rerun at `f4c9ec1`; successful attempts were not retried at an unchanged application revision for a better score. The diagnostic is excluded from final accuracy. No other question IDs or Report/Knowledge cases were generated in this task. Historical Report input copies are used by the inherited SQL scorer only.

## Reproduction

Use the measured application revision, the established authenticated provider/database environment, and the original frozen input bytes. The existing runner recreates ignored working copies from the original benchmark folder.

```powershell
.venv/Scripts/python.exe -m evaluation.run_sql_contract_benchmark --stage verify --output artifacts/evaluation/sql-three-case-reproduction --ids S13 S15 S17
.venv/Scripts/python.exe -m evaluation.run_sql_contract_benchmark --stage generate --output artifacts/evaluation/sql-three-case-reproduction --ids S13 S15 S17 --retry-provider-errors
.venv/Scripts/python.exe -m evaluation.run_sql_contract_benchmark --stage score --output artifacts/evaluation/sql-three-case-reproduction --ids S13 S15 S17 --retry-provider-errors
.venv/Scripts/python.exe -m evaluation.summarize_sql_semantic_pair --before artifacts/evaluation/sql-semantic-correctness-2026-11-04/paired --overlay artifacts/evaluation/sql-three-case-reproduction --after artifacts/evaluation/sql-three-case-reproduction-merged
```

The merge checks frozen inputs, judge and agent configuration, all replacement scores and provider outcomes, and refuses to overwrite an existing output directory. The original cohort is never edited. New aggregate numerical applicability remains 24 cases; no denominator adjustment or manual semantic credit was applied. Current source hashes were verified against the final measured manifest, and all retained 27 generations/81 scores were checked for exact record equality.
