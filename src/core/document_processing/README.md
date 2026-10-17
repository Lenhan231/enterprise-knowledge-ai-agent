# Document processing

This package converts uploaded files into parser chunks and structured table
records. It does not embed text or write to the database; the application and
repository layers own persistence and indexing. The broader OCR configuration,
evaluation, and operation guide is in
[`docs/technical/document-processing.md`](../../../docs/technical/document-processing.md).
For the shared chunk metadata fields and parser-specific extensions, see
[`metadata.md`](metadata.md).
For the staged plan from parsing through vector storage, see
[`chunking-embedding-plan.md`](chunking-embedding-plan.md).

## Processing flow

```text
upload bytes + metadata
        │
        ▼
DocumentProcessor.process()
        │ dispatch by extension
        ├── PDFProcessor ── PDF digital-born extraction / scanned-page OCR / optional parser
        ├── OfficeProcessor ── DOCX, PPTX, XLSX digital-born + scanned-image paths
        ├── TextProcessor ── TXT, Markdown digital-born text
        └── ScannedImageProcessor ── image OCR and scanned-table recovery
        │
        ▼
{chunks, tables, metadata}
        │
        ├── processed_document_chunks (parser output)
        ├── structured table storage
        └── token-bounded embedding input → document_chunks
```

`DocumentProcessor` is the format dispatcher and attaches common filename,
format, and chunk metadata. `PDFProcessor` owns PDF extraction and selects the
PDF path. Parsers return model-neutral text; `main.py` persists parser output,
then splits any overlong text to the embedding model's token limit before
creating vectors. Thus parser chunks and retrieval chunks can differ.

Digital-born extraction stays with each format processor because DOCX, XLSX,
PPTX, and PDF expose different native structures. When a format contains a
scanned page or embedded image, its adapter uses shared OCR and table-recovery
components under `scanned/`. PDF page rendering, orientation, and coordinate
mapping remain PDF-specific.

## PDF parser selection

The production upload route currently does not pass `parser_engine`, so PDFs
use the default PyMuPDF/native-text path with Tesseract fallback for pages
without usable text. `DOCUMENT_PADDLE_LAYOUT=true` can select its optional
Paddle layout path. The production route does not currently select MinerU.

Upload Test accepts a per-run parser selection: `pymupdf_tesseract`,
`pp-structurev3`, `mineru`, or `docling`. It stores parser chunks,
token-bounded embedding inputs, and tables in isolated test tables; it stops
before embedding and vector creation and does not create a production document
or retrieval entry.

When `parser_engine="mineru"`, `PDFProcessor` delegates directly to
`MineruProcessor`. It runs the local `mineru-kit` CLI at Basic tier, reads
Middle JSON, and maps page blocks to chunks with page, layout, bounding-box,
parser, and tier metadata. Configure its isolated runtime with
`MINERU_LOCAL_CLI` and `MINERU_LOCAL_HOME`. Upload Test then applies shared
cleanup and chunking; the character limit is a ceiling, not a target.

When `parser_engine="docling"`, `PDFProcessor` delegates to `DoclingProcessor`.
Install the optional parser with `uv sync --extra docling`; it uses local
RapidOCR/ONNX Runtime and Docling layout/table models. Its page, section,
bounding-box, OCR, and table output is normalized and chunked through the same
Upload Test stage as the other parsers.

## Table behavior

The default PDF path detects native or OCR tables, attempts to find a nearby
table title, and runs `_replace_flat_table_chunks()`. It serializes column names
and rows, adds a detected title as `Table: <title>`, then uses the shared
chunking strategy used by other formats. Structured rows are returned separately
for persistence. Title extraction is best-effort, so a chunk may have column
context without a title.

MinerU takes a separate path and does not call the default PDF table formatter
or title detector. Its adapter converts Markdown pipe tables and HTML table
blocks to structured rows, including repeated values from row spans. The
parser chunk is serialized as column and row text rather than raw table markup.
MinerU table chunks still may not have a title prefix, even when the default
PDF path would add one. Upload Test displays this parser output beside final
embedding chunks.

Office parsers locate embedded images in their package and send the image bytes
through shared Tesseract OCR. OCR text becomes a separate image chunk with
paragraph, slide, or worksheet location metadata. Office image tables currently
remain OCR text; structured row recovery is used by standalone images and the
PDF OCR table path.

## Source files

- `document_processor.py`: format dispatch and shared metadata.
- `processors/pdf/processor.py`: PDF flow coordination, parser selection, and
  optional image captioning.
- `processors/pdf/text_extractor.py`: page-level coordination between native
  text and scanned OCR, headings,
  and structured table extraction in one PDF traversal.
- `processors/pdf/digital_born/native_text.py`: embedded PDF text extraction.
- `processors/pdf/scanned/ocr.py`: rendered-page OCR, rotation, and deskew.
- `processors/pdf/text_chunks.py`: page-local chunks for the mixed PDF page flow.
- `processors/pdf/table_chunks.py`: PDF table formatting and matching; chunk
  boundaries come from the shared chunking router against flat page text chunks.
- `processors/pdf/table_processor.py`: PDF table title/context recovery,
  coordinate restoration, and continuation linking.
- `pipelines/mineru/processor.py`: local MinerU Basic CLI adapter.
- `pipelines/pp_structurev3/processor.py`: PP-StructureV3 integrated OCR/layout/table pipeline.
- `processors/pdf/table_extractor.py`: native and OCR word-box table extraction.
- `scanned/layout/doclayout_yolo.py`: optional diagnostic layout detector.
- `headings/`: shared numbered-heading patterns and section metadata fields;
  each format or pipeline still detects headings from its own source structure.
- `scanned/processor.py`: standalone image OCR and scanned-table recovery.
- `scanned/ocr/`: shared Tesseract runner, image text, and word-box recognition.
- `scanned/table_recovery.py`: reconstructs scanned tables from OCR word boxes.
- `processors/office/processor.py`: Office archive validation and format routing.
- `processors/office/{docx,pptx,xlsx}/digital_born/`: native text, tables,
  formulas, and format-specific structure.
- `processors/office/{docx,pptx,xlsx}/scanned/`: embedded-image OCR adapters
  that call shared OCR code.
- `processors/office/scanned/image_ocr.py`: shared Office image relationship
  handling and OCR chunk creation.
- `processors/csv/digital_born/processor.py`: UTF-8 CSV parsing into structured
  rows and searchable row-aware chunks.
- `processors/text/digital_born/processor.py`: TXT/Markdown decoding and dispatch.
- `core/document_processing/chunking/router.py`: routes text to the selected chunking strategy.
- `core/document_processing/chunking/config.py`: shared chunk size, overlap, and strategy settings.
- `core/document_processing/chunking/chunk_builder.py`: adds parser chunk metadata to split text.

For chunk boundaries and token limits, see
[`docs/technical/chunking.md`](../../../docs/technical/chunking.md).
