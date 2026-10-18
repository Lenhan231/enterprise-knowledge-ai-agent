# User guide

## Sign in

Set the demo usernames/passwords and a random `AUTH_SECRET_KEY` in `.env`, then
run the app as described in the root README. The sidebar is role-aware:

| Sign-in role | Workspace access |
| --- | --- |
| Viewer (`employee`) | Knowledge Q&A |
| Analyst (`finance_analyst`) and Sustainability Analyst | Knowledge Q&A and Commerce Dashboard |
| Document Uploader | Upload Documents only; this role cannot ask document questions or open analytics |
| Tester | Isolated Upload Test only |
| Admin | All workspace tabs, including upload, processing, Upload Test, knowledge-file management, access matrix, and agent monitoring |

The demo accounts are local and are not production identity management.
Each document's allowed reader roles independently control retrieval access.

## Ask documents

Open **Document Q&A**, choose Hybrid, Dense, BM25, or Parent retrieval, then
ask a question and inspect the cited passages and page references. Hybrid is
the default. Parent retrieval expands a match with nearby content from its
section or page. An insufficient-information answer means the indexed,
role-visible documents did not support a response.

## Upload and classify

Sign in as a Document Uploader or Admin and open **Upload Documents**. Every
upload is searchable through document Q&A. The selected roles control who can
retrieve it; Commerce decision-area tags are a separate classification. To
also use a source for Commerce decision support, enable that option and provide
its publisher, source type, applicability scope, and one or more decision
areas. Wait for processing to finish. OCR can misread scanned pages, so Admins
can compare the original with saved parser passages, OCR output, tables, and
metadata in **Document Processing**. Choose **English only** for English scans;
the default **Vietnamese + English** setting supports both languages. Removing a
source from AI retrieval does not remove it from the Admin processing inspector.

Original files are stored in private Supabase Storage. Parser output is saved
before role-filtered chunks are embedded and indexed. Uploading a file adds
knowledge for retrieval; it does not create or publish dashboard metrics.
Classifications are selected by the uploader and are not inferred or approved
automatically. Supported formats, limits, and recovery commands are in the
[root README](../README.md) and [processing guide](../src/core/document_processing/docs/document-processing.md).

## Commerce analytics

Analysts and Admins can open **Analytics** and select inventory allocation,
promotion planning, or nationwide logistics. Dashboard values come from the
Commerce SQL tables. The transaction and operations data are synthetic demo
data, not observations from a real retailer. Uploaded and seeded documents
provide operating methods and examples through RAG; they do not supply the
dashboard's numeric observations.

To ask for decision support, choose the matching domain in the dashboard,
select a suggested question or enter one in **Ask a Commerce decision
question**, then choose **Analyze decision evidence**. The answer combines
role-visible SQL observations with references filtered for that domain and
shows citations. State the period and measure you want to compare. If the
schema lacks decision inputs (for example SKU-by-location stock, campaign cost,
or route and carrier data), the agent should identify the gap rather than infer
an action from aggregate totals. Demo policies are fictional; public retailer
and platform documents are attributed examples that apply only within their
stated scope.

## Admin review and file access

In **Knowledge Management**, search for a source and filter by Commerce
decision domain or retrieval state (available, removed, or needing attention).
Inspect its publisher/domain and processing status, edit its reader roles, or
remove/restore it from AI retrieval. Removing a source keeps the original file
and parser output; it does not delete them. Ready user uploads expose an
**Open uploaded file** link; the server checks the document's role access before
streaming the original. Use **Document Processing** to
compare saved passages and structured tables with their source pages. A failed
user upload may offer **Retry embedding**, which reuses saved parser output
instead of rerunning OCR.
The **Access Control** tab describes workspace capabilities by role; document
reader access is changed on the file itself. **Agent Monitoring** reports
operational counts and latency, not user questions or generated answer text.

To inspect the full Admin upload path, upload
[`commerce_synthetic_degraded_scan_demo.pdf`](../data/evaluation/ocr/commerce_synthetic_degraded_scan_demo.pdf)
from **Upload Documents**, then open the result in **Document Processing**.
Expect two OCR pages, three passages, and one structured table (three rows by
four columns); the fixture is invented test data, so deactivate it in
**Knowledge Management** after review. For an isolated full-pipeline run, use
the same file in **Upload Test** instead.

**Upload Test** runs a selected parser and saves page previews, parser chunks,
and structured table rows in isolated test tables. It stops before tokenization
and embedding. It does not create a production document or retrieval entry.
Admins can also use it; production upload output is reviewed in Document Processing.

## Troubleshooting

- Login returns to sign-in: check the demo credentials and a 32+ character
  `AUTH_SECRET_KEY`, then reload and sign in again.
- Upload is unavailable: use the Document Uploader or Admin role and check the
  server-side Supabase URL, secret key, and private `enterprise-documents`
  bucket migration.
- No answer or sources: confirm the document is `ready`, includes your role,
  and appears in the indexed document list.
- Analytics is empty or unavailable: confirm the Commerce schema has been
  migrated and populated, then check the selected domain and API response.
