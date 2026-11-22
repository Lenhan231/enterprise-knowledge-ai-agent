# Document processing

This package converts supported files into parser output: ordered `elements`,
structured `tables`, and provenance metadata. It does not own chunking,
embeddings, retrieval, or application persistence.

Start here when tracing a document:

1. [Architecture and request flow](docs/architecture.md)
2. [Parser contract and callers](docs/document-processing.md)
3. Follow the selected path in [Docling and OCR](docs/docling-pipeline.md) or
   [invoice extraction](docs/invoice-pipeline.md)
4. Check [output metadata](docs/metadata.md), then the separate
   [chunking pipeline](../core/chunking/README.md)

## Current routes

```text
DocumentProcessor.process
  ├─ intent=document       → Docling → elements + tables
  └─ intent=invoice        → Docling OCR + tables → invoice extractor → JSON draft

parser output → application handoff → core/chunking → persistence / indexing
```

The invoice intent runs Docling for reviewable text and tables. Pretrained
Gemini and Groq API models use that evidence to extract fields for human review.

## Useful entry points

| Need to find | Start at |
| --- | --- |
| Intent and file-format routing | [document_processor.py](document_processor.py) |
| Docling layout, OCR, tables, chart handling | [docling_adapter/processor.py](docling_adapter/processor.py) |
| OCR line detection and printed/handwritten routing | [docling_adapter/scanned/](docling_adapter/scanned/) |
| Docling output mapping | [docling_adapter/result_mapper.py](docling_adapter/result_mapper.py) |
| Invoice OCR cache, extraction providers, and schema | [invoice/](invoice/) |
| Isolated Python workers | [worker_runtime.py](worker_runtime.py) |
| Local parser review UI | [testing_parser_streamlit.py](../../tools/processing/testing_parser_streamlit.py) |
| Upload Test API | [src/app/upload_test.py](../app/upload_test.py) |
| Production upload caller | [src/app/main.py](../app/main.py) |

For local commands and image build notes, see [development](docs/development.md).

## CPU OCR performance

VietOCR's RapidOCR detector uses maximum-edge resizing on CPU. Layout crops
are already rendered at OCR scale, so narrow text regions should not be
expanded until their short edge reaches 736 pixels. The CUDA route keeps its
existing detector configuration.

CPU OCR pipelines default to 2 threads. `docling_num_threads` controls the OCR
and Docling CPU budget. `docling_layout_num_threads` overrides only
PP-DocLayoutV3; invoice uploads set it from
`DOCUMENT_PROCESSING_INVOICE_LAYOUT_THREADS` (default 2), leaving VietOCR and
its RapidOCR detector at 2 threads. CUDA retains the previous default of 4
CPU threads.

Use the [parser latency command](docs/development.md#measure-parser-latency)
to compare cold and warm runs with identical inputs and inspect any changes
in text or table cells before accepting a speed improvement.
