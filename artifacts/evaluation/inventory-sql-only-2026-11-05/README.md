# SQL-only integration readiness

**Recommendation: HOLD merging.** Inventory SQL gates pass, but required full-suite CI remains red on exactly the same failures as main. No branch protection was bypassed and main was not merged into or modified.

Branch: `inventory-sql-only-integration-2026-11-05`. Base: exact latest main `d40162be0af86e2f679da4372158ea2e3d47f6ae`. Tested runtime: `af56d59`. Selected source: `inventory-production-integration-2026-11-05` at `fdd4d4c`.

## Selection and preservation

Selected SQL implementation and test hunks onto a fresh branch from main, rather than merging the historical branch. Integrated deterministic product/inventory field retrieval, canonical inventory mapping and compilation, two-snapshot product-intersection stock comparison, semantic checks, and `SQL_INVENTORY_ONLY` configuration. Router planning receives its SQL Agent's configured schema. SQL Agent and repository both enforce the inventory source allowlist. RBAC, existing approved joins, aggregate join safety, SQLGlot validation, read-only transactions, timeouts and the 200-row ceiling remain enforced.

Excluded historical cross-domain calculation/derived-join extensions, Report planning/evidence/template/delivery features, UI changes, benchmark experiment runners and cleanup deletions. Main's aggregate join validator remains intact; only its approved-key lineage helper was selected for inventory presence checks. No existing main tests were deleted. Existing inventory tests were updated for deterministic compilation and newly supported explicit period scope rather than silently accepting an old arbitrary SQL string.

`preservation.json` compares Git object IDs: API/UI (`src/app`), Knowledge Agent, RAG, Report implementation, Streamlit, Document Processing, dependencies/lockfile and CI workflow are **byte-identical to main**. Shared SQL modules and Router/planning are the intentional integration points. Report interface unit tests run against main's existing implementation. This does not certify unrelated features as bug-free; their inherited failures remain visible.

Default configuration is `SQL_INVENTORY_ONLY=false` to retain shared legacy callers' approved-source behavior. Enable `true` and restart for the mentor-approved two-table deployment. Invalid values fail closed. Docker Compose already loads `.env`; no production Compose changes are required. No database migration, metric formula, permission or dependency change.

## Results

| Check | Exact main | SQL-only candidate |
| --- | --- | --- |
| GitHub Actions full suite | 695 run; 11 failures, 56 errors, 21 skips | 738 run; 11 failures, 56 errors, 21 skips |
| Windows full suite, same environment/offline settings/UTF-8 | 643 run; 19 failures, 51 errors, 15 skips | 686 run; 19 failures, 51 errors, 15 skips |
| Added failure identities | — | **0 in both comparisons** |
| Focused SQL/security/Report interface/Router contracts | — | **194/194 passed**, no skips |
| Frozen SQL response replay with real read-only PostgreSQL | Measured candidate retained as comparison | **60/60 passed** |
| Authenticated Docker HTTP through Nginx | — | **10/10 passed**, real provider and Supabase |
| Backend image build, Compose config, Nginx config, JS syntax | — | Passed locally |

Replay compares normalized SQL, bound parameters, rows, execution/refusal status and logical provider-call counts against unchanged frozen generations. All 60 row hashes match the measured inventory candidate. Prompt hashes match for 55 cases; five prompts change because unrelated cross-domain instructions were deliberately excluded. Stored provider responses are replayed: this is regression evidence, **not a fresh Ragas or latency benchmark**. Frozen questions, references, generations and SHA-256 hashes are recorded in `manifest.json`; scoring and judge settings were not changed.

An initial replay failed one Vietnamese comparison after an encoding mistake during selection. The source text was corrected, an independent Vietnamese date-comparison regression test was added, and the complete replay rerun passed. No reference was altered. Early temporary test failures came from a test import still pointing to an experiment shim and a transaction-only test inadvertently selected from the old branch; the import now targets the actual production module and that non-main transaction test was left on its original branch. No main test was removed or disabled.

## Container HTTP evidence

Built `inventory-sql-only-backend:20261105` from the tested source. Healthy image: `sha256:b8de5d84173d9168d89d216975dfc04a7ae733ab1f70a6ebf531c7134e4bef14`. SQL Agent file hash in the running container equals the checkout hash: `9c3c0ecf7d4749329ba8e60940e98435c1273bc13f86b94afc779e0da1ec3a24`. Inventory configuration was checked inside the container.

Compose project `inventory-sql-only` serves backend on 19000 and Nginx on 19080. Through Nginx, checks cover health, anonymous 401, viewer/analyst login, viewer SQL 403, direct product retrieval, snapshot stock SUM, two-snapshot stock comparison, Intent Router Auto to completed SQL task, and an orders request refused with `outside_inventory_scope`. No auth/SQL/provider/database mocks. Database execution uses the real configured read-only Supabase connection. No Report generation or Report benchmark.

After recreating the backend, Nginx initially retained the old container address and returned 502. Recreating the proxy after backend health restored service; final smoke passed. See `container-http.json`. Backend and proxy were started with `--no-deps`: this proves the inventory SQL slice, which does not use the embedding/reranking/document services. Full rebuild and cold-start verification of those unchanged services is not claimed.

## Inherited CI blockers

[Main baseline CI](https://github.com/Lenhan231/enterprise-knowledge-ai-agent/actions/runs/41957448447) and [candidate CI](https://github.com/Lenhan231/enterprise-knowledge-ai-agent/actions/runs/41997615634) both pass dependency sync and compilation, then fail full unittest discovery. Their 67 failure/error identities match exactly. `ci-audit.json` records each traceback's cause and its presence on exact main; `local-comparison.json` provides the separate Windows comparison. CI's downstream container steps were skipped after tests failed; the local container checks above provide actual evidence independently.

The inherited blockers include removed historical API/document-SQL imports and fixtures, unavailable optional OCR/evaluation dependencies, missing retrieval/OCR evaluation assets, tests loading an uncached reranker, and document/invoice/retrieval assertions that disagree with current behavior. These are not reclassified as passing. Missing dependencies/assets need their owning test environment corrected; legacy interface expectations need an owner decision; genuine document/retrieval behavior issues need fixes in their feature areas. Restoring old modules or changing unrelated behavior to force this SQL patch green would violate its scope. All remain blockers while the required full-suite gate is red.

SQL integration is ready for review. Overall production readiness and merge approval remain **HOLD** until required CI failures are resolved or handled through the project's explicit approval process, and any required full-stack launch checks pass.

## Reproduction

Use the same Python environment and unchanged configured read-only database. `container_http.py` reads credentials from ignored `.env`, never from committed evidence. Build with the checked-in production Dockerfile and use the evidence override only for separate local ports and inventory configuration.

```powershell
python -m unittest discover -s tests -v
python evaluation/replay_inventory_integration.py --source . --cohort <frozen-inventory-demo-final> --env-file <server-env> --output <replay.json>
docker compose -p inventory-sql-only -f docker-compose.yml -f artifacts/evaluation/inventory-sql-only-2026-11-05/compose-smoke.yaml build backend-api
docker compose -p inventory-sql-only -f docker-compose.yml -f artifacts/evaluation/inventory-sql-only-2026-11-05/compose-smoke.yaml --profile proxy up -d --no-deps backend-api proxy
python artifacts/evaluation/inventory-sql-only-2026-11-05/container_http.py
```

The unchanged cohort is `artifacts/evaluation/inventory-demo-2026-11-04/final/` on the selected source branch. Use a separate checkout of that branch for replay input; historical benchmark artifacts are not copied into this production diff. All replay outcomes and manifest hashes are preserved here.
