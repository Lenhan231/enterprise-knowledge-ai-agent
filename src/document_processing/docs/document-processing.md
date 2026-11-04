# Parser contract and callers

`DocumentProcessor.process(filename, content, metadata)` validates the input,
selects a parser route, normalizes the result, and returns parser output. It
does not create parser chunks, embeddings, or production database records.

## Inputs and routes

The authoritative extension list is `SUPPORTED_FORMATS` in
[`document_processor.py`](../document_processor.py): PDF, DOCX, PPTX, XLSX,
CSV, TXT, Markdown, PNG/JPEG, TIFF, SVG, and WebP. A caller can support fewer
formats than the parser package.

| Intent | Route | Main output |
| --- | --- | --- |
| `document` (default) | [`DoclingProcessor`](../docling_adapter/processor.py) | `elements`, `tables`, parser metadata, and optional page/layout data |
| `invoice` | [`VinternProcessor`](../vintern_processor.py) | `invoice_extraction.pages` and searchable text elements; no structured tables |
| `image_caption` | [`VinternProcessor`](../vintern_processor.py) | `image_caption_extraction.pages` and caption text elements; no structured tables |

Invoice and image-caption are explicit intents selected in Upload Test; there
is no automatic invoice classifier. The invoice route currently reads page
images with Vintern instead of first running Docling. See the
[Vintern guide](vintern-pipeline.md). The default document route is described
in the [Docling guide](docling-pipeline.md).

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
