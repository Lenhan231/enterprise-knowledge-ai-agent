# Document processing metadata

This file describes metadata produced by the current upload and OCR processing
paths. It is a JSON contract stored with parser chunks and structured tables;
the database does not require one fixed set of JSONB keys.

## Shared chunk fields

The shared normalization and chunking stages add these fields to parser chunks
and structured tables:

| Field | Meaning |
| --- | --- |
| `filename` | Original uploaded filename. |
| `format` | Technical file format, such as `PDF`, `DOCX`, or `CSV`. |
| `pipeline_id` | Selected profile: `built_in`, `docling`, `mineru`, or `pp-structurev3`. |
| `parser` | Actual component that produced this chunk/table, for example `docling`, `python-csv`, or `tesseract`. |
| `chunk_index` | Zero-based index in this parser result (chunks only). |
| `actual_char_count` | Character count of the parser chunk text (chunks only). |
| `table_index` | Zero-based table index (tables only). |

Processors add source locations such as `page_number`, `sheet_name`, or
`slide_number` only when meaningful for the format. These fields
describe the parser result; the upload endpoint may later split an oversized
chunk for the embedding model and assign new retrieval chunk indexes and token
metadata. See [chunking](chunking.md).

The legacy `extracted_tables.page_number` database column is non-nullable. The
structured store uses `0` internally for tables without page locations and
returns that sentinel as `null`; source metadata retains the real sheet/slide
location.

## Heading context

Processors use `section_title` for the active heading or format-level section
and `heading_level` for its depth (1–9 where the source provides it). Markdown
uses explicit `#` levels; DOCX uses Heading styles; PPTX uses its title
placeholder; XLSX uses the worksheet name as a level-one section. PDF and OCR
pipelines infer levels from numbered labels or prominent text, so those values
are best-effort. Plain TXT only recognizes conservative standalone
numbered or all-caps heading lines. Image OCR does not infer heading levels.
When a format provides no reliable heading, both values are null or omitted.

## Request context

The same processor receives different context from each caller:

- Production upload adds `document_id`, `company`, `domain`, business
  `document_type`, fiscal year, source URL/type, and allowed roles. Its source
  type is `user_upload` unless the caller explicitly marks demo material.
- Upload Test adds `source_type="upload_test"` and the input `source_sha256`.
  It saves parser chunks and normalized table rows in isolated storage; it
  stops before tokenization, embeddings, or production document creation.
`format` and `document_type` are different concepts: `format` is the file
extension; `document_type` is the business classification selected for a
production upload.

## Parser provenance

Parser-specific fields are optional extensions to the shared fields. They must
not replace or rename shared provenance keys.

| Parser path | Example metadata |
| --- | --- |
| Default PDF | `parser="pymupdf"`, OCR method/settings when OCR was used, PDF page and table metadata. |
| MinerU Basic | `parser="mineru"`, `mineru_tier="basic"`, `layout_type`, `element_type`, page, bounding box, and `mineru_runtime="local"` at run level. |
| Paddle PP-StructureV3 | `parser="paddleocr.PP-StructureV3"`, layout and OCR details. |
| Office parsers | Format-specific parser name; XLSX may include `sheet_name`. |
| CSV | `parser="python-csv"`, delimiter, one structured table, and row-aware text chunks. |

For example, a MinerU Upload Test chunk can include `parser="mineru"` while a
production PDF chunk has `parser="pymupdf"`. That difference is intentional:
it records which engine produced the content. The common keys and their
meanings remain the same. Parser-only details such as `mineru_tier` or `bbox`
are not required on other engines' output.

Tables are returned separately from text chunks as `{table_index, columns,
rows, metadata}` with optional source locations. The production upload persists this structure in the
structured table store; Upload Test keeps columns and normalized rows in
`upload_test_tables` and `upload_test_records`. Table
chunks may also contain row-aware text for retrieval. See the
[processing guide](document-processing.md).

## Current model boundary

Production upload and Upload Test build metadata dictionaries and add caller-
and parser-specific keys. [`ChunkMetadata`](../../models/document.py) is used
by a separate ingestion utility and is not the complete production parser
schema; do not treat it as a strict allowlist for JSONB. A symlink from
`document_processing` to that dataclass would create another import path, not a
shared metadata contract. Keep `core/models` as the model owner; use this file
to understand which keys are common and which are optional provenance.

If code needs a shared runtime type in the future, define it at the common
model boundary and use the same import path from all producers. Keep JSONB
extensions for parser and caller context instead of making every engine emit
the same parser-specific fields.
