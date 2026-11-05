# Main reconciliation and production readiness

**HOLD.** Integration revision `9642d32` includes latest main `d40162be0af86e2f679da4372158ea2e3d47f6ae` as an ancestor. Main was not modified. No Report benchmark was run.

## Changes

Merged main's Knowledge, provider, invoice and document-processing updates without replacing teammates' changes. Resolved two conflicts: retained both environment settings, and retained inventory Report confirmation handling together with main's session identity checks and expired-session handling. Updated two orchestration client test fixtures to supply the current session/transcript globals and expect the current human-readable task label. The tests still verify conversation reset isolation and multiple escaped SQL result tables; neither was skipped or disabled. No SQL formulas, scoring, frozen references, dependencies, permissions or query validators were weakened.

## Evidence

| Check | Result |
| --- | --- |
| Frozen SQL replay against real read-only PostgreSQL | 60/60, unchanged prompt hashes and row hashes versus measured candidate |
| Focused SQL, inventory, security and Report interface tests | 230 run; 227 passed, 3 skipped |
| Updated orchestration client tests | 2/2 passed |
| JavaScript syntax | Passed locally |
| Compose config and backend image build | Passed |
| Container health | Healthy; image `sha256:69616e4f10236d9911e18ca0bec4097f1a961f5c1abdd321640e08904a3a24e2` |
| Real container HTTP | 10/10 checks passed, real authentication, provider and Supabase; no mocks |
| Nginx config and proxy HTTP | Configuration valid; 5/5 health/authentication/session/RBAC checks passed |
| Required CI | Failed: 905 run, 9 failures, 56 errors, 45 skips |

The SQL HTTP cases include direct product fields, canonical snapshot SUM, two-snapshot comparison, Intent Router Auto to SQL, and an explicit orders request refused as outside inventory scope. Agent metadata confirms inventory scope. Anonymous requests return 401 and viewer SQL requests return 403. The backend runs with `SQL_INVENTORY_ONLY=true`. No Report generation was requested. See `container-http.json`, `proxy-http.json`, `focused.json` and `replay.json`.

Replayed responses are frozen, not fresh Ragas scores; no new model latency or semantic accuracy claim is made. The first container attempt accidentally used the old image while the new build was exporting. It is retained as `container-http-stale-image.json`, excluded from candidate results, and superseded after force-recreating the container and checking its source and enabled inventory scope. The old-image attempt also encountered a provider 429. All checks passed on the correct image.

Compose project `inventory-readiness` exposes backend on 18000 and proxy on 18080, leaving existing services alone. Backend was started with `--no-deps`; this verifies the SQL/authentication slice, which does not call embeddings, reranker or document processing. A fresh full-stack rebuild/start of those three unrelated services is **not verified**. Existing services in the original project were healthy but are not counted as newly validated images.

## CI root causes and blockers

[Integration CI](https://github.com/Lenhan231/enterprise-knowledge-ai-agent/actions/runs/41995241019) passes dependency sync and compilation. Required unittest discovery fails, so its later container/proxy steps are skipped. The container/proxy results above were performed locally instead.

[Latest main CI](https://github.com/Lenhan231/enterprise-knowledge-ai-agent/actions/runs/41957448447) already fails with 11 failures and 56 errors over 695 tests. The previous integration failed with 6 failures and 52 errors. Every current failure identity appears in one of those two baseline runs; `ci-audit.json` records the exact cause and both baseline membership flags. `inherited-ci-causes.json` records all original 58 causes, rather than relabeling them broadly as obsolete tests.

Remaining causes include:

- Removed historical API/import contracts (`AskRequest`, document SQL, DashboardAgent, older document-processing packages), obsolete source-shape fixtures and retrieval defaults. These require an explicit owner decision on legacy support; adding parallel production implementations to satisfy historical tests would exceed this patch.
- CI dependencies/fixtures absent from the checkout: Ragas, Streamlit, OCR libraries, frozen retrieval manifests and OCR ground truth. These need the owning test environment/fixture configuration repaired; no skips or new dependencies were added here.
- Retrieval unit tests unexpectedly loading an uncached BGE model, and reranker environment selection assertions. Keep as failures until their mocks/environment or behavior are corrected by the retrieval owner.
- Main's remote parser path importing local OCR dependencies, invoice processor mocking/import failures, and DOCX section-title behavior. These are genuine document-processing issues reproduced on main, not inventory SQL regressions. They remain production blockers for those features.
- Document normalization, financial extraction and retrieval model assertions disagree with current source fields/defaults. The exact traceback causes are recorded for owner triage; the integration does not silently change those contracts.

The initial merged local suite ran 843 tests with 18 failures, 61 errors and 39 skips. Latest-main local comparison ran 633 with 25 failures, 66 errors and 15 skips; there were no added normalized failure identities. Those runs used the same Python environment, offline model settings and Windows defaults. A final UTF-8 rerun after the two client fixture repairs is separately recorded; Windows-only permissions and `resource` imports must not be confused with Linux CI failures. Required Linux CI is the definitive merge blocker.

## Recommendation

SQL replay and authenticated inventory container integration gates pass. **Do not merge main while required CI is red.** Resolve or formally accept the documented owning-team blockers through the project's normal process, and validate the remaining full-stack images before claiming whole-application production readiness. Keep inventory mode explicitly enabled at deployment. No cleanup deletions are part of this verification patch.

Reproduce SQL replay with `evaluation/replay_inventory_integration.py` using the unchanged `inventory-demo-2026-11-04/final` cohort and configured root `.env`. Reproduce container smoke with `container_http.py` from the integration checkout after building and starting the project using `compose-smoke.yaml`. Credentials are read from ignored `.env`, never embedded in evidence.
