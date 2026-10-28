# Document processing

This package owns document parsing, shared cleanup and provenance, and returns
ordered elements plus structured tables. Chunking is a separate workstream in
`src/core/chunking/`. The application owns upload handling and persistence.

## Flow

```text
upload bytes
  → DocumentProcessor routes supported files to Docling
  → parser returns ordered elements + tables
  → shared cleanup and provenance normalization
  → structured document output: ordered elements + tables
  → separate core.chunking stage
  → application persistence
```

Production upload and Upload Test use this processing package. Production
persists its normalized output through
`DocumentProcessingOutputsRepository` before chunking; Upload Test stores its
review data in its isolated schema. Model-specific token splitting, embeddings,
and retrieval indexing are outside this package.

## Main modules

| Path | Responsibility |
| --- | --- |
| `document_processor.py` | Route parsing, normalize provenance, clean ordered elements and tables. |
| `docling/` | Docling parser and result mapper. |
## Parser routing

`DocumentProcessor` sends supported files, including TXT, to Docling and
normalizes the output. Parser-specific details remain in
metadata; `pipeline_id` records the configured parser engine and `parser`
identifies the component that produced the element or table.

Docling handles supported PDF, Office, CSV, TXT, Markdown, and image inputs.

Production PDF/image parsing uses the shared benchmark profile: CPU, 1.0 image
scale, Heron layout detection, Tesseract OCR (`vie+eng`, PSM 6 by default), and
TableFormer Accurate with cell matching. Production defaults to two CPU threads;
callers such as Upload Test may override the device, OCR language, table stage,
and thread count. Page-orientation diagnostics are benchmark-only; production
does not automatically rotate source pages.

PDFs with at least 100 non-whitespace native text characters on every page are
classified as digital-born and bypass OCR. Other PDFs use the configured OCR
setting; the selected route and effective OCR state are included in parser
result metadata. For digital-born PDFs, detected raster pictures are cropped
and sent through OCR separately; their recognized boxes are mapped back onto
the source page. Office files similarly keep native text and send embedded
pictures through the scanned-image path.

The authoritative supported extension list is `SUPPORTED_FORMATS` in
`document_processor.py`.

## Output boundary

This package returns ordered `elements` and structured `tables`, retaining
available provenance and source locations such as page, sheet, slide, section,
or bounding box. It does not create parser chunks. See the separate
[chunking module](../../core/chunking/README.md) for text/table chunking and
[metadata](metadata.md) for shared parser output fields.

## Call sites

- Production upload: `/api/documents/upload` in `src/app/main.py`.
- Isolated parser inspection: `/api/upload-tests` in `src/app/upload_test.py`.
- Chunking stage: `src/core/chunking/processor.py`.
- Normalized output persistence: `src/core/database/document_processing_outputs_repository.py`.
- Chunked parser-output persistence: `src/core/database/parser_chunks_repository.py`.
- Structured table persistence: `src/core/database/structured_store.py`.
