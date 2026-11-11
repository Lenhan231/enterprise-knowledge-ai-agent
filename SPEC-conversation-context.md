# Spec: Conversation Context

> Approved follow-up (2026-10-29): Report retains its separate interface and now
> reuses the bounded Knowledge/SQL graph for Auto source collection. The new
> `orchestrated` source mode replaces the Combined UI option; `combined` remains
> an API alias. Automatic chat still does not select Report or Dashboard.
> See [Report source orchestration](docs/technical/report-source-orchestration.md)
> for requirements, behavior, limits, and verification. This amendment supersedes
> earlier Report source-collection exclusions in this document.

> Scope amendment approved by the user on 2026-10-29: unified Auto/Agentic planning
> and execution cover Knowledge and SQL only. Report and Dashboard remain standalone
> and are excluded from automatic selection, decomposition, report handoffs, and new
> acceptance targets. Their existing explicit paths receive regression checks only.
> Any older all-four-agent/report-handoff requirements below are superseded.
> Also deliver a comprehensive implementation and validation document at
> `docs/technical/agent-orchestration-implementation.md`. Task breakdown approved.


Module id: `conversation-context`
Status: Approved and implemented under the Knowledge/SQL amendment; see the final implementation document for acceptance gaps. Depends on: none.
Scope authority: [approved capability map](CAPABILITY-MAP-agent-orchestration.md).

## Objective

Resolve follow-ups such as "compare that with last year" using recent turns from
the same authenticated user and conversation. Missing context produces a specific
clarification instead of guessing the entity, metric, or year.

## Proposed behavior and interface

- Keep `AgentRequest.conversation_id` optional. No ID means a stateless request.
- Add a small server-owned context store to the existing runtime, keyed by verified
  subject and conversation ID, with a permission/role fingerprint. A changed
  fingerprint invalidates prior context before it can be used.
- Proposed limits: six completed exchanges per conversation, 12,000 total retained
  characters, 30-minute idle expiry, and at most 100 retained conversations per
  process. Evict expired/least-recently-used entries; no new database or dependency.
- Store bounded user text and response summaries/explicit scope, not credentials,
  complete SQL rows, or retrieved document bodies. Prior assistant claims are
  context, never new evidence. Recheck current permissions on every request.
- Supply planning with recent turns and their provenance. Preserve the original
  question separately from any standalone interpretation. Reject client metadata
  that attempts to provide trusted history, identity, or authorization scope.
- Serialize requests within a conversation so concurrent turns cannot consume
  half-written state. Different conversations remain independent. Waiting counts
  toward the request deadline defined in bounded-execution.
- Streamlit creates an opaque conversation ID per signed-in session, sends it on
  chat requests, and resets local history/ID on sign-out or New conversation.
  Apply the same behavior to the bundled web chat where supported.
- This is process-local prototype memory: restart, eviction, and multiple workers
  can lose context. On loss, clarify rather than fabricate continuity. Durable
  distributed memory is explicitly outside this version.

## Tech stack and project structure

Python >=3.11, existing Pydantic 2.11.7 and FastAPI 0.136.3; standard library memory
and synchronization. Reuse `src/core/models/agents.py`, `src/core/agents/`,
`src/app/agents.py`, `src/core/agents/main.py`, and the existing demo clients in
`src/core/agents/streamlit_ui.py` and `src/app/static/`. Tests live in `tests/`.

## Commands

Run from repository root in PowerShell:

```powershell
$env:PYTHONPATH = 'src'
.\.venv\Scripts\python.exe -m unittest discover -s tests -p 'test_conversation_context.py' -v
.\.venv\Scripts\python.exe -m unittest discover -s tests -p 'test_streamlit_ui.py' -v
git diff --check
```

`test_conversation_context.py` is a planned test module, not an existing passing check.

## Code style

Keep the existing typed request objects and async agent boundaries. A scoped
question uses the established Pydantic copy pattern, preserving identity:

```python
subrequest = request.model_copy(update={"question": resolved_question})
```

Use snake_case functions, small helpers, and explicit bounds. Do not introduce a
generic memory framework or let metadata overwrite trusted fields.

## Testing strategy and success criteria

Use `unittest`, fake clocks, and async tests without real providers or a database.
Verify EN/VI follow-ups retain the referenced entity/year; context absent or
ambiguous asks for only the missing information. Verify cross-user isolation even
with identical conversation IDs, permission changes, expiry, eviction, size
limits, same-conversation concurrency, stateless calls, and client reset behavior.
All isolation cases must pass. No historical answer is accepted as source evidence.

## Boundaries

- Always: derive ownership from verified identity; bound retention; preserve current authorization.
- Ask first: durable history, database migrations, new dependencies, or increased retention.
- Never: use client-submitted roles/history as trusted context or retain secrets.

## Open decisions for approval

Approve the proposed process-local limits and documented restart/multi-worker
limitations. Durable conversation memory would require a separate scope decision.
