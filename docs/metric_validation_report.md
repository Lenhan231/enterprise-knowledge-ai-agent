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


## Follow-up: semantic mapping before SQL (2026-10-31)

The user authorized a semantic interpretation step using the existing approved catalog. Inventory and unrecognized requests now map language into typed catalog IDs, dimensions, source-row filters, historical dates, product/aggregate representation and ranking. Recognized legacy non-inventory metric requests keep their existing path. Other generic requests receive a domain interpretation; an interpretation of domain=other cannot execute inventory SQL. The same configured Qwen model is used, without fine-tuning, schema discovery, new metric definitions, a new agent or a second registry.

Mapping candidates are compact descriptions/statuses generated from the existing ontology. Python checks accepted/executable definitions, known metric omissions, allowed dimensions/fields, filter types/operators, date structure, representation and ranking limits before SQL generation. SQL generation receives only selected definitions and its approved stored-value or aggregate representation. The SQL is then checked against the accepted interpretation: output dimensions/metrics, filter values, date scope, grouping, ranking and limit must agree. These checks supplement the existing AST, fanout, placeholders, permissions and read-only execution checks. Only the existing single SQL repair is allowed; failed interpretations never authorize a generic fallback.

The inventory/products FK makes their product IDs interchangeable through the approved join. Product representation explicitly selects stored fields without SUM/AVG or grouping. One JSON code fence may wrap a single JSON object, following existing agent conventions; writes, extra objects/text, unknown fields and invalid mapping/SQL still fail validation. SQL tokenization errors now reach the existing safe repair path. Accepted results expose semantic_interpretation metadata without removing existing API fields. Report section generation and database configuration are unchanged.

### Evaluation evidence

A new fixed eight-question matrix has five supported questions and three clarification/refusal cases. Wording includes unseen stock/balance/style synonyms and mixed Vietnamese-English. Original-source before is 54c6831; model/settings and case hashes match the changed-source live trials. Gold values were freshly read through the existing read-only commerce repository. No DML probe or database change was performed.

| Outcome | Original source | Refined live trial |
| --- | --- | --- |
| Supported questions executed | 1/5 | 4/5 |
| Calculations and current semantic/date contract correct | 0/5 | 4/5 |
| Correct targeted ambiguity/unresolved clarification | 2/3 | 3/3 |

The one original execution returned 200 raw snapshot rows for a question asking separate snapshot totals; execution alone does not count as metric correctness. The initial mapping trial, after.json, correctly executed three supported cases; it exposed an equivalent-product-ID false rejection and ambiguous stored-value generation instructions. Both were corrected with regressions. The refined after-refined.json executed stock ranking, category balances, category ranking and twelve dated snapshot totals correctly. Its remaining Vietnamese fill-ranking case produced the correct stored-value SQL inside a JSON fence, then a repair hit the provider's 7,000-input-token-per-minute limit. This is recorded as a failed live case, not silently scored as success.

The final parser safely normalizes that wrapper. Saved-response replay against the actual read-only database passes **5/5 supported calculations and all three expected clarifications**, including the previously blocked fill ranking. Replay involves no fresh model inference and is not an LLM success-rate estimate. A separate **fresh model retest** of that exact Vietnamese fill-ranking question also executed ten correct stored rates and passed numerical/date/formula scoring. It uses the same model and is recorded separately in live-retest.json and live-retest-score.json; there is no claim that a final single eight-case live run achieved 5/5.

Median supported-case elapsed time was 1.37s before and 3.85s in the refined live trial. Most before cases failed early, so these are not equally successful workloads. Interpretation normally adds one model call; rapid repeated requests can exceed the provider token allowance. Replay timings exclude model inference and must not be compared with live latency.

### Verification and current limits

The final focused run completed 164 tests: 163 pass and the same existing UI .files fixture fails, with zero errors or skips. Seventeen dedicated mapping tests pass, including unseen/mixed language, contract-bound SQL, permitted product-key equivalence, typed filters, IN/range/date parameters, malformed or SQL-bearing interpretation output, unresolved metrics, missing scope, changed filter/ranking/limit/dimension rejection, unauthorized requests, repeated violation without execution, and fenced JSON that still rejects writes/extra objects. Existing fake providers were updated to supply the new interpretation response before their original SQL responses. Authenticated local API and mocked Supabase smoke fixtures pass; no live write probe was run.

Final full discovery completed **509 tests: 434 passed, 11 failures, 55 errors and nine skips**. The source-only original diagnostic completed 492 tests with 12 failures, 55 errors and nine skips. All 66 final problem headers also occur in the original-source run; no new problem header appears. The original-only failure is the updated missing-snapshot fixture expecting a mapping call, which the original implementation did not make. It is an expected fixture-contract difference, not a claimed unrelated improvement. Existing removed modules/symbols, old financial fixtures, retrieval expectations and the UI .files fixture remain outside this task. Full-suite JSON records every problem header; detailed logs remain local ignored files.

The mapper is language interpretation, not proof of intent. It can still misunderstand a question or ask for clarification. Mapped SQL currently uses direct SELECTs; CTE/HAVING/DISTINCT rewrites, unsupported comparisons or unsupported dimensions are refused. Named/relative periods may require explicit ISO dates. Existing 200-row limits remain. A threshold, forecast, reorder rule or weighting formula does not become approved because an LLM proposes it. Catalog governance and the six unresolved definitions are unchanged. The full benchmark matrix was not rerun after JSON-wrapper normalization; the saved replay and isolated fresh retest are clearly separated.

### Changed-file accountability for this follow-up

| File | Reason/change | Verification |
| --- | --- | --- |
| src/core/analytics/metric_mapping.py | Typed interpretation, compact catalog selection and deterministic SQL contract checks. | 17 dedicated mapping tests pass; five replay calculations and fresh fill-ranking retest pass. |
| src/core/agents/sql_analytics_agent.py | Authorize first; interpret/validate before generation; retain the accepted slots; check repaired SQL against them. | Mapping integration, RBAC, repeated-rejection and existing SQL/Analytics tests pass. |
| src/core/analytics/text_to_sql.py | Relevant interpreted metrics, approved stored projections, bounded token-error repair and single-object JSON-fence normalization. | SQL and mapping tests pass; unsafe fenced SQL remains rejected. |
| src/core/prompts/sql.py | Preserve requested ranking limit up to 200 instead of contradictory fixed-limit instructions. | Ranking contract tests and live rankings pass. |
| tests/test_metric_mapping.py | Seventeen new contract, security, field, language and regression tests. | 17/17 pass. |
| tests/test_inventory_metric_dictionary.py | Supply mapper response and update missing-snapshot call expectations; existing unresolved checks remain pre-generation. | Inventory regressions pass. |
| tests/test_sql_generation.py | Keep original SQL/summary fixtures after an explicit other-domain response. | Existing SQL generation tests pass. |
| tests/test_sql_join_duplication.py | Preserve unsafe-join tests across the new interpretation call. | All join/fanout tests pass. |
| tests/test_sql_metric_definitions.py | Supply validated stockout interpretation and its default result limit. | Canonical formula and metric agent tests pass. |
| tests/test_app_chat.py | Supply interpretation in the authenticated generic SQL client fixture. | API fixture suite passes. |
| tests/test_supabase_analytics_smoke.py | Supply other-domain interpretations in the fake provider without changing read-only probe tests. | Mocked smoke tests pass; no live DML probe executed. |
| scripts/agents/benchmark_inventory_metrics.py | Reuse existing runner for a separate eight-case matrix and archive versioned catalog data with original source. Record mapping/catalog hashes. | Original-source and two changed-source trials completed; immutable output refusal retained. |
| scripts/agents/compare_inventory_metrics.py | Score mapped semantics and normalized JSON separately from numbers; derive matrix coverage from cases. | Numeric-versus-semantic regressions and saved comparisons pass. |
| data/evaluation/inventory_semantic_mapping_cases.json | Freeze five supported unseen/mixed-language questions and three refusal/clarification cases. | Unique IDs and equal before/after case hashes checked. |
| docs/business_metric_dictionary.md | Explain the new request flow and conservative limitations. | Reviewed against implementation and evidence. |
| docs/metric_validation_report.md | Preserve this implementation/evaluation record and file accountability. | Reviewed against test and benchmark JSON. |
| SPEC-metric-enforcement.md | Transcribe the user's approved semantic-mapping requirements and boundaries. | Contract tests cover the requirements. |
| CAPABILITY-MAP-business-metric-dictionary.md | Include typed semantic interpretation within existing metric enforcement. | No new runtime agent/service added. |
| tasks/inventory-metric-dictionary-plan.md | Record completed incremental implementation and verification slices. | Original task plan remains preserved. |

All following new evidence files are under artifacts/evaluation/vietstyle-metrics-v1/semantic-mapping/ and parse as JSON:

| File | Purpose/result |
| --- | --- |
| before.json | Original-source eight-case live results, raw prompts/responses, hashes and latency. |
| after.json | Initial three-correct-case trial; failures preserved. |
| after-refined.json | Four correct supported live cases, three targeted clarifications and the provider-blocked case. |
| gold.json | Actual read-only SQL queries and expected aggregate/ranking values. |
| comparison.json | Paired live calculation, semantic, clarification and latency scores. |
| replay.json | Current validators/execution applied to saved model responses, without fresh inference. |
| replay-comparison.json | Interim scorer result before aligning scorer JSON-fence normalization; preserved. |
| replay-final-comparison.json | Final normalized scorer confirms five correct replay calculations and three expected clarifications; separate from live results. |
| live-retest.json | Fresh same-model retest of the provider-blocked Vietnamese question. |
| live-retest-score.json | Correct numerical/formula/date scoring for that retest. |
| focused-tests.json | Earlier 149-test focused integration outcomes. |
| focused-final.json | Final focused SQL/analytics/report/API fixture outcomes. |
| full-discovery.json | Initial full discovery before two fake-provider fixture updates. |
| full-baseline.json | Completed original-source diagnostic with captured unittest problem headers. |
| full-final.json | Completed changed-source 509-test run and all remaining problem headers. |
| full-comparison.json | No new changed-source problem header; expected old missing-snapshot fixture difference explained. |

Original inventory catalog versions/formulas, preflight artifacts and earlier smoke results were not overwritten. No database records, RLS, migrations, permissions, model choice or Report section generation were changed. The local backend is restarted after verification so Streamlit uses the new interpretation path.


## Follow-up: session chat and safe SQL context (2026-10-31)

Implemented the user-approved first two chat stages on QuocAn, without persistent storage, new dependencies, migrations, data changes or model changes. Streamlit renders up to 20 exchanges with answer-specific SQL/results/evidence and stable per-turn widget keys. Report mode stays separate. Reset retains sign-in/mode while clearing drafts/history/report state; sign-out clears user-specific state. Requests capture conversation/authentication identity and discard stale responses. Saved turns never trigger fresh API calls on rerender.

Standalone SQL conversation requests reuse ConversationStore in a separate SQL-only store. Existing user/conversation keys, permission fingerprints, locks, capacity, character bounds and idle expiry apply. One serialized state entry holds the accepted MetricMapping and pending clarification, without result rows, answers or SQL. Internal _sql_context metadata is server owned; public metadata validation rejects it. Auto, Knowledge, Dashboard and Report do not receive this state; requests without conversation IDs remain stateless.

Within the existing interpretation call, SQLTurn selects new, followup or answer. Typed patches inherit omitted slots, replace filters by field and support explicit field/all-filter and ranking removal. Fresh questions inherit nothing. Pending questions remain separate from the accepted scope; invalid/refused/failed turns cannot overwrite it or implicitly reactivate an unrelated scope. Current catalog validation runs after merging and all generated/repaired SQL remains bound to the accepted interpretation. Ranking requires a specified or sole active metric. Latest dates are resolved by a fixed approved read-only lookup, then generated SQL binds the concrete snapshot; refresh occurs only on an explicit new latest request. Context commits after execution, including empty results, and clears on completed non-inventory SQL. A request timeout does not commit new state. Summarization receives the accepted scope; API fields remain compatible with optional context_used metadata.

Verification:
- Thirteen new SQL context tests pass: three-turn execution and zero-row continuity; English/mixed-language patches; replacing/removing/clearing filters/ranking; fresh questions; missing/expired/restarted state; pending clarifications; rejected unknown metrics; user/session and permission isolation; client injection rejection; no context in other modes or absent-ID requests; failure preservation; serialized concurrent turns; timeout rollback; and authorization before provider/data access.
- Six new Streamlit AppTests pass: multiple exchanges retain SQL/results and unique downloads; rerenders do not resubmit; mode changes preserve history; 20-exchange cap and error turns; reset/late response rejection; sign-out clears history/report/authentication; reports remain separate with fresh drafts; and repeated dashboard charts/context captions render without exceptions.
- Final focused suite: 195 tests, 194 passes, one known pre-existing UI .files fixture failure, zero errors/skips. JSON preserves exact modules and test names.
- Full discovery: 528 tests, 453 passes, 11 failures, 55 errors and nine skips. All 66 problem headers exactly match the recorded prior 509-test run; no new problem header appears. Existing removed-module/symbol, old financial, retrieval and UI fixture problems were not repaired. Full output logs are local ignored files; committed JSON preserves the summary and problem headers.
- Live test with the unchanged Qwen provider and read-only commerce repository: stock by category at latest -> only blue products -> top three categories. All three executed, returned 4/4/3 rows, and retained snapshot 2022-12-31. Each numeric result matched an independently queried gold result. The first turn used no prior context; the next two used it. The live driver used SQLAnalyticsAgent through the router without answer synthesis or API telemetry writes, and paced turns by 60 seconds to respect the existing token allowance.
- Compilation, JSON parsing, whitespace checks and recorded runtime hashes pass. UI tests exercise the login screen and sign-out lifecycle with a simulated authenticated client; live queries used the application read-only repository, not production DML probes.

Changed-file accountability:

| File | Reason/change | Verification |
| --- | --- | --- |
| src/core/analytics/metric_mapping.py | Typed SQL conversation/patch/clarification models, deterministic merge and existing catalog revalidation; contextual mapping prompt. | Thirteen context tests, existing 17 mapping tests and live sequence pass. |
| src/core/agents/router.py | Separate locked SQL-only state, identity/expiry isolation, execution-only commits and timeout handling. | Context, concurrency, isolation, legacy routing and mode tests pass. |
| src/core/agents/sql_analytics_agent.py | Server-only context consumption, latest resolution, exact pinned SQL validation, context metadata and sanitized snapshot-read failures. | Context sequence, existing SQL safety/metric tests and live numeric checks pass. |
| src/core/analytics/text_to_sql.py | Explain server-resolved concrete dates in the existing generation prompt. | Pinned-date query and existing prompt/SQL regressions pass. |
| src/core/agents/analytics_agent.py | Supply the accepted interpretation to answer summarization. | Analytics and summary regressions pass. |
| src/core/prompts/agents.py | Add accepted query scope to the existing summary template. | Summary-format and report/orchestration regression checks pass. |
| src/core/agents/streamlit_ui.py | Session transcript, keyed historical result rendering, separate Report controls, context captions, reset/sign-out and stale-response guards. | Six AppTests and existing Streamlit renderer/client tests pass. |
| tests/test_sql_followups.py | Thirteen deterministic context, execution, rejection, identity and lifecycle tests. | 13/13 pass. |
| tests/test_session_chat.py | Six session UI/retained-data/report/dashboard/reset AppTests. | 6/6 pass. |
| docs/business_metric_dictionary.md | Explain session follow-ups and their boundaries. | Reviewed against tests and live evidence. |
| docs/metric_validation_report.md | Preserve this implementation record and measured limitations. | Reviewed against evaluation JSON. |
| tasks/inventory-metric-dictionary-plan.md | Record the completed first two chat stages and deferred persistence. | Matches the approved plan. |
| artifacts/evaluation/session-chat/live-sequence.json | Unchanged-model raw prompts/responses, per-turn result payloads, independent gold queries/rows and runtime hashes. | All three numeric results match gold. |
| artifacts/evaluation/session-chat/live-sequence-score.json | Deterministic numeric, context-use and pinned-date verification. | All three correct; runtime hashes match. |
| artifacts/evaluation/session-chat/focused-tests.json | Exact focused test outcomes/modules. | 194/195 pass; known UI fixture failure retained. |
| artifacts/evaluation/session-chat/full-discovery.json | Full discovery outcomes and existing problem headers. | Completed; known 66 failures/errors, nine skips. |
| artifacts/evaluation/session-chat/full-comparison.json | Compare problem headers with the prior full run. | No new or removed problem headers. |

Limits remain intentional: history is session/process-local, inventory SQL context is not shared across modes/workers, existing result/time limits remain, and language classification can still ask for clarification. The extra model context and answer synthesis can hit the existing provider token limit during rapid requests. Persistent conversation storage and token streaming were not implemented.
