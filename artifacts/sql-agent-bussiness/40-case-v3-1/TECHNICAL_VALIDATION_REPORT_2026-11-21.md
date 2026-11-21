# SQL Agent benchmark v3.1 technical validation

**Status:** technical validation run complete with disclosed test failures. Reviewer 1 and a user-reported Reviewer 2 record each cover 40/40 approvals; adjudication remains pending. Not frozen. The 40-case SQL Agent cohort was not executed.

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

The repository-approved generator executed 30 Gold queries against the frozen snapshot. All 30 matched the provisional SQL/parameters/columns/rows exactly: 404 rows total, zero query failures, zero database writes, zero SQL Agent calls. At that execution time there were no human approvals; the later review record is listed below. The output remains provisional.

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
| `PYTHONPATH=src uv run --project /home/lenhanm1/orca/workspaces/enterprise-knowledge-ai-agent/main --no-sync python -m unittest discover -s tests/sql -p 'test_benchmark_v3_1_contract.py' -v` | PASS: 23 run, 23 passed (includes the archived-checklist provenance and review-record hash/freeze-gate regressions). |
| `PYTHONPATH=src uv run --project /home/lenhanm1/orca/workspaces/enterprise-knowledge-ai-agent/main --no-sync python -m unittest discover -s artifacts/sql-agent-bussiness/tests -v` | PASS: 45 run, 45 passed. |
| `PYTHONPATH=src uv run --project /home/lenhanm1/orca/workspaces/enterprise-knowledge-ai-agent/main --no-sync python -m unittest discover -s tests/sql -q` | PASS: 544 run, 534 passed, 10 skipped. |
| `PYTHONPATH=/home/lenhanm1/orca/workspaces/enterprise-knowledge-ai-agent/pr61-validation-20261121/src:/home/lenhanm1/orca/workspaces/enterprise-knowledge-ai-agent/pr61-validation-20261121/artifacts/sql-agent-bussiness/40-case-preparation uv run --project /home/lenhanm1/orca/workspaces/enterprise-knowledge-ai-agent/main --no-sync python -m unittest discover -s artifacts/sql-agent-bussiness/40-case-v3 -p 'test_*.py' -v` | FAIL: 55 run, 54 passed; one preserved manifest checksum mismatch for `REVIEW_CHECKLIST.md` (expected `0aa3…`, actual `117b…`). |
| `PYTHONPATH=src uv run --project /home/lenhanm1/orca/workspaces/enterprise-knowledge-ai-agent/main --no-sync python -m unittest discover -s tests -t . -q` | FAIL: 1,611 run, 1,530 passed, 80 skipped, 1 error. `tests.documents.test_document_formats.DocumentFormatTest.test_heic_heif_and_avif_decode_with_the_configured_runtime` HEIF fixture-encoding subprocess exited nonzero (`CalledProcessError` from `PIL.Image.save(..., format='HEIF')`). This is outside SQL/benchmark code. |

`PYTHONPATH=src uv run --project /home/lenhanm1/orca/workspaces/enterprise-knowledge-ai-agent/main --no-sync python -m py_compile artifacts/sql-agent-bussiness/40-case-v3-1/semantic_audit_v3_1.py artifacts/sql-agent-bussiness/40-case-v3-1/scorer_v3_1.py artifacts/sql-agent-bussiness/40-case-v3-1/generate_gold_results_v3_1.py artifacts/sql-agent-bussiness/40-case-v3-1/run_mutation_probes_v3_1.py tests/sql/test_benchmark_v3_1_contract.py` passed. JSON parsing passed for the six v3.1 manifest/preflight/Gold/mutation and pilot data/score files. `git diff --check` passed. The v3 historical checksum and HEIF test failures are not hidden or counted as passes.

For the review-record regression, an initial run against the worktree-local `.venv` stopped at test import because that environment lacked `sqlglot`; rerunning with the repository's existing Python environment (`--project .../main --no-sync`) executed the suite successfully. This was an environment setup failure, not a test assertion failure.

## Review and execution gates

- `TECHNICAL_VALIDATION_COMPLETE = YES_WITH_DISCLOSED_TEST_FAILURES` — the read-only data, Gold, mutation, scorer, ranking, pilot, and SQL-agent validations ran; the two test failures above remain visible.
- `REVIEWER_1_APPROVAL_RECORD = 40/40 APPROVE` — see [review record](review_v3_1_reviewer_1_Lenhan231_complete.json), bound to the exact case/Gold/result hashes. The user confirmed that all 40 cases had been reviewed in the browser UI, but the page produced no recoverable export. This JSON records that confirmation; its timestamp is the artifact logging time, not the original review time, and per-case rationales were not supplied.
- `REVIEWER_2_APPROVAL_RECORD = 40/40 APPROVE (USER-REPORTED)` — see [review record](review_v3_1_reviewer_2_user_reported_complete.json), bound to the same exact hashes. The user reports that their friend approved all 40 before the HTML reset. No direct export, actual reviewer identity, original timestamps, or rationales were available; the synthetic reviewer ID is not identity proof.
- `HUMAN_REVIEW_RECORDS = TWO_40_OF_40_APPROVALS` — Reviewer 1 is directly user-confirmed; Reviewer 2 is user-reported as a separate friend. The second identity and direct export are not independently verifiable from this artifact.
- `READY_FOR_40_CASE_GOLD_PREPARATION = YES` — both review records are present; proceed with adjudication and final Gold preparation for these exact candidate hashes.
- `READY_FOR_FREEZE = NO` — both approval records are logged; adjudication and test follow-up remain.
- `READY_FOR_40_CASE_EXECUTION = NO` — do not execute the 40-case Agent cohort until independent review and formal freeze.

The v3.1 case set remains a draft. No original v2/v3 evidence was overwritten.

## Review logging and UI persistence note

The user confirmed that all 40 cases had already been reviewed and approved in the local HTML page, but no JSON export was retained. The page stores state only in that browser's `localStorage`; it does not write to the repository or sync across browsers. Reviewer 1's 40/40 `APPROVE` record was logged at `2026-11-21T13:30:10Z`; this is the logging time, not the original review time. No per-case rationale or original timestamp was supplied.

The user later reported that a friend had also reviewed the same 40 cases and selected `APPROVE` for all before the HTML reset. Reviewer 2's 40/40 record was logged at `2026-11-21T13:56:13Z` with synthetic slot label `friend-of-Lenhan231`; the actual name/ID, export, original per-case timestamps, and rationales were not supplied. Both records are hash-bound to the exact v3.1 case, Gold SQL, and provisional result files. Reviewer 2's identity and independence are user-attested and not independently verifiable from this artifact. Adjudication remains pending, so the cohort stays unfrozen and unexecuted.

Regression: `test_recovered_reviewer_approval_is_linked_and_does_not_freeze_cohort` verifies both sets of 40 decisions, reviewer record hashes, source artifact hashes, pending adjudication, and no-freeze/no-execution gates.

## Scorer v3.2 addendum

This is a scoring-only revision for PR #61. It does not change `cases_v3_1_draft.json`, `gold_sql_v3_1_draft.json`, `gold_results_v3_1_provisional.json`, reviewer records, or historical v3/v3.1 run output. The case-set, Gold-definition, and Gold-results hashes therefore remain the values recorded in the draft manifest. The scorer/protocol version and their source hashes are new and recorded separately in `scoring_artifacts_sha256`.

Changes:

- Canonical columns align by case-insensitive exact name, case-approved alias, or identical SQLGlot projection expression with resolved relation/column lineage. Ambiguous lineage returns `REVIEW_REQUIRED`; unknown columns are not fuzzy-matched. Star-only aggregates do not establish a field alias.
- Business values compare independently of column order and row order. Explicit business keys are used only when declared; otherwise maximum bipartite multiset matching preserves duplicates and applies Decimal tolerance safely. NULL matches only NULL. Ordered-case row sequence is measured separately as output-contract compliance.
- Business Result Accuracy ignores unapproved extra output columns but compares all canonical values/rows. Output Contract Compliance fails for unapproved extras, missing/duplicate canonical fields, violated row limits, and incorrect ordered output. Business End-to-End Accuracy still requires a linked independent SQL audit PASS and both result/contract PASS.
- The audit exporter accepts reviewer-supplied decisions and requires non-empty evidence, auditor ID/version, exact case-set linkage, and observed SQL/parameters. Export time is not represented as original review time; output is explicitly unauthenticated and cannot establish reviewer identity or independence.

Sample scorer outcomes from deterministic synthetic fixtures:

| Fixture | Business Result | Output Contract | Reason |
|---|---|---|---|
| Reordered columns and approved alias | PASS | PASS | `strict_schema_match=false`; canonical field mapping is preserved. |
| Same resolved SQL projection under a different label | PASS | PASS | `canonical_column_mapping` binds the alias to Gold lineage. |
| One unknown label matches two Gold projections | REVIEW_REQUIRED | REVIEW_REQUIRED | `ambiguous_sql_projection_lineage`. |
| Correct required values plus an unapproved `trace_id` column | PASS | FAIL | `unexpected_extra_columns`. |
| NULL versus zero | FAIL | PASS for unordered output shape | `business_result_rows_mismatch`; NULL is not coerced. |
| Independent review rejects aggregation/grouping/JOIN/snapshot/NULL/alias mutation | Gold rows can still PASS | End-to-end FAIL | audit decision `FAIL` gates semantic success; Agent boolean is ignored. |

The v3.2 regression suite runs all 30 stored execute-case Gold result sets locally, without invoking the SQL Agent or re-querying the held-out cohort. This validates scorer compatibility with the provisional references; it is not a fresh database audit, reviewer approval, or 40-case Agent run.

Executed test evidence for the scorer v3.2 revision:

| Command | Result |
|---|---|
| `PYTHONPATH=src uv run --locked --project . python -m unittest discover -s tests/sql -p 'test_benchmark_v3_1_contract.py' -v` | PASS: 39 run, 39 passed. Includes all 30 stored Gold result sets and synthetic mapping/tolerance/export cases. |
| `PYTHONPATH=src uv run --locked --project . python -m unittest discover -s artifacts/sql-agent-bussiness/tests -q` | PASS: 45 run, 45 passed. |
| `PYTHONPATH=src uv run --locked --project . python -m unittest discover -s tests/sql -q` | PASS: 562 run, 552 passed, 10 skipped. |
| `PYTHONPATH=src:artifacts/sql-agent-bussiness/40-case-preparation uv run --locked --project . python -m unittest discover -s artifacts/sql-agent-bussiness/40-case-v3 -p 'test_*.py' -q` | FAIL: 55 run, 54 passed, 1 historical hash assertion. `test_freeze_manifest_is_explicitly_draft_and_hashes_review_artifacts` expected `test_v3_artifacts.py` SHA `9ef7240b…`, current file is `96adc0d9…`. The v3 historical manifest and test files were left unchanged. |

The focused v3.2 and SQL suites are fully passing. The legacy v3 artifact suite remains red because its old manifest pins the test source file's previous bytes; this does not indicate a scorer v3.2 assertion failure, and the historical manifest was not rewritten. The 40-case SQL Agent benchmark, live database reference generation, and external model calls were not run for this revision.

Limitations remain: SQL expression lineage only supports straightforward SELECT projections and is not full-query equivalence; independent semantic decisions remain human-supplied plain JSON without signatures; the v3.1 case set does not declare explicit business keys, so its comparisons use multisets; ordered output with mismatched business rows is `REVIEW_REQUIRED`; and numeric tolerance is a case-level rule rather than a typed per-column schema. The static HTML review UI still stores live clicks in browser-local storage. The two logged review records are the durable source for this session, with Reviewer 2 explicitly marked user-reported.

## Scorer v3.3 addendum — business-centric end-to-end scoring

This scoring-only revision keeps the v3.1 case set, Gold SQL, provisional Gold results, database fingerprint, reviewer records, and all historical run outputs unchanged. It does not create semantic audit records or additional-column safety approvals. The cohort remains `DRAFT_NOT_FROZEN`; the held-out 40-case SQL Agent benchmark was not run.

Business End-to-End Accuracy now requires successful execution, a linked independent SQL semantic audit `PASS`, Business Result Accuracy `PASS`, explicit runner security-validation evidence, zero reported unsafe executions, and essential output requirements. It may pass with Output Contract Compliance `FAIL` only when the sole contract deviation is unapproved extra columns and every such column has exactly one linked safety review that passes all required checks. Missing, ambiguous, duplicate, stale, contradictory, or wrong-typed execution safety evidence yields `REVIEW_REQUIRED`; a failed safety check or explicitly unsafe execution yields `FAIL`. Present safety flags must be JSON booleans. Business Result Accuracy, SQL Semantic Accuracy, Output Contract Compliance, and Business End-to-End Accuracy remain separate metrics with per-case reason codes.

The additional-output review record is linked to the exact SQL, parameters, case contract, full case set, observed result, and values of the reviewed column. Its seven reviewer-supplied checks cover required business values, row cardinality, grain/population, metric/aggregation, meaning, sensitivity, and access authorization. The scorer does not infer a reviewer decision or use an LLM judge. These plain JSON records are not authenticated, so the artifact cannot prove reviewer identity, independence, policy contents, or that supplied evidence is true. SQLGlot projection lineage remains a narrow expression/column-label check, not full-query equivalence.

Synthetic regression outcomes (fixtures are not human review evidence):

| Scenario | Business Result | Output Contract | Business E2E |
|---|---|---|---|
| Correct required values plus one safe, fully linked extra column | PASS | FAIL | PASS |
| Same extra column with no linked safety evidence | PASS | FAIL | REVIEW_REQUIRED |
| Extra sensitive/unauthorized column with failed safety checks | PASS | FAIL | FAIL |
| Reviewer decision says PASS but a required check says FAIL | PASS | FAIL | REVIEW_REQUIRED |
| Malformed execution safety flag types | PASS | PASS | REVIEW_REQUIRED |
| Case-insensitive canonical column names | PASS | PASS | PASS |
| Reordered columns, approved aliases, unordered rows, and independently audited equivalent SQL | PASS | PASS | PASS |
| Wrong business values, missing/extra rows, NULL-to-zero, required ordering/ranking violation, or independent semantic audit FAIL | FAIL or unresolved per evidence | FAIL or REVIEW_REQUIRED | FAIL |

The existing five-case development pilot was scored only as a no-write compatibility probe, using its stored observations and reference. It is legacy v2 case data, lacks v3.3 independent SQL audit records and the v3.1 output contract. All four attempted supported cases therefore returned E2E `REVIEW_REQUIRED` for unresolved semantic audit; the reported `0/4` is not a valid v3.3 benchmark score. The old pilot files and their historical scores were not overwritten. Its runner event contains an agent-side `semantic_approval` flag, which the v3.3 scorer does not treat as independent audit evidence.

Executed v3.3 regression evidence:

| Command | Result |
|---|---|
| `PYTHONPATH=src uv run --locked --project . python -m unittest discover -s tests/sql -p 'test_benchmark_v3_1_contract.py' -q` | PASS: 48 run, 48 passed. Includes malformed safety-marker types, synthetic positive/negative/review-required cases, and all 30 stored Gold row comparisons. |
| `PYTHONPATH=src uv run --locked --project . python -m unittest discover -s artifacts/sql-agent-bussiness/tests -q` | PASS: 45 run, 45 passed. |
| `PYTHONPATH=src uv run --locked --project . python -m unittest discover -s tests/sql -q` | PASS: 571 run, 561 passed, 10 skipped. |
| `PYTHONPATH=src:artifacts/sql-agent-bussiness/40-case-preparation uv run --locked --project . python -m unittest discover -s artifacts/sql-agent-bussiness/40-case-v3 -p 'test_*.py' -q` | FAIL: 55 run, 54 passed, 1 pre-existing historical hash assertion. The archived v3 manifest pins `test_v3_artifacts.py` to `9ef7240b…`; current bytes hash to `96adc0d9…`. Historical files were not changed. |
| `uv run --locked --project . python -m py_compile artifacts/sql-agent-bussiness/40-case-v3-1/scorer_v3_1.py artifacts/sql-agent-bussiness/40-case-v3-1/output_safety_audit_v3_3.py tests/sql/test_benchmark_v3_1_contract.py` | PASS. |
| `git diff --check` | PASS. |

No live database query, external model call, held-out benchmark execution, or new human review was performed for v3.3. `FREEZE_MANIFEST_V3_1_DRAFT.json` records scorer/protocol v3.3.0 and the new source hashes while preserving the original case, Gold SQL, result, and database fingerprints. Both static checks passed.

## Codex review P2 follow-up

The runner's `CountingRepository` records `approved` or `unverified` only after the repository call returns successfully. `normalize_payload()` serializes either event with `security_validated: true` and sets `semantic_approval` according to the event kind. The scorer now accepts both known kinds as security-validated only when `security_validated is True`; it ignores `semantic_approval`, so a linked independent SQL Semantic Audit `PASS` remains mandatory. Unknown kinds, missing evidence, and malformed flags remain unresolved. A mixed event list containing any confirmed unsafe event or failed security check is `FAIL`, even if another event is valid.

E2E now gathers confirmed failures and unresolved dimensions before deciding. Any confirmed execution, semantic, business-result, additional-output safety, or material output-contract failure produces `FAIL`; unresolved semantic/business/security/output evidence is retained in its reason codes. Without a confirmed failure, unresolved evidence remains `REVIEW_REQUIRED`. The v3.3 business-centric exception for independently safety-reviewed harmless extra columns remains unchanged.

These regressions use synthetic cases only. The 40 benchmark questions, Gold SQL, Gold Results, frozen database fingerprint, historical run outputs, and review records were not modified. No held-out SQL Agent run, live database query, external model call, new review decision, or freeze occurred.

Executed P2 follow-up checks:

| Command | Result |
|---|---|
| `PYTHONPATH=src uv run --no-sync python -m unittest discover -s tests/sql -p 'test_benchmark_v3_1_contract.py' -v` | PASS: 50 tests. Includes runner `unverified` event security, audit separation, unknown/mixed event handling, failure precedence, and v3.3 extra-column behavior. |
| `PYTHONPATH=src uv run --no-sync python -m unittest discover -s artifacts/sql-agent-bussiness/tests -v` | PASS: 46 tests. Includes a direct assertion of the actual normalized runner event schema. |
| `PYTHONPATH=src uv run --no-sync python -m unittest discover -s tests/sql -q` | PASS: 573 run, 563 passed, 10 skipped. |
| `PYTHONPATH=src:artifacts/sql-agent-bussiness/40-case-preparation uv run --no-sync python -m unittest discover -s artifacts/sql-agent-bussiness/40-case-v3 -p 'test_*.py' -q` | FAIL: 55 run, 54 passed, 1 legacy hash assertion. The historical manifest pins `test_v3_artifacts.py` to `9ef7240b…`; current bytes hash to `96adc0d9…`. Both the test file and manifest are byte-identical to `origin/main`, confirming this is pre-existing. Neither historical file was rewritten. |
| `uv run --no-sync python -m py_compile artifacts/sql-agent-bussiness/40-case-v3-1/scorer_v3_1.py artifacts/sql-agent-bussiness/40-case-v3-1/output_safety_audit_v3_3.py tests/sql/test_benchmark_v3_1_contract.py artifacts/sql-agent-bussiness/tests/test_runner.py` | PASS. |
| `git diff --check` | PASS. |
