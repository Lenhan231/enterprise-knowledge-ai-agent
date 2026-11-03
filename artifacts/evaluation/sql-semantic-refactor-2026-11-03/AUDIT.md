# SQL interpretation audit (before implementation)

Baseline: `3ba340d`, branch `QuocAn`; application baseline `f8996f6`. November 2 references and scores remain frozen.

| Case | Answerable / catalog | Observed failure and verified boundary | Interpretation of evidence |
|---|---|---|---|
| S02 | Yes; distinct observed products is a structural count, not a business KPI | Mapping returned `invalid_date_scope` before SQL; original model mapping was not recorded | Date is explicit. Exact malformed slot cannot be established from the trace. Generic inventory aggregates are also blocked by `validate_metric_definitions`. |
| S03 | Yes; stock_on_hand scalar | Same pre-SQL date error; underscore field name produces no alias candidate | Snapshot mappings reject even an identical redundant end date; report planner already normalizes this case. This is a reproducible code defect, not proof of the unrecorded model response. |
| S04 | Yes; stock_on_hand sum per category | Same pre-SQL date error | Same limitation of trace attribution; no SQL or data failure observed. |
| S10 | Yes; unweighted stored fill_rate mean per observation | SQL uses `< 2022-12-31`, omitting month-end | SQL generation error, correctly rejected. Natural month validator separately interprets year alone; mapping/compiler must preserve inclusive month scope. Oracle uses the sole December observation, not a newly approved monthly KPI. |
| S11 | Yes; stored stockout_days per product | Generated GROUP BY includes measure; scalar recognition requires ungrouped output | SQL representation error, correctly rejected. Unspecified ranking limit became 10, while frozen oracle uses 200. |
| S14 | Yes; missing observations, not zero stock | Approved product key plus snapshot predicate in LEFT JOIN ON rejected as non-column equality | Safety validator lacks narrowly constrained join-side filters. NOT EXISTS remains another possible safe form. |
| S23 | Yes; explicitly requested unit ratio, not canonical order-based return_rate | SQL planner asks whether units mean orders | Unnecessary semantic clarification; canonical return_rate is not the requested formula. Safe independently aggregated CTE joins currently lack a lineage/uniqueness proof. Do not loosen join checks globally. |
| S26 | Yes; recorded flag plus existence of orders | Inventory-only mapping asks to abandon orders | Mapping prompt restricts domain; inventory SQL context strips transaction sources. Approved schema alone does not implement this combined semantic contract. |
| S27 | Yes; separately aggregated category comparison | Inventory-only mapping refuses ordered quantity | Same cross-domain restriction; validator explicitly forbids unrelated inventory metric sources and derived joins. Needs a separate proven multi-grain contract, not removal of the guard. |
| S28 | Yes; structural key-quality check, not a KPI | Generated outer SELECT omits LIMIT | Correct security rejection. Even a bounded version then encounters generic inventory-aggregate rejection. Frozen reference counts excess duplicate rows, whereas wording could mean all participating rows; disclose this evaluation convention. |

Alias candidates currently act as mandatory selections in `_required_metrics`, pre-validation and `decode_metric_mapping`. `resolve_metric_names` also misses underscore-separated source fields. No traced case establishes an incorrect alias selection; substituting unit ratio with return_rate remains a risk, not a verified cause here.

The inventory mapping plus second SQL LLM call repeats already resolved choices. The report planner already has a deterministic inventory compiler; move that compiler into analytics and reuse it in both callers. Keep the final SQLGlot, catalog, placeholder, join-grain and repository authorization checks.

## Implementation scope

First fix shared temporal normalization, candidate-versus-required handling, task-relevant schema context, deterministic canonical inventory compilation, and narrowly safe outer-join predicates. Reach SQL agent, report planning caller, shared analytics helpers, regression tests and a separate evaluation output. No catalog formula or approval changes, migrations, dependencies, UI changes, or frozen reference edits.

Do not claim all cross-domain cases fixed by this slice. Derived aggregate joins require lineage and uniqueness validation before execution. Preserve conservative refusal until that proof exists. Provider quotas and absent historical observations are separate from interpretation defects.
