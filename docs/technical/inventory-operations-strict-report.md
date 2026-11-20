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

Inventory presentation follows the Sales report's numbered source links, KPI cards, inclusive display dates, separate policy quotes and expandable rule evaluations. The annual summary explicitly distinguishes its one selected inventory snapshot from period-scoped fulfillment, returns and reviews. Human-readable data notes retain source failures, stale snapshots, unsupported metrics and coverage limits. Full query/document identifiers and fixed rule conditions remain in the canonical saved report; previews and PDFs show concise citations and business-facing copy. PDF charts use stable page layouts and decision headings stay with their explanations. Reopening an existing saved report applies the updated presentation without recalculating its metrics.

## Verification

`tests/test_inventory_operations.py` covers contract bytes, scope, all fixed SQL plans, parameters, missing/stale/incomplete snapshots, rule boundaries, unsupported dimensions, policy RBAC/source filtering, immutable definitions, the seven-section/five-widget renderer, saved report ownership, policy revocation, PDFs and both report-delivery APIs. Read-only PostgreSQL VALUES fixtures additionally verify all nine arithmetic formulas, period cutoffs, independent snapshots, null flags, empty sources and product filters. Set `INVENTORY_REPORT_TEST_URL` to opt into those fixtures. They create no tables and write no data.

Sales contract, context, workflow, saved-report, adaptive report and browser-renderer regressions use the existing tests. `SALES_REPORT_TEST_URL` enables the existing read-only Sales arithmetic fixtures. Full-suite and focused test logs and a sample JSON/PDF preview are under the local `artifacts/inventory-operations/` directory.

Verified on 2026-11-19 against latest main `ef5ac950`:

- Focused reports: 159 tests, 147 passed, 12 opt-in database tests skipped in the offline run. All 11 read-only Inventory/Sales PostgreSQL fixtures also passed in the database-enabled run; the remaining optional saved-store PostgreSQL test was not run.
- Full suite: 1,450 tests, 1,362 passed, 9 failures, 16 errors, 63 skipped. A clean main worktree ran 1,433 tests with the exact same 25 failing/error test names, 1,348 passing and 60 skipped. This change adds 14 passing checks and three optional database checks to that full-suite run.
- Python compilation, JavaScript syntax checks and the existing Node report-workspace check passed. All three sample PDF pages were rendered and visually inspected. No live browser was connected, so browser-level visual testing remains unverified.
- The full suite remains red on existing evaluation-fixture, Windows permission/decoder and legacy Streamlit failures. No unrelated fixes were added. Machine-readable results are in local `artifacts/inventory-operations/verification.json`.

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


## Policy retrieval and guidance correction ? 2026-11-20

Fixed report policy retrieval uses role-scoped lexical lookup across the four original source titles and the Enterprise Operating Policy EN/VN companions. Current document ACLs, ready status and active knowledge-base membership are checked before document IDs are passed to retrieval ranking. Returned IDs are rechecked, and backends that cannot enforce document filters fail closed. Fixed topic queries cover stockout, reorder, overstock and returns; page headers, contents entries and duplicate passages are excluded. Document text remains quoted evidence and cannot change metric formulas or decision rules.

Both report presentations separate the recorded reason for review from a concrete next step. Inventory validation is a collapsed browser disclosure and a compact PDF summary; the immutable JSON still retains all seven sections and its full audit limitations. Reports use the available page width. The Jan?Nov 2026 workflow was checked using the Operations role: all nine metrics were available, catalog-relative snapshot coverage matched all 97 products, and policy evidence was retrieved.

No generated source records were inserted. The existing Sales record fingerprint was unchanged. An optional nullable provenance column was added while a separately authorized synthetic-data extension was being assessed; the extension was not executed and no report calculation uses that column.
