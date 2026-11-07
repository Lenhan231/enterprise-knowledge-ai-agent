# E5 neighbor context: fixed-budget ablation

Shared evidence v2, unchanged saved dense vectors; 80 cases reuse 20 paired intents. Not an encoder or generation benchmark. Exact source-provenance coverage; Q14 excluded from full-intent rate.

## Vietnamese queries → Vietnamese documents

Full-evidence counts are out of 19; component counts are out of 61. Budgets count the exact rendered context using the E5 tokenizer, not an LLM tokenizer. Uncapped dense10 is diagnostic only.

| Strategy | Budget | Complete intents | Components | Mean context tokens | Mean chunks |
|---|---:|---:|---:|---:|---:|
| dense10_uncapped | uncapped | 17/19 | 57/61 | 2417 | 10.0 |
| dense10_2048 | 2048 | 16/19 | 55/61 | 1922 | 8.1 |
| dense30_2048 | 2048 | 16/19 | 55/61 | 1995 | 8.6 |
| neighbors_2048 | 2048 | 13/19 | 52/61 | 2013 | 9.8 |
| dense10_4096 | 4096 | 17/19 | 57/61 | 2417 | 10.0 |
| dense30_4096 | 4096 | 18/19 | 59/61 | 4043 | 16.9 |
| neighbors_4096 | 4096 | 17/19 | 57/61 | 4022 | 17.9 |

## Four directions: complete-evidence counts /19

| Variant | VI→VI | EN→EN | VI→EN | EN→VI |
|---|---:|---:|---:|---:|
| dense10_uncapped | 17 | 14 | 9 | 12 |
| dense10_2048 | 16 | 12 | 9 | 12 |
| dense30_2048 | 16 | 13 | 9 | 12 |
| neighbors_2048 | 13 | 12 | 8 | 8 |
| dense10_4096 | 17 | 14 | 9 | 12 |
| dense30_4096 | 18 | 17 | 11 | 13 |
| neighbors_4096 | 17 | 15 | 9 | 12 |

## Vietnamese regressions and gains vs same-budget dense10

- dense30, 2048: gained none; lost none.
- neighbors, 2048: gained Q13-vi-to-vi; lost Q07-vi-to-vi, Q12-vi-to-vi, Q16-vi-to-vi, Q17-vi-to-vi.
- dense30, 4096: gained Q20-vi-to-vi; lost none.
- neighbors, 4096: gained Q13-vi-to-vi; lost Q11-vi-to-vi.

## Vietnamese vs English question token counts

Same 20 question intents, raw text without model prefixes/instructions/special tokens. Translation length and tokenizer both affect the ratio; no universal Vietnamese multiplier or conversational-model billing claim.

| Tokenizer | VI total | EN total | VI/EN |
|---|---:|---:|---:|
| multilingual-e5-base | 549 | 553 | 0.99× |
| bge-m3 | 549 | 553 | 0.99× |
| qwen3-embedding-0.6b | 578 | 500 | 1.16× |

## Method and limits

Neighbors: each top10 seed then previous and next final chunk in same document/language and ACL; deduplicate; skip whole candidates that do not fit. No partial chunks or gold-label selection.

Planning/tokenization only, excludes embedding/DB/network/generation and evidence scoring. Does not estimate end-to-end latency.

Exploratory post-hoc fixed-budget ablation on 20 paired intents/80 cases; Q14 full-intent excluded. Context evidence coverage can use >10 chunks and is not Recall@10. No generation quality/cost measured. All policy variants predeclared before results, unchanged vectors. Context tokens are not encoder input length and can exceed 512.

Neighbor chunk_index adjacency follows frozen parser serialization, which can separate extracted tables from prose. It is not guaranteed physical page/row adjacency. Production expansion needs persisted document order and ACL/ready/company filters; this offline snapshot cannot validate current database permissions. No production or database changes; old benchmark artifacts unchanged.
