# Document processing metadata

This file describes metadata produced by the current upload and OCR processing
paths. It is a JSON contract stored with parser chunks and structured tables;
the database does not require one fixed set of JSONB keys.

## Shared chunk fields

`DocumentProcessor.process()` adds these fields to every parsed chunk:

| Field | Meaning |
| --- | --- |
| `filename` | Original uploaded filename. |
| `format` | Technical file format, such as `PDF` or `DOCX`. |
| `chunk_index` | Zero-based index in this parser result. |
| `actual_char_count` | Character count of the parser chunk text. |

Processors add `page_number` when the source has a known page. These fields
describe the parser result; the upload endpoint may later split an oversized
chunk for the embedding model and assign new retrieval chunk indexes and token
metadata. See [chunking](../../../docs/technical/chunking.md).

## Request context

The same processor receives different context from each caller:

- Production upload adds `document_id`, `company`, `domain`, business
  `document_type`, fiscal year, source URL/type, and allowed roles. Its source
  type is `user_upload` unless the caller explicitly marks demo material.
- OCR Lab adds `source_type="ocr_test"` and the input `source_sha256`. It saves
  parser chunks and tables in isolated OCR test storage and does not embed them.
- Seed ingestion supplies source-document metadata separately and currently
  constructs the `ChunkMetadata` dataclass in
  [`src/core/models/document.py`](../models/document.py).

`format` and `document_type` are different concepts: `format` is the file
extension; `document_type` is the business classification selected for a
production upload.

## Parser provenance

Parser-specific fields are optional extensions to the shared fields. They must
not replace or rename shared provenance keys.

| Parser path | Example metadata |
| --- | --- |
| Default PDF | `parser="pymupdf"`, OCR method/settings when OCR was used, PDF page and table metadata. |
| MinerU Basic | `parser="mineru"`, `mineru_tier="basic"`, `layout_type`, `element_type`, page, and bounding box. |
| Paddle PP-StructureV3 | `parser="paddleocr.PP-StructureV3"`, layout and OCR details. |
| Office parsers | Format-specific parser name; XLSX may include `sheet_name`. |

For example, a MinerU OCR Lab chunk can include `parser="mineru"` while a
production PDF chunk has `parser="pymupdf"`. That difference is intentional:
it records which engine produced the content. The common keys and their
meanings remain the same. Parser-only details such as `mineru_tier` or `bbox`
are not required on other engines' output.

Tables are returned separately from text chunks as `{page_number, table_index,
columns, rows, metadata}`. The production upload persists this structure in the
structured table store; OCR Lab keeps it with the isolated test run. Table
chunks may also contain row-aware text for retrieval. See the
[processing guide](../../../docs/technical/document-processing.md).

## Current model boundary

[`ChunkMetadata`](../models/document.py) is currently used by seed ingestion;
production upload and OCR Lab build dictionaries and add caller- and
parser-specific keys. The dataclass is therefore not the complete production
schema and must not be treated as a strict allowlist for JSONB. A symlink from
`document_processing` to that dataclass would create another import path, not a
shared metadata contract. Keep `core/models` as the model owner; use this file
to understand which keys are common and which are optional provenance.

If code needs a shared runtime type in the future, define it at the common
model boundary and use the same import path from all producers. Keep JSONB
extensions for parser and caller context instead of making every engine emit
the same parser-specific fields.
