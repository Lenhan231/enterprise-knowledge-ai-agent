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
        ├── PDFProcessor ── native PDF text / Tesseract / optional layout parser
        ├── OfficeProcessor ── DOCX, PPTX, XLSX
        ├── TextProcessor ── TXT, Markdown
        └── ImageProcessor ── image OCR
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

## PDF parser selection

The production upload route currently does not pass `parser_engine`, so PDFs
use the default PyMuPDF/native-text path with Tesseract fallback for pages
without usable text. `DOCUMENT_PADDLE_LAYOUT=true` can select its optional
Paddle layout path. The production route does not currently select MinerU.

OCR Lab accepts a per-run parser selection: `pymupdf_tesseract`,
`pp-structurev3`, or `mineru`. OCR Lab stores isolated test output; running a
parser there does not ingest a production document or create embeddings.

When `parser_engine="mineru"`, `PDFProcessor` delegates directly to
`MineruProcessor`. It calls the configured Hugging Face Space
(`MINERU_HF_SPACE`, default `opendatalab/MinerU`) at Basic tier, then maps page
blocks to chunks with page, layout, bounding-box, parser, and tier metadata.
Each block is chunked separately with the common text chunker (default maximum
1,100 characters). Neighboring short blocks are not merged; whitespace within
a block is collapsed. The character limit is a ceiling, not a target.

## Table behavior

The default PDF path detects native or OCR tables, attempts to find a nearby
table title, and runs `_replace_flat_table_chunks()`. Its row-aware fragments
include column names and repeat a detected title as `Table: <title>`; structured
rows are returned separately for persistence. Title extraction is best-effort,
so a chunk may have column context without a title.

MinerU takes a separate path and does not call the default PDF table formatter
or title detector. Its adapter converts Markdown pipe tables and HTML table
blocks to structured rows, including repeated values from row spans. The
parser chunk is serialized as column and row text rather than raw table markup.
MinerU table chunks still may not have a title prefix, even when the default
PDF path would add one. OCR Lab displays this parser output, not the final
embedding chunks.

## Source files

- `processors/document_processor.py`: format dispatch and shared metadata.
- `processors/pdf/processor.py`: PDF extraction, parser selection, and default
  PDF table formatting.
- `processors/pdf/mineru_processor.py`: MinerU Hugging Face adapter.
- `processors/pdf/layout_processor.py`: Paddle layout processing.
- `processors/pdf/table_extractor.py`: native and OCR word-box table extraction.
- `processors/pdf/doclayout_yolo.py`: optional DocLayout-YOLO detection helper.
- `processors/image/processor.py`: standalone image OCR and table extraction.
- `processors/office/processor.py`: DOCX, PPTX, and XLSX parsing.
- `processors/text/processor.py`: TXT/Markdown decoding and dispatch.
- `core/chunking/text_chunker.py`: shared character-based chunking strategies.

For chunk boundaries and token limits, see
[`docs/technical/chunking.md`](../../../docs/technical/chunking.md).
