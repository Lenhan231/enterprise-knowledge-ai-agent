# SQL Agent benchmark rerun with follow-up context

Application revision `8649a7eb3576f8b8d3b68a8377fb2b688c6eb31b` completed all 40 frozen cases. The original case set, Gold SQL, Gold rows, read-only database fingerprint, SQL provider chain, schema selector, pacing, package versions, and v3.3.0 scorer matched Nhan’s official run. This rerun restored the five follow-up inputs, so a change in score against the published run includes both the runner correction and the agent changes.

| Metric | Nhan’s original run | Updated agent with corrected runner |
|---|---:|---:|
| Business end-to-end accuracy | 10/30 (33.3%) | 14/30 (46.7%) |
| SQL semantic accuracy | 14/30 (46.7%) | 22/30 (73.3%) |
| Business result accuracy among executed supported cases | 11/20 (55.0%) | 16/26 (61.5%) |
| Output contract compliance among executed supported cases | 13/20 (65.0%) | 17/26 (65.4%) |
| Valid clarification or abstention | 8/10 (80.0%) | 6/10 (60.0%) |
| Unsafe executions | 0 | 0 |

All five follow-ups recorded their context and prior-turn hashes and executed SQL.

| Case | Result |
|---|---|
| B40-026 | Correct 2024 COGS calculation, with all 12 rows equal after extracting the date from the UTC-midnight month timestamp. The unchanged scorer marks the literal result as a mismatch. |
| B40-027 | Business end-to-end pass. The query carried forward 2025 and narrowed the population to delivered orders. |
| B40-028 | Fail. The year-over-year query joined month-start timestamps across different years and omitted the requested difference. |
| B40-029 | Business end-to-end pass. The query carried forward the 2024 returns scope and applied top two and the requested tie-break. |
| B40-030 | Required rows match. The additional `days_of_supply` field needs output-safety review, so the end-to-end score stays `REVIEW_REQUIRED`. |

B40-001 and B40-004 also matched all frozen rows after converting exact UTC-midnight month timestamps to dates. The official scores retain the literal comparisons. The run recorded one security-validated unverified execution (B40-023), zero SQL-provider fallback calls, and zero local Codex fallback calls.

The SQL and output-safety review records are AI-assisted and unauthenticated. They are linked to the exact observed SQL and frozen case contracts. The active runner’s execution-time SHA-256 is recorded in [data.json](data.json). Its Git blob is `ff789d4dacd18a6f171235d26f9d28176e248795` in this local repository. The subsequent one-line runner change added the SQL contract test to historical hash validation. Case execution and scoring behavior remained the same.

See [the full report](report.md), [machine-readable scores](scores.json), and [raw observations](data.json).
