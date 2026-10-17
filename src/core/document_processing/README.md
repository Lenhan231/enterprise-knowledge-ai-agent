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
        │ formats/ routes by extension
        ├── PDF / Office / CSV / text / image ── selected pipeline format adapter
        ├── Office ── DOCX, PPTX, XLSX native + embedded-image paths
        ├── CSV / Text ── format-specific readers
        └── Image ── shared OCR and scanned-table recovery
        │
        ▼
{chunks, tables, metadata}
        │
        ├── document_parser_chunks (parser output)
        ├── structured table storage
        └── token-bounded embedding input → document_chunks
```

`DocumentProcessor` selects one pipeline, whose `formats/` router handles every
supported file extension and common provenance. Each parser returns
model-neutral output; `main.py` persists parser output,
then passes parser output to the shared tokenizer in `core/tokenization/` to split overlong passages
before vector creation. Parser chunks and token-bounded chunks remain separate
outputs so each stage can be inspected.

Digital-born extraction stays with each format processor because DOCX, XLSX,
PPTX, and PDF expose different native structures. When a format contains a
scanned page or embedded image, its adapter uses shared OCR and table-recovery
components under `scanned/`. PDF page rendering, orientation, and coordinate
mapping remain PDF-specific.

## Parser selection

The production upload route currently does not pass `parser_engine`, so it uses
the `built_in` profile. Its format adapter selects PyMuPDF/Tesseract for PDF,
Tesseract for images, and native format readers for Office, CSV, and text.
Upload Test can independently select any profile for every supported format.
`pipeline_id` records the selected profile; `parser` records the component that
actually produced each chunk or table. Missing page/bbox data stays absent.

Upload Test accepts a per-run parser selection: `built_in`,
`pp-structurev3`, `mineru`, or `docling`. It stores parser chunks and tables
in isolated test tables. The “Parser chunks only” output stage skips tokenization;
the optional token-limit preview stores a second, bounded representation. Both
stages stop before embedding and do not create a production document or retrieval entry.

When `parser_engine="mineru"`, `pipelines/mineru/processor.py` dispatches to
the matching adapter under `pipelines/mineru/formats/`. The PDF adapter runs
Basic tier and maps Middle JSON; Office and CSV use native Flash parsing; raster
images use Basic OCR; text files use the native text reader. Office images are
sent individually through MinerU Basic OCR. Configure its isolated runtime with
`MINERU_LOCAL_CLI` and `MINERU_LOCAL_HOME`. Upload Test then applies shared
cleanup and chunking; the character limit is a ceiling, not a target.

When `parser_engine="docling"`, the document router selects
`pipelines/docling/processor.py`.
Install the optional parser with `uv sync --extra docling`; it uses local
RapidOCR/ONNX Runtime and Docling layout/table models. Its page, section,
bounding-box, OCR, and table output is normalized and chunked through the same
Upload Test stage as the other parsers.

## Table behavior

Every digital-born table and structured pipeline table uses
`chunking.router.build_chunks(kind="table")`: it serializes columns and rows,
repeats the title/header for each chunk, and keeps row boundaries intact. The
default PyMuPDF PDF path preserves extracted page text and appends separate
structured table chunks through the shared table chunker. It does not compare
or replace flat page text; PDF title recovery remains best-effort.

MinerU converts Markdown pipe tables and HTML table blocks to structured rows,
then uses the same table chunk builder as Docling, PP-StructureV3, CSV, Office,
and the default PDF path. Parser-specific extraction metadata remains attached
to each table and chunk. Upload Test displays parser chunks beside final
embedding chunks.

Built-in and PP-StructureV3 Office readers locate embedded images and run them
through their selected OCR engine, keeping paragraph, slide, or worksheet
location metadata. MinerU parses Office structure at Flash tier, reads the
image assets from MinerU's own result archive, then sends DOCX/PPTX/XLSX images
through MinerU Basic OCR and adds OCR text as separate image chunks. This avoids
re-reading Office XML through the root format reader. Image OCR chunks retain
the MinerU asset path; table recovery remains available on the PDF/image parser
result paths.

## Source files

- `document_processor.py`: pipeline selection, common cleaning, provenance, and chunk metadata.
- `readers/`: format readers shared by pipelines where their native extraction applies.
- `pipelines/{built_in,docling,mineru,pp_structurev3}/formats/router.py`: per-profile format routing.
- `pipelines/mineru/formats/`: MinerU adapters for PDF, raster images, Office, CSV, and text.
- `pipelines/{built_in,docling,mineru,pp_structurev3}/`: parser engines
  that produce the same `{chunks, tables}` result shape.
- `pipelines/built_in/processor.py`: built-in PDF pipeline coordinator.
- `pipelines/built_in/pdf_images.py`: embedded PDF image extraction and optional captions.
- `pipelines/built_in/text_extractor.py`: page-level coordination between native
  text and scanned OCR, headings,
  and structured table extraction in one PDF traversal.
- `formats/pdf/digital_born/native_text.py`: embedded PDF text extraction.
- `pipelines/built_in/scanned/pdf_ocr.py`: rendered-page OCR, rotation, and deskew.
- `pipelines/built_in/scanned/ocr/`: Built-in Tesseract runner and image OCR helpers.
- `pipelines/built_in/text_chunks.py`: page-local chunks for the mixed PDF page flow.
- `chunking/table/chunker.py`: shared row-aware table chunk creation; parser
  pipelines supply structured table data and context metadata.
- `pipelines/built_in/table_processor.py`: PDF table title/context recovery,
  coordinate restoration, and continuation linking.
- `pipelines/mineru/processor.py`: local MinerU Basic CLI adapter.
- `pipelines/mineru/result_mapper.py`: MinerU Markdown/Middle JSON table and chunk normalization.
- `pipelines/pp_structurev3/processor.py`: PP-StructureV3 integrated OCR/layout/table pipeline.
- `pipelines/pp_structurev3/page_parser.py`: PP-Structure predictions to ordered page blocks and tables.
- `pipelines/docling/result_mapper.py`: Docling items to shared chunks and structured tables.
- `pipelines/built_in/table_extractor.py`: native and OCR word-box table extraction.
- `utils/layout/doclayout_yolo.py`: optional Upload Test diagnostic layout detector.
- `headings/`: shared numbered-heading patterns and section metadata fields;
  each format or pipeline still detects headings from its own source structure.
- `formats/image/processor.py`: standalone image OCR and scanned-table recovery.
- Tesseract OCR and table recovery live under `pipelines/built_in/scanned/` because
  they implement the Built-in parser's OCR path.
- `pipelines/built_in/scanned/table_recovery.py`: reconstructs tables from Built-in OCR word boxes.
- `formats/office/processor.py`: Office archive validation and format routing.
- `formats/office/{docx,pptx,xlsx}/digital_born/`: native text, tables,
  formulas, and format-specific structure.
- `formats/office/{docx,pptx,xlsx}/scanned/`: embedded-image OCR adapters
  that call shared OCR code.
- `formats/office/scanned/image_ocr.py`: shared Office image relationship
  handling and OCR chunk creation.
- `pipelines/helpers/`: shared parser-pipeline helpers, including HTML table parsing
  and selected-pipeline OCR for embedded Office images.
- `formats/csv/digital_born/processor.py`: UTF-8 CSV parsing into structured
  rows and searchable row-aware chunks.
- `formats/text/digital_born/processor.py`: TXT/Markdown decoding and dispatch.
- `core/document_processing/chunking/router.py`: routes text or table content to its chunker.
- `core/document_processing/chunking/text/`: text chunk construction and fixed/sentence strategies.
- `core/document_processing/chunking/table/chunker.py`: shared row-preserving table chunks.
- `core/document_processing/chunking/config.py`: shared chunk size, overlap, and strategy settings.
- `core/document_processing/chunking/text/chunk_builder.py`: builds text chunks and attaches metadata.
- `tokenization/`: counts model tokens and splits final passages while repeating
  section and table headers when an oversized chunk needs token-level splitting.

For chunk boundaries and token limits, see
[`docs/technical/chunking.md`](../../../docs/technical/chunking.md).
