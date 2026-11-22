# Invoice OCR and JSON extraction

## Flow

```text
PDF/image → Docling OCR, layout and TableFormer → reviewable text and tables
  → Gemini or Groq extract from text and tables
  → schema-checked JSON draft → public.invoice_extractions
```

`DocumentProcessor` first uses Docling with Vietnamese/English OCR and table
extraction. Text providers receive OCR text and table cells. Set
`DOCUMENT_PROCESSING_INVOICE_PROVIDER=gemini` and `GEMINI_API` to use the
`gemini-3.1-flash-lite` API. The Gemini path sends the header and table prompts
as separate JSON-mode requests. The alternative `groq` provider uses
`GROQ_API_KEY` and defaults to `openai/gpt-oss-120b`. No invoice LLM
fine-tuning or local GPU worker is required. Existing deployments must change
any legacy `DOCUMENT_PROCESSING_INVOICE_PROVIDER=modal` or `local` setting to
`gemini` or `groq` before rebuilding.

Table extraction returns both item rows and explicitly labeled subtotal, tax,
and total values. The merge accepts totals from OCR text or table evidence;
an item's `amount` is never copied into `total_amount` without a matching total
label in the source.

If extraction fails after Docling completes, the document-processing process
keeps that Docling result in a bounded, process-local cache for 15 minutes. A
retry of the same file with the same parser settings can reuse OCR and table
results while still calling the selected extraction provider. The cache holds
up to four results, with an 8 MiB total limit and a 2 MiB per-result limit; it
does not survive a service restart.

The OCR pass classifies text-line orientation and recognizes VietOCR text in
batches of up to 16 line crops per page. Both preserve crop order; orientation
uses the same confidence and rotation rules as single-crop inference.

## JSON schema

[`invoice.v1`](../invoice/schema.py) contains `invoice_no`, `date`, `seller`, `buyer`, `items`
(`description`, `quantity`, `unit`, `unit_price`, `amount`), `subtotal`,
`tax_amount`, and `total_amount`. Values are strings or null. Tax-ID fields are
intentionally excluded. Strict validation rejects extra keys and malformed
types. Results always require human review; the model is not trusted to
reconcile totals or fill unreadable values.

## Production persistence

`POST /api/invoices/upload` stores the private source under the `invoices/`
prefix in the existing private storage bucket and creates a `processing` row in
`public.invoice_extractions`. It returns the invoice ID immediately; OCR and
extraction continue in a backend background task. The Admin client polls
`GET /api/invoices/{invoice_id}` until the row is `review_required` or `failed`.
The completed row contains the JSON, source hash, OCR elements/tables, model
revision, and runtime metadata. This table has no foreign key to `documents`.
Invoice uploads do not create knowledge documents, parser chunks, or embedding
records. `GET /api/invoices/{invoice_id}` is limited to the uploader and admins.

The web Upload form exposes “Invoice extraction” separately from “Knowledge
document”; it hides the knowledge-base access-role controls for invoice mode
and displays the returned JSON draft. Invoice uploads can select Gemini 3.1
Flash-Lite or Groq GPT-OSS 120B. The normal document upload remains on its existing
parser/chunking/indexing route.

The configured invoice request timeout is 1,200 seconds to allow for OCR and provider calls. Every
result is marked `review_required`, so verify extracted fields against the
source before using them in downstream financial workflows.

Historical invoice model training artifacts are retained for provenance, but are not part of the supported or submitted workflow.
