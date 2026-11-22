# Run evidence for the v3 evaluation

Raw outputs behind the numbers in the report: answer rows, scores, RAGAS results, retrieval runs and the experiment-12 load test.
`MANIFEST.json` lists the sha256 and size of every file here, so a copy can be checked against what the report used.

| Folder | What it holds |
|---|---|
| `answers/` | Answer rows from the production Knowledge path, per version and set |
| `exp1/` – `exp6/` | Retrieval experiments (chunking, embedders, dense extra, fusion weights, amount normalisation, reranker) |
| `exp12/` | Load test: 1, 2, 4 and 8 concurrent users (requests, samples, per-level summary) |
| `pool/` | Pooling candidates used to build the relevance labels |
| `ragas-modal/` | RAGAS metrics per version |
| `modal/` | Generation runs on the self-hosted copy of the same models, with `RESULTS-20261121.md` |

Progress logs (`*.log`) are not kept, by the repository rule; they hold no results.
