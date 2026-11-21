# SQL Agent 40-case v3 readiness

## Decision

`READY_FOR_INDEPENDENT_HUMAN_REVIEW = YES`

`READY_FOR_40_CASE_EXECUTION = NO`

Protocol/scorer semantics are version 3.1.0. Valid unsupported outcomes require a non-empty answer, no SQL or execution event, and a valid optional choices list; malformed clarification responses no longer count as correct abstentions.

This is a technically prepared draft, not an approved or frozen benchmark. Two independent semantic reviews and adjudication are still pending. The canonical review file is `cases_v3_draft.json`; reviewer decisions belong in a separately versioned review record, not in unreviewed author notes.

## Dataset and reference status

- 40 cases: 30 execute, 5 clarify, 5 abstain without query.
- Dataset validation: `PASS_STRUCTURAL_DRAFT`, 40 cases, zero errors.
- Gold SQL structural validation: `PASS_STRUCTURAL_DRAFT`, 30 references, zero errors.
- Gold results: 30/30 executed successfully through the approved read-only executor; 404 stored rows.
- Gold results status: provisional, zero reviewer approvals.
- Snapshot: frozen analytics snapshot fingerprint `dbc14b99acc2920ffaeb4190ba45708982c971f0671b0b9e8114b595f2594028`; read-only role verified before both reference and mutation runs.
- SQL Agent generation calls: 0. Held-out SQL Agent cases executed: 0. Database writes: 0.
- A separate five-question development pilot ran at application revision `60eafaee964a6de48a0c8d13925e3207d5116588`; it is not part of the 40-case cohort. Four supported questions passed business E2E and the unsupported question returned a schema-grounded abstention without SQL or execution. The run used Cloudflare `@cf/openai/gpt-oss-20b` with the configured Groq/local fallback policy; no fallback was invoked. It was scored by the historical pilot scorer, not the v3 cohort scorer. Evidence is under `artifacts/sql-agent-bussiness/runs/pilot5-v31-cloudflare-20261121/`.

## Discriminative evidence

The preserved v3.0 `mutation_results.json` and v3.1 `mutation_results_v3_1.json` record 28 controlled variants on the same snapshot. Of 26 valid variants executed, 23 differed from Gold under the business result comparison policy and 3 were observationally equivalent (88.46% result-based detection). Two other variants were correctly rejected by approved JOIN safety checks. Separately, the business population validator rejected the missing-delivered-filter variant (1/1).

Known limits remain visible: removing the B40-008 non-NULL reason filter is equivalent because the selected 2024 rows have no NULL reasons; removing B40-023's both-snapshot membership condition is equivalent because both snapshots contain the same 97 products; reversing B40-029's numeric sort is equivalent because all three reasons have equal returned quantity. B40-029 still distinguishes TOP 2 and the alphabetical tie-break. B40-020 does not claim missing-fee coverage, and B40-028's NULL policy is not exercised by a missing-month row in this snapshot.

## Follow-up adapter

B40-026 through B40-030 use `context-conditioned SQL`, not conversational-memory evaluation. The adapter supplies the prior user question, approved typed state and the current follow-up in a normal direct SQL request. Tests verify that the request and SQL-generation prompt receive this context and reject SQL/Gold/result/assistant-answer leakage. Whether a model correctly uses that context remains unmeasured because no v3 SQL Agent case was run.

## Executed test evidence

| Exact command | Passed | Failed | Skipped | Status |
|---|---:|---:|---:|---|
| `PYTHONPATH=src:artifacts/sql-agent-bussiness:artifacts/sql-agent-bussiness/40-case-preparation:artifacts/sql-agent-bussiness/40-case-v3 uv run --project /home/lenhanm1/orca/workspaces/enterprise-knowledge-ai-agent/main --no-sync python -m unittest discover -s artifacts/sql-agent-bussiness/40-case-v3 -v` | 55 | 0 | 0 | PASS |
| `PYTHONPATH=src:artifacts/sql-agent-bussiness:artifacts/sql-agent-bussiness/40-case-preparation uv run --project /home/lenhanm1/orca/workspaces/enterprise-knowledge-ai-agent/main --no-sync python -m unittest discover -s artifacts/sql-agent-bussiness/40-case-preparation/tests -v` | 21 | 0 | 0 | PASS |
| `PYTHONPATH=src uv run --project /home/lenhanm1/orca/workspaces/enterprise-knowledge-ai-agent/main --no-sync python -m unittest discover -s artifacts/sql-agent-bussiness/tests -v` | 45 | 0 | 0 | PASS |
| `PYTHONPATH=src uv run --project /home/lenhanm1/orca/workspaces/enterprise-knowledge-ai-agent/main --no-sync python -m unittest discover -s tests/sql -v` | 523 | 0 | 10 | PASS |
| `PYTHONPATH=src:artifacts/sql-agent-bussiness:artifacts/sql-agent-bussiness/40-case-preparation:artifacts/sql-agent-bussiness/40-case-v3 uv run --project /home/lenhanm1/orca/workspaces/enterprise-knowledge-ai-agent/main --no-sync python -m unittest test_followup_adapter -v` | 7 | 0 | 0 | PASS |
| `PYTHONPATH=src:artifacts/sql-agent-bussiness:artifacts/sql-agent-bussiness/40-case-preparation:artifacts/sql-agent-bussiness/40-case-v3 uv run --project /home/lenhanm1/orca/workspaces/enterprise-knowledge-ai-agent/main --no-sync python -m unittest test_mutation_probes_v3 -v` | 8 | 0 | 0 | PASS |

The v3, follow-up, and mutation test counts overlap. The 10 SQL-suite skips were explicitly reported by unittest; no failed tests were hidden. Dataset and Gold SQL structural statuses were also directly checked and both had zero validation errors. Final `git diff --check`, Python syntax, JSON parse, and untracked-artifact whitespace checks are recorded in `FREEZE_MANIFEST.json`.

## Reproducibility identity

- Application HEAD: `60eafaee964a6de48a0c8d13925e3207d5116588`.
- Branch: `codex/sql-model-ab-20261121`.
- Python: 3.11.16.
- Case-set canonical hash: `56ef0dd5ec0d2fc15539665b91a230a923e1836cc4a18cf5c6fe8fcd795146c6`.
- Gold SQL definition hash: `07a9a92d6761797b672ad57e40ea67cb72b3f7bb41b1df9cbaa96ce0ac3f0af0`.
- Mutation run: `mutation-v3-20261121T080242Z` (v3.0 preserved) and current protocol 3.1 rerun recorded in `mutation_results_v3_1.json`.
- Source hashes and database fingerprint are in `FREEZE_MANIFEST.json` and the Gold/mutation result artifacts.

No production source file was changed for this benchmark preparation. Gold references remain provisional pending two independent reviews, adjudication, and final frozen hashes; do not execute the 40-case cohort before those gates are complete.
