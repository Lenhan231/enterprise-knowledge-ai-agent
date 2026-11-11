# SQL inventory capability matrix

This matrix describes the measured `3564c06` revision. It does not approve a production merge.

| Operation | Evidence | Outcome / limit |
|---|---|---|
| Product fields, literal filters, IN/NULL, sorting and limits | I01-I10, P01/P02/P06 | Direct-field group result match 7/13 → 13/13; calls 17 → 0. Complete English/Vietnamese clauses only. |
| Inventory keys/year/month retrieval | I07/I10 | Deterministic metadata retrieval; inventory measures still require canonical mapping. |
| Master catalog COUNT and category grouping | I12/I13 | Executed and matched. COUNT(product_id) and COUNT(*) are equivalent under the product PK; the judge disagreed on I13. |
| Inventory/products JOIN and SUM | I16-I18/I21/I32/I36 | Actual PostgreSQL results match. Products PK + inventory FK verified, zero orphan rows. Aggregation precedes result limiting. |
| Filtered distinct product COUNT, including zero | I26/I27/P27, I28/I38 | Scalar empty population returns one zero-count row; explicit grouped requests retain their groups. Native selected-date binding verified. |
| AVG of stored rates / days of supply | I22/I23/I35/P22 | Catalog unweighted AVG, non-null values; original rate formulas/weights are not inferred. |
| Boolean flags | I28/I29, catalog tests | Stored indicators or approved counts/shares; no inferred operational reorder threshold or quantity. |
| TOP-N stock rankings | I19/I20/P19 | Explicit limits, stable product identity and NULL-preserving ordering. I20's reference leaves descending NULL priority implicit; see semantic audit. |
| Exact snapshot and product history | I16/I30/I33 | Date filters preserved. Missing historical snapshot yields no observations, not zero stock. |
| Month/year observation trends | I31/I37, legacy S12 | Separate exact snapshot groups. Calendar/monthly rollup across multiple observations remains unapproved. |
| Two-snapshot stock change | I49/I50, legacy S13, adversarial SQLite + real PostgreSQL | Intersection and NULL arithmetic verified. Exact legacy S13 execution and numeric scores 0 → 1; strict semantic score remains 0. Main comparison group strict match 0/2 → 1/2 due to I49's extra reference name column. |
| Unsupported scopes and ambiguous thresholds | I40-I48 | Valid refusal audit 6/9 → 9/9. Supported clarifications 3/50 → 0/50. |
| Permissions / read-only / source allowlist | Focused security tests, real reader and database constraints | Permission checked before model/database calls; nested third-table queries and writes rejected. No database permissions or migrations changed. |
| API and Report integration contracts | Existing contract/unit suites | Passing focused contracts, including Report fact provenance. Report benchmark explicitly deferred; no end-to-end Report benchmark approval. |

The inventory-metric group matched 28/30 → 30/30 frozen result sets. The five structural queries matched 5/5 in both runs. Main benchmark facts concern this dataset and these frozen cases; they do not establish exhaustive semantic correctness for arbitrary paraphrases or layouts.
