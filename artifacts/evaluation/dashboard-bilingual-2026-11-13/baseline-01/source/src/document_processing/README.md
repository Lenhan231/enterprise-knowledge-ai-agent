# Document processing

This package converts supported files into parser output: ordered `elements`,
structured `tables`, and provenance metadata. It does not own chunking,
embeddings, retrieval, or application persistence.

Start here when tracing a document:

1. [Architecture and request flow](docs/architecture.md)
2. [Parser contract and callers](docs/document-processing.md)
3. Follow the selected path: [Docling and OCR](docs/docling-pipeline.md) or
   [Vintern invoice and image caption](docs/vintern-pipeline.md)
4. Check [output metadata](docs/metadata.md), then the separate
   [chunking pipeline](../core/chunking/README.md)

## Current routes

```text
DocumentProcessor.process
  ├─ intent=document       → Docling → elements + tables
  ├─ intent=invoice        → Vintern → invoice JSON draft + text element
  └─ intent=image_caption  → Vintern → caption + text element

parser output → application handoff → core/chunking → persistence / indexing
```

Invoice and image-caption are explicit Upload Test intents. The document
parser does not automatically classify an upload as an invoice. The current
invoice intent asks Vintern to read page images directly; it does not combine
Vintern with Docling OCR.

## Useful entry points

| Need to find | Start at |
| --- | --- |
| Intent and file-format routing | `document_processor.py` |
| Docling layout, OCR, tables, chart handling | `docling_adapter/processor.py` |
| OCR line detection and printed/handwritten routing | `docling_adapter/scanned/` |
| Docling output mapping | `docling_adapter/result_mapper.py` |
| Invoice/caption preprocessing and output shaping | `vintern_processor.py` |
| Vintern model loading and inference | `vintern_worker.py` |
| Upload Test API | `src/app/upload_test.py` |
| Production upload caller | `src/app/main.py` |

For local commands and image build notes, see [development](docs/development.md).

## CPU OCR performance

VietOCR's RapidOCR detector uses maximum-edge resizing on CPU. Layout crops
are already rendered at OCR scale, so narrow text regions should not be
expanded until their short edge reaches 736 pixels. The CUDA route keeps its
existing detector configuration.

CPU pipelines default to 2 threads. `docling_num_threads` controls the budget
for both PP-DocLayoutV3 and TableFormer; override it when profiling a different
CPU allocation. CUDA retains the previous default of 4 CPU threads.

Use the [parser latency command](docs/development.md#measure-parser-latency)
to compare cold and warm runs with identical inputs and inspect any changes
in text or table cells before accepting a speed improvement.
