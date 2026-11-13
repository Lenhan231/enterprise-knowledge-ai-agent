# Step 1: exact chunk-to-source provenance

Completed 2026-10-19. This adds automatic source coordinates to newly built embedding chunks. It does not change dense ranking, retrieve neighboring chunks, score evidence, migrate a database, or rebuild old indexes. No GPU/model weights/database/inference API was used. Tokenizers were loaded from local cache for verification only.

## Before -> after

`TokenCounter.split_text` previously returned strings only. It still returns the same list of strings. New `split_text_with_offsets` runs the same splitting logic and returns `(text, source_start, source_end)` for each original Unicode slice. It uses tokenizer offsets, not substring search, so repeated phrases do not accidentally map to the first occurrence.

`build_embedding_chunks` previously replaced `chunk_index` with the final index without preserving the source parser identity or each child's coordinates. It now retains the same text, old metadata values and final indexes, and adds:

| Metadata | Meaning |
| --- | --- |
| source_parser_index | Original parser index, chosen from the explicit parser index, top-level chunk index, metadata index, or input position |
| source_content_sha256 | Hash of the exact source parser text; prevents labels from being applied to a changed source |
| source_child_index / source_child_count | Zero-based part number and total parts from this one parent |
| source_spans | Exact source_start/source_end and chunk_start/chunk_end intervals for the text actually included |

Identity is document_id + source_parser_index + source_content_sha256. Character positions are zero-based, end-exclusive Python Unicode indexes WITHIN THE PARSER PASSAGE. They are not raw PDF byte offsets or whole-document character offsets. Chunk coordinates refer to the returned text before any encoder-specific prefix is added.

## Why source_spans is a list

An ordinary fragment is usually one contiguous source interval. A table fragment with repeated headers can contain the source header at the beginning and a later row group, with omitted rows in between. These must be separate intervals; a single bounding interval would falsely claim the omitted rows were retrieved. The existing CRLF-to-LF header normalization is also tracked precisely: copied characters map to exact original characters; generated separators do not invent evidence coverage.

Illustration only: if a source has a header at [0, 30) and a needed row at [100, 150), a later child may map those two intervals. It must not claim [0, 150). A future evidence scorer can union the actual intervals from retrieved A and B without double-counting overlap. This step supplies the coordinates; it does not yet implement that scorer or cause retrieval to fetch B.

## Scope and behavior

The upload, retry and Upload Test paths already share build_embedding_chunks, so the change is at that existing boundary. The repository stores generic JSON metadata and retrieval contracts carry it through; no SQL schema or new column is required. Source input dicts are not mutated. Existing page/section/role metadata is retained.

Old saved vectors and live database rows have not acquired this metadata automatically. Later local benchmark preparation should build a versioned bounded corpus with these fields. Existing table_row_start/table_row_end metadata still describes the original parser row group, not precise rows in a split child; use source_spans for exact coverage. Sentence/row-aware fitting, model input recipes, the evidence scorer and context expansion are separate steps, not implemented here.

## Verification

Eight focused checks passed: two existing TokenCounter checks, four new provenance checks, and two retry-caller checks. New cases cover repeated Unicode text, overlap, repeated table headers with omitted source rows, CRLF normalization, source-index precedence, skipped empty chunks, unchanged source dicts and token limits.

A separate offline comparison used the two frozen corpora (532 VI + 531 EN = 1,063 parent passages across ten documents), cached MiniLM and Qwen tokenizers, and the legacy implementation from the recorded Git commit. At both caps 512 and 384, all output text, pre-existing metadata values and chunk order/count matched legacy behavior. Every mapped substring equaled its source slice, all non-whitespace source and child characters were accounted for, and token bounds held. Cap 384 is only a verification setting to exercise splitting, not an application configuration change.

| Tokenizer | Verification cap | Final chunks | Parents split |
| --- | ---: | ---: | ---: |
| sentence-transformers/all-MiniLM-L6-v2 | 512 | 1063 | 0 |
| sentence-transformers/all-MiniLM-L6-v2 | 384 | 1768 | 705 |
| Qwen/Qwen3-Embedding-0.6B | 512 | 1063 | 0 |
| Qwen/Qwen3-Embedding-0.6B | 384 | 1881 | 818 |

Raw counts, input hashes, tokenizer revisions and the legacy commit are in source-mapping-step1.json. Focused unit checks are runnable from the repository with unittest discovery for test_token_counter.py, test_embedding_chunker.py and test_retry_document_embeddings.py. This does not establish a green full regression suite.

## Next step

Use these source intervals to compute supported requirements from the evidence-v1 labels, with union coverage across multiple returned chunks and no credit for a header-only hit. Keep that scorer evaluation-only and test it on A-only, B-only, A+B, duplicate overlap, generated header and changed-source examples before a model run. Then wire the explicit four-direction local benchmark. Evaluate neighbor/parent expansion separately from dense-only ranking so improvements are attributable.
