# Chunking and section metadata

## Current behavior

The primary seed-PDF and upload paths now share one bounded splitter with two
configurable strategies. `sentence` groups sentence/paragraph boundaries up
to a character ceiling, then the existing model tokenizer enforces the final
512-token limit. It is structure-aware heuristic chunking, not an embedding-
similarity semantic segmenter. `fixed` preserves overlapping character
windows as the controlled baseline. The current default is `sentence`; no
strategy is considered optimal until retrieval and answer quality are compared.

| Path | Strategy and current setting | Source |
| --- | --- | --- |
| Seed PDF reports | Page-aware sentence-aware chunks: 1,200 character ceiling; 0 normal overlap | `Ingestion.ingestion`; choose `fixed` for baseline |
| Uploaded PDF | Page-aware sentence-aware chunks: 1,100 character ceiling; 0 normal overlap | `DocumentProcessor.process` |
| Uploaded TXT/MD, OCR images, Office text | Paragraph/sentence-aware where source text preserves paragraph breaks; 1,100 character ceiling; 0 normal overlap | `DocumentProcessor._split` |
| Fixed baseline | Word-boundary fixed windows: 1,100/120 upload, 1,200/150 seed | `DOCUMENT_CHUNKING_STRATEGY=fixed` or seed CLI flag |
| HTML seed reports | LangChain percentile embedding-semantic boundaries | `SemanticDocumentChunker` in `core/chunking/semantic_chunker.py` |

Before embedding, the seed and upload paths now apply the configured tokenizer
limit: `EMBEDDING_MAX_SEQUENCE_LENGTH=512` total tokens (including model
special tokens), with 32 content tokens of overlap when a source chunk needs
splitting. Original parser chunk sizes remain the first-stage limits.

PDF chunking stays within pages and carries page number, layout type, and the
current section title. Short visually prominent native-text lines and
explicitly numbered OCR lines (`Chapter`, `Article`, numbered subsections) can
set `section_title`; the current heading carries across pages. Unnumbered
OCR-only headings remain unsupported. Existing indexed rows keep their old
metadata unless they pass the exact-match backfill below. A read-only live
snapshot on 2026-09-28 initially found 4,278/4,750 manifest chunks with a
section title. Guarded metadata-only backfills then updated 22/28 eligible
chunks in `VNM-CGR-2025-EN`, 267/269 in the 2026 Charter and Governance Rules,
and 99 in five 2020–2024 governance reports. Each applied report had exact
chunk-count, index, and content matches. The full corpus now has 4,666/4,750
chunks titled; 84 remain null. Of those, 41 belong to the disclosure report,
23 to 2020–2024 governance reports, 8 to the CGR-2025 and 2026 charter/rules,
and 12 to annual/sustainability reports, HTML policies, or product information.
The per-document read-only snapshot is the [coverage audit](../../artifacts/evaluation/section-title-corpus-coverage-post-backfill-20260928.json).
A dry-run for seven annual/sustainability PDFs was skipped because parsed and stored
chunk counts differed; no rows were changed for them. See the [2020–2024
governance apply report](../../artifacts/evaluation/section-title-backfill-governance-2020-2024-applied.json)
and [annual/sustainability dry-run](../../artifacts/evaluation/section-title-backfill-annual-sustainability-dry-run-20260928.json).
The parser fix was also validated on a real scanned Governance Rules
page; its source/page hashes are in the [OCR section-title smoke artifact](../../artifacts/evaluation/vinamilk-section-title-ocr-smoke-20260928.json)
(3/3 chunks titled on PDF page 4). The backfill skips documents unless every
stored chunk index and content string exactly matches the current parser output;
it changes only section-title JSON metadata and writes a prior-value backup.
Stored `parent_id` values remain null; runtime `parent` retrieval uses up to two
neighboring chunks on the same page and under the same section title (or page
when no title exists).
This bounded context
expansion does not yet provide full structural parents for long sections.

The common parser records `chunk_strategy`, character ceiling and overlap in
each chunk's metadata. Uploads read `DOCUMENT_CHUNKING_STRATEGY` (default
`sentence`). Seed PDF ingestion defaults to `sentence` and accepts
`--chunking-strategy fixed|sentence` for controlled corpus builds. Existing
stored vectors do not change when this setting changes; re-ingestion and
re-embedding are required to switch the active indexed corpus.

On the public 2024 annual report (96 text-bearing pages, source SHA-256
`f0d99c9a6650e5f718f098784de037b342a5b9fff4184f5fd00ef7f8656c774a`), the
read-only boundary diagnostic produced 428 fixed chunks (mean 970 chars,
10.5% of chunk ends at sentence punctuation) and 438 sentence-aware chunks
(mean 857 chars, 81.7% sentence-punctuation boundaries). Both remained below
the 1,100-character ceiling. This diagnostic does not measure retrieval,
context quality, or answers and is not enough to choose a strategy; the raw
per-page summary is in
`artifacts/evaluation/vinamilk-chunking-2024-boundary-diagnostic.json`.

A paired dense-retrieval diagnostic compares the five fixed annual-report
vectors currently in Supabase with sentence-aware chunks and vectors built in
memory from the same 2020–2024 reports. It uses five finance questions, the
application's year preference, and the existing 384-dimensional embedding
model. Document MRR is 1.0 for both strategies (the five-document corpus is
restricted to the five matching annual reports, so this is only a pipeline
sanity check). The original 2026-09-26 run measured passage MRR 0.2715 fixed
vs 0.2648 sentence-aware; an intermediate 2026-09-28 run measured 0.2715 vs
0.2731. A source check found the 2022 case asked for net revenue but its two
fixed labels pointed to a financial-summary table labelled only “revenue”.
Those labels now point to the audited consolidated income statement (fixed
chunks 239 and 240, PDF pages 109–110). On the corrected case set, passage MRR
is 0.2615 fixed vs 0.2626 sentence-aware; both snapshots have Recall@5 0.10.
Because the case-file hash and labels changed, these are different evaluation
snapshots, not a reproducibility claim or demonstrated improvement. Fixed
references are source-checked; sentence labels are still transferred by
same-page trigram overlap and have not been independently reviewed. This five-
question diagnostic does not establish a winner or test BM25, hybrid,
reranking, or answer quality. The latest baseline used 1,912 stored vectors;
the alternate had 1,979 chunks. Sentence parsing took 39.10 s, embedding took
71.00 s, and peak RSS was 1,676.7 MiB on CPU. It is read-only with respect to
Supabase. The corrected-label run is in
`artifacts/evaluation/vinamilk-chunking-retrieval-source-reviewed-20260928.json`;
reproduce with:

```bash
uv run python scripts/evaluate_chunking_retrieval.py \
  --output artifacts/evaluation/vinamilk-chunking-retrieval-source-reviewed-20260928.json
```

The detailed per-question results, transferred-label mappings, case and source
PDF hashes, candidate hashes, environment and limitations are recorded in the
artifact. The active case set uses the corrected 2022 references; the two
earlier artifacts remain historical snapshots.

After re-ingesting the 11 annual and sustainability reports with the token
limit, a prior Supabase audit found `section_title` on 3,773 of 3,780 report
chunks (99.8%). All report chunks had `allowed_roles`, and none exceeded the
configured sequence limit. That count excludes governance/charter sources and
does not represent the full 25-document manifest. It measures coverage only;
heading precision and recall have not been evaluated. Seven of those report
chunks had no detected heading.

An isolated run through the actual seed PDF parser/metadata adapter on the
public 2024 annual report returned 397 chunks and one extracted table;
`section_title` survived on 396/397 chunks and all chunks had
`layout_type="text"`. This run used a stub token counter to isolate parser and
metadata flow, and did not embed or write to Supabase; it confirms metadata
propagation, not database persistence or heading accuracy.

## Known limit and verification

`TokenCounter` records token counts and splits overlength chunks by fast
tokenizer offsets while preserving page/section metadata. A 1,200-character
chunk exceeded the model limit during the prior corpus run; re-ingest and verify
all stored chunks before considering this fix proven on the live corpus. Keep
`EMBEDDING_MAX_SEQUENCE_LENGTH` aligned with the selected model. Do not change
stored chunk sizes without re-embedding the matching vectors and evaluating
retrieval quality.

Focused checks: `tests/test_text_processor_chunking.py`,
`tests/test_document_processor.py`, `tests/test_pdf_upload_processing.py` and
`tests/test_seed_ingestion.py`. The paired retrieval result above is preliminary;
proposal evaluation still needs broader independently reviewed queries and
paired QA. The boundary-only diagnostic is not a retrieval benchmark.
