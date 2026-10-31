# Capability map: Inventory Management metric dictionary

Status: user approved the module map and inventory conventions, with all new domain work restricted to Inventory Management.

| Module id | Responsibility | Depends on |
| --- | --- | --- |
| metric-catalog | Versioned inventory YAML catalog, provenance/governance validation and unresolved inventory candidates | none |
| metric-enforcement | Existing ontology integration; typed semantic interpretation, bilingual aliases, formulas, dimensions, grain, snapshot scope and targeted clarification | metric-catalog |
| metric-evaluation | Deterministic inventory regressions, unchanged-model benchmarks, minimal Report metadata compatibility and documentation | metric-enforcement |

Build order: metric-catalog -> metric-enforcement -> metric-evaluation. These are review boundaries, not new runtime services.

Specifications: [catalog](SPEC-metric-catalog.md), [enforcement](SPEC-metric-enforcement.md), [evaluation](SPEC-metric-evaluation.md). Execution plan: [inventory tasks](tasks/inventory-metric-dictionary-plan.md). The existing tasks/plan.md is preserved.

## Approved scope

- Historical stock; stored and mean stored fill rate; stockout share/days; days of supply; sell-through; inventory receipts and sales movement; recorded reorder/overstock indicators; observed SKU count and product inventory history.
- Product identity/category/segment/size/color support inventory grouping.
- Original fulfillment formula/weighting, operational reorder point/quantity, safety stock, accuracy and turnover remain unresolved when evidence is missing.
- Explicit dates or database-latest selection; historical limitations; missing rows are never zero; no combined balances across dates.
- Provenance, technical validation, team acceptance and official business-owner approval remain independent.
- No new sales/finance, customer, return, delivery or marketing definitions. Existing unrelated runtime behavior and immutable broad preflight evidence stay outside this scoped change.
- Preserve verified permissions, approved SQL restrictions, read-only execution, parameterization, result limits and Report generation.
