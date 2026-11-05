# Invoice OCR and JSON extraction

## Flow

```text
PDF/image → Docling OCR, layout and TableFormer → ordered text + table cells
  → Qwen/Qwen2.5-0.5B-Instruct text-only worker → schema-checked JSON draft
  → public.invoice_extractions
```

The invoice intent does not send the image to Qwen. `DocumentProcessor` first
uses Docling with Vietnamese/English OCR and table extraction, then
`InvoiceTextProcessor` sends those text results to an isolated Transformers
worker. The model revision is pinned in `invoice_text_processor.py`; the
worker uses the interpreter configured by `DOCUMENT_PROCESSING_VINTERN_PYTHON`
and shares the document-processing model cache.

## JSON schema

`invoice.v1` contains `invoice_no`, `date`, `seller`, `buyer`, `items`
(`description`, `quantity`, `unit`, `unit_price`, `amount`), `subtotal`,
`tax_amount`, and `total_amount`. Values are strings or null. Tax-ID fields are
intentionally excluded. Strict validation rejects extra keys and malformed
types. Results always require human review; the model is not trusted to
reconcile totals or fill unreadable values.

## Production persistence

`POST /api/invoices/upload` stores the private source under the `invoices/`
prefix in the existing private storage bucket, then writes the JSON, source
hash, OCR elements/tables, model revision, and runtime metadata to
`public.invoice_extractions`. This table has no foreign key to `documents`.
Invoice uploads do not create knowledge documents, parser chunks, or embedding
records. `GET /api/invoices/{invoice_id}` is limited to the uploader and admins.

The web Upload form exposes “Invoice extraction” separately from “Knowledge
document”; it hides the knowledge-base access-role controls for invoice mode
and displays the returned JSON draft. The normal document upload remains on
its existing parser/chunking/indexing route.

The first CPU inference may download model weights into `/models`; subsequent
loads use the persistent model cache. CPU inference is synchronous and every
result is marked `review_required`, so verify extracted fields against the
source before using them in downstream financial workflows.
