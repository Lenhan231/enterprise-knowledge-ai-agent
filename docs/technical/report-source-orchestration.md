# Report source orchestration

Updated: 2026-10-29. This follow-up implements the user's approved expansion of
the Knowledge/SQL scope: Report keeps its own chat/form and generation pipeline,
and reuses the new router only to collect sources. Dashboard remains independent.

## Behavior

The Report source selector now defaults to **Auto (Knowledge + SQL)** in the
bundled web and Streamlit clients. The backend value is `orchestrated`. Existing
`combined` requests are a compatibility alias for this same workflow; they no
longer broadcast the complete report question to both specialists. Explicit
`documents` and `analytics` choices retain their existing behavior. Omitting the
API field still defaults to `documents` for compatibility.

The planner receives the report question and template headings in a trusted
`report_sources` workflow. It creates focused Knowledge/SQL tasks, including
dependencies where one source must inform the next. It uses the same validated
plan, authorization, bounded retry/revision, and 120-second collection budget as
Auto chat. Report itself is never a planner tool, so this cannot recursively
dispatch another report.

The collector returns authorized document excerpts and usable SQL task rows.
It skips the final combined chat answer: generated specialist prose does not
become report evidence. Collection runs once, then each report section uses the
bounded source pool. Existing citation checks, numeric validation, section repair,
template order, output formats, status appendix, and download behavior remain.

Partial source collection produces a partial report when a section can be
grounded. A precise clarification stops section generation and returns its actual
question. No usable evidence or no validated section produces no downloadable
report. Source failures cannot trigger the old full-question broadcast fallback.

## API and frontend contract

Use authenticated multipart `POST /api/agents/report` in the main app, or
`POST /api/report` in the standalone agent API. Fields:

| Field | Values / behavior |
|---|---|
| question | Existing report question validation applies. |
| template | Optional Markdown or DOCX upload; built-in template if omitted. |
| source_mode | `orchestrated`, `documents`, `analytics`; `combined` remains accepted. |
| output_format | Existing `markdown` / `docx` selection and template compatibility checks. |
| conversation_id | Optional opaque string, at most 128 characters. Use a separate report ID. |

Keep the separate report textbox and template/download controls. Send
`source_mode=orchestrated` for Auto, and a stable report conversation ID for
clarification replies. Reset it on sign-out/account change. The router stores this
context under `report:<id>`, scoped to verified identity and permission fingerprint,
separately from general chat. Context is process-local and expires or is evicted
under the same bounds as chat; it is not durable report history.

Auto requires both existing document and analytics permissions, like the former
combined mode. Permission denial occurs before model or source work. Choose an
explicit permitted source mode when the user has only one source permission.

Successful downloads retain `X-Report-Status` and the status/source appendix.
HTTP 422 clarification responses retain the existing structured `detail` with
`code=clarification_required` and the actual clarification text. Existing failure
and permission HTTP behavior remains. Programmatic report results additionally
include `metadata.source_collection` with status, route, task trace, revisions,
specialist invocation count, and planning fallback information. The download
response itself is still a file, not a new JSON envelope.

## Limits and verification

Source collection is bounded to four planned tasks, six specialist invocations,
one plan revision, and the existing shared deadline. Report section generation
keeps its separate existing 90-second per-attempt timeout and one repair; the
120-second source budget is not an end-to-end report SLA. Streamlit's report
transport timeout remains 600 seconds; deployed proxy limits need separate checks.

Report evidence retains the existing limits: 100 SQL rows globally across tasks,
five document candidates per section, 24,000 serialized context characters per
section, and 100 registered sources. Omissions are disclosed. Reusing a source
pool does not guarantee that every requested heading has sufficient evidence.
Numeric/citation validation is not a proof that all prose is semantically correct.

Regression coverage in `tests/test_report_orchestration.py` verifies focused
dispatch, one collection across headings, no combined-answer synthesis, partial
sources, clarification, no invented export, and report/chat context isolation.
Existing report generation and transport suites verify grounding, templates,
permission checks, file status, and compatibility requests. The broader routing
measurements and remaining live evidence gaps are recorded in
[the implementation report](agent-orchestration-implementation.md).
