# Parser contract and callers

`DocumentProcessor.process(filename, content, metadata)` validates the input,
selects a parser route, normalizes the result, and returns parser output. It
does not create parser chunks, embeddings, or production database records.

## Inputs and routes

The authoritative extension list is `SUPPORTED_FORMATS` in
[`formats.py`](../formats.py). The document intent accepts PDF, DOC/DOCX,
PPT/PPTX, XLS/XLSX, CSV, TXT, Markdown, PNG, JPEG, TIFF, BMP, GIF, WebP, SVG,
HEIC/HEIF, and AVIF. Animated GIF and WebP frames produce separate pages.
Legacy Office support covers binary Office files stored in a Compound File
container. Invoice and image captioning have their own format lists.

| Intent | Route | Main output |
| --- | --- | --- |
| `document` (default) | [`DoclingProcessor`](../docling_adapter/processor.py) | `elements`, `tables`, parser metadata, and optional page/layout data |
| `invoice` | [`DoclingProcessor`](../docling_adapter/processor.py) → [configured invoice extractor](invoice-pipeline.md) | Docling `elements`/`tables` plus validated `invoice_extraction.fields` |
| `image_caption` | [`VinternProcessor`](../image_caption/vintern_processor.py) | `image_caption_extraction.pages` and caption text elements |

The invoice intent runs Docling OCR and table extraction first. The configured
provider reads either the resulting text and cells or the original page images.
Production uploads save the source and
review-required draft in `invoice_extractions`, separately from `documents`,
parser chunks, and embeddings. See the [invoice guide](invoice-pipeline.md).
Image captioning uses Vintern; see the [Vintern guide](vintern-pipeline.md).
The default document route is described in the [Docling guide](docling-pipeline.md).

## Parser output boundary

The common result has `elements`, `tables`, and `metadata`. Depending on the
route it can also carry page previews/sizes, raw PP-DocLayoutV3
`layout_detections`, orientation corrections, or an intent-specific extraction
object. Element and table provenance is described in [metadata](metadata.md).

The application decides what happens next:

```text
upload bytes → DocumentProcessor → normalized parser output
                                  ├─ parser-handoff → persist output → chunking worker
                                  └─ direct upload   → inline chunking / indexing
```

The parser-handoff API is implemented in `src/app/main.py` and chunked by
`src/core/chunking/worker.py`. The direct upload API also lives in
`src/app/main.py`; it calls the chunking processor inline. Upload Test is an
inspection path in `src/app/upload_test.py`, with separate review storage.

For the next stage, read the [chunking guide](../../core/chunking/README.md).
