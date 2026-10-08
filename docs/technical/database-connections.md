# Database connections

## Why connections are bounded

The app connects to Supabase PostgreSQL through the shared pooler in session
mode (`DATABASE_URL` uses port `5432`). Each repository borrows a direct
psycopg connection for its operation and closes it afterward. Supavisor rejected
the 16th simultaneous session with `EMAXCONNSESSION` because this project's
session pool is limited to 15 clients.

`core.database.connection_limit` uses a process-wide Psycopg pool and semaphore
for all repositories. The pool starts empty, grows only when requests need
connections, retains idle sessions for at most four minutes, and caps concurrent
sessions at 10 by default. Extra threads wait up to 20 seconds for a slot;
individual connection attempts time out after 10 seconds. Row factories are
reset for each checkout so repositories can share the pool safely. Set
`DATABASE_MAX_CONNECTIONS_PER_PROCESS` between 1 and 12 when needed. Keep the
sum across app processes at or below 12 to leave headroom under the observed
15-session cap for migrations and operator tools.
The pgvector adapter is registered when each physical connection is created,
not on every repository checkout.

Reusing checked-in sessions avoids paying the Supabase connection handshake
for every repository on every request. Before this change, an explicit
promotion ROI request spent about 12 seconds opening three repository
connections, before its SQL, retrieval, and response work; use the live request
check and load script to remeasure after deployment or pool changes.

The promotion campaign-window aggregate now also reads a materialized view.
The previous repository query took 7.645 seconds; the materialized-view read
took 1.115 seconds on the same Supabase dataset, and PostgreSQL reported
0.098 ms execution time for the ordered 50-row scan (excluding network time).
After an app restart, the authenticated ROI-abstention request returned HTTP
200 with six citations in 20.91 seconds on its cold call, then 7.09 and 6.02
seconds on warm calls. The answer used the deterministic missing-cost/holdout
fallback; these timings are not a generated-answer or load benchmark.
