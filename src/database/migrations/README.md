# Database migrations

Migration execution has one source of truth: [`supabase/migrations`](../../../supabase/migrations).
Apply and track those timestamped files with the Supabase CLI; do not run a
second numbered SQL sequence. The numbered files were retired after their
schema changes were consolidated into the timestamped history.

See the [database section of the deployment guide](../../../docs/deployment-guide.md#database-migrations)
for fresh-project setup, migration-history repair, and the read-only schema
check.

That check compares local timestamped files with the remote
`supabase_migrations.schema_migrations` history before validating the pgvector
schema, corpus metadata and repository mapping. A mismatch fails the check
rather than being repaired automatically.
