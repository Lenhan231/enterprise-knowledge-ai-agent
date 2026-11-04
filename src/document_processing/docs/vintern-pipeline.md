# Vintern invoice and image-caption pipeline

The `invoice` and `image_caption` intents use Vintern directly on page images.
They are explicit Upload Test choices, not automatic document classification.
Dispatch is in [`document_processor.py`](../document_processor.py), request
preparation/output shaping is in [`vintern_processor.py`](../vintern_processor.py),
and model inference is in [`vintern_worker.py`](../vintern_worker.py).

## Current flow

```text
PDF/image → render/normalize pages → request.json
  → start isolated Python worker → load tokenizer and Vintern
  → infer on each page in order → response.json
  → parse invoice JSON or retain caption → elements + intent result
```

The invoice route **replaces** Docling for that request. It does not run OCR
first, does not consume Docling `elements` or `tables`, and does not return
structured tables. The image-caption route uses the same runtime with a
different prompt.

## Invoice result

The prompt requests a compact Vietnamese object with invoice type/number/date,
seller/tax ID, buyer, line items, tax, and total. For each page, the output is
stored under `invoice_extraction.pages` with:

- `page_number`
- `fields` (parsed object, or `null` if the response is not parseable)
- `raw_response`
- `review_required: true`

The JSON is also serialized into a searchable text element. Parsing accepts a
JSON object (and a Python-literal fallback); it does **not** validate required
keys, field types, totals, or arithmetic. Pages are extracted independently;
there is no cross-page merging. Treat the result as a draft and verify it
against the source image.

## Runtime and performance

- Model default: `5CD-AI/Vintern-1B-v2`, pinned to a model/code revision in
  `vintern_processor.py`. Override with `DOCUMENT_PROCESSING_VINTERN_MODEL`.
- The model is loaded once per worker invocation, and the worker is launched
  for each parser request. It then processes pages sequentially.
- PDF pages are rendered at 2×. The worker splits each page into 448-pixel
  crops (up to 12 tiles plus an overview crop for multi-tile pages).
- If no device is configured, inference uses CPU. Generation currently allows
  up to 1024 new tokens with 3-beam search.
- Worker timeout defaults to 1800 seconds. Override with
  `DOCUMENT_PROCESSING_VINTERN_TIMEOUT_SECONDS` or `vintern_timeout_seconds`.
- The app and Docker image keep Vintern in a separate Python environment to
  avoid Transformers version conflicts. Docker currently installs CPU-only
  PyTorch; selecting `cuda` alone does not add GPU support.

An async Upload Test job keeps a long request from blocking the proxy, but it
does not make CPU inference faster. A production invoice attempt on the
CPU-only server reached the 30-minute worker timeout; this configuration is
not a practical invoice service. Keep this limitation in mind when evaluating
changes to the invoice route.

## Where invoice redesign fits

The current implementation is a direct visual extraction path. If the
pipeline changes to OCR followed by structured extraction, update this page
and the route diagram in [architecture](architecture.md) to reflect the new
source of evidence and inference boundary. Do not describe Docling as an
invoice JSON extractor: it returns parser elements/tables; a separate
structured-extraction step would have to produce and validate invoice fields.

For the isolated runtime setup and local UI command, see
[development](development.md).
