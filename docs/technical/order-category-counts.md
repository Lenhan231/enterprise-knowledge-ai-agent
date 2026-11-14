# Order counts by product category

Implemented locally on QuocAn, 2026-11-14.

## Main synchronization

Fetched main at `5fbe1c6` and imported the seven SQL-related commits added since the prior `98eb87c` check: `b2ae747`, `5255538`, `bae42d5`, `5fb9ab0`, `45b2fa5`, `c1278ea`, `5fbe1c6`. These include customer grouping, month follow-ups, promotion compilers and hard SQL-flow tests. Unrelated OCR/infrastructure commits were excluded. The local mandatory Jev gate, policy context, request contracts, category dashboard and security checks remain on top of that SQL implementation.

## Recognition and meaning

The reported request was: “compare the number of order placed in may 2026 between Streetwear and Casual categories”.

Previously, singular “number of order” did not match the metric, plural “categories” did not supply products to prompt context, and order_count lacked category as a supported dimension. Jev also received only a subset of metric fields, omitting supported dimensions and grouping semantics.

The resolver now recognizes singular/plural order-count phrasing and Vietnamese counting wording. It excludes an immediate “order item(s)” continuation so item counts do not become order counts. Category/category-plural context includes the approved orders → order_items → products bridge.

The metric definition supports category grouping and documents this exact convention:

- Count DISTINCT orders.order_id within each products.category.
- Multiple item lines of the same category count once per order.
- An order containing multiple categories counts once in each, so category totals are not mutually exclusive and must not be summed as a distinct-order grand total.
- Use orders.order_date for the placement period. Do not invent order-status filters.

Jev receives the canonical formula, supported dimensions, category join and grouping semantics. SQL planning receives the same full metric definition. The existing metric validator still rejects non-distinct/item-row counts, and the security validator still separately checks permissions, sources, columns, functions, joins, parameters, read-only execution, row limits and deadlines. Jev's threshold remains 0.8; metric recognition does not bypass it.

## Verification

134 focused Python tests passed, including the newly imported main SQL scenarios. Regression coverage includes exact wording, Vietnamese aliases, plural category context, non-unique item lines, one order spanning categories, .79 clarity rejection, permission denial and unapproved SQL rejection even when clarity is .95.

The exact request passed one live Groq/Jev/SQL/dashboard run. Jev's clear probability was .97 (threshold .8). A bar chart returned Casual 1 and Streetwear 29 orders for May 2026. A separate handwritten, parameterized SELECT using the same restricted analytics role returned identical counts. This verifies that request against the data observed at verification time; it does not establish broad repeatability. No new 50-question benchmark was run.

The full suite ran 957 tests with 55 failures, 91 errors and 31 skips; existing broad-suite/import/fixture problems remain, and this is not a clean before/after comparison. The focused checks pass. Logs are preserved locally at `%TEMP%/order-category-full-tests.log`. The final common-alias additions were separately checked with all six order-category regression tests passing.

The backend was restarted on Groq, and backend/Streamlit health checks passed. Earlier benchmark artifacts were preserved; no new frozen source cohort or remote push was created. One successful live request is not a guarantee of deterministic Jev decisions on every retry; no global confidence threshold was changed.
