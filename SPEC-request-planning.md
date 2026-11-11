# Spec: Unified Request Planning

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


Module id: `request-planning`
Status: Approved and implemented under the Knowledge/SQL amendment; see the final implementation document for acceptance gaps. Depends on: `conversation-context`.
Scope authority: [approved capability map](CAPABILITY-MAP-agent-orchestration.md).

## Objective

Make auto and agentic one automatic experience that selects supported agents and
decomposes the user's objective into focused, executable tasks. A mixed question
must not simply be copied in full to Knowledge and SQL.

## Proposed behavior and provider contract

- Canonical public mode: `auto`, labeled "Auto" in the clients; retain `agentic`
  as an API compatibility alias with identical planning/execution semantics.
  Explicit `knowledge`, `sql`, `dashboard`, and `report` remain available.
- Use one validated model planning call in unified mode. Existing rules support
  narrow unambiguous provider-failure fallbacks; they must not silently override
  a valid model plan because a broad keyword matched.
- Allowed task agents are Knowledge, SQL analytics, Dashboard, and Report.
  Dashboard currently means inventory control, not arbitrary chart generation.
  Unsupported visualizations return a capability explanation or an appropriate
  supported data task, never an unrelated inventory dashboard.
- A plan contains the resolved objective, output intent, focused tasks with stable
  IDs, agent, question, dependency IDs, and typed references to needed predecessor
  results; or a targeted clarification. Preserve entities, metrics, time ranges,
  comparisons, filters, requested output, and language from the user's request.
- Validate allowed agents, bounded question sizes, unique IDs, existing dependency
  references, acyclic dependencies, task count, and compatibility with explicit
  modes before any tool dispatch. The plan cannot supply identity or raw SQL.
- Separate source requirements from presentation: asking for a report does not
  remove SQL/document obligations. The existing report source-mode contract must
  select documents, analytics, or combined accordingly. Reuse prior task evidence
  when supported; do not blindly repeat a complete workflow inside ReportAgent.
- Explicit specialist modes skip multi-agent selection but still use context and
  existing authorization. If they cannot fulfill the requested combination,
  explain the mismatch without silently widening the selected mode.
- Do not treat a self-reported confidence score as a calibrated probability.
  Clarify missing material scope or unresolved ambiguity, not merely low confidence.
- Provider failure or malformed output permits at most one repair attempt within
  execution budgets. A safe deterministic single-task fallback is allowed; do not
  send an unsplit mixed question to both agents as a fallback. When decomposition
  is unavailable, report that limitation rather than blaming clear user wording.
- Plan revision takes the original objective, validated prior plan, and bounded
  task outcomes. It returns a validated remaining plan without modifying completed
  results or expanding the authorized/requested scope. Execution owns revision limits.

## Examples and success criteria

| User objective | Required decomposition |
|---|---|
| Compare 2022 and 2021 revenue and explain the change using reports | SQL: revenue comparison for those years. Knowledge: documentary explanations for that company/time range. Synthesis: separate observed change from documented explanation; do not infer causation. |
| Find the categories with most stockouts, then retrieve the policies relevant to those categories | SQL: supported stockout ranking. Knowledge: focused lookup using validated returned categories; depends on SQL. Clarify first if the inventory snapshot scope is genuinely unresolved. |
| Read the policy threshold, then count records exceeding it | Knowledge: cited threshold with units/scope. SQL: structured task using that verified value; depends on Knowledge. Missing threshold blocks the count rather than inventing one. |
| Show inventory dashboard and explain its flags using policy | Dashboard and focused Knowledge task; retain dashboard payload and cite the explanation. |

All mixed fixtures must show different, source-appropriate subquestions and retain
the original filters. Tests must inspect dispatched questions, not only route labels.
All four destinations and both dependency directions must be represented in EN/VI.

## Tech stack and project structure

Existing Python >=3.11, Pydantic 2.11.7, LangGraph >=1.2.4, and Groq provider.
Contracts belong with `src/core/models/`; planning and graph integration stay in
`src/core/agents/`; prompts follow `src/core/prompts/`. Update API and client mode
declarations in their existing files. No new planning framework.

## Commands

```powershell
$env:PYTHONPATH = 'src'
.\.venv\Scripts\python.exe -m unittest discover -s tests -p 'test_request_planning.py' -v
.\.venv\Scripts\python.exe -m unittest discover -s tests -p 'test_agentic_agent.py' -v
.\.venv\Scripts\python.exe -m unittest discover -s tests -p 'test_app_chat.py' -v
git diff --check
```

The first test module is planned; update legacy selection tests to the new contract.

## Code style

Use the existing Pydantic boundary-validation style:

```python
result = AgentResult.model_validate(state["result"])
```

Use small typed plan objects, literal agent names, explicit validation, and async
provider handling compatible with existing sync and async test providers.

## Testing strategy

Use `unittest` and fake model outputs to cover decomposition, alias equivalence,
invalid/cyclic plans, query scope preservation, no unconditional keyword override,
unavailable agents, malformed JSON, provider failure, and clarification contracts.
Keep model-quality measurements separate from deterministic contract tests.

## Boundaries

- Always: validate model output and preserve original scope and verified identity.
- Ask first: new providers/dependencies, arbitrary chart support, or broader SQL capabilities.
- Never: execute model-produced SQL directly, infer permissions from a plan, or silently drop a requested source.

## Open decisions for approval

Approve `auto` as the canonical label with `agentic` retained as an alias, and the
proposed bounded fallback behavior when planning is unavailable.
