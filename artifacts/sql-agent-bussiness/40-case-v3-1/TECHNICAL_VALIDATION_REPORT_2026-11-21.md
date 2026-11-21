# SQL Agent benchmark v3.1 technical validation

**Status:** technical validation run complete with disclosed test failures. Ready for independent human review. Not frozen. The 40-case SQL Agent cohort was not executed.

## Revision and scope

- Branch: `benchmark/v3-1-output-contract-20261121`
- Application revision: `a7dc1150ba86182923a1aaed56c654d5597a714a`
- Python used by the repository environment: 3.11.16
- No production writes and no 40-case Agent calls occurred.
- The five-case pilot is development evidence separate from the v3.1 40-case cohort.

## Root causes and disposition

| Area | Cause / evidence | Disposition |
|---|---|---|
| P02 delivered population | A prior answerable query omitted `order_status = 'delivered'`. The semantic population validator blocked it. The generation prompt now carries authoritative population filters (`src/core/agents/sql/text_to_sql.py`); the bounded repair receives the exact missing population contract. Mocked tests cover successful repair and exhausted repair without execution (`tests/sql/test_sql_agent_flow.py`). | Fresh pilot P02 executed with the delivered filter and matched Gold rows. The 40-case population mutation was rejected by the population validator. |
| P05 unsupported dimensions | Approved schema has no warehouse, supplier, or lead-time fields. Returning model clarification options had previously failed response validation. `SQLAnalyticsAgent.run_payload()` now detects unavailable dimensions and returns a schema-grounded unsupported response before SQL execution (`src/core/agents/sql/agent.py`). | Fresh pilot P05 returned a safe unsupported result, with no SQL or execution. Existing integrated tests cover the missing dimensions. |
| Semantic scorer trust | The v3 scorer accepted an observation's `sql_semantic_valid` boolean as the semantic oracle. | The versioned v3.1 scorer ignores that boolean and requires one audit record linked to the observed SQL, parameters, case contract, and case set. Missing, duplicate, or mismatched records become `INDETERMINATE`. The linkage does not authenticate reviewer identity or replace human review. |
| Ranking vs output order | Unordered row-multiset comparison could hide a wrong ranking direction when the selected rows happen to tie on this database. B40-005 also has an unordered one-row output but still requires correct TOP-1 selection. | `semantic_audit_v3_1.py` checks explicit order keys, directions, tie-breaks, and TOP-N with SQLGlot. Across 30 Gold queries, 8 ranking/TOP-N obligations passed and 22 cases correctly required no ordering check. This AST check is not a full semantic audit. |
| P02 calendar-year equivalence | P02 uses `EXTRACT(YEAR FROM order_date) = 2025`; Gold uses a half-open date range. | Fresh preflight verified `commerce.orders.order_date` is PostgreSQL `date`. Scorer tests accept the equivalent DATE expression and reject unsafe equivalence assumptions for timestamp types or wrong ranges. The missing delivered predicate remains independently required. |
| Historical v3 checklist digest | The immutable v3 manifest records checklist digest `0aa3f33211a0c696a305928f78c4e7c599a53fe7e906a08a0cc43662e234066c`; current checklist digest is `117b75d2477f3fa1c8519ed0d6c3825a1fb5861bb4b1c667e65cc0bb22540fdf`. | Preserved both historical bytes and manifest. The old artifact test's digest mismatch is reported; the archived manifest was not rewritten. |

## Read-only 40-case reference and mutations

Preflight at `2026-11-21T11:47:16Z` returned `VERIFIED_READ_ONLY_PREFLIGHT`, verified the host allowlist and least-privilege role, and reproduced fingerprint `dbc14b99acc2920ffaeb4190ba45708982c971f0671b0b9e8114b595f2594028`. The value matches the provisional references. Snapshot evidence includes 15 tables, 47 inventory snapshots, no warehouse dimension, and no supplier/lead-time fields.

The repository-approved generator executed 30 Gold queries against the frozen snapshot. All 30 matched the provisional SQL/parameters/columns/rows exactly: 404 rows total, zero query failures, zero database writes, zero SQL Agent calls. The output remains provisional, with zero human approvals.

All 28 valid mutations were executed through the approved read-only repository. Result-based detection was **23/26 (88.46%)**; three valid variants were observationally equivalent on this snapshot:

- `M008-01-missing-nonnull-filter`
- `M023-03-missing-common-product-condition`
- `M029-02-wrong-ranking-direction`

The ranking AST regression separately rejects the M029 wrong direction even when its rows happen to match. Approved-join, join-fanout, and population-contract validator probes each detected 1/1 assigned mutations. These results are not human semantic approval.

Evidence files:

- [Read-only preflight](database_preflight_v3_1_20261121T114601Z.json)
- [Gold rerun](runs/technical-validation-v3-1-20261121T114601Z/gold_results_v3_1_rerun.json)
- [Mutation rerun](runs/technical-validation-v3-1-20261121T114601Z/mutation_results_v3_1_rerun.json)
- [Draft manifest](FREEZE_MANIFEST_V3_1_DRAFT.json)

## Fresh five-case development pilot

The archived P01–P05 case hash was `ddade2d597b30a6bb4c74fc7b997dfe9a617e6c5348cd8b64bf7016463d100c4`; the reference hash was `295c53652e5fe3a7fc8c3c35cffb9ecf4f6bc23e44b6db861955e369d0932a17`. The new run used application revision `a7dc1150ba86182923a1aaed56c654d5597a714a`, source fingerprint `5feb222132233fa2bd8ee010eac42b804a64bb0d0f13ad80b7252c3b0728a57d`, SQL prompt hash `cf1829c735a357a9bff55bd04d649ad807cb2bbdff134da36542d73371144e60`, and the same frozen read-only database fingerprint.

Provider configuration: Groq `openai/gpt-oss-20b`; schema selector `perplexity/pplx-decider-flash-v1.3:free`; repair budget 1. Worktree was dirty due only to benchmark evidence/docs/tests and is recorded as such in the run manifest. P03 used one local Codex SQL-generation fallback, so this is end-to-end SQL Agent evidence, not a single-SQL-LLM comparison. No secondary SQL provider fallback occurred.

| Case | Historical clean pilot | Fresh run | Evidence |
|---|---|---|---|
| P01 | PASS | PASS | Executed; business rows match. |
| P02 | FAIL | PASS | `order_status = 'delivered'` retained; calendar-year expression accepted for verified DATE; business rows match. |
| P03 | PASS | PASS | Executed; one local Codex SQL-generation fallback. |
| P04 | PASS | PASS | Executed; business rows match. |
| P05 | FAIL | PASS | Safe schema-grounded unsupported result; no SQL execution. |

| Metric | Historical protocol 1.1.2 / scorer 2.0.2 | Fresh protocol 1.2.0 / scorer 2.1.0 |
|---|---:|---:|
| Supported business end-to-end | 3/4 (75%) | 4/4 (100%) |
| SQL semantic accuracy | 3/4 (75%) | 4/4 (100%) |
| Business result accuracy | 3/3 (100%) | 4/4 (100%) |
| Strict result exact match | 1/4 (25%) | 2/4 (50%) |
| Valid unsupported abstention | 0/1 (0%) | 1/1 (100%) |
| Repair recovery | 0/1 (0%) | 0/0 (not measurable) |
| Schema selector raw Recall@5 | 0/0 (not measurable; historical JEV HTTP 402) | 4/4, 3 applicable cases |
| Unsafe executions | 0 | 0 |

These are descriptive before/after observations, not a causal estimate: protocol/scorer, selector, model settings, and source revision differ. The new run's Recall@5 is from the alternate Perplexity selector, not JEV. JEV remains unmeasured; the earlier HTTP 402 was retained as an external provider blocker without inferring its cause. The run made 7 total model calls: 2 SQL provider submissions, 1 metric interpretation submission, 3 schema-selection requests, and 1 local Codex fallback. Repair calls were 0. P50/P95 request latency was 9,746/48,435 ms.

P02's live provider SQL used inline constants (`'delivered'` and year `2025`) with an empty parameter list. It passed semantic validation and matched the Gold result on this frozen case. The bounded-repair regression uses bound parameters; this one live response does not establish that providers always follow the parameterized style.

Run evidence: [per-case SQL and provenance](../runs/pilot5-pr61-a7dc115-20261121T131000Z/data.json), [scores](../runs/pilot5-pr61-a7dc115-20261121T131000Z/scores.json), and [report](../runs/pilot5-pr61-a7dc115-20261121T131000Z/report.md). The pilot scorer is v2.1.0 and does not use the new v3.1 independent-audit gate; do not mix its semantic score with a future independently audited 40-case score.

## Test execution

Commands were run in the repository's Python 3.11.16 environment (`uv run --project /home/lenhanm1/orca/workspaces/enterprise-knowledge-ai-agent/main --no-sync`).

| Command | Result |
|---|---|
| `PYTHONPATH=src uv run --project /home/lenhanm1/orca/workspaces/enterprise-knowledge-ai-agent/main --no-sync python -m unittest discover -s tests/sql -p 'test_benchmark_v3_1_contract.py' -v` | PASS: 21 run, 21 passed. |
| `PYTHONPATH=src uv run --project /home/lenhanm1/orca/workspaces/enterprise-knowledge-ai-agent/main --no-sync python -m unittest discover -s artifacts/sql-agent-bussiness/tests -v` | PASS: 45 run, 45 passed. |
| `PYTHONPATH=src uv run --project /home/lenhanm1/orca/workspaces/enterprise-knowledge-ai-agent/main --no-sync python -m unittest discover -s tests/sql -q` | PASS: 544 run, 534 passed, 10 skipped. |
| `PYTHONPATH=/home/lenhanm1/orca/workspaces/enterprise-knowledge-ai-agent/pr61-validation-20261121/src:/home/lenhanm1/orca/workspaces/enterprise-knowledge-ai-agent/pr61-validation-20261121/artifacts/sql-agent-bussiness/40-case-preparation uv run --project /home/lenhanm1/orca/workspaces/enterprise-knowledge-ai-agent/main --no-sync python -m unittest discover -s artifacts/sql-agent-bussiness/40-case-v3 -p 'test_*.py' -v` | FAIL: 55 run, 54 passed; one preserved manifest checksum mismatch for `REVIEW_CHECKLIST.md` (expected `0aa3…`, actual `117b…`). |
| `PYTHONPATH=src uv run --project /home/lenhanm1/orca/workspaces/enterprise-knowledge-ai-agent/main --no-sync python -m unittest discover -s tests -t . -q` | FAIL: 1,611 run, 1,530 passed, 80 skipped, 1 error. `tests.documents.test_document_formats.DocumentFormatTest.test_heic_heif_and_avif_decode_with_the_configured_runtime` HEIF fixture-encoding subprocess exited nonzero (`CalledProcessError` from `PIL.Image.save(..., format='HEIF')`). This is outside SQL/benchmark code. |

`PYTHONPATH=src uv run --project /home/lenhanm1/orca/workspaces/enterprise-knowledge-ai-agent/main --no-sync python -m py_compile artifacts/sql-agent-bussiness/40-case-v3-1/semantic_audit_v3_1.py artifacts/sql-agent-bussiness/40-case-v3-1/scorer_v3_1.py artifacts/sql-agent-bussiness/40-case-v3-1/generate_gold_results_v3_1.py artifacts/sql-agent-bussiness/40-case-v3-1/run_mutation_probes_v3_1.py tests/sql/test_benchmark_v3_1_contract.py` passed. JSON parsing passed for the six v3.1 manifest/preflight/Gold/mutation and pilot data/score files. `git diff --check` passed. The v3 historical checksum and HEIF test failures are not hidden or counted as passes.

## Review and execution gates

- `TECHNICAL_VALIDATION_COMPLETE = YES_WITH_DISCLOSED_TEST_FAILURES` — the read-only data, Gold, mutation, scorer, ranking, pilot, and SQL-agent validations ran; the two test failures above remain visible.
- `READY_FOR_INDEPENDENT_HUMAN_REVIEW = YES` — the v3.1 candidate, hashes, Gold, results, and limitations are packaged for review.
- `READY_FOR_40_CASE_GOLD_PREPARATION = YES` — proceed with two independent semantic reviews and adjudication of these exact candidate hashes.
- `READY_FOR_FREEZE = NO` — zero independent approvals; adjudication and test follow-up remain.
- `READY_FOR_40_CASE_EXECUTION = NO` — do not execute the 40-case Agent cohort until independent review and formal freeze.

The v3.1 case set remains a draft. No original v2/v3 evidence was overwritten.
