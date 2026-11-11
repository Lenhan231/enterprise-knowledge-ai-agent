# Capability Map: Unified Agent Orchestration

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


Status: Map and all five module specs approved by the user on 2026-10-29.
Map, specs, plan, and task breakdown approved. Knowledge/SQL implementation and
local demo verification completed; broader live acceptance remains incomplete.
See docs/technical/agent-orchestration-implementation.md for final evidence.

## Objective

Address the router limitations identified in this session: fixed one-pass dispatch,
separate auto/agentic behavior, restricted agentic destinations, brittle rule-based
selection, absent conversation-aware routing, identical full-question dispatch to
SQL and Knowledge, limited failure recovery, concatenated hybrid answers, and
insufficient representative evaluation.

## Working assumptions for review

- One automatic experience combines selection and agentic coordination across
  Knowledge, SQL, Dashboard, and Report. Explicit specialist modes remain available;
  existing auto/agentic API values should remain compatible where practical.
- Reuse the existing LangGraph runtime, agent interfaces, and security controls.
  Prefer no new dependencies or separate agent framework.
- Mixed requests produce focused specialist subtasks that preserve the original
  entities, dates, filters, and user objective. Independent tasks may run together;
  tasks needing earlier results must run in dependency order.
- Follow-up interpretation uses bounded history scoped to the authenticated user
  and conversation. History and model-generated tasks cannot grant permissions.
- Execution may inspect results and revise work within explicit step, time, and
  retry limits. Genuine ambiguity prompts a targeted clarification; missing evidence
  must not become an invented answer or repeated futile execution.
- Every dispatched subtask retains verified identity and applicable retrieval/data
  scope. Authorization denials must not be bypassed by retrying or replanning.
- Evaluation covers English and Vietnamese, all destinations, mixed and dependent
  tasks, follow-ups, provider failures, and access boundaries. Numerical targets
  and execution budgets will be proposed in the module specs, not assumed here.

## Modules

| Module id | Responsibility | Depends on |
|---|---|---|
| conversation-context | Resolve follow-ups from bounded, authorized conversation context; define context provenance and isolation. | None |
| request-planning | Unify auto/agentic selection; select all supported destinations; decompose mixed requests into focused tasks and dependencies; distinguish actionable requests from ambiguity; define validated plan and revision contracts. | conversation-context |
| bounded-execution | Dispatch scoped subrequests; run independent/dependent tasks appropriately; inspect outcomes, request bounded plan revisions, handle timeouts/retries/partial failures, and record per-request execution traces. | request-planning |
| grounded-response | Answer the original question from task results with consistent citations, explicit gaps and partial-success reporting; support synthesis failure without misleading concatenation or unsupported claims. | bounded-execution |
| orchestration-evaluation | Verify actual API/runtime behavior and mode compatibility; evaluate routing, decomposition, execution, grounded answers, access isolation, failures, and latency separately. | grounded-response |

Build order: conversation-context -> request-planning -> bounded-execution -> grounded-response -> orchestration-evaluation.

Tests accompany every module. The final evaluation module integrates and measures
the complete workflow; it does not defer earlier correctness or security checks.

These are capability boundaries, not a requirement to create five packages or
services. Plan revisions are supplied through request-planning's contract;
bounded-execution owns the loop and budgets, avoiding a circular dependency.

## Scope boundaries

- Preserve SQL validation/read-only constraints and document access filtering.
- Include API/UI mode alignment so users receive the unified behavior.
- Include supported Dashboard/Report selection and handoffs without rebuilding
  their underlying features.
- Exclude unrestricted autonomous actions, arbitrary SQL, a new analytics schema,
  new document ingestion features, and replacement of the RAG or SQL engines.
- Routing accuracy alone does not establish successful or authorized answers.

## Next gate

After map approval, write root-level SPEC-<module-id>.md documents using these
stable ids. Each module proceeds through Specify -> Plan -> Tasks -> Implement
with the requested skill's human review gates. No implementation is authorized
by approval of this map alone.

## Spec index

| Module id | Specification |
|---|---|
| conversation-context | [SPEC-conversation-context.md](SPEC-conversation-context.md) |
| request-planning | [SPEC-request-planning.md](SPEC-request-planning.md) |
| bounded-execution | [SPEC-bounded-execution.md](SPEC-bounded-execution.md) |
| grounded-response | [SPEC-grounded-response.md](SPEC-grounded-response.md) |
| orchestration-evaluation | [SPEC-orchestration-evaluation.md](SPEC-orchestration-evaluation.md) |

Additional user instruction: automatically start the agent Streamlit demo after
implementation and verification, and report its working local URL. This is part
of final acceptance, not a request to start the unchanged demo at the spec stage.
