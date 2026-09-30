# Database connections

## Why connections are bounded

The app connects to Supabase PostgreSQL through the shared pooler in session
mode (`DATABASE_URL` uses port `5432`). Each repository borrows a direct
psycopg connection for its operation and closes it afterward. Supavisor rejected
the 16th simultaneous session with `EMAXCONNSESSION` because this project's
session pool is limited to 15 clients.

`core.database.connection_limit` applies one process-wide semaphore to every
repository connection. The default maximum is 10 simultaneous sessions; extra
threads wait up to 20 seconds for a slot. Connection establishment has a
10-second timeout. Failed connection attempts and repeated close calls release
the slot safely. Set `DATABASE_MAX_CONNECTIONS_PER_PROCESS` between 1 and 12
when needed. Keep the sum across all app processes at or below 12 to leave
headroom under the observed 15-session cap for migrations and operator tools.

This limits concurrent sessions but does not retain/reuse them. If the project
pool size or deployment process count changes, remeasure before raising the
limit. The in-repo check covers queueing and slot release; a separate local
HTTP stress run validates the live path against Supabase.
