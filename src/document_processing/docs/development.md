# Local development and runtime

Run commands from the repository root unless a command says otherwise. The
main local inspection UI is `testing_parser_streamlit.py`; it calls the parser
directly and stores review runs separately from production uploads.

## Run Upload Test locally

```sh
PYTHONPATH=src .venv/bin/streamlit run \
  tools/processing/testing_parser_streamlit.py \
  --server.address 127.0.0.1 --server.port 8502
```

By default, local review data is under
`src/document_processing/.owner_store/`. Set `DOCUMENT_PROCESSING_STORE` to
use a different folder. Upload Test can select pages from a PDF before
processing and can select the `document` or `invoice` intent. Invoice
extraction uses Docling and the configured [invoice provider](invoice-pipeline.md).

## Local invoice worker

The local Qwen invoice worker uses a separate environment to isolate its
Transformers and PyTorch versions. By default, the app looks for
`.venv-invoice-worker/bin/python`; set
`DOCUMENT_PROCESSING_INVOICE_WORKER_PYTHON` to use a different interpreter.

```sh
uv venv .venv-invoice-worker --python 3.11
uv pip install --python .venv-invoice-worker/bin/python \
  --index-url https://download.pytorch.org/whl/cpu \
  torch==2.3.1
uv pip install --python .venv-invoice-worker/bin/python \
  transformers==4.57.6 accelerate==1.15.0 peft==0.21.2
```

These commands install CPU PyTorch. For GPU inference, install a PyTorch build
that matches the host CUDA runtime. See the [invoice guide](invoice-pipeline.md).

## Build the parser image

Install LibreOffice locally to parse legacy DOC, XLS, and PPT files. The
document-processing image includes LibreOffice and a separate HEIC/AVIF
decoder. Apply the document MIME migration before enabling the new formats
for uploads to the private source bucket.

From the repository root:

```sh
docker build -f docker/Dockerfile.document-processing -t document-processing .
docker run --rm document-processing
```

The image's default command starts the FastAPI document-processing service on
port 8000. It does not include the full application or Streamlit. Model caches
should be mounted to persist downloads between local container runs.

## Where to inspect a failure

1. Confirm the caller's selected `intent` and parser config.
2. Check the Upload Test result: parser metadata records engine, route, model,
   and review status where available.
3. Check application logs for the upload/job ID, then the document-processing
   service logs for `/parse` status and worker traceback.
4. For local invoice extraction, check the selected provider and the isolated
   worker logs when Qwen runs outside Modal.

For large PDFs, filter application logs for `PDF_BATCH_STARTED`,
`PDF_BATCH_SAVED`, or `PDF_JOB_FAILED`; events include the document ID, attempt,
and page range. Saved events include `parse_elapsed_ms`,
`checkpoint_elapsed_ms`, and total `elapsed_ms`; failed events include elapsed
time when a batch was active.

Filter for `DOCUMENT_PROCESS_COMPONENT_ERROR` to see the failing component,
error type, and available request identifiers. Docling can report a page and
stage even when other pages completed. Page and frame limit errors include
`error_code=page_limit_exceeded`, the observed `page_count`, the configured
`page_limit`, and `count_unit`.

Do not use production or SSH as a local verification step. Use the explicit
deployment workflow for a separately authorized production change.

## Measure parser latency

```sh
PYTHONPATH=src .venv/bin/python scripts/processing/benchmark_parser.py input.pdf \
  --repeats 2 --output /tmp/parser-speed.json
```

Run the same file and configuration on each revision. The first run includes
model initialization; later runs reuse loaded converters. Compare both elapsed
time and the content fingerprint, then inspect any changed text or table cells.
A matching fingerprint covers text and table cells, not layout coordinates.

CPU resize check on 2026-11-11 (SSH host with 6 CPUs; Docling 2.129.0,
RapidOCR 3.9.2, PyTorch 2.10.0 CPU):

- Synthetic `invoice_0432.pdf`, same process after loading models: previous
  resize 96.07s; maximum-edge resize 78.35s and 84.56s (12–18% faster).
  The 16 text elements and all numeric values were retained. One table word
  changed from `Ổ cẩm` to the source label's `Ổ cắm`.
- Long Hau 2008 financial scan, page 6: line detection 36.09s → 2.28s;
  all cells in the 30-row table were identical. OCR noise in the binding-hole
  strip changed; that strip contains no financial data.
- These are two CPU regression samples, not a corpus-wide accuracy benchmark.
  CUDA detection and the invoice LLM step were not changed.

Follow-up CPU thread check on the same host: PP-DocLayoutV3's warm median
for the synthetic invoice was 15.05s with Paddle's default 10 threads, 9.94s
with 2 threads, and 14.57s with 4 threads. All 16 detected labels and boxes
matched within 0.001 pixels. The parser now passes `docling_num_threads` to
layout inference and defaults CPU pipelines to 2 threads (CUDA remains 4).
With this budget, the financial scan took 94.15s versus the earlier 154.32s;
its text, numeric values, and all 30 table rows were identical. These remain
sample measurements on a shared CPU host; profile explicit thread overrides
before changing the budget for other hardware.
