# VietStyle dense baseline — 2026-10-18

Model: `sentence-transformers/all-MiniLM-L6-v2`, revision `1110a243fdf4706b3f48f1d95db1a4f5529b4d41`, encoder limit 512, device cuda:0.

Scope: five VietStyle files, 532 unchanged indexed chunks, 20 Vietnamese questions, top 10 chunks. Live text/metadata/roles and vectors exactly matched the frozen snapshots. Read-only database transaction; no translation, answer generation, or paid API calls.

| Metric | Result |
| --- | ---: |
| Mean expected-source recall@10 | 80.00% |
| Cases with every expected source found | 10/20 |
| Mean retrieval latency | 523.7 ms |
| Median retrieval latency | 324.5 ms |
| Available-source ceiling (README missing) | 95.00% |

Source recall counts expected file names appearing in the top 10 chunks; it is not chunk relevance or answer accuracy. README.txt remains unavailable for Q01/Q18/Q19 and stays in the denominator. Latency includes query embedding and search, excludes model loading, and is a single run. Historical An scores use different data/chunks/model/settings and are not a controlled comparison.

| Case | Source recall@10 | Missing expected sources |
| --- | ---: | --- |
| Q01 | 33.33% | 03_Policy_Rules_Registry.csv, README.txt |
| Q02 | 100.00% | None |
| Q03 | 100.00% | None |
| Q04 | 100.00% | None |
| Q05 | 50.00% | 03_Policy_Rules_Registry.csv |
| Q06 | 100.00% | None |
| Q07 | 66.67% | 03_Policy_Rules_Registry.csv |
| Q08 | 66.67% | 03_Policy_Rules_Registry.csv |
| Q09 | 100.00% | None |
| Q10 | 100.00% | None |
| Q11 | 100.00% | None |
| Q12 | 66.67% | 03_Policy_Rules_Registry.csv |
| Q13 | 100.00% | None |
| Q14 | 100.00% | None |
| Q15 | 100.00% | None |
| Q16 | 66.67% | 03_Policy_Rules_Registry.csv |
| Q17 | 50.00% | 03_Policy_Rules_Registry.csv |
| Q18 | 66.67% | README.txt |
| Q19 | 66.67% | README.txt |
| Q20 | 66.67% | 03_Policy_Rules_Registry.csv |

## Code change

Before: the existing two-report runner hardcodes PVFCCo/Long Hau IDs and gold chunk labels. It cannot directly evaluate VietStyle source-file labels.

After: added `scripts/retrieval/evaluate_vietstyle_dense.py`. It validates the frozen corpus/vector hashes and model revision/limit, then calls the existing RetrievalService with method=dense and the five document IDs. Production retrieval code and Supabase data were unchanged in this run.

Verification: all 20 saved scores were independently recomputed from returned source names, all 200 contexts stayed inside scope, and every case returned ten chunks.

Reproduce:

```bash
.venv/bin/python scripts/retrieval/evaluate_vietstyle_dense.py \
  --snapshot artifacts/evaluation/embedding-comparison-20261018 \
  --output artifacts/evaluation/embedding-comparison-20261018/dense-baseline.json
```
