# User guide

## Sign in

Set the demo usernames/passwords and a random `AUTH_SECRET_KEY` in `.env`, then
run the app as described in the root README. The demo accounts map to these
roles: `viewer` → employee, `analyst` → finance analyst,
`sustainability_analyst` → sustainability analyst, `admin` → admin, and
`uploader` → document uploader. The role shown by the app is the effective
role. These accounts are for a local demo, not production identity management.

Employees can view and ask the documents. Finance and sustainability analysts
and executives also see analytics. Admins can review extracted KPI evidence
and manage access. Uploaders can upload and assign document roles, but cannot
view analytics or approve metrics. Document-level access is independently
controlled by the roles selected for each uploaded file.

## Ask documents

Open Document Q&A, choose Hybrid, Dense, BM25, or Parent context, then enter a
question and review the cited source passages and page references. Hybrid is
the default; Parent context expands a matched passage with nearby text from its
section/page. Access follows the signed-in role and each document's assigned
roles; changing a role in the browser does not grant access. If no matching
passage is retrieved, narrow the question to a named company, year, metric, or
section. An insufficient-information answer means the indexed, accessible
documents did not support a response.

## Upload and classify

Sign in as `uploader` or `admin`, then open the document upload view. Select the
file, document title, document type, domain, fiscal year if known, and the roles
that may access it. Submit once and wait for processing to report `ready`.
Original files are kept in private Supabase Storage; parser output is saved to
PostgreSQL before embeddings and role-filtered retrieval chunks are written.
Supported formats and file-size limit are listed in the root README. If
embedding fails, admins can inspect saved OCR/layout passages in Document
processing, including extracted table rows and parser metadata; maintainers can
retry embedding without reprocessing the original:
`uv run python scripts/retrieval/retry_document_embeddings.py UPLOAD-<document-id>`.

Assign only the roles that need the document. Public annual reports may be
available to all demo roles, while internal or sensitive files should receive
a narrower role set. This prototype's classification is assigned by the
uploader; it does not infer or approve sensitivity automatically.

## Analytics review

Finance/sustainability analysts, executives, and admins can open Enterprise
Analytics. Dashboard coverage counts are computed from indexed database rows.
Financial KPI candidates extracted from reports stay out of published metrics
until an admin opens the evidence, checks the source/page and normalized value,
then verifies or rejects it. Click a detected figure to copy it into the review
field, then confirm that it belongs to the candidate's reporting year and
metric in the linked PDF; selecting a figure does not publish the KPI. Enter
values as ungrouped digits (`59723`) or Vietnamese-grouped input (`59.723`,
decimal example `59.723,5`). The form previews the interpreted value; published
dashboard amounts use the same Vietnamese format (`59.723`, decimal
`59.723,5`) so reviewers see the same separators they entered.
Open
the cited original at its page before checking the year and scale; uploaded
PDFs are streamed from private Storage only to admins. Use one comparable unit
across fiscal years (for example, `billion VND`), and only then publish. Only
verified candidates feed KPI cards/charts.

## Troubleshooting

- Login returns to sign-in: check that all demo credentials and a 32+ character
  `AUTH_SECRET_KEY` are present, then reload and sign in again.
- Upload is unavailable: use uploader/admin and check server-side Supabase URL,
  secret key, and the private `enterprise-documents` bucket migration.
- No answer or no sources: confirm the document is `ready` and includes your
  effective role; use the document search/coverage view to confirm indexing.
- Analytics shows no metrics: process a report and complete admin review; raw
  extracted candidates are intentionally not published.
