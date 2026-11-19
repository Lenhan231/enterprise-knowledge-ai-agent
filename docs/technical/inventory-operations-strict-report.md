# Inventory & Operations strict report

The server preserves `data/semantic/inventory_operations_strict.json` byte for byte. Its runtime JSON has nine fixed metrics, five fixed widgets and four fixed rules. It deliberately has no `sections` field: the existing report preview and PDF project that payload into the contract's seven sections. Policy status, quoted passages and document citations live in the allowed data-quality limitations; the saved document retains typed policy provenance separately for access rechecks.

## Request and execution

Use the existing report prompt, for example `Monthly inventory report for May 2026`, `Inventory operations report for July 2026`, or `Annual inventory report for 2026`. Explicit `inventory_operations` metadata selects the same route on both report-delivery APIs. Explicit `inventory_risk` metadata or wording continues through adaptive reporting. Sales keeps its existing route and public scope-parser imports.

Calendar parsing is shared with Sales. Inventory supports category and product breakdowns using the existing fixed widget axes. Filters use quoted values, such as `for segment "Core"`, `for category "Bikes"`, or `for product "12"`. A bare segment breakdown requires clarification because none of the immutable widgets has a segment axis. Explicit snapshot requests retain snapshot granularity. Unsupported per-metric dimensions return `not_available`; no approximate attribution is performed.

The SQL Agent executes fixed parameterized plans through the existing `query` security boundary: requester authorization, deployed source/column allowlist, SQL validation, read-only repository, timeout and row cap. No model calculates metric values, generates SQL for this route, changes report definitions or evaluates rules. Null fields remain unavailable; flags are recorded booleans, never inferred from zero stock.

## Snapshot and coverage policy

Select one global `MAX(snapshot_date)` strictly before the requested `end_exclusive`. Use that exact date for every point-in-time metric, product table and flag distribution. A month and a calendar year use the same cutoff policy. The selected snapshot may precede the period and is then disclosed as stale. Missing snapshots leave point-in-time metrics null and explicitly unavailable. The history widget independently counts flags on each date inside the requested half-open period; it never sums balances across dates.

The attachment's report-specific wording says `<= end_exclusive`, while its general DATE policy specifies `[start,end_exclusive)`. This implementation consistently uses `< end_exclusive` so a snapshot dated June 1 cannot become the May report's closing observation. The selected date is recorded in coverage_start/coverage_end, SQL evidence filters.snapshot_date and a selected-snapshot disclosure; no new runtime keys are introduced.

I01–I03 require available validated flag counts with SQL provenance. I04 additionally requires a non-stale snapshot, positive catalog population, matching distinct observed-product and source-row counts, no missing/unmatched catalog products, and all three flags known. Coverage is relative to the authorized current catalog; historical membership and transaction-source completeness are not certified. Stale, incomplete or unknown coverage withholds I04. A triggered rule preserves its investigation-only action; policy compliance is never inferred.

## Policy and delivery

The Knowledge Agent receives the original verified identity and document roles. Only the contract's four fixed policy source names are accepted (file extensions and underscore/space separators are normalized). Missing permission skips retrieval. Retrieved text is quoted evidence, not an instruction or a verified approval/effective-date claim. Every passage retains its document identifier and citation. Reopening and exporting saved reports recheck current document access and remove inaccessible policy passages from both context and JSON limitations.

The existing saved-report library, owner isolation, revision checks and PDF endpoint serve both types. Inventory permits title edits; its seven sections and widget types/order remain immutable. Sales presentation editing is unchanged. The contract validator runs before generation returns and whenever a saved report is loaded or saved.

## Verification

`tests/test_inventory_operations.py` covers contract bytes, scope, all fixed SQL plans, parameters, missing/stale/incomplete snapshots, rule boundaries, unsupported dimensions, policy RBAC/source filtering, immutable definitions, the seven-section/five-widget renderer, saved report ownership, policy revocation, PDFs and both report-delivery APIs. Read-only PostgreSQL VALUES fixtures additionally verify all nine arithmetic formulas, period cutoffs, independent snapshots, null flags, empty sources and product filters. Set `INVENTORY_REPORT_TEST_URL` to opt into those fixtures. They create no tables and write no data.

Sales contract, context, workflow, saved-report, adaptive report and browser-renderer regressions use the existing tests. `SALES_REPORT_TEST_URL` enables the existing read-only Sales arithmetic fixtures. Full-suite and focused test logs and a sample JSON/PDF preview are under the local `artifacts/inventory-operations/` directory.

## Changed files

- `.gitattributes`: stable contract bytes across Windows/Linux checkouts.
- `data/semantic/inventory_operations_strict.json`: original supplied contract.
- `src/core/reports/calendar_scope.py`, `sales_performance.py`: shared calendar parsing, preserving Sales imports and behavior.
- `src/core/reports/inventory_operations.py`: fixed contract, policy evidence, validation, decisions and assembly.
- `src/core/agents/sql/inventory_report.py`, `sql/agent.py`: fixed validated SQL plans and SQL Agent entry point.
- `src/core/agents/report/agent.py`, `src/core/reports/planning.py`: strict routing while preserving adaptive inventory and exact-date requests.
- `src/core/reports/document.py`, `export.py`: fixed inventory presentation and existing PDF delivery.
- `src/app/reports.py`: natural request routing, saved reports, policy reauthorization and safe presentation edits.
- `src/app/agents.py`, `src/core/agents/main.py`: inventory report type on both existing delivery endpoints.
- `src/app/static/app.js`, `index.html`, `report-workspace.js`, `sales-report.js`: existing prompt, library, fixed preview and chart rendering.
- `tests/test_inventory_operations.py`, `tests/test_saved_reports.py`: inventory workflow and cross-report presentation regression checks.
- `docs/technical/inventory-operations-strict-report.md`: implementation policy and verification notes.
