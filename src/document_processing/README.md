# Document processing

This package parses supported files into ordered elements and structured
tables. Its ownership ends at normalized document-processing output; chunking
and persistence are handled by separate modules in the application.

For supported formats and OCR settings, see the [processing guide](docs/document-processing.md).
Shared provenance fields are listed in [`docs/metadata.md`](docs/metadata.md).

## Flow

```text
DocumentProcessor.process(file)
    └── DoclingProcessor → {elements, tables}
            └── common cleanup + provenance

application → core.chunking → persist chunks/tables
```

Production upload and Upload Test call this parser package and the separate
chunking module. Upload Test stores isolated results. This package does not
handle chunking, tokenization, embeddings, or retrieval indexing.

## Package map

| Path | Responsibility |
| --- | --- |
| `document_processor.py` | Route supported files to Docling; normalize output and provenance. |
| `docling_adapter/` | Docling parser implementation and result mapper. |
`pipeline_id` records the configured parser engine; `parser` identifies the
component that produced an element or table. See [`docs/metadata.md`](docs/metadata.md).

## Local owner store UI

Install the optional Streamlit UI and run it on loopback:

```sh
uv sync --extra docling --extra document-processing-ui
PYTHONPATH=src .venv/bin/streamlit run src/document_processing/streamlit_app.py --server.address 127.0.0.1 --server.port 8501
```

By default, source files and Docling JSON output are saved under
`src/document_processing/.owner_store/`. Set `DOCUMENT_PROCESSING_STORE` to
use another local folder.
