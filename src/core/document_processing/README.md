# Document processing

This package parses supported files into ordered elements and structured tables.
It does not persist documents or create embeddings. The application owns upload
and persistence; tokenization and embedding are downstream stages.

For end-to-end flow, OCR settings, supported formats, and chunking, see the
package docs index at [`docs/README.md`](docs/README.md). Shared
provenance fields are listed in [`docs/metadata.md`](docs/metadata.md).

## Flow

```text
DocumentProcessor.process(file)
    └── selected pipeline → format adapter → {elements, tables}
                                  │
                                  └── common cleanup + provenance

ChunkingProcessor.process(parsed output)
    ├── text elements → text strategies
    └── table elements → row-aware table chunks

application → persist parser chunks/tables → downstream tokenization and indexing
```

Production upload and Upload Test use the same parser and chunking stages.
Upload Test stores isolated results and stops before production indexing.

## Package map

| Path | Responsibility |
| --- | --- |
| `document_processor.py` | Select a parser profile, normalize provenance, clean parser output. |
| `pipelines/{built_in,docling,mineru,pp_structurev3}/` | Parser implementations and per-pipeline format routers. |
| `readers/` | Native readers shared by pipeline adapters where applicable. |
| `pipelines/helpers/` | Shared helpers used by parser pipelines. |
| `ocr/`, `layout/`, `headings/` | Shared OCR utilities, layout helpers, and heading metadata. |
| `chunking/processor.py` | Downstream routing and ordering of text/table chunks. |
| `chunking/text/` | Text chunk building and strategies. |
| `chunking/table/chunker.py` | Row-preserving table chunks with repeated headers/context. |

The selected parser profile is recorded as `pipeline_id`; `parser` identifies
the component that produced an element or table. Parser-specific metadata stays
optional. Do not treat `core/models/document.py` as the complete parser-output
schema; see [`docs/metadata.md`](docs/metadata.md).
