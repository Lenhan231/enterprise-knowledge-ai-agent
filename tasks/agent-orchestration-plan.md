# Technical Plan: Unified Agent Orchestration

> 2026-10-29 Report follow-up: the standalone Report interface now uses the new
> Knowledge/SQL workflow for Auto source collection (`orchestrated`; legacy
> `combined` is an alias). Dashboard remains independent. See the
> [Report integration document](../docs/technical/report-source-orchestration.md). The user also authorized pushing
> the completed changes to main and rebuilding local Docker. Earlier completion
> notes describe the preceding stage.

> Scope amendment approved by the user on 2026-10-29: unified Auto/Agentic planning
> and execution cover Knowledge and SQL only. Report and Dashboard remain standalone
> and are excluded from automatic selection, decomposition, report handoffs, and new
> acceptance targets. Their existing explicit paths receive regression checks only.
> Any older all-four-agent/report-handoff requirements below are superseded.
> Also deliver a comprehensive implementation and validation document at
> `docs/technical/agent-orchestration-implementation.md`. Task breakdown approved.


Status: Approved and implemented under the Knowledge/SQL scope amendment; see todo.md for validation and acceptance gaps.
Authority: [approved capability map](../CAPABILITY-MAP-agent-orchestration.md)
and its five approved module specs. Final implementation and verification evidence
is recorded in [todo.md](todo.md) and the complete implementation document.

## Approach

Extend the existing LangGraph router and reuse Knowledge, SQL analytics, Inventory
Dashboard, ReportAgent, and existing providers. Use a small validated task plan,
scoped request copies, bounded execute/inspect/revise transitions, and one response
assembler. No new services, general-purpose scheduler, agent registry, dependencies,
database migrations, or separate memory framework are planned.

`auto` becomes the canonical automatic mode; `agentic` uses exactly the same path
as a compatible alias. Explicit modes retain their specialist behavior and current
authorization checks. Tests change where old behavior intentionally conflicts with
the approved contracts; unrelated broken legacy imports are documented separately.

## Dependency graph and build sequence

conversation-context -> request-planning -> bounded-execution -> grounded-response
-> orchestration-evaluation. Tests accompany each increment. Keep capability
boundaries as small functions/models in the existing runtime; they do not imply
separate deployable modules.

### 1. Establish the baseline and trusted request boundary

Inspect all AgentRouter constructors/callers, client mode declarations, provider
calls, report handoffs, and current SQL/result shapes. Run focused current tests
before changing behavior and record their outcomes. Do not silently repair unrelated
legacy tests. Inspect existing local backend/model services and Streamlit availability
without reading secrets into output or restarting unrelated processes.

Keep verified identity and accepted retrieval/source settings separate from
client metadata. Reject or ignore reserved internal fields consistently in both
API entry points. Derive all subrequest identity from the server-owned request.
Require verified document access at the Knowledge boundary as well as SQL access
at its existing boundary; missing role scope must not broaden retrieval.

Checkpoint: baseline results recorded; forged internal metadata cannot affect
identity, history, plans, results, or budgets.

### 2. conversation-context: bounded history through a real chat path

Add a small runtime-owned in-memory history store and conversation locks keyed by
subject and conversation ID. Include a permission fingerprint; enforce the approved
six-exchange, 12,000-character, 30-minute, 100-conversation limits with fake-clock
tests. Bound lock/store bookkeeping too: never evict an active lock and permit
overlapping execution for the same key. Release cancelled/expired waiters cleanly.

Supply recent context to planning; do not separately generate an evidence-bearing
answer from history. Preserve original and resolved questions. Keep no-ID calls
stateless. Retain concise turn/scope summaries rather than complete task payloads.

Wire a session conversation ID and New conversation/reset behavior into Streamlit,
then the bundled web chat. This delivers a testable follow-up path before complex
multi-agent recovery. Document process-local/restart/multi-worker limitations.

Checkpoint: real request serialization carries the ID; user/permission/concurrency
isolation and retention tests pass; absent history leads to a targeted clarification.

### 3. request-planning: one validated automatic path

Define bounded Pydantic task/plan objects alongside existing request models. A task
identifies its agent, focused question, dependencies, and typed predecessor-result
references. Original objective and requested output remain separate from tasks.
Plans contain no executable SQL, permissions, or unvalidated metadata overrides.

Use one planner prompt covering supported agents, bilingual decomposition, output
intent, evidence needs, and clarification. Validate task counts, identifiers,
dependency existence/cycles, capability limits, and question sizes before dispatch.
Pass explicit scopes to each specialist; preserve dates, entities, filters, units,
and comparative intent. The planner's revision interface accepts bounded previous
outcomes, with execution owning revision counts and deadlines.

Replace separate auto/agentic selection branches with shared planning. Retain
explicit-mode bypass. Rules provide only safe, unambiguous single-task fallbacks
when provider planning is unavailable. They no longer automatically replace valid
plans because of broad keywords. Failed mixed decomposition returns planning
unavailable, not the unchanged question sent to two agents.

Checkpoint: controlled auto/agentic outputs match; all four destinations and both
dependency directions validate; tests inspect focused task questions and scopes.

### 4. bounded-execution: first focused tasks, then recovery

First execute valid independent plans with request copies and typed outcomes.
Next add dependency-order execution: predecessor values are bounded structured
inputs with evidence provenance; they never become raw SQL substitutions. Do not
let dependent work run against an empty/failed predecessor result.

Extend the graph with outcome inspection and one optional revision. Count every
specialist attempt against six total invocations, two concurrent tasks, one retry
per task, four tasks per plan, and the one-replan cap. Distinguish transient errors
from missing schema/evidence, clarification, and denial. Preserve successful
independent results and mark blocked descendants explicitly.

Enforce the 120-second deadline beginning before conversation-lock acquisition.
Cap planning calls at 15 seconds, each specialist at 60 seconds, and synthesis at
20 seconds, always constrained by remaining time. Propagate remaining deadlines
through existing provider/HTTP/database boundaries; set finite SDK timeouts and
disable hidden SDK retries for budgeted work. Track blocking thread work until
it exits so timeout does not create unbounded retry accumulation. Cancel async
siblings and queued work on request cancellation.

Record outcomes in per-request graph state and returned metadata, not shared
`last_destination`. Reuse existing telemetry with sanitized bounded task traces
and correct partial/failed status. Keep compatibility fields only where harmless.

Checkpoint: dependency, retry, revision, denial, cancellation, timeout, and concurrent
request tests pass with injected short budgets. SQL validation stays unchanged.

### 5. Reuse Report and Dashboard without duplicating work

Keep Dashboard restricted to its actual Inventory Control capability. Preserve its
existing structured payload. Unsupported chart intents must not silently dispatch
to inventory; clarify/explain capabilities or return supported data as appropriate.

For reports requiring both data sources, represent evidence acquisition as focused
SQL/document tasks and make report assembly depend on those outcomes. Extend the
existing ReportAgent/source collector with an internal trusted precollected-input
path only where needed. Preserve normal authorization, section validation, source
coverage, and dedicated template-download behavior. Client metadata cannot inject
trusted precollected results. A report consuming evidence must not re-run the same
full mixed question through its own SQL/RAG collection cycle.

Checkpoint: supported dashboard selection renders, report source requirements
remain intact, and tests prove no duplicate collection in precollected workflows.

### 6. grounded-response: coherent answers and honest fallback

Map local evidence IDs to unique response-wide IDs before serializing agent
results. Preserve source scope, task identity, rows, units, dates, and limitations.
Synthesize against the original objective with only usable evidence. Validate known
citation IDs and mechanical value/source coverage constraints; do not equate these
checks with semantic proof.

If synthesis is unavailable/invalid, render supported findings with correct sources
and explicit missing-task/fallback labels. Normalize completion status and `ok`;
retain SQL export, dashboard rendering, and report information in structured data.

Align both API defaults and clients to one Auto option, retain the API alias, and
make transport timeouts consistent (135 seconds in Streamlit). Correct telemetry
and UI status handling for mixed partial/clarification responses.

Checkpoint: citation collisions, invalid drafts, partial results, unchanged numbers,
payload preservation, fallback labeling, and dedicated report regressions pass.

### 7. orchestration-evaluation: measure the new runtime

Extend the existing benchmark entry point with an explicit new unified-runtime
configuration and configurable fresh output path. Its current classifier monkey
patch/capture logic cannot represent the new planner; retain legacy comparisons
as labeled baselines and evaluate shared runtime construction for unified mode.
Use returned request metadata rather than shared route state. Validate CLI output
and fixture/implementation hashes before the live run.

Preserve historical 25/50-case artifacts and original labels. Record label ambiguity
without relabeling to improve scores. Add the approved 24 EN/VI orchestration cases
with task/scope contracts and separate deterministic versus live evidence.

Proposed final benchmark invocation after CLI support is implemented:

```powershell
$env:PYTHONPATH = 'src'
.\.venv\Scripts\python.exe scripts/agents/benchmark_router_25.py --configuration unified --output artifacts/evaluation/router-unified-20261029
```

This is a planned CLI, not a command that exists or has been run yet. Refuse to
overwrite existing run artifacts; choose a new suffix if the output exists.

Run the 50-case benchmark and eight authorized live scenarios against the current
corpus, including both dependency directions, follow-ups, Report, Dashboard, and
denial. Review task completion and factual grounding separately from safe abstention.
Require the approved 90% accuracy, macro F1 >=0.85, hybrid recall >=0.90, all access
checks passing, and seven/eight live task contracts fulfilled. Record unavailable
provider/source evidence as incomplete acceptance, never mock it as a live success.

Checkpoint: artifact records isolate route accuracy, task completion, reviewed
faithfulness, latency, and provider failures with reproducible settings/hashes.

### 8. Final review and automatic Streamlit startup

Run the focused module suite plus affected router, API, analytics, report, monitoring,
benchmark, and Streamlit regressions. Run Python compilation and `git diff --check`.
Review the complete change for quality, security, scope, and unnecessary abstractions.
Fix new failures; record pre-existing broader-suite issues separately. Update usage
and limitations in the existing technical docs; make no production deployment.

Inspect listeners before launching. Reuse a verified matching local backend where
it serves the changed code; otherwise start the local FastAPI backend without
disrupting unrelated services. Launch the agent Streamlit client in a hidden
background process, defaulting to loopback 8501. Use an available alternative port
if necessary. Install only the existing declared optional Streamlit extra if missing.

Verify health, sign-in, a real mixed request, rendered answer/status, and citations.
Leave the demo running and report its working URL and log/process details. Startup
is already authorized; do not ask again. No secrets in terminal output or artifacts.

## Verification mechanics

Run module test commands in the approved specs after each behavior increment. Use
`unittest`/`IsolatedAsyncioTestCase` and fake clocks/providers for deterministic
contracts; real provider and authorized database checks are a separate final layer.
Do not run all historical tests repeatedly when an unchanged baseline import failure
is already documented. Broaden checks only when a change warrants it.

No code commits, pushes, migrations, or remote deployment are implied by this plan.
Leave implementation reviewable in the working tree unless separately authorized.

## Parallel versus sequential work

Implementation follows the dependency order in one agent session. No delegated
agents are needed. Independent runtime tasks may execute concurrently as specified;
this is application behavior, not a requirement for parallel development. Tests
and fixture preparation can be performed independently once their contracts are
fixed, but integration/evaluation waits for the complete runtime.

## Main risks and mitigations

| Risk | Mitigation |
|---|---|
| Decomposition drops a year/filter or invents a policy threshold | Inspect actual dispatched questions/typed inputs in tests; require source provenance and live semantic review. |
| A nested report repeats acquisition or exceeds the budget | Internal precollected source path; propagate remaining time through report sections and provider calls. |
| Thread timeout leaves expensive work running | Finite transport/provider timeouts, retained in-flight accounting, no new overlapping retries for abandoned work. |
| Shared runtime leaks context/results between requests | Subject/permission-scoped history, conversation serialization, request-local graph state and traces. |
| Mixed results are falsely reported complete | Normalize all specialist statuses, required source coverage, and blocked task outcomes before synthesis/telemetry. |
| Provider/corpus cannot support live acceptance | Preserve failure artifacts; mark the specific acceptance checks incomplete and report the actual limitation. |
| Existing frontend/backend deployment differs from local source | Validate both API constructors and actual local demo; make no claim about remote deployment. |

## Workflow state and next gate

All pre-implementation gates were approved. The detailed dependency-ordered task
list in [todo.md](todo.md) records completed implementation and local demo checks,
plus the remaining T21 live acceptance gap. The historical Docker plan remains
preserved in `tasks/plan.md`.

The spec skill references `planning-and-task-breakdown`, but that skill is absent
from the available skill catalog and searched local skill locations. This plan
uses the spec skill's own component/dependency/order/risk/checkpoint requirements
and the available incremental-implementation guidance; no missing package behavior
is assumed. No additional skill installation is required for this plan.
