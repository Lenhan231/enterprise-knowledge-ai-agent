# Completed SQL benchmark

Published 2026-11-04. The full after cohort measures application revision `153e5d5e8684e742fffdd7e464bf5848be555931`, not subsequent fixes on QuocAn. The before cohort is `../sql-semantic-refactor-2026-11-03/combined/sql_analytics/`.

| Measure | Before | After |
|---|---:|---:|
| Execution accuracy | 13/28 (46.4%) | 20/28 (71.4%) |
| SQL semantic equivalence | 5/28 (17.9%) | 6/28 (21.4%) |
| Numerical accuracy, inherited scorer mean | 44.8% (27 scored) | 69.2% (26 scored) |
| Requests executing SQL, including empty results | 17/30 | 23/30 |
| Latest-attempt provider failures | 9/30 | 0/30 |
| Request latency p50 / p95 | 2.223s / 22.110s | 2.420s / 7.467s |

All 30 questions have final attempts and all 90 current metric records are present, with zero evaluator errors or pending scores. Failed historical attempts remain in the append-only generation and scoring files. Provider retries affect this comparison: the improvement cannot be attributed entirely to semantic changes. Latencies describe final attempts, include in-request waits, and exclude between-request pacing.

Scoring uses Ragas with the unchanged `CodexCLIJudge`, `gpt-5.6-luna`, medium reasoning configuration. Questions and references are frozen; exact hashes, model configuration and source reproduction metadata are in [final/manifest.json](final/manifest.json). Numerical applicability follows the inherited scorer and therefore differs across runs; the percentages are not a fixed-denominator paired comparison.

Raw SQL generations and metric records are in [final/sql_analytics/](final/sql_analytics/). Machine-readable aggregate results are in [final/comparison.json](final/comparison.json); its Report entries are incomplete historical context, not a completed Report evaluation.

## Remaining limitations

Semantic equivalence remains low. Five final cases requested clarification (S13, S14, S25, S29, S30), and two failed SQL validation (S23, S28). S30 needs unavailable supplier data; S13, S14 and S25 are unnecessary clarifications or capability limitations. S29 safely avoids claiming current inventory but gives an inadequate explanation. The unsupported-case clarification count must not be reported as a verified valid-refusal rate.

Later fixes and read-only conformance checks are documented in [AUDIT.md](AUDIT.md). Their checks are separate from this full cohort and do not establish improved benchmark scores for the latest revision. Report work remains paused until the SQL follow-up is finished. The full repository test suite still has existing failures; this publication does not claim a green full suite or completed latest-revision evaluation.
