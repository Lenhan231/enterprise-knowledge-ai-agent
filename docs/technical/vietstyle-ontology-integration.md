# VietStyle policy ontology integration

Subsequent SQL synchronization: [order-category recognition and counting](order-category-counts.md) records the seven additional SQL commits imported through main `5fbe1c6` and a live verification of the reported category comparison.

Implemented locally on QuocAn, 2026-11-14. Governing source: Enterprise Operating Policy v1.0, document VSC-OPS-POL-001. The registry records the exact source SHA256 and numbered policy-page references. The Inventory Policy Pack is a simulation draft and does not govern this integration.

## Main synchronization

Fetched origin/main through `98eb87c`. No new commits were found in the Knowledge agent, retrieval, or reranking paths. Imported these SQL commits with cherry-pick, retaining author history and resolving dashboard wiring conflicts:

| Main commit | Local commit | Change |
|---|---|---|
| 7172ab1 | 684becc | Schema-aware SQL agent and configured-schema discovery |
| 78dcfb4 | 8d5160c | Current-month resolution and clarification retry handling |
| 58191ac | b793bfa | Direct planning for standalone analytics |
| 9a3b3eb | cc1caec | Monthly totals unless daily detail is requested |
| b59edf8 | 598005d | Date bounds in scalar answers |
| eddc197 | 141727d | Compiled month-over-month revenue comparisons |
| af24b2f | b37a5b3 | Direct comparison summaries |
| 5f47b5d | d87dea2 | Comparison formatting in Auto |

Unrelated UI, OCR and deployment commits were not imported. Existing uncommitted dashboard fixes and benchmark evidence were preserved in a named stash and reapplied; the stash remains available as a backup. No remote push occurred.

## Runtime flow

The new SQL implementation lives in `core.sql_agent.agent`; the old import path re-exports the class and payload converter. Both backend entry points keep DashboardAgent and share the same SQL instance with Analytics. The local reusable Jev client, mandatory 0.8 gate, bounded retries, service diagnostics, chart mapping and timeout handling are retained on the new implementation.

`data/semantic/vietstyle_business_ontology_v1.yaml` defines cited entities, grains, the product relationship and policy constraints. `policy_context` selects only entities available to the configured SQL runtime. Context reaches Jev, inventory interpretation and SQL planning. It supplies business meaning; it never expands schema access or supplies an executable formula.

The existing metric catalog remains the formula authority, including unit, temporal semantics, provenance and approval status. Policy approval is not business approval of team-defined metric formulas. The registry stores its source hash so runtime containers and frozen benchmarks need only the semantic YAML files; the policy document itself need not be loaded or copied into a runtime image. Docker's build context includes the new registry.

Successful/clarification SQL metadata carries policy identity and applied rule IDs. Chart scope carries policy provenance. Existing SQL and chart validators enforce snapshot, grain, unit and composition rules; policy text is not executed as code.

## Request contracts

The planner is instructed to include this bounded structure alongside SQL, parameters and explanation:

```json
{
  "columns": ["category", "stockout_count"],
  "dimensions": ["category"],
  "chart_type": "bar",
  "measure_filters": {
    "stockout_count": {"column": "stockout_flag", "equals": true}
  }
}
```

When supplied, the decoder enforces exact ordered output aliases and independently filtered boolean measures before execution. Extra fields, duplicate columns, malformed values, missing FILTER expressions and shared root-WHERE substitutions are rejected. Boolean literals and bound boolean parameters are supported. Invalid contracts enter the existing one-repair planning path and cannot grant SQL permissions. Source, column, function, join, parameter, metric, read-only-role, row-limit and timeout checks remain independent.

Dashboard validates the contract again, preserves catalog-derived units and refuses a chart type incompatible with the explicit user request. Its existing conservative donut proof remains in place.

Compatibility: older plan payloads and compiled inventory plans can omit request_contract. Dimensions are checked as declared output aliases; they do not replace existing grain/grouping validators. The contract is model-authored, so agreement between it and SQL does not prove agreement with the user's intent. This integration is a policy-grounded foundation, not a complete natural-language semantic verifier. Independent inventory flag counts remain explicitly rejected by the single-filter inventory mapper; this does not add full conditional-count planning support.

## Verification

The integrated focused set passed 150 Python tests and five Node renderer tests. A subsequent cleanup regression passes as well. Tests cover policy source hash and scope, extra-column rejection, literal and parameterized independent filters, repair before business-query execution, provider cleanup, real SDK parsing via a mocked HTTP transport, clarity failure without SQL, dynamic schemas, join fanout, SQL approval, metric fractions, monthly comparisons, Streamlit's actual streaming chat path and all three chart renderers. SQL-focused fixtures mock clarity decisions; dedicated Jev tests exercise the actual gate implementation. No live API key is needed for these tests.

JavaScript syntax, Python imports, conflict-marker and whitespace checks pass. A network-isolated full-suite run executed 944 tests: 54 failures, 91 errors, 31 skips. It includes legacy missing imports and fixtures and was started before the last two focused fixture corrections and the added cleanup test. The final focused checks pass; the repository-wide suite is not green, and this run is not a clean before/after comparison. The full log is preserved locally at `%TEMP%/ontology-integration-full-tests.log`.

No new live benchmark, browser visual/keyboard review, Docker image build or deployment was performed; earlier benchmark scores predate this integration. Plan/SQL contract agreement does not establish natural-language correctness, and optional legacy contracts can still be omitted. A new live comparison is needed before reporting a reliability improvement.
