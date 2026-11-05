# Inventory production integration gate

Recommendation: **hold merge into main**. The inventory integration preserves the measured candidate's outputs and removes its shared-contract regressions, but required CI remains red on existing failures.

Branch: `inventory-production-integration-2026-11-05`. Application runtime tested at `8a58e06`; replay/HTTP harness correction and CI at `8cb61637393ebe5f7a9b4a2a11a4ed31b25afc76`. The latter does not change application source. Base: latest local QuocAn `e297839`; measured inventory candidate: `3564c0638d0c9654240d222638e02b1ea8b057c5`.

## Minimal integration

The original candidate globally restricted shared SQL schemas. Its 70 added failures were real shared-validator, planner and legacy-agent contract regressions; calling them all outdated broad-domain tests was incorrect. This patch retains the existing shared defaults and applies inventory restrictions to the configured SQL Agent, SQL prompt/validator, repository, Intent Router and Report planner.

Set `SQL_INVENTORY_ONLY=true` in the server `.env` and restart to deploy inventory-only behavior. The default is false to preserve existing application contracts. Docker Compose already forwards `.env` through `backend-api.env_file`; no Compose change is required. Invalid flag values fail startup. The inventory profile permits only `commerce.inventory` and `commerce.products`, including nested SQL sources and repository execution. Existing RBAC, approved joins, metric formulas, SQLGlot checks, query limits and read-only execution remain in place. No database permissions, schema, dependencies or frozen references change.

Rollback: revert the integration commit, or disable the flag to restore the existing broader approved-source profile. Disabling the flag intentionally restores legacy scope and is not an inventory-only deployment.

The validated deterministic field retrieval, canonical inventory compilation, two-snapshot comparison and temporal safeguards remain intact. No new agent or mapping stage was introduced. The focused compatibility patch relative to the candidate is [candidate-integration.patch](candidate-integration.patch).

## Verification

| Gate | Measured candidate / baseline | Integration | Interpretation |
| --- | --- | --- | --- |
| Frozen response replay against real PostgreSQL | 60/60 checks pass | 60/60 checks pass | Identical prompt hashes, normalized SQL, parameters, rows, status and logical model-call counts |
| Focused inventory, SQL safety and Report contracts | — | 227 passed, 3 skipped / 230 | No failures or errors |
| Local full suite, same environment | Latest QuocAn: 747 run, 11 failures, 51 errors, 39 skips | 769 run, 11 failures, 51 errors, 39 skips | Zero added failure identities |
| Linux CI full suite | Candidate: 31 failures, 97 errors | 831 run, 6 failures, 52 errors, 45 skips | 70 failure instances removed, zero added |
| Authenticated real HTTP smoke | — | All recorded checks pass | Real login/session, RBAC, SQL Agent, router and PostgreSQL |

The replay uses stored original provider responses, unchanged frozen questions/references and the original harness's JSON serialization. It is a reproducible regression check, **not a new Ragas evaluation**. Original judge configuration and grading logic are unchanged. Historical accuracy/latency scores must not be presented as freshly measured integration scores. Replay timings exclude provider latency; no speedup claim is made. No fresh provider calls were needed for the paired replay. The authenticated smoke did use live SQL/Auto provider requests.

See [regression-summary.json](regression-summary.json), [measured-candidate-replay.json](measured-candidate-replay.json), [integration-replay.json](integration-replay.json), and [api-smoke.json](api-smoke.json). The smoke checks anonymous rejection, viewer denials, analyst access, forged identity rejection, direct-field retrieval, canonical SUM, snapshot comparison, Auto routing, outside-scope refusal and Report request validation. Telemetry writes were stubbed; authentication, authorization, SQL execution and routing were real. This was loopback HTTP, not an external staging or container/proxy smoke.

Report compatibility was checked through existing unit/contracts and negative HTTP requests. Report generation was explicitly blocked in the smoke harness. **No Report benchmark or Report generation was started.**

## Remaining failures and merge blockers

[failure-audit.json](failure-audit.json) records every local baseline/current failure and all 70 resolved candidate regressions with root-cause classifications. Remaining local failures include stale imports/API fixtures, missing optional OCR dependencies, Windows-only `resource` imports, and existing document/financial retrieval assertions. They are reproduced on the unchanged latest QuocAn base. Windows-only failures do not themselves explain Linux CI failures.

[CI run 41984392265](https://github.com/Lenhan231/enterprise-knowledge-ai-agent/actions/runs/41984392265) passes dependency installation and compilation but fails the full suite. Its remaining 58 failure instances are a multiset subset of the candidate's existing failures. [ci-verification.json](ci-verification.json) lists them; [ci-comparison.json](ci-comparison.json) records the comparison. Required full-suite CI remains a merge blocker even though no new regressions were found. Downstream container/proxy smoke steps were skipped after the test failure and are not claimed as passing. Unrelated functionality/tests were not removed or disabled to force green CI.

Inherited frozen-reference ambiguities and scorer limitations remain unchanged. This work establishes regression parity with the measured inventory candidate, not perfect semantic correctness or production readiness.

## Reproduction

Use the same project Python environment and unchanged configured read-only database. For local full-suite parity set `HF_HUB_OFFLINE=1` and `TRANSFORMERS_OFFLINE=1` in both checkouts.

```powershell
python -m unittest discover -s tests
python -m unittest discover -s tests -p "test_inventory*.py"
python -m unittest discover -s tests -p "test_report*.py"
python evaluation/replay_inventory_integration.py --source <integration-checkout> --cohort <original-inventory-demo-final> --env-file <server-env> --output <integration-replay.json>
python evaluation/replay_inventory_integration.py --source <measured-candidate-checkout> --cohort <original-inventory-demo-final> --env-file <server-env> --output <measured-candidate-replay.json>
python scripts/operations/smoke_inventory_api.py --env-file <server-env> --output <api-smoke.json>
```

The original cohort is `artifacts/evaluation/inventory-demo-2026-11-04/final/`. Frozen question/reference SHA-256 values are recorded in the regression summary. For the full focused gate also run `test_sql_generation.py`, `test_sql_join_duplication.py`, `test_sql_metric_definitions.py`, `test_sql_followups.py`, and `test_metric_mapping.py` using unittest discovery. Do not rerun provider-intensive benchmarks merely to reproduce the replay.
