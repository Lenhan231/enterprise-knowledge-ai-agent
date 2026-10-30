# Capability map: VietStyle business metric dictionary

Status: proposed; awaiting human review under the invoked spec-driven-development skill. No module specification or application implementation has been started.

| Module id | Responsibility | Depends on |
| --- | --- | --- |
| metric-catalog | One versioned YAML catalog, explicit provenance and governance fields, schema validation, supported definitions and unresolved candidates | — |
| metric-enforcement | Load that catalog through the existing ontology; resolve English/Vietnamese aliases; enforce formulas, dimensions, grain and temporal scope; return safe clarifications | metric-catalog |
| metric-evaluation | Deterministic calculation/safety regressions, unchanged-model SQL benchmark comparison, validation report and documented assumptions | metric-enforcement |

Build order: metric-catalog → metric-enforcement → metric-evaluation.

These are review boundaries, not new runtime services. Keep the current SQL Agent, AST safety checks, join checks, verified authorization, CommerceRepository and Report generation path. The catalog is the only metric-definition source; METRIC_ONTOLOGY may remain a derived compatibility mapping.

The detailed user task supplies the initiative requirements. Each module specification will trace to this map after its boundaries are reviewed; the existing task and report documentation will not be overwritten.

## Initial assumptions to review

- Team-defined executable metrics require an explicit capstone acceptance status; this is distinct from business-owner approval and never implied by a passing calculation.
- Daily, monthly and yearly rollups share one net-order-value definition and its declared date field; they are not separate formulas.
- Separate source daily revenue, net order-item value and recorded payment value. Observed equality is evidence of reconciliation, not semantic equivalence.
- Explicitly named net order-item value uses quantity × historical unit_price − line discount, across all placed-order statuses unless a separately named status-filtered definition is requested. It is not collected cash or statutory net revenue.
- Bare revenue/sales, unspecified return rate and underspecified inventory dates receive targeted clarification where context does not choose a definition safely.
- A stored SKU fill-rate value and a team-defined unweighted mean of stored values are separate metrics. Do not reconstruct the original fulfillment formula or weighting method.
- Return-rate candidates declare order/unit denominator, order-date cohort, eligible statuses, observed-return cutoff and duplicate treatment. Category order denominators are non-additive. No implicit order/unit choice.
- Unknown currency remains unknown. Snapshot answers are historical and dated; absent rows are not zero.
- Unsupported attribution, conversion, true period-unique visitors and source-unexplained measures stay unresolved. Source_defined requires explicit source documentation, not a field name or successful query.

## Existing evidence

See [the inspection and proposal](docs/business_metric_dictionary.md) and [preflight artifacts](artifacts/evaluation/vietstyle-metrics-v1/preflight/). Existing application code and model configuration remain unchanged.
