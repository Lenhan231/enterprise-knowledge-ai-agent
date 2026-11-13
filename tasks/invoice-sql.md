# Invoice SQL integration

Approved scope: extend the existing SQL agent with typed invoice headers and items sourced from `public.invoice_extractions`. Preserve raw extraction data. Publish only after explicit review; missing values stay NULL. Use Vietnamese number formatting for extracted strings and ISO, Vietnamese long-form, or day/month/year dates. Reject malformed values rather than guessing.

Temporary access: every server-verified user with `analytics:read` can read every published invoice through the dedicated read-only database role. No owner filtering until RBAC is implemented; no anonymous or direct raw-extraction grants.

Implementation: transactional approval/publishing CLI and repository, typed `commerce` tables with RLS, SQL allowlists/keys/metrics/routing, regression tests, and SQL-agent documentation. Reprocessing invalidates the published copy; deleting the extraction cascades. Do not approve existing real extractions automatically.

Verification: `.venv/Scripts/python.exe -m unittest discover -s tests -p test_invoice_sql.py -v`, SQL regression tests, then repository test discovery. Verify migration and temporary reader behavior against Supabase with transaction-rolled-back fixtures. No new dependencies, UI, RBAC, or unrelated refactors.

## Implementation and verification (2026-11-07)

- Applied migration `20261107054431_invoice_sql_projection` to FA26AI69; local version matches remote history. Existing extraction remains unapproved; no test fixtures persist.
- Added explicit administrative approval CLI, typed normalization, atomic publishing, source invalidation/cascade, and duplicate-file protection.
- Extended SQL allowlists, keys, metric definitions, classifier, prompts, currency checks, and result limitations. Current `commerce_reader` inherits only the new reader role's read privileges; raw extraction and write access remain denied.
- Updated `docs/technical/sql-agent.vi.md`, including the temporary all-readers policy and RBAC replacement steps.
- Invoice unit/agent checks: 9 passed. SQL regressions: 186 run, 157 passed, 21 skipped, 8 failures/errors in legacy `test_sql_analytics.py`; all eight reproduced against unchanged HEAD.
- Opt-in live invoice integration: 6 passed, including duplicate-file rollback, publication, invalidation, cascade, reader restrictions, and configured repository role verification.
- SQL regression run excluding the unchanged legacy `test_sql_analytics` module: 172 run, 151 passed, 21 skipped. Python compilation, CLI help, and diff whitespace checks passed.
- Full discovery: 765 run, 11 failures, 51 errors, 43 skipped; includes legacy tests and unrelated import/fixture failures. These were not repaired in this feature.
- Live Groq → SQL agent → read-only repository → Supabase smoke passed (`invoice_count = 0`); database security advisors show no new findings.
- No automatic approval of real invoices, no changes to extraction UI, no new dependencies, no commits. Approval currently uses the operator CLI; the raw extraction table is an external prerequisite.
