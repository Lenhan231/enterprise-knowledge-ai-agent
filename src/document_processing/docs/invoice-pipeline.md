# Invoice OCR and JSON extraction

## Flow

```text
PDF/image → Docling OCR, layout and TableFormer → ordered text + table cells
  → Gemini API or Qwen3-0.6B + private LoRA → schema-checked JSON draft
  → public.invoice_extractions
```

The invoice intent sends OCR text and table cells to the configured text model;
it does not send invoice images to the LLM. `DocumentProcessor` first uses
Docling with Vietnamese/English OCR and table extraction. Set
`DOCUMENT_PROCESSING_INVOICE_PROVIDER=gemini` and `GEMINI_API` to use the
`gemini-3.1-flash-lite` API. The Gemini path sends the header and table prompts
as separate JSON-mode requests. The default `modal` provider sends those same
text prompts to the isolated GPU endpoint. When Modal is not configured, the
Qwen path uses the local isolated Transformers worker, which loads the pinned
`Qwen/Qwen3-0.6B` base revision and the
private `lenhanm1/qwen3-0.6b-invoice-lora-900` adapter. Set
`HF_INVOICE_LLM_TOKEN` in the
document-processing service environment so the worker can read the adapter.
Model and adapter revisions are pinned in `invoice_text_processor.py` and can
be overridden with `DOCUMENT_PROCESSING_INVOICE_*` environment variables. The
local worker uses the interpreter configured by `DOCUMENT_PROCESSING_VINTERN_PYTHON`
and shares the document-processing model cache.

Table extraction returns both item rows and explicitly labeled subtotal, tax,
and total values. The merge accepts totals from OCR text or table evidence;
an item's `amount` is never copied into `total_amount` without a matching total
label in the source.

For GPU inference, deploy `modal_invoice_endpoint.py` from the repository root
with `modal deploy src/document_processing/modal_invoice_endpoint.py`. The
Modal Secret `invoice-hf-token` must expose `HF_INVOICE_LLM_TOKEN`. Set the
endpoint URL as `DOCUMENT_PROCESSING_INVOICE_MODAL_URL` in the document-
processing service environment; requests are authenticated with an HMAC derived
from that same token. When the URL is unset, extraction falls back to the local
isolated worker.

## JSON schema

`invoice.v1` contains `invoice_no`, `date`, `seller`, `buyer`, `items`
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
Flash-Lite or the fine-tuned Qwen3-0.6B adapter served through Modal GPU; the
choice applies to that upload only. The normal document upload remains on
its existing parser/chunking/indexing route. The isolated Upload Test stores
the same extraction in its run metadata and renders it above the Docling
elements/tables, so the OCR evidence and JSON draft can be inspected together.

The first local inference may download base and adapter weights into `/models`;
subsequent loads use the persistent model cache. Modal loads the base and adapter
once per GPU container and reuses them for later requests. The configured
invoice request timeout is 1,200 seconds to allow for OCR and cold starts. Every
result is marked `review_required`, so verify extracted fields against the
source before using them in downstream financial workflows.
