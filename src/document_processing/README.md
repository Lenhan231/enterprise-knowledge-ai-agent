# Document processing

This package parses supported files into ordered elements and structured
tables. Its ownership ends at normalized document-processing output; chunking
and persistence are handled by separate modules in the application.

For supported formats and OCR settings, see the [processing guide](docs/document-processing.md).
Shared provenance fields are listed in [`docs/metadata.md`](docs/metadata.md).

## Flow

```text
DocumentProcessor.process(file)
    └── DoclingProcessor (format router)
          ├── native document conversion → {elements, tables}
          └── scanned/embedded_images → OCR selected PDF/Office pictures only
                └── result_mapper → {elements, tables}
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
| `docling_adapter/processor.py` | Route native document conversion and scanned embedded images. |
| `docling_adapter/digital_born/` | Native PDF detection and DOCX structure enrichment. |
| `docling_adapter/scanned/` | Layout/OCR flow for selected raster images embedded in PDFs and Office documents. |
| `docling_adapter/result_mapper.py` | Normalize native and scanned results into shared elements and tables. |
`pipeline_id` records the configured parser engine; `parser` identifies the
component that produced an element or table. See [`docs/metadata.md`](docs/metadata.md).

PDFs with at least 100 non-whitespace native text characters on every page use
Docling's native text path with OCR disabled. If any page falls below that
threshold, the PDF is routed as scanned and uses OCR when enabled in the parser
configuration. The selected route and effective OCR setting are returned in
the parser result metadata.

## Module Docker image

Build and start the private parser service from the repository root:

```sh
docker compose build document-processing
docker compose up -d --no-deps --wait document-processing
```

The image serves the authenticated `/parse` and `/health` endpoints on its
internal Docker network. It contains Docling, VietOCR, RapidOCR, and
Vietnamese/English Tesseract. Set `DOCUMENT_PROCESSING_OCR_ENGINE` in the
service environment to `tesseract` to select Tesseract instead of VietOCR.

Startup initializes the default scanned, native PDF, and embedded-image
pipelines before reporting healthy. This loads the OCR, layout, and table
models into memory; import-only checks do not count as preloading. A model
loading failure prevents startup. The embedding and reranker services also
load their models before accepting requests; the backend calls those services.

Converters are reused across requests with equivalent settings. Up to four
configurations are retained; custom settings can initialize another pipeline
on first use and evict an older configuration. Startup takes longer and idle
RAM usage increases. Hugging Face weights persist in the model-cache volume;
VietOCR's temporary weights and Torch's default cache are container-local.

For the independent chunking image, see
[`core/chunking/README.md`](../core/chunking/README.md#module-docker-image).

## Local owner store UI

Install the optional Streamlit UI and run it on loopback:

```sh
PYTHONPATH=src \
  .venv/bin/streamlit run src/document_processing/testing_parser_streamlit.py \
  --server.address 127.0.0.1 --server.port 8502
```

By default, source files and Docling JSON output are saved under
`src/document_processing/.owner_store/`. Set `DOCUMENT_PROCESSING_STORE` to
use another local folder. PDF uploads can select arbitrary pages, such as
`2, 5, 9`, before Docling runs, which is useful for reviewing a few pages of a
large document. Leaving the field blank processes the full PDF.
