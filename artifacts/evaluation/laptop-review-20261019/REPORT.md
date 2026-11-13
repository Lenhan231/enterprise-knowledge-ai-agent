# Laptop review: saved embeddings, retrieval evidence and production chunking

Date: 2026-10-19. Reviewed Huy commit `2aa9187`.

## Scope and outcome

Completed the agreed steps 1–4: fast-forward the laptop checkout, replay saved
rankings, inspect representative failures, and review existing chunking.
The English VietStyle dataset is still pending. No model was downloaded or
loaded, and no inference API, database, OCR, GPU or embedding rerun was used.
Application code and historical benchmark inputs/results were not changed.

**Conclusion:** the stored rankings are reproducible, but their coarse labels
can both overstate and understate answer-bearing retrieval. Neither experiment
yet supports a final production model choice or proves the section-ranking
problem is solved. There are concrete context/row-splitting risks to address
when preparing the next controlled experiment.

## 1. Verification

`review_saved.py` independently computes role-visible normalized cosine rankings
from the saved arrays. It does not import the benchmark scorer or an encoder.
It checks corpus/case hashes, document scope, candidate row-order and vector-file
hashes, matrix shape/finiteness/normalization, revisions recorded in config,
complete top-ten orders, per-case file/page scores and direction aggregates.
It also compares the 20 MiniLM replay orders with the saved database report.

- VietStyle: 20 baseline + 80 candidate rankings reproduced.
- Financial four-direction pilot: 144 candidate rankings reproduced.
- Total: **244 exact top-ten orders**, with matching case scores.
- **17 file hash checks** passed either as exact bytes or with explicitly
  recorded CRLF-to-LF normalization for Windows text checkouts. Six text files
  needed normalization. All checked vector files match byte-for-byte.
- The original PDFs, retained evidence and cached pages match their manifest
  hashes under the same explicit text handling. Every extracted page word is
  covered by the saved 525 chunks, whose text slices match the cached pages.
- All three final candidate configs report no truncated inputs. This review
  verified that recorded status, not token lengths by loading tokenizers again.

Important portability limitation: the existing candidate runner requires exact
raw text hashes. Windows `core.autocrlf=true` changed checkout line endings, so
it would reject these snapshots as-is. The review accepts only exact bytes or
the precise recorded hash after CRLF-to-LF conversion; it does not rewrite the
snapshots or silently claim raw-byte equality. Before future Windows reruns,
preserve the manifest's LF bytes using targeted Git attributes/checkout handling.

Saved-query arrays have no separate recorded file hash in these runs. Matching
rankings validate the stored arrays/results together; this does not independently
prove which encoder produced them or validate the original GPU execution.
The full application regression suite was not rerun; the handoff records known
inherited failures on main. No claim of a currently green full suite is made.

Reproduce from the repository root with the existing environment:

```powershell
.venv/Scripts/python.exe -X utf8 artifacts/evaluation/laptop-review-20261019/review_saved.py
```

Outputs: `verification.json` (checks, per-case top-ten texts and best labeled-page
ranks) and `gold-page-ranks.md` (all 48 query ranks across all three models).
Only NumPy and the standard library are used. Reports are regenerated in this
review folder; original benchmark folders are read-only inputs.

## 2. What the metrics establish

### VietStyle: expected source-file coverage, not relevant passages

| Encoder | Mean expected-file coverage@10 |
|---|---:|
| MiniLM baseline | 80.00% |
| multilingual-e5-base | 93.33% |
| BGE-M3 | 89.17% |
| Qwen3-Embedding-0.6B | 86.67% |
| English e5-large-v2 | 78.33% |

The missing README remains required by Q01/Q18/Q19; the available-file ceiling
is 95%. A returned chunk from the correct file need not contain the answer.
The workbook accounts for 485/532 chunks (91.2%), another dataset characteristic
to preserve/record rather than silently rebalance. This dataset has no verified
English counterpart yet, so it cannot isolate cross-language performance.

### Financial pilot: evidence-page coverage, not answer-bearing chunks

| Direction | Cases | Multilingual E5-base | BGE-M3 | Qwen3 |
|---|---:|---:|---:|---:|
| VI → VI | 10 | 80.00% | 80.00% | 70.00% |
| EN → EN | 12 | 41.67% | 41.67% | 41.67% |
| VI → EN | 12 | 66.67% | 41.67% | 50.00% |
| EN → VI | 10 | 10.00% | 80.00% | 70.00% |

The two mixed-document intents are scored separately. The 48 queries represent
24 paired intents, not 48 independent questions. All final candidates rank the
same two complete reports and 525 chunks without target-language filtering.
Only final top-level `candidates/` are included; the superseded 100-word attempt
is excluded. Different documents, extraction quality and tiny direction groups
still confound language-only conclusions.

## 3. Content review: confirmed examples and limits

### A. Present in the corpus but ranked far below ten

For English questions, the first labeled-page ranks are:

| Query | Expected evidence | E5-base | BGE | Qwen |
|---|---|---:|---:|---:|
| Q01-en, mission/vision | Annual report page 5 | 15 | 33 | 63 |
| Q03-en, business sectors | Annual report page 12 | 131 | 132 | 123 |
| Q06-en, 2008 revenue/profit/tax | Annual report page 14 | 26 | 25 | 51 |

These are not missing-text failures: mission/vision wording, business-sector
list and financial figures are present in the cached pages and indexed chunks.
BGE's first Q01 result instead describes a subsidiary's development direction
on page 22. Its first Q03/Q06 result is a performance-summary fragment on page
35. Topic similarity and missing local context are plausible contributors;
these observations alone do not establish a single root cause.

All models miss the labeled page in English for Q01, Q03, Q06, Q07, Q11 and
Q12. Simply increasing top K slightly would not reach the Q03 page. A reranker
cannot recover a passage that is absent from its candidate set.

### B. Page-level successes without the figures requested

Q18-en asks for Long Hau net revenue and its increase; Q19-en asks for profit
before tax in 2008 versus 2007. Both label Long Hau page 8.

- BGE retrieves `long_hau_fs::chunk::48` at rank 6 for Q18 and rank 9 for Q19.
- Qwen retrieves that same chunk at rank 5 for Q18 and rank 4 for Q19.
- In all four cases this is the **only retrieved chunk on the labeled page**.
- Chunk 48 contains OCR noise, company/report heading, date and unit, but no
  revenue or profit figures. Nevertheless, page Recall@10 is 100% for each case.
- The actual net-revenue row is in chunk 49: 331,212,837 versus 156,430,834,
  with the source using dot separators and units of thousand VND. Profit before
  tax is in chunk 51: 172,820,359 versus 61,592,023.

This confirms that a page hit can hide the exact problem the team described.
It does not establish that every other retrieved page lacks alternative evidence.
Answer-bearing labels and content review are needed for that stronger claim.

### C. Valid alternative evidence can be scored as a miss

Q14-en asks which firm audited Long Hau. All three models rank the cover
(`long_hau_fs::chunk::0`, page 1) first; it explicitly names **Ernst & Young**.
The label only names the audit report on page 5. E5's first page-5 hit is rank
17, so it receives zero page recall even though its first result appears to
answer the question. Alternative evidence should be human-reviewed and added
in a versioned label revision, not silently inserted into this frozen run.

### D. OCR and small chunks can reward report boilerplate

For Q16-vi (Long Hau total assets), BGE ranks a page-14 fragment containing
OCR garbage plus the company/report date first. The first labeled-page hit
is rank 20. The assets total is actually retained on page 6. Other highly
ranked chunks repeat report headings and dates without the requested total.
This is evidence of noisy inputs and weak local context; cleaning or changing
chunking would require a fresh, controlled corpus rather than editing results.

## 4. Production chunking review

The financial pilot uses an experimental 60-whitespace-word splitter with
12-word overlap. It does **not** exercise the production chunking pipeline.
Do not attribute its exact fragment boundaries to production code.

| Stage / function | Existing behavior | Finding |
|---|---|---|
| `document_processing/chunking/text/router.py::split_text` and sentence strategy | Default 1,100-character, sentence/paragraph-aware parser splitting; long sentences fall back to fixed splitting | Useful structure already exists; do not build a second system |
| `document_processing/chunking/table/chunker.py::build_table_chunks` | Groups complete rows by character size; repeats section/table/column headers | Preserves rows initially, but one very long row is allowed to exceed the character target |
| `tokenization/token_counter.py::split_text` | Uses tokenizer character offsets, reserves special tokens, overlaps fragments and rechecks token length | Final split is token-position based, not sentence or table-row aware |
| `tokenization/embedding_chunker.py::build_embedding_chunks` | Applies final model limit, repeats recognized leading context headers, copies metadata, assigns fresh indexes | An overlong table fragment can be split inside rows; inherited row-range metadata then describes the original group rather than each exact child |
| Same function | Replaces `chunk_index` with the final index | Does not add an explicit original parser-chunk ID/index and child-part index/count, making traceability harder |
| `embeddings/embedding_service.py::_load_backend` | Explicitly sets runtime sequence cap; rejects caps above known architecture capacity | The old MiniLM native-256/configured-512 discrepancy has already been addressed; do not revert that fix |
| `EmbeddingService.embed_documents/embed_query` | Sends supplied strings to the backend | Candidate-specific E5 prefixes/Qwen instructions and final overlength rejection are in the benchmark runner, not a shared live input recipe |

Upload, retry and Upload Test already share `build_embedding_chunks`. A fix at
that shared boundary would reach all three. Source page/section/table metadata
is already retained; preserve it. Parent retrieval already exists as an explicit
mode, with nearby chunk expansion. It is not part of these dense experiments.
In the current repository its default radius is two: from page-8 header chunk
48 it could reach revenue chunk 49, but not profit chunk 51. Context expansion
therefore needs deliberate evaluation rather than assuming it solves every miss.

These are code-path risks, not proof they occurred in the unchanged VietStyle
snapshot: its saved MiniLM audit reports all 532 chunks within cap 512 (largest
402 tokens including special tokens). Final financial candidate audits report
maxima 234 E5, 232 BGE and 465 Qwen. No new encoder/tokenizer run was performed.

### Smallest proposed changes, before implementation

1. **Traceability first:** add original parser-chunk identity and child-part
   index/count in `build_embedding_chunks`; preserve current final retrieval
   IDs and page/section metadata. Currently only final indexes are guaranteed.
   Verify with a long parser input split into multiple children, without a model.
2. **Boundary-aware token fitting:** reuse existing sentence/row boundaries when
   forming final chunks, budget repeated headers and special tokens, and use
   offset splitting only for a single overlong sentence/row. Currently the final
   token pass may cut either. Recompute precise row coverage for each child;
   mark a row fragment explicitly instead of claiming it contains a whole group.
   Verify token bounds, text coverage, row continuity and repeated headers.
3. **Model recipe before model migration:** share the selected encoder's
   prefixes/instructions and token budgeting across indexing/querying; pin its
   revision and reject overlength final inputs. Currently benchmark recipes are
   stronger than the generic live wrapper. This is conditional on model choice,
   not a reason to switch the live model now.
4. **Evidence labels before another winner claim:** retain immutable old labels;
   add answer-bearing spans/rows and reviewed alternative evidence in the next
   dataset version. Report passage success separately from page/file coverage.

No production change is applied by this review. These proposals should be
explained and measured against a new versioned corpus before any vector rebuild.

## What changed in this task

- Pulled Huy by fast-forward from `84393ed` to `2aa9187`.
- Added `review_saved.py`: previously no laptop-local replay report existed;
  it independently checks saved arrays/rankings without model or service access.
- Added generated `verification.json`, `gold-page-ranks.md` and this report.
- No production source edits, tests added, model changes, database actions,
  commits or pushes. Verification is the saved-vector replay described above.

Next work remains the aligned English VietStyle dataset and a controlled
four-direction evaluation, followed separately by translated-hybrid evaluation.
Keep the current production index until a model/recipe and migration are agreed.
