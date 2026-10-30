# Inventory metric dictionary implementation

The user approved the capability map and conventions with scope restricted to Inventory Management. Existing preflight evidence/benchmarks are retained as historical records; only inventory cases contribute to the scoped comparison.

- [ ] metric-catalog: add the versioned inventory-only catalog, validate its schema and load it through the existing ontology; test bilingual/plural resolution and unresolved entries; commit.
- [ ] metric-enforcement: prove snapshot scope and approved formulas/dimensions, fix stored fill-rate ranking and targeted clarifications, carry historical dates and definition metadata; run focused safety/calculation regressions; commit.
- [ ] metric-evaluation: preserve Report generation and propagate inventory metric context, freeze an inventory-only before benchmark from the original commit, replay before plans and run unchanged-model after cases, compare deterministic correctness and latency; run existing tests/full discovery and record limitations; commit.

No new sales, finance, customer, returns or marketing definitions. Product identity/category/segment and inventory source consistency checks remain supporting inventory context. Unrelated existing functionality is preserved.
