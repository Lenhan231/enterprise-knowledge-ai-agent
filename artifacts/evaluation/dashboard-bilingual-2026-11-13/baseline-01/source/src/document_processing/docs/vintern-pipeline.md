# Vintern image-caption pipeline

The `image_caption` intent uses Vintern directly on page images. Invoice
extraction now uses Docling OCR plus a text-only Qwen model; see the
[invoice pipeline guide](invoice-pipeline.md).
Dispatch is in [`document_processor.py`](../document_processor.py), request
preparation/output shaping is in [`vintern_processor.py`](../vintern_processor.py),
and model inference is in [`vintern_worker.py`](../vintern_worker.py).

## Current flow

```text
PDF/image → render/normalize pages → request.json
  → start isolated Python worker → load tokenizer and Vintern
  → infer on each page in order → response.json
  → retain caption → elements + image_caption_extraction
```

This route is only for image captioning; it does not return structured tables.

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

For the isolated runtime setup and local UI command, see
[development](development.md).
