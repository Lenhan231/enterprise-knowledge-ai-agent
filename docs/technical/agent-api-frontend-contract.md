# Agent chat API contract for the Vercel frontend

Contract revision: 2026-10-31. Scope: unified Knowledge/SQL chat, inventory SQL follow-ups, and Report source
collection. Report and Inventory Dashboard retain separate, explicit interfaces. This contract describes
the local implementation; publishing the frontend or changing Vercel settings is
outside this change.

## Endpoint and authentication

Use `POST /api/agents/chat` on the frontend origin. The existing `vercel.mjs`
configuration rewrites `/api/*` to the configured HTTPS backend tunnel origin.
Keep same-origin cookie authentication and the existing sign-in/out endpoints.
Use `credentials: "same-origin"`; keep the `ngrok-skip-browser-warning: 1` header
where the configured tunnel requires it. Never expose Groq, database, Supabase,
or internal-service keys in browser configuration.

The authenticated server determines identity, role, document scope, and analytics
permissions. A conversation ID is only a correlation identifier, not a credential.
Direct cross-origin backend calls require a separately verified origin/cookie
configuration; this change retains the existing frontend-origin rewrite approach.

## Request

```ts
type AgentMode = "auto" | "agentic" | "knowledge" | "sql" | "report" | "dashboard";
type RetrievalMethod = "dense" | "bm25" | "hybrid" | "parent"
  | "translated_hybrid" | "translated_hybrid_rerank";

interface AgentChatRequest {
  question: string;                 // trimmed, 1..2000 characters
  agent_mode?: AgentMode;            // default: auto
  retrieval_method?: RetrievalMethod; // default: translated_hybrid_rerank
  conversation_id?: string | null;   // <=128 characters
  metadata?: Record<string, unknown>; // <=20 fields; ordinary client options only
}
```

Unknown top-level fields are rejected. Metadata cannot contain keys beginning
with `_` or reserved fields: `identity`, `user_id`, `permissions`, `roles`,
`history`, `plan`, `task_results`, `deadline`, `budget`, `precollected`, or
`resolved_question`. Do not submit chat history or execution plans in metadata.

`auto` combines agent selection and bounded agentic execution for Knowledge and
SQL. `agentic` is an accepted compatibility alias for exactly the same path.
Display one Auto option, not separate Auto and Agentic choices. Keep explicit
Knowledge/SQL choices and existing standalone Report/Dashboard controls.
Automatic chat does not select Report or Dashboard; asking for these features can
produce a clarification directing the user to their standalone mode.

Example:

```json
{
  "question": "Count products by category and find inventory guidance for those categories.",
  "agent_mode": "auto",
  "retrieval_method": "translated_hybrid_rerank",
  "conversation_id": "browser-session-generated-opaque-id"
}
```

## Conversation lifecycle

Create an opaque random ID with `crypto.randomUUID()` for a signed-in chat session.
Reuse it for follow-ups. Generate a new ID and clear displayed conversation state
on New conversation, sign-out, and account change. Do not share IDs between users
or put them in public URLs. Without an ID, requests are stateless.

History is process-local and scoped to verified subject and current permission
fingerprint: Auto retains up to six exchanges; standalone SQL retains one bounded
validated inventory scope and pending clarification, without rows, answers or SQL.
Each store has a 12,000-character limit, 30-minute idle expiry,
and capacity of 100 conversations per process. Restarts, eviction, or another worker may lose
context. Handle a follow-up clarification normally; do not fabricate client-side
history or silently reconstruct an answer from stale assistant text.

### Standalone SQL follow-ups

The HTTP request schema is unchanged. Send `agent_mode: "sql"` and reuse the
conversation ID. SQL memory is isolated from Auto, Knowledge, Dashboard and Report,
even when the same ID is used. Changing modes preserves the visible transcript;
returning to SQL can resume its unexpired scope. Report keeps its own form and ID.

Complete questions start fresh. Clear follow-ups inherit omitted metrics,
dimensions, filters, date, representation and ranking. A filter on the same field
replaces that field's conditions; explicit removal clears only named fields.
Ambiguous references request clarification. Unsupported metrics remain blocked.
Every calculation rechecks permissions and definitions and executes a fresh query.
An executed zero-row result can establish scope; failed queries cannot replace
the last accepted scope. A successful non-inventory SQL question clears that anchor.

An explicit latest-snapshot request resolves the date once. Follow-ups keep that
date until the user requests another snapshot or explicitly refreshes latest.
Show the returned date as historical data, never as current inventory.

Optional SQL metadata (absent fields must remain supported):

```ts
interface InventorySQLMetadata {
  context_used?: boolean; // true when a follow-up/clarification used server scope
  semantic_interpretation?: {
    domain: "inventory" | "other";
    metrics: string[];
    dimensions: string[];
    filters: Array<{
      field: string;
      operator: "eq" | "lt" | "lte" | "gt" | "gte" | "in";
      value: string | number | boolean | Array<string | number | boolean>;
    }>;
    time: {mode: "latest" | "snapshot" | "range" | "history";
           start?: string | null; end?: string | null} | null;
    ranking: {metric: string; direction: "asc" | "desc"; limit: number} | null;
    representation: "aggregate" | "product";
    clarification?: string | null;
  };
  requested_time?: {mode: "latest" | "snapshot" | "range" | "history";
                    start?: string | null; end?: string | null};
  metric_catalog_version?: string;
  historical_inventory?: boolean;
  snapshot_dates?: string[]; // dates represented in rows; can be empty
  metric_error_code?: string;
}
```

Use `semantic_interpretation.time` for the accepted scope, including zero-row
results. `requested_time` explains an explicit latest selector resolved by the
server; it need not appear on later replies. When `context_used` is true, display
the retained snapshot and filters beside that answer. Interpretation metadata is
an explanation, not proof of execution: still check `data.query_status`.
Never send this object back as trusted state or supply `_sql_context`; private
metadata keys are rejected. Display returned clarification messages and reply
through the same SQL conversation ID rather than constructing client-side patches.

### Session transcript and reset behavior

Keep the latest 20 exchanges in session memory, each with a stable turn ID,
submitted mode, user question and original response payload (or transport error).
Attach SQL, parameters, rows, sources, limitations and charts to that turn.
Rerender saved payloads without submitting requests again. Scope download/widget
keys to the turn ID and nested result path, so repeated answers do not collide.

New conversation clears transcript, drafts, report outputs and both conversation
IDs while retaining sign-in and selected mode. Sign-out/account change also clears
authentication and user-specific state. Before submitting, capture the conversation
ID and authenticated session identity/generation; discard late success or error
responses if either changed. Clear the transcript before another user signs in.
These are session records, not persistent history; no history-storage endpoint is
introduced. This behavior is implemented in Streamlit; a separate frontend must
implement its own transcript and stale-response guard.

## Response envelope

The response remains `AgentResult`; new orchestration fields live in metadata.
Clients must tolerate additional metadata and data fields.

```ts
interface Evidence {
  citation_id: string | null; // response-wide S1, S2, ... in combined responses
  source_type: string;
  source: string;
  content: string | null;
  metadata: Record<string, unknown>;
}
interface AgentResult {
  answer: string;
  agent: string; // knowledge, analytics, hybrid, agentic; standalone values unchanged
  evidence: Evidence[];
  data: Record<string, unknown>;
  metadata: {
    ok?: boolean;
    status?: "complete" | "partial" | "clarification_required" | "failed";
    selected_route?: "knowledge" | "analytics" | "hybrid" | "clarification" | "unrouted" | "report" | "dashboard";
    fallback?: boolean;
    planning_fallback?: boolean;
    clarification_required?: boolean;
    limitations?: string[];
    revisions?: number;
    specialist_invocations?: number;
    task_trace?: Array<{
      id: string; agent: "knowledge" | "sql"; depends_on: string[];
      status: "complete" | "partial" | "empty" | "clarification_required"
        | "failed" | "timed_out" | "blocked";
      attempts: number; elapsed_ms: number; error_type: string | null;
    }>;
    latency?: Record<string, unknown>;
    [key: string]: unknown;
  };
}
```

`agent` describes the returned response, not a request-mode selector. Do not expect
the old `agentic` string for every automatic answer. Use `metadata.selected_route`
for diagnostics and `metadata.status` for user-facing completion state.

| Status | UI behavior |
|---|---|
| complete | Show answer, sources, and returned structured results. |
| partial | Show available findings and explicit gaps; do not label the whole request successful. |
| clarification_required | Display the targeted question and retain the conversation ID for the reply. |
| failed | Show the unavailable/failure message and allow a deliberate retry or explicit specialist choice. |

`fallback: true` means evidence-based fallback output, not successful model
synthesis. It can coexist with complete or partial source coverage. Always display
the limitations. Older standalone responses may omit status; retain their existing
rendering and use `ok` where available rather than requiring new metadata.

## Structured results and citations

Automatic SQL data is nested under `data.sql`; Knowledge data under
`data.knowledge`. Additional results for the same specialist use keys
`task:<task-id>`. Explicit SQL retains its existing top-level `data.rows` structure.
Render result groups dynamically instead of assuming one SQL table per request.

SQL groups can include `rows`, `sql`, `parameters`, and `query_status`. A rejected
query can instead include `attempted_sql`. Only label a query executed when its
query status says so; diagnostics are not evidence of successful SQL execution.
Failed tasks may expose these authorized query diagnostics without result rows.

Combined citations are renumbered consistently across tasks. Resolve `[S#]`
against the response's `evidence` array only. Do not reuse citation indexes from a
previous turn or make up document/page links for database sources. Escape source
titles, excerpts, row values, and all generated text; render Markdown through the
existing safe renderer. Keep diagnostic traces in an optional detail view.

Illustrative partial response (values are examples, not live results):

```json
{
  "answer": "The query returned 12 products [S1]. Document guidance is unavailable.",
  "agent": "hybrid",
  "evidence": [{"citation_id":"S1","source_type":"database","source":"commerce.products","content":null,"metadata":{}}],
  "data": {"sql":{"rows":[{"count":12}],"query_status":"executed"}},
  "metadata": {"ok":false,"status":"partial","selected_route":"hybrid","fallback":true,"limitations":["Document evidence unavailable."]}
}
```

## HTTP failures and timeouts

HTTP 200 means a valid response envelope, not necessarily completed work. Inspect
metadata status. HTTP 401 requires sign-in, 403 is a denied source/permission,
422 is invalid request input, and 503 is service unavailability. Never automatically
reroute a 403 through another role or silently remove requested evidence sources.
Error `detail` may be a string or a FastAPI validation-error array.

The unified backend chat budget is 120 seconds. Set the browser/transport timeout
to at least 135 seconds and verify the actual tunnel/rewrite/proxy limits support
that interval. If a proxy times out, show a transport error; do not translate it
into a successful empty answer. Avoid automatic client retries: the backend already
has bounded retries and replanning, and a retried request can duplicate work.

```ts
const response = await fetch("/api/agents/chat", {
  method: "POST",
  credentials: "same-origin",
  headers: {"Content-Type": "application/json", "ngrok-skip-browser-warning": "1"},
  signal: AbortSignal.timeout(135_000),
  body: JSON.stringify({question, agent_mode: "auto", conversation_id: conversationId})
});
// Check response.ok, parse JSON, then inspect result.metadata.status.
```

## Frontend migration and verification

1. Replace duplicate Auto/Agentic controls with one Auto default; keep the alias
   accepted in any existing saved client requests.
2. Add conversation IDs and New conversation/sign-out resets.
3. Handle partial, clarification, failed, and fallback states explicitly.
4. Support nested/dynamic result groups and response-wide citations.
5. Keep the separate Report/Dashboard interfaces. Replace Report's Combined source
   option with Auto (`source_mode=orchestrated`), and send a separate report
   `conversation_id`; see the [Report multipart contract](report-source-orchestration.md).
6. Test Knowledge-only users, SQL denial, both dependency directions, follow-ups,
   provider outage, sign-out, and proxy timeout behavior.

The bundled client implements mode/context/status/result-group updates. A separate
teammate-owned Vercel frontend must adopt this contract independently; its deployed
behavior has not been verified or changed by this local implementation.
