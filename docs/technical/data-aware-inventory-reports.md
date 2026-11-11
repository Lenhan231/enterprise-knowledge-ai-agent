# Data-aware reports over the shared Auto/SQL schema

Reports using Analytics or Auto sources select their structure from the request,
the shared `APPROVED_COLUMNS` and `APPROVED_JOINS`, and canonical metric definitions.
Report planning receives the same full approved Commerce schema as general Auto/SQL
planning. The former report-only inventory/products restriction and blanket
rejection of transaction measures have been removed. Document-only reports retain
their existing workflow.

Schema approval establishes a query boundary, not data availability or support for
every metric/grain. Return-rate requests (including `tỉ lệ trả hàng` and `tỷ lệ trả
hàng`) go through the same SQL Analytics Agent and canonical metric validation as
other SQL requests. A missing definition, incompatible category attribution or
unavailable data still produces clarification, a partial report or a source error.

## Planning and evidence

`ReportPlan` specifies purpose, sections, table columns, reusable evidence tasks,
metric mappings, product fields, filters, snapshot scope and unsupported requirements.
The model selects these contracts; it cannot supply executable report SQL.
Inventory tasks use existing formula, mapping, join and SQL validators. Product
tasks support canonical source attributes and a separate master-product COUNT.
Other tasks carry a focused question without an inventory mapping or product
columns. The shared SQL Analytics Agent generates and validates their SQL; report
planning never emits executable SQL. This supports single-domain and mixed
inventory/order/sales/etc. reports within the existing approved schema. Validated
query scope, parameters, raw output fields and metric units travel with the facts.
Raw fields without a matched canonical metric are labeled `source_field`; the
report does not invent units or conversions. Source row IDs preserve duplicate
returned records. Authorization, approved joins, read-only SQL and result limits
remain unchanged.
The shared query decoder binds ISO dates as native dates for asyncpg.

Missing inventory time scope requires clarification. Actual result dates appear in
the coverage appendix. Historical balances remain grouped by exact snapshot;
missing observations never become zero stock. Unknown currency, unapproved
business policies and catalog caveats remain visible. Product price/cogs are raw
source fields, not an approved inventory valuation.

Structured facts record metric/field, raw value, unit, dimensions, filters, date,
source, formula and approval status. Quantitative narrative is rendered from
matching facts, preventing generated prose from relabeling a cited number.
Qualitative document interpretation retains citation checks and is explicitly
not fully semantically verified. Decimal comparisons preserve operand IDs;
rate differences use percentage points and relative changes use percent.

Aggregates execute over the filtered database scope before LIMIT. Detail queries
return at most 200 rows per task with stable ordering. Reaching that ceiling means
unknown completeness unless the user explicitly requested a ranked subset.
Tables render independently from the LLM; each block has at most 50 data rows.
Facts that cannot fit the chosen layout are included in detail appendices.
Narrative evidence is bounded separately and its omissions are disclosed.

The generation engine lives in `core.reports.generation`; inventory mapping and
snapshot rules remain specialized contracts. Sharing the current Commerce schema
does not make arbitrary new industry schemas plug-and-play. Adding a new data
domain still requires approved schema/joins, metric definitions, permissions,
documents and acceptance tests. No runtime schema discovery or automatic metric
invention is introduced.

## Confirmation contract

Both multipart endpoints (`/api/agents/report` and `/api/report`) accept:

| Field | Behavior |
|---|---|
| `template_choice` | Optional `uploaded` or `suggested`; absence never implies consent to a mismatch. |
| `accept_supported_scope` | Boolean, default false; explicitly accepts the supported part of a mixed request. |

An unsuitable template or partially unsupported request returns HTTP 409 with a
structured `detail`: `status=confirmation_required`, `confirmation_required`,
`mismatch_reasons`, `unsupported_requirements`, `suggested_structure`,
`template_decision_required` and `scope_decision_required`.

The web client and Streamlit combine these decisions into one review step. A
resubmission repeats planning and authorization; confirmation cannot enable an
unsupported metric or invented evidence. Entirely unsupported requests return
422 with a supported alternative. Clarifications retain the existing 422 contract.
No observations for the requested scope returns 422, while total provider/source
outages return 503. Downloads retain `X-Report-Status`.
`X-Report-Summary` adds bounded JSON counts for complete/unavailable/failed sections,
narrative omissions and failure reasons, displayed by both clients. Per-section
status and full coverage remain in the downloaded appendix.

Markdown remains the default file type. An uploaded template determines its file
type unless an incompatible explicit output type is supplied, which is rejected.

## Explicit template regions

In a marked Markdown template:

```markdown
# Category stock

Company disclaimer retained verbatim.

{{report:Category stock}}

| snapshot_date | category | stock_on_hand |
| --- | --- | --- |
| {{report:rows}} | | |
```

DOCX uses the same standalone paragraph marker beneath a matching Word Heading
and the rows marker in the first placeholder data row. Every section and table
must be marked; mixed, duplicate and misplaced markers are rejected. Static body
text, headers, footers, images and styles remain outside replacement regions.
Retained text is labeled user-provided and unverified. Unmarked templates keep
legacy heading-based replacement and disclose that body text/table data are replaced.

## Execution and verification

The report budget is 180 seconds, with the final 10 reserved for rendering.
Independent queries and narrative sections run with at most two in flight per
request. Identical queries share results. Each narrative section has at most two
attempts shared between repair and transient retry; completed sections are not
regenerated. Transient connection/timeout failures get one query retry. Actual
provider/database calls receive deadline-aware timeouts.

Verified tables remain downloadable if narrative generation fails. `complete`,
`partial`, and `failed` describe delivery completeness; source caveats and limited
semantic assurance are tracked separately. A later retry is a new request.
Summary logs contain status, counts and timing, never source contents.
Planning sends shared catalog constraints once instead of repeating them for every
metric. Planning gets one repair or transient retry within the request budget;
rate limits are reported explicitly without immediately repeating exhausted-key
requests. Safe logs record provider error type/status or validation code, never
credentials, raw provider errors or prompt contents. Provider failures expose an
`error_code` distinguishing rate limiting, timeouts and configuration failures.
Explicit product-ranking listings render their summaries directly from verified
facts; they do not require a second model call unless interpretation is requested.

Run the report suite and affected regression tests:

```powershell
uv run python -m unittest discover -s tests -p "test_report*.py"
uv run python -m unittest discover -s tests -p "test_streamlit_ui.py"
uv run python -m unittest discover -s tests -p "test_sql_generation.py"
uv run python -m unittest discover -s tests -p "test_metric_mapping.py"
uv run python -m unittest discover -s tests -p "test_inventory_metric_dictionary.py"
node --check src/app/static/app.js
```

Tests use fake providers/repositories, authenticated local API clients, controlled
concurrency events, DOCX structure/style assertions and the shipped JavaScript
dialog function. They do not establish production latency or visual fidelity in
Word. Authenticated staging generation and visual browser/Word inspection remain
deployment checks. No migrations, dependencies, PDF/charts, background jobs or
exhaustive exports are introduced.
