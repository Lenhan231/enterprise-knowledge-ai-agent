# Inventory metric validation report

Completed on branch `QuocAn`; baseline `78ddb20`, runtime implementation `fa74b34`. Scope is Inventory Management only. The catalog contains **21 entries: 15 executable team-defined conventions and six unresolved candidates**. Team acceptance permits these historical analyses; no official business-owner approval is claimed.

## Inspection and implementation

Read-only Supabase metadata/aggregate queries verified inventory/product keys, relationships, grain, coverage, nulls and distributions. Original preflight evidence is immutable. Snapshot coverage is monthly through 2022-12-31, with 60,247 product-snapshot observations; missing rows are unknown. Recorded indicators overlap and movement units do not consistently reconcile to order units. See [assumptions and unresolved definitions](business_metric_dictionary.md).

The existing ontology loads versioned YAML. Relevant definitions and approved relationships reach SQL generation; inventory formula, source/dimension, grain and date checks run before execution. The agent asks targeted clarifications for missing historical scope or unresolved definitions. Result/evidence metadata retains dates and governance. Report source collection has minimal compatibility changes; section generation is unchanged. Verified permissions, approved schemas/columns, SQL AST/parameter checks, safe joins, read-only transactions and result limits remain in force. No validator-bypass fallback exists.

Review corrected shared-allowlist mutation during prompt assembly, rejected OR-based false snapshot proof, enforced actual unfiltered database-latest dates, and prevented a generated subset of a year from masquerading as full-year history. Flag ratios explicitly count inventory product IDs through the safe product dimension join; existing conservative COUNT(*) fanout protection remains unchanged.

## Tests and limits

- Main focused suite: **134 tests, 133 passes, one existing failure**, zero errors/skips. Includes all 20 new inventory/catalog/evidence/scoring tests, which pass. Covers English/Vietnamese aliases, catalog schema/governance, every executable formula, numeric fixtures, missing products/zero denominators, scalar vs aggregate grain, date/snapshot proof, safe joins, unsupported dimensions/aggregates, unresolved/unapproved rejection, RBAC ordering and both Report collection paths.
- Additional compatibility suite: **24 tests, 16 passes, one failure and seven errors**. Inventory dashboard, route evaluation and agentic tests pass. The eight failures/errors are in the old financial `test_sql_analytics` module: obsolete positional SQLAgent constructor, retired authorized-financial CTE expectations and matching error-message expectations. Running unchanged source `78ddb20` against the same four unchanged modules reproduces all eight.
- Combined selected verification: **158 tests, 149 passes, two failures and seven errors**. The original-source baseline for these existing modules is 138 tests, 129 passes and the same nine problems. No new regression is observed in the selected modules. [Test comparison](../artifacts/evaluation/vietstyle-metrics-v1/inventory/test-comparison.json).
- The other existing failure is `test_orchestration_clients.WebConversationTest.test_inflight_answer_cannot_cross_a_conversation_reset`: its mock input has no `.files`, so UI setup raises before the reset assertion. It predates implementation.
- Full discovery was attempted with offline model flags, tracing disabled and local PostgreSQL integration tests disabled. **Both the original-source diagnostic and changed-source runs timed out at 150 seconds**, during retrieval tests; this is not a full-suite pass. The original-source diagnostic uses the current test tree, including expected failures from new semantic tests. Partial comparison excludes those new tests. There are 46 common failing/error status lines and no changed-source-only problem line in the observed overlap; original-only lines include cases the changed run never reached and one updated canonical fixture, not demonstrated improvements. Partial log counts must not be treated as completed test totals.
- Import diagnostics identify existing removed-symbol imports (`_financial_retrieval_query`, `_RESPONSE_CACHE`), missing repository modules (`tools.ingestion.generate_commerce_demo_policies`, `document_processing.pipelines`) and legacy financial `source_labels` assumptions. No unrelated repair was attempted. Local ignored `.log` files retain detailed output; committed JSON preserves test names, limits and diagnostics.
- Python compilation and `git diff --check` pass. YAML schema/source-column checks pass. The dependency lock was refreshed offline without a version upgrade. Docker packaging was inspected for the semantic data copy; no Docker image was built.

## Paired live benchmark

[Before](../artifacts/evaluation/vietstyle-metrics-v1/inventory/before.json) uses archived unchanged source `78ddb20`. [Final after](../artifacts/evaluation/vietstyle-metrics-v1/inventory/after-complete.json) uses runtime `fa74b34`. Both use the same eight inventory questions, `qwen/qwen3.8-27b`, temperature 0, reasoning disabled, 1,000 output tokens, sequential 20-second pacing and the existing read-only repository. Case hash and model/settings equality are asserted. No model change, fine-tuning, report synthesis or production write probe occurred.

Calculations are checked against freshly queried [frozen aggregate gold](../artifacts/evaluation/vietstyle-metrics-v1/inventory/gold.json), not hardcoded application values. A passing metric requires numeric/group/date agreement **and** canonical formula/date/dimension validation. Fill ranking permits ties at the cutoff. A matching number alone fails semantic scoring. Saved plans are replayed through current validators without executing rejected SQL. Generation/SQL-validation counts use final strict JSON plans and the current safety validator; they are reported separately from original-agent execution.

| Measure | Before | Final after |
| --- | --- | --- |
| Supported questions producing strict JSON SQL | 5/6 | 5/6 |
| Supported plans passing current SQL safety validation | 4/6 | 5/6 |
| Supported questions executed | 1/6 | 5/6 |
| Executed calculations matching gold | 1/6 | 5/6 |
| Full current metric/date/evidence correctness | 0/6 | 5/6 |
| Unresolved questions safely withheld | 2/2 | 2/2 |
| Targeted clarification with expected structured code | 0/2 | 2/2 |

The original stock total matched the number but omitted the historical date from returned evidence, so it earns calculation credit and fails the stricter semantic/evidence score. Before weighted-fill clarification already asked about weighting, but suggested defining a custom calculation; it receives no structured catalog-clarification credit. This is not a claim that every before clarification was generic or unsafe.

| Case | Final outcome |
| --- | --- |
| Q8 lowest stored product fill rates | Correct ten historical product rates; exact source values, not AVG by product. |
| Stock on hand, 2022-12-31 | Correct 104,235, with snapshot date. |
| Mean stored fill rate by category | Four correct unweighted category means. |
| Stock by snapshot in 2022 | Twelve correct separately dated totals; no cross-date balance sum. |
| Units received, latest snapshot | Correct 4,081 recorded movement units, with snapshot date. |
| Stockout share by category | Final run rejected Markdown-fenced JSON twice; no unsafe execution. The immediately preceding run executed four correct category shares. |
| Reorder quantity | Pre-generation `metric_unresolved`; missing operational inputs explained. |
| Demand-weighted fill rate | Pre-generation `metric_unresolved`; missing numerator/denominator and weights explained. |

Median elapsed time across eight cases: 1.39s before, 2.94s after. Across six supported cases: 1.39s before, 3.15s after. Most before cases failed early; these medians do not compare equally successful workloads. Unresolved after cases take approximately 1?2 ms and zero model calls. All timings exclude deliberate inter-case pacing.

The benefit comes from explicit team semantics, alias corrections, relevant prompts, dated evidence and deterministic enforcement. No benefit is attributed to a different model. This small live sample cannot establish a general accuracy rate. The earlier `after-reviewed.json` run achieved 6/6 supported calculations and two targeted clarifications; the final repeat achieved 5/6 because the provider returned Markdown fences despite unchanged settings. Preserve all trials (`after.json`, `after-final.json`, `after-reviewed.json`, `after-complete.json`) rather than selecting the best score. The remaining strict JSON formatting limitation is reported, not bypassed. Raw responses, repairs, returned rows, source hashes and per-case timing are retained.

Reproduce without overwriting evidence:

```powershell
.venv/Scripts/python.exe scripts/agents/benchmark_inventory_metrics.py --source-ref 78ddb20 --output NEW-before.json
.venv/Scripts/python.exe scripts/agents/benchmark_inventory_metrics.py --output NEW-after.json
.venv/Scripts/python.exe scripts/agents/compare_inventory_metrics.py --before NEW-before.json --after NEW-after.json --gold artifacts/evaluation/vietstyle-metrics-v1/inventory/gold.json --output NEW-comparison.json
.venv/Scripts/python.exe -m unittest discover -s tests -p test_inventory_metric_dictionary.py -v
```

These benchmark commands use the configured provider and database reader. They run read-only SELECTs and refuse to overwrite their output. The original broader smoke results remain in `preflight/`; out-of-scope sales/return cases do not affect the inventory comparison.

## Changed-file accountability

Verification labels: **I** = 20 inventory tests pass; **F** = focused suite 133/134 with the known UI fixture failure; **C** = compatibility suite 16/24 with all eight old financial failures reproduced before; **B** = live paired runs and frozen-gold scoring; **S** = compilation, schema/JSON/whitespace checks. Documentation was reviewed against the implementation and evidence. No clean full-suite or Docker-build claim is made.

| File | Reason and change | Checks/results |
| --- | --- | --- |
| `CAPABILITY-MAP-business-metric-dictionary.md` | Scope the approved modules to inventory; preserve unrelated services. | Documentation review; S pass |
| `SPEC-metric-catalog.md` | Record catalog schema, governance and bilingual contract. | I pass; documentation review |
| `SPEC-metric-enforcement.md` | Record formula, dimension, grain, snapshot and clarification acceptance criteria. | I pass; documentation review |
| `SPEC-metric-evaluation.md` | Record deterministic evaluation and unchanged-model boundaries. | I/B pass with stated generation limitation |
| `data/semantic/vietstyle_metrics_v1.yaml` | Provide 15 executable definitions and six unresolved candidates with explicit assumptions. | I/S pass; B five final supported cases correct |
| `data/evaluation/inventory_metric_dictionary_cases.json` | Freeze six supported and two unresolved inventory questions. | Unique IDs/case hash checked; B completed |
| `docker/Dockerfile.backend-api` | Copy runtime semantic YAML into the backend image. | Static packaging inspection; image build not run |
| `pyproject.toml` | Declare already installed PyYAML as a direct runtime dependency. | Offline lock refresh and runtime imports pass |
| `uv.lock` | Record the direct dependency without upgrading its locked version. | Offline lock refresh pass |
| `src/core/analytics/metric_ontology.py` | Load validated inventory YAML into the existing ontology; normalize bilingual/plural aliases and stored-rate rankings. | I pass; F/C known baseline issues only |
| `src/core/analytics/metric_validation.py` | Validate governance, canonical formulas, source dimensions, scalar/aggregate grain, snapshot/date scope and coded clarifications. | I pass; F known fixture failure; B final five correct |
| `src/core/analytics/text_to_sql.py` | Reuse strict snapshot proof and supply relevant inventory definitions/schema without mutating the allowlist. | I/F safety tests pass; B formatting rejection retained |
| `src/core/prompts/sql.py` | Explain exact-date evidence, canonical joins, explicit source-grain counts and historical conventions. | I pass; B final five executions |
| `src/core/agents/sql_analytics_agent.py` | Validate requests before generation and retain governance/date metadata plus compatible errors. | I/F permission and execution tests pass |
| `src/core/agents/execution.py` | Retain metrics/limitations when collecting SQL task results for reports. | I direct/orchestrated evidence tests pass; F report tests pass |
| `src/core/reports/sources.py` | Pass inventory definitions and historical limitations into existing evidence context. | I both collection paths pass; F report tests pass |
| `scripts/agents/benchmark_inventory_metrics.py` | Record immutable original-source/changed-source live runs with matching model/settings. | B completed; S pass; output overwrite refusal |
| `scripts/agents/compare_inventory_metrics.py` | Score numbers separately from semantics, dates, clarifications and latency. | I scoring regressions pass; B comparisons complete |
| `tests/test_inventory_metric_dictionary.py` | Add 20 deterministic catalog, calculation, safety, clarification, report-context and scoring regressions. | 20/20 pass |
| `tests/test_sql_metric_definitions.py` | Keep legacy coverage while aligning inventory formulas and returned snapshot evidence with the catalog. | All tests in this module pass in F |
| `tasks/inventory-metric-dictionary-plan.md` | Track the three approved, verified implementation slices. | Completed; original tasks/plan.md preserved |
| `docs/business_metric_dictionary.md` | Document inventory-only formulas, governance, source inconsistencies and unresolved business decisions. | Documentation/evidence review; S pass |
| `docs/metric_validation_report.md` | Report measured results, limitations and every changed file. | Evidence/JSON review; S pass |

Evidence files are test deliverables, not runtime registries. All JSON files parse successfully; benchmark files were retained without overwrite. Logs are local ignored files.

| File | Purpose and verification |
| --- | --- |
| `artifacts/evaluation/vietstyle-metrics-v1/preflight/database-profile.json` | Original read-only schema/profile/policy evidence; used for catalog assumptions; preserved. JSON parse pass. |
| `artifacts/evaluation/vietstyle-metrics-v1/preflight/offline-baseline.json` | Original 84-test baseline, including known UI failure; preserved. JSON parse pass. |
| `artifacts/evaluation/vietstyle-metrics-v1/preflight/contracts-baseline.json` | Original 30 passing contract tests; preserved. JSON parse pass. |
| `artifacts/evaluation/vietstyle-metrics-v1/preflight/llm-before.json` | Original broader smoke evidence; preserved and excluded from scoped scoring. JSON parse pass. |
| `artifacts/evaluation/vietstyle-metrics-v1/inventory/before.json` | Original-source eight-case inventory benchmark; B completed. JSON parse pass. |
| `artifacts/evaluation/vietstyle-metrics-v1/inventory/after.json` | First implementation trial; failures retained as evidence. JSON parse pass. |
| `artifacts/evaluation/vietstyle-metrics-v1/inventory/after-final.json` | Intermediate prompt trial; five supported executions; retained. JSON parse pass. |
| `artifacts/evaluation/vietstyle-metrics-v1/inventory/after-reviewed.json` | Six supported executions with correct calculations; retained. JSON parse pass. |
| `artifacts/evaluation/vietstyle-metrics-v1/inventory/after-complete.json` | Final runtime repeat: five correct supported executions, two targeted clarifications; fenced JSON rejection retained. JSON parse pass. |
| `artifacts/evaluation/vietstyle-metrics-v1/inventory/gold.json` | Read-only aggregate query and deterministic expected values; B verified. JSON parse pass. |
| `artifacts/evaluation/vietstyle-metrics-v1/inventory/comparison.json` | Intermediate before/reviewed-after scoring; preserved. JSON parse pass. |
| `artifacts/evaluation/vietstyle-metrics-v1/inventory/comparison-complete.json` | Final paired stage, calculation, semantic and latency comparison; scoring tests pass. JSON parse pass. |
| `artifacts/evaluation/vietstyle-metrics-v1/inventory/focused-tests.json` | 134-test main suite outcomes and module list. JSON parse pass. |
| `artifacts/evaluation/vietstyle-metrics-v1/inventory/compatibility-baseline.json` | Original-source 24-test compatibility outcomes. JSON parse pass. |
| `artifacts/evaluation/vietstyle-metrics-v1/inventory/compatibility-tests.json` | Changed-source same 24 tests; same failures/errors. JSON parse pass. |
| `artifacts/evaluation/vietstyle-metrics-v1/inventory/test-comparison.json` | Selected-module aggregate comparison; existing failure/error sets asserted equal. JSON parse pass. |
| `artifacts/evaluation/vietstyle-metrics-v1/inventory/full-baseline.json` | 150-second original-source diagnostic timeout and environment limits. JSON parse pass. |
| `artifacts/evaluation/vietstyle-metrics-v1/inventory/full-discovery.json` | 150-second changed-source discovery timeout and environment limits. JSON parse pass. |
| `artifacts/evaluation/vietstyle-metrics-v1/inventory/full-partial-comparison.json` | Observed common/one-sided problem lines; explicitly incomplete and excludes new inventory tests. JSON parse pass. |
| `artifacts/evaluation/vietstyle-metrics-v1/inventory/import-diagnostics.json` | Concrete existing missing modules/symbols and legacy-field import errors. JSON parse pass. |

## Remaining review and risk

Demand-weighted fill rate, reorder quantity/point, safety stock, accuracy and turnover require business evidence. Source flag thresholds, stored rate formulas and movement-period semantics remain undocumented. Inventory is historical through 2022, with incomplete product coverage per snapshot. Language resolution is conservative and may request exact dates; a semantic catalog cannot guarantee LLM formatting or interpretation. The full repository suite remains incomplete with pre-existing failures; Docker image build and live report synthesis were not run. No database, RLS, migration, model or Report-generation changes were made.


## Follow-up: stock-ranking aliases (2026-10-31)

The Streamlit question ?Which 10 products had the lowest stock in the latest inventory snapshot?? exposed a missing alias. The recognized metric set was empty; the latest-snapshot MAX() subquery then triggered the existing refusal of unknown inventory aggregates. This was a resolution failure, not a missing stock column or denied database permission.

Changed files: `data/semantic/vietstyle_metrics_v1.yaml` adds lowest stock, highest stock and stock levels to the existing stock-on-hand definition; `src/core/analytics/metric_ontology.py` retains these explicit stock requests when other metrics are present; `tests/test_inventory_metric_dictionary.py` adds alias/protected-unresolved and agent-execution regressions; this report records the verification. No formula, permission, schema restriction, SQL parser or validator-bypass change was made.

Both new regressions failed before the fix and pass afterward. All 22 inventory tests pass. The combined inventory, SQL generation, metric definitions, join safety, AnalyticsAgent, request-planning, inventory-dashboard and Report-orchestration suites pass **89/89 tests**. A separate discovery of `test_sql*.py` ran 64 tests with the same previously documented old financial test problems (one failure, seven errors); no unrelated repairs were made. Whitespace checks pass.

A live SQLAnalyticsAgent test with the unchanged configured provider and the read-only commerce repository executed the exact question successfully: ten products with stock_on_hand 3, all at snapshot 2022-12-31, ordered by stock then product name. The returned definition is stock_on_hand using its stored-value representation. Detailed local evidence is in ignored `artifacts/local/lowest-stock-regression.json`. The backend was restarted to load the updated catalog; Streamlit remains at http://127.0.0.1:8501. Original benchmark artifacts and scores were not overwritten or rerun for this alias-only correction.
