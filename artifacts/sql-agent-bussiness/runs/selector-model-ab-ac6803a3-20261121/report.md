# SQL Schema Selector A/B Pilot

Application revision: `ac6803a368d36154ae3a1dfba8a969dc19be93d0`
Protocol/scorer: `1.2.0` / `2.1.0`
Case-set SHA-256: `ddade2d597b30a6bb4c74fc7b997dfe9a617e6c5348cd8b64bf7016463d100c4`
Reference SHA-256: `295c53652e5fe3a7fc8c3c35cffb9ecf4f6bc23e44b6db861955e369d0932a17`
Frozen snapshot SHA-256: `dbc14b99acc2920ffaeb4190ba45708982c971f0671b0b9e8114b595f2594028`
Read-only role verified: `True`
Same SQL-generation provider/model and repair budget: `groq / openai/gpt-oss-20b`; budget `1`

## Results

| Metric | Decider Flash | Decider 1.3 |
|---|---:|---:|
| Business E2E | 4/4 (100%) | 4/4 (100%) |
| Business result | 4/4 (100%) | 4/4 (100%) |
| SQL semantic | 4/4 (100%) | 4/4 (100%) |
| Strict exact | 2/4 (50%) | 2/4 (50%) |
| Unsupported abstention | 1/1 (100%) | 1/1 (100%) |
| Selector raw Recall@5 | 4/4 (100%) | 4/4 (100%) |
| Selector successes | 3/3 | 3/3 |
| SQL-generation entries | 2 | 2 |
| Local Codex SQL fallback | 1 | 1 |
| Repository executions | 4 | 4 |
| Unsafe executions | 0 | 0 |
| Latency p50 / p95 | 9964 / 20275 ms | 8313 / 40242 ms |

## Per-case selector outcomes

| Case | Flash candidates | Decider 1.3 candidates | Selection |
|---|---|---|---|
| P02 | commerce.customers, commerce.geography, commerce.order_items, commerce.orders, commerce.shipments | commerce.customers, commerce.geography, commerce.order_items, commerce.orders, commerce.shipments | identical |
| P03 | commerce.inventory, commerce.order_items, commerce.orders, commerce.products, commerce.shipments | commerce.inventory, commerce.order_items, commerce.orders, commerce.products, commerce.shipments | identical |
| P04 | commerce.inventory, commerce.order_items, commerce.products, commerce.returns, commerce.reviews | commerce.inventory, commerce.order_items, commerce.products, commerce.returns, commerce.reviews | identical |

## Interpretation

The models tied on this pilot: all three schema-selection candidate lists matched exactly, and both achieved raw Recall@5 of 4/4. They also produced the same aggregate business and SQL-semantic scores. This is not enough evidence to select a winner: only three questions called the selector, and this cohort was not designed as a held-out model benchmark.

Latency is noisy at this size. Decider 1.3 had a higher P95, driven by P03; each run also used one local Codex SQL-generation fallback, whose exact model identity is not captured. These results compare the SQL Agent pipeline with a different schema selector, not isolated SQL-generation model quality.

No 40-case cohort was executed. Keep JEV route classification separate; this A/B changes only the direct SQL schema-selection model.

## Run artifacts

- Flash: [`pilot5-selector-flash-ac6803a368d3-20261121T033000Z/experiment/report.md`](../pilot5-selector-flash-ac6803a368d3-20261121T033000Z/experiment/report.md)
- Decider 1.3: [`pilot5-selector-decider13-ac6803a368d3-20261121T033000Z/experiment/report.md`](../pilot5-selector-decider13-ac6803a368d3-20261121T033000Z/experiment/report.md)
- Machine-readable comparison: `comparison.json`
