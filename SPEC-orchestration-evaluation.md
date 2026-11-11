# Spec: Orchestration Evaluation and Local Demo

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


Module id: `orchestration-evaluation`
Status: Approved and implemented under the Knowledge/SQL amendment; see the final implementation document for acceptance gaps. Depends on: `grounded-response`.
Scope authority: [approved capability map](CAPABILITY-MAP-agent-orchestration.md).

## Objective

Demonstrate that the actual unified runtime decomposes and completes authorized
requests, improves routing over the recorded baseline, and remains usable in the
Streamlit demo. Separate routing, task execution, faithfulness, and operational
limits so a route-only score cannot masquerade as answer success.

## Proposed evaluation contract

- Preserve existing 25/50-case datasets and run artifacts. Reuse/extend the current
  benchmark runner; never overwrite historical results or relabel cases to match
  predictions. Record source commit/working-tree hashes, dataset hash, provider,
  model, settings, fallback use, timings, and failures.
- Evaluate the actual API runtime construction and unified planning path, not a
  differently wired `IntentClassifier` presented as the production configuration.
  Compare raw-model, rules-only, and unified configurations where meaningful.
- Keep legacy route-label comparisons explicitly separate from new output-intent
  behavior. Review ambiguous report/dashboard labels before interpreting accuracy.
- Proposed legacy 50-case targets: at least 90% route accuracy, macro F1 >=0.85,
  and hybrid recall >=0.90. Report counts and errors as well as percentages.
  These are acceptance targets, not guarantees inferred from a small test set.
- Add at least 24 separately labeled EN/VI scenario fixtures, covering every
  supported destination, independent mixed tasks, SQL->Knowledge and
  Knowledge->SQL dependencies, follow-ups, ambiguous scope, unsupported data,
  provider failures, partial results, and role isolation. Record expected task
  questions/constraints and success conditions, not exact generated wording.
- Deterministic fake-provider/agent tests must pass all scope, ordering, budget,
  citation-membership, status, and access-isolation contracts. They establish
  mechanics, not live model quality.
- Run at least eight authorized live task scenarios, including two independent
  mixed requests, both dependency directions, a follow-up, Dashboard, Report, and
  a denial. Proposed target: all access checks pass and at least seven of eight
  fulfill their predeclared task contract; manually review factual claims against
  supplied evidence. Use EN and VI across the set. No unsupported numerical or
  policy claim is acceptable in the reviewed answers.
- Review mixed/dependent examples against predeclared available corpus/schema;
  do not count unavailable data as a successful answer merely because a refusal
  was safe. Score safe abstention and task completion separately.
- Report latency for planning, each task, synthesis, and total. Verify the 120-second
  global budget mechanically; live p50/p95 is descriptive until a representative
  load dataset exists. Do not use the previous 1.76-second router-only mean as a
  complete-workflow latency target.
- Provider outages/rate limits or unavailable authorized sources must be recorded
  as unavailable live evidence, never replaced by mock successes. Do not mark
  final acceptance complete while a required live criterion remains unverified.

## API, UI, and demo acceptance

- `auto` and `agentic` produce equivalent behavior for identical controlled inputs
  through both API entry points. Default clients expose one Auto choice plus
  explicit specialists. Report-template upload/download and SQL export still work.
- Streamlit transmits conversation IDs and clears them on sign-out/New conversation.
  Its chat transport timeout exceeds the backend budget (proposed 135 seconds).
- After implementation and verification, automatically start the existing agent
  Streamlit demo on loopback port 8501, using the authenticated backend on port 8000
  or an already configured local URL. Check for existing listeners first; reuse a
  verified matching instance or choose/report an available alternative without
  killing unrelated processes. Keep background helpers hidden on Windows.
- Verify Streamlit health, backend health, login behavior, and one authorized unified
  mixed request; inspect the rendered UI and sources. Report the final local URL,
  running process/log locations, and any provider-dependent limitation.
- Startup is explicitly authorized by the user; do not ask again at completion.
  Do not start the unchanged demo and represent that as implementation completion.

## Tech stack and project structure

Python >=3.11 `unittest`, existing FastAPI TestClient, existing benchmark scripts,
and Streamlit >=1.40,<2 from the existing optional extra. New fixtures live in
`data/evaluation/`; new immutable run artifacts in `artifacts/evaluation/`;
tests in `tests/`; usage/limitations in `docs/technical/agents-and-evaluation.md`
and README where appropriate. Do not replace the unrelated Docker plan in
`tasks/plan.md` without preserving its contents when the planning phase begins.

## Commands

From the repository root in PowerShell:

```powershell
$env:PYTHONPATH = 'src'
.\.venv\Scripts\python.exe -m unittest discover -s tests -p 'test_*orchestration*.py' -v
.\.venv\Scripts\python.exe -m unittest discover -s tests -p 'test_agentic_agent.py' -v
.\.venv\Scripts\python.exe -m unittest discover -s tests -p 'test_app_chat.py' -v
.\.venv\Scripts\python.exe -m unittest discover -s tests -p 'test_streamlit_ui.py' -v
.\.venv\Scripts\python.exe -m unittest discover -s tests -p 'test_agent_benchmarks.py' -v
.\.venv\Scripts\python.exe scripts/agents/benchmark_router_25.py --help
.\.venv\Scripts\python.exe -m uvicorn app.main:app --env-file .env --host 127.0.0.1 --port 8000
.\.venv\Scripts\python.exe -m streamlit run src/core/agents/streamlit_ui.py --server.address 127.0.0.1 --server.port 8501 --server.headless true
git diff --check
```

Planned orchestration tests must exist and execute a nonzero number of cases.
The benchmark invocation with a new output location will be specified in the
approved technical plan after confirming its CLI; `--help` runs no evaluation.
The two server commands are long-running launch commands, not sequential tests.
Install the already-declared Streamlit optional extra only if absent.

## Code style

Follow the existing async unittest pattern:

```python
class LangGraphRouterTest(unittest.IsolatedAsyncioTestCase):
    async def test_agentic_mode_calls_only_selected_agent(self):
        ...
```

Prefer focused behavior tests over implementation snapshots. Keep artifact fields
explicit, and distinguish actual provider fallback from deliberate rule decisions.

## Testing strategy and boundaries

- Always: run each module's focused checks and the combined regression set; document
  pre-existing suite import failures separately; record live limitations honestly.
- Ask first: changing numeric acceptance targets, paid infrastructure, new dependencies,
  database migrations, remote deployment, or expanding evaluation data retention.
- Never: claim mocked runs establish live answer quality, print credentials, overwrite
  historical benchmarks, or weaken authorization to make the demo succeed.

## Open decisions for approval

Approve the proposed numerical targets, scenario counts, and live acceptance
contract. Final demo startup is already requested and needs no additional approval.
