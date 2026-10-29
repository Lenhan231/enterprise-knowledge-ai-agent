# Spec: Bounded Agent Execution

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


Module id: `bounded-execution`
Status: Approved and implemented under the Knowledge/SQL amendment; see the final implementation document for acceptance gaps. Depends on: `request-planning`.
Scope authority: [approved capability map](CAPABILITY-MAP-agent-orchestration.md).

## Objective

Execute focused plans with dependencies, inspect outcomes, and recover from
recoverable failures within finite limits. Preserve useful authorized results
instead of losing the entire response when one independent task fails.

## Proposed execution contract

- Extend the existing LangGraph workflow with execute/inspect/revise transitions;
  retain the existing agents. Do not create a separate orchestration service.
- Dispatch each task using a copy of the original request with its focused question
  and validated task inputs. Preserve verified subject, identity, permissions,
  conversation ID, retrieval method, and trusted data scope. Strip client attempts
  to overwrite internal plans/results/history/budgets.
- Independent tasks may run concurrently; dependent tasks run only after their
  required predecessor output is usable. Carry referenced values as structured
  data with source provenance, never by interpolating untrusted text into SQL.
- Normalize existing result shapes into outcomes: complete, partial, empty,
  clarification-required, denied, timed-out, or failed. Missing `ok` cannot hide
  an explicit failure/clarification status. No result is treated as complete merely
  because an agent returned text.
- Inspect source coverage and task status. Permit one bounded plan revision for
  fixable task formulation or a targeted additional evidence lookup. Do not claim
  that outcome inspection proves arbitrary semantic correctness.
- Retry transient failures once when useful. Empty evidence, missing schema fields,
  unsupported business questions, and authorization denial are not transient.
  Failed dependencies block descendants while unrelated work may finish.
- Denials never cause a search through other identities, roles, or data sources to
  bypass access checks. Return a policy-consistent denial; do not expose denied
  data through traces, memory, summaries, or partial responses.

## Proposed budgets for approval

| Limit | Default |
|---|---:|
| Tasks in a validated plan | 4 |
| Total specialist invocations, including retries and revised tasks | 6 |
| Concurrent specialist tasks | 2 |
| Plan revisions after initial execution | 1 |
| Retry per task | 1 |
| Planning/repair provider call | 15 seconds per call |
| Specialist invocation | 60 seconds, capped by remaining request time |
| Final synthesis | 20 seconds, capped by remaining request time |
| Entire unified chat request, including history lock waiting | 120 seconds |

An exhausted budget returns explicit partial/failed status, not an infinite loop.
All repairs/retries share the global deadline. Existing dedicated report-file
generation keeps its separate behavior; reports selected in unified chat obey
the chat deadline. Internal report work must observe remaining time too.

Async timeouts alone do not stop synchronous work in a thread. Propagate provider,
HTTP, and database timeouts where supported; cancel awaitable siblings on request
cancellation; do not launch new retries while abandoned blocking work can pile up.
Document any unavoidable non-cancellable boundary and retain bounded in-flight work.

## Trace and result boundary

Expose bounded per-request task IDs, agents, dependencies, attempts, durations,
statuses, revision reason, and limitations in result metadata. Do not use shared
`last_destination` as the authoritative per-request outcome under concurrency.
Reuse existing latency and agent-run recording; summarize partial/failed outcomes
correctly. Do not persist raw prompts, document bodies, or SQL row contents in
telemetry. Preserve the public `AgentResult` envelope.

## Tech stack and project structure

Python >=3.11 asyncio, existing LangGraph and Pydantic. Main changes remain in
`src/core/agents/router.py`, small supporting helpers/models if justified, existing
API wrappers, and existing provider timeout boundaries. Tests remain in `tests/`.

## Commands

```powershell
$env:PYTHONPATH = 'src'
.\.venv\Scripts\python.exe -m unittest discover -s tests -p 'test_bounded_execution.py' -v
.\.venv\Scripts\python.exe -m unittest discover -s tests -p 'test_analytics_agents.py' -v
.\.venv\Scripts\python.exe -m unittest discover -s tests -p 'test_agent_monitoring.py' -v
git diff --check
```

The first test module is planned. No live database is needed for budget tests.

## Code style

Preserve the existing async specialist contract:

```python
return {"knowledge": await self.knowledge_agent.run(state["request"])}
```

Use typed outcome data and a small bounded loop/graph. Avoid a plugin registry,
general-purpose scheduler, or duplicated workflows.

## Testing strategy and success criteria

Use async `unittest` with fake agents and short injected budgets. Prove independent
parallel execution and both dependency directions, exact focused subrequests,
identity preservation, retry/revision limits, cancellation, partial success,
denial handling, blocked descendants, concurrent-request trace isolation, and
deadline exhaustion. All dispatch/security/budget fixtures must pass. Replanning
must make a bounded change rather than repeating the same failed request.

## Boundaries

- Always: preserve SQL validation/read-only restrictions and document ACLs; count every attempt.
- Ask first: larger budgets, new dependencies, deployment changes, or new persistent telemetry fields/schema.
- Never: retry denied work through another role, relax validation to recover, or report partial work as complete.

## Open decisions for approval

Approve the budgets above and the shorter limit for automatically selected reports
compared with the dedicated report-download endpoint.
