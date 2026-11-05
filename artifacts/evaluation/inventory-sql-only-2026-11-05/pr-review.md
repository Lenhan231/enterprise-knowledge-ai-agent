# Final PR preparation review

Decision: **HOLD merge**. SQL implementation and the five changed prompt cases pass their checks. Full CI is still red on inherited failures; an independent reviewer has not approved this change, and no exception has been granted.

## Base and complete diff

Fetched main again: `d40162be0af86e2f679da4372158ea2e3d47f6ae` remains the current base and an ancestor of this branch. Reviewed implementation, test changes, replay harness and evidence files across the complete PR diff. No unrelated production change or test deletion was found. SQL source is unchanged since tested revision `af56d59`; PR preparation adds evidence and corrects the container-smoke transport description from 18000 to its actual Nginx port 19080. It does not change a test outcome.

Git object equality in `preservation.json` reconfirms unchanged Knowledge, RAG, Report, API/UI, Streamlit and Document Processing source. Dependencies and CI workflow also remain unchanged. Router/planning and shared SQL modules are intentional integration points, covered by the focused integration tests. Approved schema/joins/date columns and the 200-row safety ceiling match main. SQLGlot checks, aggregate join safety, RBAC, repository revalidation and read-only execution remain intact.

## Five changed prompts

The prompt changes remove unrelated cross-domain instructions and advertise relevant approved schema and keys. None introduces a question-ID route or question-specific production answer. Replay alone cannot establish behavior under fresh generation, so the exact five requests were also submitted through authenticated Docker/Nginx to the configured live provider and read-only Supabase.

| Case | Reviewed live SQL behavior | Result |
| --- | --- | --- |
| I11 latest available snapshot | MAX(snapshot_date) over inventory; no product/sample/date restriction | Passed |
| I12 master product count | COUNT(*) over the complete products table, without inventory intersection | Passed |
| I13 category counts | Category grain, COUNT(non-null product primary key), no inventory join or inner limit | Passed |
| I14 distinct December snapshots | DISTINCT snapshot_date; inclusive December start/exclusive January start; stable date order | Passed |
| I15 excess duplicate rows | Group by both snapshot_date and product_id; COALESCE(SUM(group_count - 1), 0) | Passed |

All returned cell values match the unchanged frozen results. Output aliases and unspecified ordering are not treated as semantic differences. I15 generated an inline grouped subquery rather than the frozen CTE; both retain the complete key and excess-row formula. Existing SQLGlot/metric validation accepted it. Actual SQL, parameters and request timings are in `changed-prompts-live.json`.

I14 and I15 initially failed with provider RateLimitError. Those two request failures are retained under `previous_attempts`; only failed requests were retried after the quota window. Final result: 5/5 passed, with two recorded request-level provider quota failures. No Ragas rescoring, reference modification, broad benchmark or Report generation. One live run per successful case does not guarantee robustness across every provider sample.

## Configuration

Checked the running reviewed container: `SQL_INVENTORY_ONLY=true`. The override in `compose-smoke.yaml` sets it explicitly. The SQL Agent and repository enforce inventory/products scope, including nested sources, and HTTP smoke demonstrates an outside-scope refusal. Production `.env.example` retains false for compatibility; the intended inventory deployment must explicitly set true and restart. No production environment was modified and no deployment was performed. Production activation remains a release approval/configuration task.

## Review and protection gate

Repository metadata reports main `protected=false`, no active branch rules and no repository rulesets. The detailed protection endpoint requires administrative authentication and was not changed. No CODEOWNERS file was found. Absence of automatic enforcement does not authorize merging: the user's review/check gate still applies.

Authenticated PR author: `Anquoc211`. Independent reviewer selected: repository owner `Lenhan231`, whose repository permission was confirmed as admin. Request review of SQL semantics/security, shared API compatibility and explicit inventory deployment configuration. Request the maintainer's decision on the inherited CI blockers; an exception must be explicit and authorized, not inferred from matching baseline failures. No protection change, bypass, force-push, test disabling or automatic merge is requested.

Exact-main CI comparison and all inherited causes remain in `ci-audit.json`: main 695 tests versus candidate 738, both 11 failures/56 errors/21 skips, zero added failure identities. Focused tests remain 194/194 passed; SQL replay remains 60/60; authenticated container smoke remains 10/10. These establish SQL review readiness, not an approved merge. Maintainer approval and passing required checks or an explicitly granted exception remain outstanding.
