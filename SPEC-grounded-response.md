# Spec: Grounded Combined Response

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


Module id: `grounded-response`
Status: Approved and implemented under the Knowledge/SQL amendment; see the final implementation document for acceptance gaps. Depends on: `bounded-execution`.
Scope authority: [approved capability map](CAPABILITY-MAP-agent-orchestration.md).

## Objective

Answer the user's original mixed-source question as one coherent response using
the completed task evidence. Preserve numerical results and document scope,
attribute claims consistently, and clearly disclose unavailable portions.

## Proposed behavior and consumer contract

- Unified auto and legacy agentic use the same response assembly. A single usable
  specialist result may pass through with normalized execution status; combined
  tasks use bounded synthesis against the original objective and actual outcomes.
- Assign unique response-wide citation IDs and retain a mapping from each task's
  original IDs. Rewrite/serialize task references consistently before synthesis
  or fallback so two local `[S1]` references cannot point at different sources.
- Supply factual SQL rows, document evidence, units, dates, filters, source scope,
  task status, and limitations as data. Retrieved text and earlier answers cannot
  override system instructions or grant permissions.
- Cite factual claims with supplied IDs only. Keep observed correlations distinct
  from documented explanations and causal claims. Missing policy thresholds,
  cost fields, years, or evidence must remain explicit gaps.
- Validate citation membership, required source coverage, and preservation of
  structured reported values where mechanically checkable. Reject invalid drafts
  and use an evidence-based fallback within budget. Citation validation alone is
  not proof of semantic entailment; evaluation must assess faithfulness separately.
- Fallback presents available supported findings and missing/failed tasks with
  correct citations and an explicit fallback/partial label. Do not blindly join
  the original agent prose, fabricate conclusions, or describe a provider outage
  as user ambiguity.
- Return `metadata.status` as `complete`, `partial`, `clarification_required`,
  or `failed`; `ok` is true only when required coverage is complete. Denial remains
  an authorization outcome according to the API policy, never ordinary completion.
- Preserve existing structured payloads: SQL rows/query export, dashboard data,
  and report information remain renderable and inspectable. Keep deterministic
  source/task mappings for multi-result payloads. Explicit report downloads retain
  their existing file format and grounding rules.
- For a targeted clarification, state the unresolved input without losing usable
  completed findings. Omit all inaccessible evidence and sensitive trace fields.
- Update Streamlit and bundled web rendering only as needed for unified status,
  structured payloads, sources, and conversation continuity. Keep orchestration
  internals out of the normal answer; use an optional diagnostic view if needed.

## Tech stack and project structure

Existing Python >=3.11, Pydantic models, provider adapter, and report grounding
helpers where applicable. Work stays in `src/core/agents/`,
`src/core/models/agents.py`, `src/core/agents/streamlit_ui.py`, and relevant
`src/app/static/` clients. Reuse `core.reports` validation patterns without forcing
ordinary chat through full report generation.

## Commands

```powershell
$env:PYTHONPATH = 'src'
.\.venv\Scripts\python.exe -m unittest discover -s tests -p 'test_grounded_response.py' -v
.\.venv\Scripts\python.exe -m unittest discover -s tests -p 'test_streamlit_ui.py' -v
.\.venv\Scripts\python.exe -m unittest discover -s tests -p 'test_report_agent.py' -v
git diff --check
```

The first test module is planned; the existing report tests protect dedicated
report behavior rather than establishing ordinary chat faithfulness.

## Code style

Reuse existing model copies and result metadata:

```python
result = result.model_copy(update={"metadata": {**result.metadata, "selected_route": route}})
```

Keep evidence mapping explicit and deterministic. Prefer small helpers over a new
response-generation framework; never mutate shared source objects across requests.

## Testing strategy and success criteria

Use `unittest` with fake synthesis providers. Verify citation collision remapping,
unknown citations, changed numbers/units, missing source coverage, provider failure,
empty results, partial output, preserved dashboard/SQL payloads, and EN/VI answers.
All deterministic citation/status contracts must pass. Include human-reviewed
combined examples that establish semantic faithfulness rather than just valid IDs.

## Boundaries

- Always: preserve provenance, units, scope, limitations, and actual completion status.
- Ask first: new model providers/dependencies or changes to dedicated report file contracts.
- Never: manufacture citations or policy values, silently omit a required source, or present fallback as verified model synthesis.

## Open decisions for approval

Approve the shared completion-status contract and explicit evidence-based fallback.
No automatic claim of full semantic verification is proposed.
