# General count queries and actionable failures

## Scope and build order

| Capability | Owner | Depends on |
|---|---|---|
| count-contract | analytics/counting.py: bounded typed counts and deterministic SQL | Existing schema/SQL authorization |
| count-runtime | SQL agent: same model call, compiled query, dashboard outputs | count-contract |
| failure-feedback | SQL error classification and actionable business messages | Existing response/UI contract |
| count-evaluation | Independent reference counts and explicit coverage denominator | count-runtime |

Implement locally; preserve existing unmodified SQL/inventory paths and do not push/deploy.

## Semantics

One count query has one approved source, up to eight named counts, shared filters/time,
and optional returned grouping fields. Each count selects rows, non-NULL field values,
or distinct non-NULL field values. Every count has its own ANDed conditions; conditions
on different counts never become a shared intersection. A NULL boolean matches neither
true nor false. Explicit is_null/is_not_null are supported. Empty scalar populations
return zero; grouped populations do not fabricate absent groups.

SKU means distinct product_id in inventory observations, not catalog size. Latest
snapshot is MAX(snapshot_date), shared by all counts and unaffected by count/population
predicates. An explicit requested period restricts that MAX to the requested window;
otherwise it is global. A unique source date field is resolved from schema without user
input; multiple legitimate date fields require an actionable choice. Inventory history/ranges
keep separate exact snapshot groups; no implicit accumulation of balances or identities
across snapshots. Exact dates/ranges must match the original request. NULL identity is
excluded from distinct counts; rows counts retain duplicates and NULL identities.

The new compiler never joins: source-row counts cannot be inflated by product/fact joins.
Additional tables, arbitrary SQL, expressions, guessed identities, compound distinct keys,
and derived/window counts are rejected. Existing guarded SQL joins remain unchanged;
their support is not counted as new compiler coverage. Canonical metric checks remain
in force outside inventory; inventory counts use explicitly typed source fields and SQL
compiled from that checked contract, rather than treating boolean fields as metrics.

## Runtime and feedback

Use the existing inventory interpretation or SQL generation call to emit count_query
plus outputs. No extra planner model. Invalid generated contracts get at most one repair;
no partial query executes. Genuine missing requirements produce a concrete question.
Malformed/mismatched generated plans report generation failure; unsupported capabilities
report an explanation/alternative rather than a request to clarify a complete question.
Technical error codes remain available for diagnostics, without credentials/provider errors.

## Verification and coverage

Use unittest for compiler/negative/runtime/API checks and SQLite fixtures with SQLGlot
transpilation plus an independently implemented Python/reference-SQL oracle. Include
NULLs, duplicates, overlapping flags, empty populations, renamed columns, shared filters,
grouping, date boundaries, latest snapshot and forbidden joins/fields. Add read-only live
database comparisons and separate model end-to-end trials. Publish exact denominators,
case lists, failures, skips and scope. Do not call a finite benchmark “all possible counts”
or confuse deterministic correctness with model success or line coverage.

Commands (PowerShell): `$env:PYTHONPATH='src'; uv run python -m unittest discover -s tests -p 'test_count*.py' -v`;
`uv run python -m unittest discover -s tests -v`; `uv run python -m compileall -q src tests scripts`.
No dependencies, production writes, permission changes, or special-case prompt matching.
