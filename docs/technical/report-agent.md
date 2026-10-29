# Report Agent

Reports support Markdown and DOCX, with an optional uploaded structural template.
Both report endpoints use the same generator and status contract:

- Authenticated application: `POST /api/agents/report`, using the existing login session or bearer token.
- Standalone agent service: `POST /api/report`, requiring its configured server-side identity resolver or explicitly enabled local-development identity.

## Multipart fields

| Field | Values | Default |
| --- | --- | --- |
| question | Nonblank report question, at most 2,000 characters | Required |
| template | DOCX or UTF-8 Markdown; at most 10 MiB | Built-in Summary, Findings, Limitations |
| source_mode | documents, analytics, combined | documents |
| output_format | markdown, docx | Markdown without upload; uploaded format otherwise |

A conflicting explicit format and uploaded template is rejected. Documents require verified document permission and roles; analytics requires verified analytics permission. Employees can generate document-only reports. Request metadata cannot grant roles or permissions. Analytics connections are created only when queried.

## Results and frontend handling

Successful downloads use HTTP 200, `Content-Disposition`, a format-specific content type and `X-Report-Status: complete` or `partial`. Partial reports are usable artifacts containing gaps or coverage warnings. Their status, limitations, coverage and readable source references are embedded in the downloaded document, so those disclosures survive sharing.

```javascript
const body = new FormData();
body.set('question', question);
body.set('source_mode', 'documents');
if (template) body.set('template', template);
const response = await fetch(`${apiBase}/api/agents/report`, {
  method: 'POST', credentials: 'include', body,
});
if (!response.ok) {
  const error = await response.json();
  throw new Error(JSON.stringify(error.detail));
}
const status = response.headers.get('X-Report-Status');
const report = await response.blob();
// Keep the downloaded artifact, and visibly warn the user when status === 'partial'.
```

The response exposes the status and filename headers without changing trusted origins. The separately deployed Vercel frontend must implement this contract; it was not modified here.

No artifact is returned on total failure. Errors use 403 for source permissions, 422 for invalid inputs or unrepaired generated output, and 503 for unavailable sources/providers. A generation failure includes a safe structured `detail` with `status`, `code` and `limitations`; ordinary input/auth errors retain FastAPI's existing detail format. Oversized authenticated uploads retain their existing HTTP 413 behavior.

If SQL planning needs clarification, collection stops before document retrieval or report drafting. The API returns HTTP 422 with `detail.code` and `detail.status` set to `clarification_required`, and `detail.clarification` containing the planner's actual question. The demo displays that question; the user can clarify the report request and resubmit. Report chat returns the same question in its answer with `metadata.clarification_required=true`.

Report chat mode returns Markdown in `AgentResult.answer`; source options can be supplied through metadata but remain permission-checked. Result metadata includes status, section checks, coverage, limitations and verification scope. `metadata.ok` is true only for complete reports.

## Processing and grounding limits

- At most 20 unique headings and 20 tables with at most 20 columns; headings and header cells are capped at 200 characters. Every table must follow a recognized heading. Word headings use Heading styles; Markdown headings use ATX `#` syntax.
- Up to five raw role-filtered passages per section, 100 unique report contexts, and 24,000 serialized evidence characters per section. Over-budget passages are omitted and disclosed. Retrieval is not exhaustive.
- Analytics considers the first 100 returned rows; their actual JSON values become citable evidence. Returned rows are not a guarantee that the complete database population was inspected.
- One section at a time, up to 600 words and 100 rows per table, with a report-only 4,096-token generation budget. Each section has one repair attempt. Provider calls use finite timeouts.
- Each paragraph and table row requires valid source citations, unless it is an explicit unavailable statement. Numeric claims must match cited values and percentage notation. Ambiguous separators, unsupported numeric notation and unverified conversions are withheld conservatively.
- These checks do not prove semantic entailment, accounting scope, arithmetic correctness or completeness. A complete status means the processing/checks passed, not that every statement is true.
- Generated content replaces template body prose and data rows. Structural headings, table headers and DOCX document styles/headers/footers are retained. Arbitrary rich-template/image fidelity and generated charts are outside this iteration.

The existing telemetry schema accepts completed/failed/rate_limited only. Complete reports map to completed; partial reports map to failed with error type ReportPartial. This preserves a visible distinction without a database migration or overstating success rates.

## Streamlit demo

```powershell
.\.venv\Scripts\python.exe -m streamlit run src/core/agents/streamlit_ui.py --server.address 127.0.0.1 --server.port 8501 --server.headless true --browser.gatherUsageStats false
```

The demo defaults to the authenticated backend at `http://127.0.0.1:8000`, uses existing demo sign-in accounts, and retains its cookie only in the server-side Streamlit session. Choose Report, select sources, optionally upload a template, then generate. It displays partial warnings, a Markdown preview and persistent downloads. `API_BASE_URL` overrides the backend; `API_AGENT_PREFIX=/api` targets the standalone service when explicitly configured.
