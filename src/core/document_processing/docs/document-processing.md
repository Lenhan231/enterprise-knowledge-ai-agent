# Document processing

This package owns document parsing, shared cleanup and provenance, and creation
of parser chunks plus structured tables. The application owns upload handling
and persistence. This guide stops at parser output.

## Flow

```text
upload bytes
  → DocumentProcessor selects one parser pipeline
  → pipeline adapter reads the format and returns ordered elements + tables
  → shared cleanup and provenance normalization
  → ChunkingProcessor creates text/table parser chunks
  → application persists parser chunks and structured tables
```

Production upload and Upload Test use the same processing and chunking code.
Upload Test persists into its isolated test schema; production persists parser
chunks and tables through the application repositories. Model-specific token
splitting, embeddings, and retrieval indexing are outside this package.

## Main modules

| Path | Responsibility |
| --- | --- |
| `document_processor.py` | Select pipeline, normalize provenance, clean ordered elements and tables. |
| `pipelines/{built_in,docling,mineru,pp_structurev3}/` | Pipeline implementations, format routers, and result adapters. |
| `readers/` | Native digital-born and scanned readers for supported formats. |
| `pipelines/helpers/` | Shared helpers used by parser pipelines. |
| `pipelines/built_in/scanned/` | Built-in OCR and table recovery components. |
| `utils/` | Shared diagnostics and utilities such as layout detection. |
| `headings/` | Heading metadata inference and normalization. |
| `chunking/processor.py` | Order normalized elements and create parser chunks. |
| `chunking/text/` | Character-based sentence and fixed text strategies. |
| `chunking/table/chunker.py` | Row-aware chunks with repeated table context and headers. |

## Pipeline selection

`DocumentProcessor` accepts `parser_engine`: `built_in`, `docling`, `mineru`,
or `pp-structurev3`. Each selected pipeline has its own format router and
normalizes its output through the shared document processor. Parser-specific
details remain in metadata; `pipeline_id` records the selected pipeline and
`parser` identifies the component that produced the element or table.

The built-in pipeline uses PyMuPDF/Tesseract for PDFs and images and native
readers for digital-born Office, CSV, TXT, and Markdown. Docling, MinerU, and
PP-StructureV3 are separate parser options; availability depends on their local
runtime and model installation. Format support can differ by pipeline.

The authoritative supported extension list is `SUPPORTED_FORMATS` in
`document_processor.py`.

## Chunk and table output

`ChunkingProcessor` receives `{elements, tables}` from the parser. It groups
related text elements, routes tables through the row-aware table chunker, keeps
source order, and emits `{chunks, tables}`. Every chunk retains parser
provenance and available source location such as page, sheet, slide, section,
or bounding box. Tables remain structured as columns and rows while also
producing readable parser chunks; each table fragment repeats its section,
title, and column headers.

See [parser chunking](chunking.md) for the character-based strategies and
[metadata](metadata.md) for the shared parser output fields.

## Call sites

- Production upload: `/api/documents/upload` in `src/app/main.py`.
- Isolated parser inspection: `/api/upload-tests` in `src/app/upload_test.py`.
- Production parser-chunk persistence: `src/core/database/parser_chunks_repository.py`.
- Structured table persistence: `src/core/database/structured_store.py`.
