# Unified Agent Orchestration: Implementation Tasks

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


Status: Implementation and local demo verification complete; live acceptance target remains unmet (T21).
Authority: [approved plan](agent-orchestration-plan.md) and
[approved module specifications](../CAPABILITY-MAP-agent-orchestration.md).

Execute in the listed order, one focused behavior slice at a time. Each task below
has at most five planned files; a newly discovered broader change must be split
before editing. Repeated files across tasks are intentional incremental work.
New helper/test filenames are proposed locations, not a requirement to create
abstractions when the existing file cleanly fits the behavior.

## Execution and verification conventions

Run commands from the repository root in PowerShell after setting
`$env:PYTHONPATH = 'src'`. Every Python invocation below uses
`.\.venv\Scripts\python.exe`; no global Python installation is assumed.
Tests listed for new modules must be created and run with a nonzero case count.

For each behavior slice: write a focused failing test, implement the smallest
complete change, run the named checks, and record the outcome here. Validate the
affected earlier paths when integration changes them. Do not add production
dependencies, migrate data, commit/push, deploy remotely, or change approved limits
without applicable authorization. Runtime code remains untouched until task approval.

### Baseline and request boundary

- [x] T01: Record focused baseline and local runtime inventory.
  - Module: orchestration-evaluation (baseline prerequisite for all modules).
  - Depends on: task-list approval.
  - Acceptance: record router/API/report/Streamlit baseline results, existing import
    failures, relevant callers, local service health/listeners, and installed
    Streamlit availability without printing secrets or restarting services.
  - Verify: `.\.venv\Scripts\python.exe -m unittest discover -s tests -p 'test_agentic_agent.py' -v`;
    repeat with `test_analytics_agents.py`, `test_app_chat.py`, `test_report_agent.py`,
    and `test_streamlit_ui.py`. Use `Get-NetTCPConnection -State Listen` and
    `.\.venv\Scripts\python.exe -m pip show streamlit` for read-only inventory.
  - Files: this task record only; runtime inventory is summarized without credentials.

- [x] T02: Protect server-owned orchestration fields at both API boundaries.
  - Module: conversation-context/request-planning prerequisite.
  - Depends on: T01.
  - Acceptance: client metadata cannot supply trusted history, identity, task plans,
    predecessor results, or execution budgets; accepted retrieval/source options
    retain their existing meaning. Use one shared validation helper if needed.
  - Verify: `.\.venv\Scripts\python.exe -m unittest discover -s tests -p 'test_app_chat.py' -v`;
    repeat with `test_orchestration_api.py`, covering both entry points.
  - Files: `src/core/models/agents.py`, `src/core/agents/main.py`, `src/app/agents.py`,
    `tests/test_app_chat.py`, `tests/test_orchestration_api.py`.

- [x] T03: Enforce verified document scope before Knowledge execution.
  - Module: bounded-execution security prerequisite.
  - Depends on: T02.
  - Acceptance: absent document permission/roles fail closed for both answer and
    evidence retrieval; valid identities retain role-filtered retrieval. No new SQL
    privileges or broader document visibility are introduced.
  - Verify: `.\.venv\Scripts\python.exe -m unittest discover -s tests -p 'test_orchestration_access.py' -v`;
    repeat with `test_report_agent.py` and `test_app_chat.py` for affected behavior.
  - Files: `src/core/agents/knowledge_agent.py`, `tests/test_orchestration_access.py`,
    affected identity fixtures in `tests/test_app_chat.py` and `tests/test_report_agent.py`.

### Conversation context

- [x] T04: Add bounded authenticated history and conversation serialization.
  - Module: conversation-context.
  - Depends on: T03.
  - Acceptance: six exchanges/12,000 characters, 30-minute expiry, 100-conversation
    capacity; subject/permission isolation; stateless no-ID calls; bounded active
    locks and waiters; cancellation cleanup; active keys never lose serialization.
  - Verify: `.\.venv\Scripts\python.exe -m unittest discover -s tests -p 'test_conversation_context.py' -v`
    with fake time, concurrent calls, permission changes, eviction, and expiry.
  - Files: `src/core/agents/conversation_context.py`, `src/core/agents/router.py`,
    `tests/test_conversation_context.py`.

- [x] T05: Carry/reset conversation IDs in both existing clients.
  - Module: conversation-context.
  - Depends on: T04.
  - Acceptance: Streamlit and bundled web chat send an opaque session conversation
    ID; New conversation and sign-out clear local state/ID. Request serialization
    is tested. Prior answer text remains context, not retrieved evidence.
  - Verify: `.\.venv\Scripts\python.exe -m unittest discover -s tests -p 'test_streamlit_ui.py' -v`;
    repeat with `test_orchestration_clients.py`; inspect sign-out/reset behavior at
    the final live demo checkpoint.
  - Files: `src/core/agents/streamlit_ui.py`, `src/app/static/app.js`,
    `src/app/static/index.html`, `tests/test_streamlit_ui.py`,
    `tests/test_orchestration_clients.py`.

### Unified planning

- [x] T06: Define and validate focused task plans and dependency references.
  - Module: request-planning.
  - Depends on: T04.
  - Acceptance: typed agent/question/dependency/result-reference contracts; bounded
    task/question sizes; reject cycles, missing dependencies, duplicate IDs,
    unsupported agents, raw executable SQL, and authorization fields.
  - Verify: `.\.venv\Scripts\python.exe -m unittest discover -s tests -p 'test_request_planning.py' -v`
    with EN/VI mixed plans, both dependency directions, and malformed plans.
  - Files: `src/core/models/agent_plan.py`, `tests/test_request_planning.py`.

- [x] T07: Implement context-aware planning with safe repair/fallback.
  - Module: request-planning.
  - Depends on: T06.
  - Acceptance: one initial model plan preserves objective/entities/years/filters;
    independent mixed questions become distinct source-appropriate subtasks;
    dependency references are explicit; ambiguity yields targeted clarification.
    One repair is allowed; valid plans are not overridden by broad rules.
    Provider outage cannot fall back to unsplit dual dispatch. History cannot
    authorize tools or provide fresh factual evidence.
  - Verify: `.\.venv\Scripts\python.exe -m unittest discover -s tests -p 'test_request_planning.py' -v`
    using controlled sync/async providers, malformed output, outage, and follow-ups.
  - Files: `src/core/agents/planning.py`, `src/core/prompts/agent_plan.py`,
    `tests/test_request_planning.py`.

- [x] T08: Route auto and agentic through the same planner.
  - Module: request-planning.
  - Depends on: T07.
  - Acceptance: `run` and the `agentic` compatibility mode share planning;
    explicit modes retain their bypass; both API constructors supply the actual
    shared runtime behavior; all four supported specialist destinations are selectable.
  - Verify: `.\.venv\Scripts\python.exe -m unittest discover -s tests -p 'test_agentic_agent.py' -v`;
    repeat with `test_analytics_agents.py` and `test_orchestration_api.py`.
  - Files: `src/core/agents/router.py`, `src/core/agents/main.py`,
    `src/app/agents.py`, `tests/test_agentic_agent.py`, `tests/test_analytics_agents.py`.

### Bounded execution

- [x] T09: Execute focused independent tasks and normalize outcomes.
  - Module: bounded-execution.
  - Depends on: T08.
  - Acceptance: at most two tasks run concurrently; each request copy keeps verified
    scope; independent failure preserves useful siblings; explicit empty/failure/
    clarification/denial statuses are never inferred complete from returned prose.
  - Verify: `.\.venv\Scripts\python.exe -m unittest discover -s tests -p 'test_bounded_execution.py' -v`
    inspecting actual dispatched subquestions, scope, parallelism, and outcomes.
  - Files: `src/core/agents/router.py`, `src/core/agents/execution.py`,
    `tests/test_bounded_execution.py`.

- [x] T10: Execute dependent tasks using validated predecessor outputs.
  - Module: bounded-execution.
  - Depends on: T09.
  - Acceptance: SQL->Knowledge and Knowledge->SQL tasks consume only referenced,
    bounded, provenance-bearing values; blocked/empty predecessors prevent dependent
    execution; values are never interpolated into raw SQL or trusted instructions.
  - Verify: `.\.venv\Scripts\python.exe -m unittest discover -s tests -p 'test_bounded_execution.py' -v`
    covering ordering, missing values, hostile predecessor text, and preserved filters.
  - Files: `src/core/agents/execution.py`, `src/core/agents/planning.py`,
    `src/core/agents/sql_analytics_agent.py`, `tests/test_bounded_execution.py`,
    `tests/test_orchestration_access.py`.

- [x] T11: Add bounded inspection, transient retry, and one replan.
  - Module: bounded-execution.
  - Depends on: T10.
  - Acceptance: enforce four tasks per plan, six total specialist attempts, one retry
    per task, one revision, and two concurrent tasks; completed work is retained;
    repeated/no-progress plans stop; denial, missing schema/evidence, and unresolved
    scope cannot trigger futile retry loops or role-bypass routes.
  - Verify: `.\.venv\Scripts\python.exe -m unittest discover -s tests -p 'test_bounded_execution.py' -v`
    with deterministic counters and revised-plan fixtures.
  - Files: `src/core/agents/router.py`, `src/core/agents/execution.py`,
    `src/core/agents/planning.py`, `tests/test_bounded_execution.py`.

- [x] T12: Enforce request deadlines and bound blocking provider work.
  - Module: bounded-execution.
  - Depends on: T11.
  - Acceptance: global 120-second deadline includes history waiting; planning/repair
    <=15 seconds per call, specialists <=60, synthesis <=20, each capped by remaining
    time. SDK retries cannot secretly exceed limits; timed-out thread work stays
    accounted for and cannot accumulate through retries; async cancellation cleans up.
  - Verify: `.\.venv\Scripts\python.exe -m unittest discover -s tests -p 'test_orchestration_timeouts.py' -v`;
    repeat with `test_bounded_execution.py`, using short injected budgets and a
    controllably blocking fake provider rather than long sleeps.
  - Files: `src/core/agents/execution.py`, `src/core/agents/planning.py`,
    `src/core/llm/groq_provider.py`, `tests/test_orchestration_timeouts.py`,
    `tests/test_bounded_execution.py`.

- [x] T13: Carry remaining time through specialist provider calls.
  - Module: bounded-execution.
  - Depends on: T12.
  - Acceptance: SQL generation, analytics summarization, RAG answer generation,
    and report generation honor server-owned remaining time; existing finite
    database/HTTP timeouts are retained; dedicated report endpoint behavior stays
    unchanged. Any additional deep provider boundary becomes a separate task
    rather than silently widening this task beyond five files.
  - Verify: `.\.venv\Scripts\python.exe -m unittest discover -s tests -p 'test_orchestration_timeouts.py' -v`;
    repeat affected analytics/RAG/report tests selected from the T01 baseline.
  - Files: `src/core/agents/sql_analytics_agent.py`, `src/core/agents/analytics_agent.py`,
    `src/core/rag/rag_service.py`, `src/core/agents/report_agent.py`,
    `tests/test_orchestration_timeouts.py`.

### Report/dashboard handoffs

- [x] T14: Reuse precollected evidence for dependent report tasks.
  - Module: bounded-execution/grounded-response.
  - Depends on: T13.
  - Acceptance: report assembly accepts internal validated prior outcomes without
    repeating the original mixed SQL/RAG query; authorizes every required source;
    preserves section grounding/coverage and dedicated file generation. Client
    metadata cannot inject precollected evidence. Inventory-only dashboard limits
    are represented in planning tests and preserved at dispatch.
  - Verify: `.\.venv\Scripts\python.exe -m unittest discover -s tests -p 'test_report_agent.py' -v`;
    repeat with `test_orchestration_reports.py` and `test_request_planning.py`.
  - Files: `src/core/agents/report_agent.py`, `src/core/reports/sources.py`,
    `src/core/agents/execution.py`, `tests/test_orchestration_reports.py`,
    `tests/test_report_agent.py`.

### Grounded response and integration

- [x] T15: Assemble response-wide citations and validate synthesis.
  - Module: grounded-response.
  - Depends on: T14.
  - Acceptance: local citation collisions map consistently to unique response IDs;
    synthesis uses original objective and usable outcomes; reject unknown citations
    and mechanically detectable changed values/units; required source coverage and
    limitations survive assembly. No claim of complete semantic proof from ID checks.
  - Verify: `.\.venv\Scripts\python.exe -m unittest discover -s tests -p 'test_grounded_response.py' -v`
    with mixed-source collisions, unsupported references, changed values, and EN/VI.
  - Files: `src/core/agents/response.py`, `src/core/agents/router.py`,
    `tests/test_grounded_response.py`, `tests/test_agentic_agent.py`.

- [x] T16: Return honest fallback/status and preserve structured payloads.
  - Module: grounded-response.
  - Depends on: T15.
  - Acceptance: provider failure produces cited supported findings plus explicit
    gaps; no blind concatenation of raw agent answers; `complete`/`partial`/
    `clarification_required`/`failed` and `ok` agree. SQL export, dashboard payload,
    and report information remain available without leaking denied evidence.
  - Verify: `.\.venv\Scripts\python.exe -m unittest discover -s tests -p 'test_grounded_response.py' -v`;
    repeat with `test_analytics_agents.py` and `test_streamlit_ui.py`.
  - Files: `src/core/agents/response.py`, `src/core/agents/router.py`,
    `src/core/agents/sql_analytics_agent.py`, `tests/test_grounded_response.py`,
    `tests/test_analytics_agents.py`.

- [x] T17: Align API defaults, telemetry, and request-local traces.
  - Module: bounded-execution/grounded-response.
  - Depends on: T16.
  - Acceptance: `auto` is the canonical API default; alias remains accepted;
    per-request traces/status drive results and telemetry under concurrency;
    shared `last_destination` is not authoritative; traces exclude prompts, rows,
    document bodies, and inaccessible evidence. No telemetry schema migration.
  - Verify: `.\.venv\Scripts\python.exe -m unittest discover -s tests -p 'test_orchestration_api.py' -v`;
    repeat with `test_agent_monitoring.py` and `test_app_chat.py`.
  - Files: `src/app/agents.py`, `src/core/agents/main.py`,
    `src/core/agents/router.py`, `tests/test_orchestration_api.py`,
    `tests/test_agent_monitoring.py`.

- [x] T18: Expose one Auto experience in Streamlit and bundled web chat.
  - Module: grounded-response/orchestration-evaluation.
  - Depends on: T17 and T05.
  - Acceptance: one Auto choice plus explicit specialists; no duplicate agentic
    choice; legacy API alias still works; Streamlit chat timeout is 135 seconds;
    partial/fallback/clarification states and citations render clearly; users with
    document-only access may use permitted Auto paths without analytics privileges.
  - Verify: `.\.venv\Scripts\python.exe -m unittest discover -s tests -p 'test_streamlit_ui.py' -v`;
    repeat with `test_orchestration_clients.py`; final rendered UI inspection at T24.
  - Files: `src/core/agents/streamlit_ui.py`, `src/app/static/app.js`,
    `src/app/static/index.html`, `tests/test_streamlit_ui.py`,
    `tests/test_orchestration_clients.py`.

### Evaluation and delivery

- [x] T19: Add representative bilingual orchestration fixtures.
  - Module: orchestration-evaluation.
  - Depends on: T18.
  - Acceptance: at least 24 reviewed EN/VI scenarios cover all supported destinations,
    independent/dependent combinations, follow-ups, ambiguity, failures, and access
    isolation; label expected tasks/scopes and success conditions before live runs.
    Preserve historical datasets/labels and distinguish safe abstention from completion.
  - Verify: `.\.venv\Scripts\python.exe -m unittest discover -s tests -p 'test_orchestration_evaluation.py' -v`
    validates fixture coverage, unique IDs, expected sources/scopes, and dependencies.
  - Files: `data/evaluation/orchestration_cases.json`,
    `tests/test_orchestration_evaluation.py`.

- [x] T20: Evaluate the actual unified runtime with fresh artifacts.
  - Module: orchestration-evaluation.
  - Depends on: T19.
  - Acceptance: benchmark CLI supports `--configuration unified --output <fresh-dir>`;
    evaluates the same runtime construction/planner as the API; route-only stubs
    are labeled separately; records hashes/model/settings/fallback/timing/errors;
    rejects output overwrite and never treats zero cases as success.
  - Verify: `.\.venv\Scripts\python.exe -m unittest discover -s tests -p 'test_orchestration_evaluation.py' -v`;
    repeat with `test_agent_route_evaluation.py` and `test_agent_benchmarks.py`;
    `.\.venv\Scripts\python.exe scripts/agents/benchmark_router_25.py --help`.
  - Files: `scripts/agents/benchmark_router_25.py`,
    `tests/test_orchestration_evaluation.py`, `tests/test_agent_route_evaluation.py`.

- [ ] T21: Run the 50-case benchmark and eight authorized live workflows.
  - Module: orchestration-evaluation.
  - Depends on: T20.
  - Acceptance: report actual results against >=90% accuracy, macro F1 >=0.85,
    hybrid recall >=0.90, all access checks passing, and >=7/8 live task contracts
    fulfilled. Review factual grounding for unsupported claims separately. Include
    independent mixed tasks, both dependency directions, follow-up, Report,
    Dashboard, and denial. Provider/source unavailability leaves the corresponding
    acceptance check incomplete; it is never replaced with a mock success.
  - Verify: `.\.venv\Scripts\python.exe scripts/agents/benchmark_router_25.py --configuration unified --output artifacts/evaluation/router-unified-20261029`;
    choose a fresh suffix if needed. Execute predeclared live cases through the
    authenticated API and inspect returned rows, document evidence, and task traces.
  - Files: new benchmark `results.json`, new live-workflow artifact, and reviewed
    summary under a fresh run directory in `artifacts/evaluation/`; this task record.

- [x] T22: Complete regression, quality/security review, and targeted fixes.
  - Module: all modules.
  - Depends on: T21 (record unavailable live checks honestly; do not skip review).
  - Acceptance: all new module tests and affected regression tests pass; Python
    compilation and whitespace checks pass; apply code-review-and-quality and
    Ponytail review principles to the connected change. Fix any new finding in
    a focused <=5-file follow-up slice and rerun only affected checks. Preserve
    existing SQL validation, report grounding, and authorization boundaries.
  - Verify: run the module commands in the five approved specs plus affected
    analytics/API/report/monitoring/benchmark/Streamlit suites;
    `.\.venv\Scripts\python.exe -m compileall -q src/core/agents src/core/models src/core/prompts src/core/llm src/core/reports src/app`;
    `git diff --check`. Record known unrelated baseline failures separately.
  - Files: test/review findings in this record; any remediation gets an explicit
    follow-up entry naming its files, acceptance check, and verification outcome.

- [x] T23: Document behavior, usage, and evidence limits.
  - Module: orchestration-evaluation.
  - Depends on: T22.
  - Acceptance: explain unified mode and alias, focused/dependent subtasks, supported
    dashboard/report limits, history retention/process-local behavior, budgets,
    partial/fallback status, actual benchmark results, and live evidence gaps.
    Keep deployment claims limited to what was actually verified locally.
  - Verify: check documented commands/URLs against actual CLI/runtime behavior;
    validate local document links and `git diff --check`.
  - Files: `README.md`, `docs/technical/agents-and-evaluation.md`,
    `tasks/todo.md`, `tasks/agent-orchestration-plan.md`,
    `CAPABILITY-MAP-agent-orchestration.md`.

- [x] T24: Automatically start and verify the Streamlit agent demo.
  - Module: orchestration-evaluation.
  - Depends on: T23.
  - Acceptance: inspect listeners; reuse a verified matching backend or start one
    serving changed source; start the existing agent Streamlit UI in a hidden
    background process on loopback 8501 or an available alternative. Verify health,
    sign-in, and an authorized mixed request in the rendered UI; inspect citations,
    focused task behavior, and follow-up continuity. Leave it running and report
    working URL plus process/log details. If live acceptance is blocked by an
    external provider/source, still launch the locally working demo and clearly
    report that limitation; do not mark overall acceptance complete. No new startup
    approval is needed.
  - Verify: backend health and Streamlit `/_stcore/health`; authenticated UI smoke;
    use these launch commands with hidden `Start-Process` helpers and separate logs:
    `.\.venv\Scripts\python.exe -m uvicorn app.main:app --env-file .env --host 127.0.0.1 --port 8000`;
    `.\.venv\Scripts\python.exe -m streamlit run src/core/agents/streamlit_ui.py --server.address 127.0.0.1 --server.port 8501 --server.headless true`.
    Do not kill unrelated listeners or print credentials.
  - Files: runtime stdout/stderr logs (ignored local files) and this task record.

## Review gate

The map, specs, technical plan, and task breakdown were approved. Implementation
and local verification were executed under the narrowed Knowledge/SQL scope.
After approval, execute these tasks autonomously in dependency order, update the
checkboxes with evidence, and proceed through verification and the already
authorized demo startup. Do not request another routine phase approval before
implementation. Material new scope/dependency/schema decisions still follow the
approved boundaries.

## Implementation evidence

- T01 baseline: 25/25 focused tests passed (3 router, 4 analytics, 9 API, 1 report, 8 Streamlit). Existing localhost listeners: backend 8000 and Streamlit 8501. Streamlit is installed.
- T14 report precollection and new dashboard routing are omitted under the approved scope amendment; standalone regression coverage is retained.

## Final implementation evidence (2026-10-29)

- Runtime scope is Knowledge/SQL only. T14 automatic report handoff was explicitly
  excluded; existing Report/Dashboard standalone paths passed regression checks.
- Focused task plans, both dependency directions, bounded retry/revision, scoped
  history, citations, numeric checks, timeouts, and client conversation resets are
  implemented. Tests are consolidated in test_conversation_context.py,
  test_request_planning.py, test_bounded_execution.py, test_orchestration_contracts.py,
  test_orchestration_evaluation.py, test_orchestration_clients.py, test_groq_failover.py,
  and affected existing suites rather than empty modules with the originally proposed names.
- Final full-suite comparison: 463 current tests versus 426 original-code tests;
  both have the same 64 failing identities and nine skipped tests. No new failures.
- T21 evaluation runs are performed: paced live-model routing 48/50, macro F1
  0.9609, hybrid recall 14/14; final-source replay reproduces all routes. The live
  eight-case batch fulfills 5/8 full contracts, below 7/8, due to evidence gaps.
  T21 stays unchecked because its overall acceptance target is not met.
- Final default-settings Streamlit AppTest completed a real combined Vietnamese
  SQL/document question with generated synthesis, two evidence sources, rendered
  tables, a Sources expander, and zero exceptions. The existing matching demo is
  running at http://127.0.0.1:8501; backend health is good on port 8000.
- Python compilation, JavaScript syntax, and git diff --check pass.
- No commit/push, remote deployment, dependency addition, database migration, or
  source-data mutation was performed. Local backend image rebuilt for the demo.
- Complete findings, artifact links, review fixes, and limits:
  docs/technical/agent-orchestration-implementation.md.
- Vercel frontend handoff: docs/technical/agent-api-frontend-contract.md.
