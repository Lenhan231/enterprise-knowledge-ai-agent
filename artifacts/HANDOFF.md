# Handoff for Codex on another machine

Updated: 2026-10-19, Asia/Saigon. Read this before continuing the user's work.

## Latest: Q15 regression analyzed, 2026-10-19

Read reranker-bge-v2-m3-v1/Q15_ANALYSIS.md. Corrects earlier overstatement: official v2 4/4→2/4, but transaction ID remains explicitly in reranker rank4, SOP parser5 Unicode[888,947) (“Adjustment Transaction ID Mã giao dịch điều chỉnh sau duyệt”). Label only accepts separately extracted table SOP8, dense9→rerank11. This is a confirmed missing equivalent-source alternative. History guard SOP4 dense7→rerank27 is a genuine omission of the explicit no-delete/no-direct-source-edit detail; registry rank9 has related no-overwrite-history wording but is not automatically sufficient for both prohibitions. Core fields and timestamp/counter retained ranks1/4. Promoted SOP cover/AI/general-policy chunks occupy slots; relevance sorting does not enforce complete multi-fact coverage. Table lacks section_title and inherited form caption; context-deficit cause is plausible, not experimentally proven. No label/vector/rank/score changes or GPU rerun. Even accepting the transaction-ID alternative would leave Q15 full-intent failed due to history. Next consider bilingual/source-wide review of duplicate label and controlled context-prefix/parent experiment before swapping models. All work uncommitted.

## Latest: no-budget cross-encoder reranker benchmark completed, 2026-10-19

User clarified token question concerned chatting with Codex and explicitly removed context-token caps from future work. User authorized us to implement reranker assuming An lacks one. Read dense-evidence-benchmark-v1/reranker-bge-v2-m3-v1/{comparison,IMPLEMENTATION}.md. Existing Huy evaluate_rerankers.py used CrossEncoder for older Vinamilk evaluation; not production, not found in cached QuocAn fdfe6ca (latest remote fetch blocked by authentication). Explained CrossEncoder is the library/model architecture and BGE-reranker-v2-m3 is the trained model, separate from E5 embedding. New evaluate_vietstyle_reranker.py +4 tests reuse old model registry/scorer and saved E5 vectors. Downloaded runtime weights to WSL HF cache, pinned953dc6f6f85a1b2dbfca4c34a2796e7dde08d41e, then ran offline RTX2060 fp16 batch2. E5top30→BGEraw-logit-sort→top10; both outputs10 chunks, no context budget; per-pair max507 under configured1024, zero truncation.80 cases/2400 scores independently replayed (--verify-only),4 new tests passed. VI->VI full17→17/19, EN->EN14→14, VI->EN9→12, EN->VI12→12. Candidate-pool full availability19/18/14/14 respectively; not top10 oracle. VI fixesQ20(M13dense12→rerank7), losesQ15(transaction form11, no-delete guard27). Q13improves6→8/9 components but guard remainsrank21. Q01regresses in3 directions. Mean added rerank402ms, median379ms, excludes loading/dense/generation; peakGPU1114MiB. Do not enable globally based on current Vietnamese result; inspect short guard/field evidence selection and seek held-out evaluation next. No production, DB/index, embedding_service, translation or LLM changes. Original artifacts unchanged; all work uncommitted. User prefers English, switches Vietnamese on request. Continue explaining before/after code changes so user can follow.

## Latest: fixed-budget E5 neighbor test completed, 2026-10-19

User authorized neighbor test and asked whether Vietnamese uses more tokens. Added evaluate_neighbor_context.py +4 tests, no production changes. Read dense-evidence-benchmark-v1/neighbor-context-e5-v1/{comparison,IMPLEMENTATION}.md. Predeclared2048/4096 caps, exact rendered context counted by pinned E5 tokenizer (proxy, not LLM/chat tokenizer). Policies: dense10, interleaved seed→previous→next within same doc/lang/ACL, dense30; whole chunks only, dedup and skip overbudget, no gold-guided selection. 80 saved rankings replayed,560 context variants scored; baseline equals v2; independent character coverage and560 selection audits passed;19 targeted tests passed. VI->VI complete cases/19: at2048 dense10=16,neighbors13,dense30=16; at4096 dense10=17,neighbors17,dense30=18. Neighbors fixesQ13 but at4096 losesQ11 (budget crowding); at2048 gainsQ13 but losesQ07/Q12/Q16/Q17. Q20 not fixed by neighbors; dense30_4096 fixesQ20 but still missesQ13. Mean context tokens at4096: dense10 2417,neighbors4022,dense30 4043. Do not promote blanket expansion; recommend next reranker experiment on broad candidates with fixed budget, or explicit selective expansion as a new ablation. Small post-hoc set, not held-out. Same20 paired raw queries: E5/BGE549VI vs553EN(0.99x);Qwen578VI vs500EN(1.156x). No universal Vietnamese multiplier, not a chat billing estimate. No GPU/encoder/generation/DB/translation changes. Old artifacts unchanged; all work remains uncommitted.

## Latest: evidence v2 review and all-model rescore completed, 2026-10-19

User authorized us to review labels and rescore. Read evidence-v2/README.md and annotation-changes.json. Read 20 definitions; source-focused bilingual audit Q11/Q12/Q13/Q18/Q20, not exhaustive independent corpus relabelling. Added complete alternatives Q11 conflict/checks, Q12 verify, Q20 no-write/citation/conflict; Q18.no_guess now optional but missing actual PO/backorder evidence still required. Q20 normal Planner→Procurement flow required; exceptional branch optional. Q13 and Q14 objects unchanged; Q14 still unresolved. 66 components:61 required ready,2 unresolved,3optional;198 spans (99/language). Validator now accepts --folder; defaults v1. New rescore_vietstyle_evidence.py verifies old hashes, replays dense top10 and independently checks new character coverage. No GPU/model/vector/rank change; original v1 untouched. 15 evidence tests passed and 240 rankings rescored. New results under dense-evidence-benchmark-v1/rescored-evidence-v2/. Full evidence counts per19 v1→v2: VI->VI E5 15→17, BGE13→14, Qwen13→14; EN->EN13→14/14→15/13→14; VI->EN8→9/14→15/14→15; EN->VI11→12/13→14/12→13. E5 VI->VI remains incomplete Q13 and Q20. This is post-hoc label correction, not model improvement or independent held-out evidence. Component denominator now61 vs62. No production/DB/translation changes, no generation evaluation. Next: discuss/measure real retrieval gaps Q13/Q20 with fixed labels and explicit context budget, or obtain human policy-role resolution. All changes still uncommitted.

## Latest: reviewed E5 VI->VI losses, 2026-10-19

Read dense-evidence-benchmark-v1/LOSS_ANALYSIS_VI.md. User requested analysis, no label or retrieval edits. Q11 2/3: existing sole AND alternative requires CSV index2 at rank17, but SOP index3 rank3 + Deck index3 rank9 provide strong equivalent checklist candidate. Q13 6/9: genuine missing preparation/blind-count details in SOP index1 rank17; no-delete-source guard SOP index4 rank27, though audit-trail summary exists rank3. Q18 1/2: workbook rank1 explicitly missing PO/backorder and zero placeholders; failure requires extra no-guess slide rank15, a potentially excessive retrieval criterion. Q20 3/5: true missing approval chain Manual index13 rank12; conflict alternative SOP rank9 + CSV rank10 not accepted because label only Manual index14 rank27. Strict minimal k values17/27/15/27 are diagnostics from saved vectors, not recommended tuning. Current 15/19 scores unchanged. No confirmed generation behavior; no encoder truncation. Next: review evidence v2 consistently for all models/languages before context expansion/reranking experiments. No automatic label changes or GPU rerun.

## Step 3 dense evidence benchmark completed, 2026-10-19

Latest completed task: wired optional evidence scoring into existing evaluate_embedding_candidates.py, added prepare_vietstyle_evidence_benchmark.py and independent saved-vector replay/compare_vietstyle_evidence.py. Read artifacts/evaluation/vietstyle-bilingual-20261019/dense-evidence-benchmark-v1/{IMPLEMENTATION,comparison,INSIGHTS}.md. Shared 1,063 unchanged parser passages with source mapping (532 VI + 531 EN); all three pinned cached tokenizers passed cap512 including formatting (E5 max476, BGE474, Qwen425), zero truncation. 80 cases/model reuse 20 paired intents across four directions, each searching all 5 target-language documents; no gold-source filtering. Language field exists only in experimental snapshot, no database change. Ran E5-base/BGE-M3/Qwen0.6B on RTX2060, float32, batches2/2/1, entirely offline cached weights. Independent replay verified all 240 rankings and character/component coverage; 11 evidence tests plus 4 mapping tests passed. Full evidence success (19 eligible intents, Q14 excluded): VI->VI E5 15, BGE13, Qwen13; EN->EN 13/14/13; VI->EN 8/14/14; EN->VI 11/13/12. Ready component totals62 per direction include clear parts of Q14. E5 VI->VI covers55/62, BGE53/62, Qwen51/62. Source-file diagnostics retained but not comparable to new evidence metrics. No MiniLM run under the new metric, no translation/hybrid/reranker/generation, no production/index change. Next suggestion: inspect E5 VI->VI missing cases Q11,Q13,Q18,Q20 and confirm alternative-evidence labels before changing retrieval or committing to a model. Results are label-dependent and small-sample, not answer-generation accuracy. All changes remain uncommitted, including earlier stages. No push authorized for this task.

## Step 2 evidence scorer implemented, 2026-10-19

Latest: `src/core/evaluation/evidence_metrics.py::score_evidence` now scores frozen top-k chunk provenance against required ready components: union exact source intervals, AND within alternative bundles, OR across bundles. Ignore whitespace gaps only. Duplicate ranking slots remain consumed; overlap does not inflate coverage. Missing/stale/tampered mappings raise rather than becoming misses. Q14 full success stays null; optional/pending excluded from ready denominator. Inputs are dict chunks with text/metadata and target-language source lookup; run existing label validator before scoring. Read evidence-v1/evidence-coverage-step2.md and JSON. Seven new tests plus eight related tests passed. Oracle integration with all source chunks (not model retrieval) covers 62 required ready components and 19 eligible intents in both languages; empty rankings cover zero. No production ranking/model/DB/GPU change. Next: wire this into the offline dense candidate benchmark, preserving provenance alongside vectors. Context expansion still separate. All current work remains uncommitted; do not overwrite earlier uncommitted work.

## Step 1 source mapping implemented, 2026-10-19

The user asked to proceed in explained parts. Part 1 adds automatic source provenance at the existing shared tokenization boundary. Read evidence-v1/source-mapping-step1.md and its JSON audit. TokenCounter now has split_text_with_offsets while split_text preserves its prior string-only API. build_embedding_chunks adds source_parser_index, source_content_sha256, source_child_index/count, and exact source_spans (source and output Unicode ranges). Repeated headers map separately from later body rows; CRLF normalization is mapped without falsely claiming omitted source text. No substring-guess mapping. Existing text/metadata/index behavior was verified against legacy code on 1,063 source passages using cached MiniLM/Qwen tokenizers at caps 512 and 384; no non-whitespace source text lost, all spans exact. Eight targeted tests passed. No encoder weights/model/GPU/DB/API execution or database/index migration. Source mapping is in metadata for future newly built chunks only. It does not cause dense to retrieve A+B and does not fix row-aware splitting. Next part: evaluation-only evidence interval coverage/scorer, then local benchmark wiring; context expansion must be evaluated separately. Existing saved snapshots remain unchanged. Current changes are uncommitted.

## Evidence labels v1 created, 2026-10-19

The user authorized creating evaluation-only evidence labels, not a GPU benchmark or retrieval changes. Read `artifacts/evaluation/vietstyle-bilingual-20261019/evidence-v1/README.md` and REVIEW.md. The 20 existing VN/EN question pairs now have 65 answer components and 184 exact source spans (92 per language), with alternative bundles, hashes, Unicode offsets and source metadata. There are 62 ready required components, 2 pending approval-role components in Q14, and 1 optional context component. Nineteen intents are fully ready; Q14 must be reported separately until Manual/SOP role variations are clarified. Calculation inputs in Q09/Q10 come from questions; formulas/defaults come from sources. Q18 is unavailable-data abstention, not a real zero-valued PO lookup. No old source/question/reference/result files were changed. The standard-library validator `scripts/retrieval/validate_vietstyle_evidence.py --self-check` passed exact-quote/hash/location/bilingual/derivation checks and rejects tampered quotes/wrong-language sources. No retrieval-to-evidence mapping/scorer is implemented yet; create/validate it before a new benchmark, preserving source provenance across final chunk splitting. Never index labels or reference answers, or use them to guide ranking. Labels are assistant-curated, not independently human-certified; alternatives remain non-exhaustive. No live DB/model changes, inference API, model loading or GPU rerun.

## Corrected English simulation pack created locally, 2026-10-19

The user authorized us to create the English counterpart ourselves. `artifacts/evaluation/vietstyle-bilingual-20261019/corrected-en-v1/` now contains all five corrected English files; the original mixed-language download remains under sources/en/. Read BUILD_NOTES.md and english-build-manifest.json. The DOCX is unchanged; CSV SLA/workbook/slide text is translated; the SOP is rebuilt from the frozen VN content as a clean selectable-text three-page PDF with all 8 sections and 3 complete tables. Workbook coordinates/types/values/formulas and CSV policy IDs/non-SLA fields are verified unchanged. Twenty English questions/reference answers are in benchmark-questions-en-v1.json, with inherited source-file labels and the missing README limitation retained. These are assistant translations, not independent human-certified gold or new answer-bearing passage labels. Build script: scripts/retrieval/build_vietstyle_english.py (stdlib + existing PyMuPDF). Corrected files were reparsed locally; ZIP CRC/contents and hashes were checked; PDF pages visually inspected. No production code, live model or DB changes, and no model/benchmark run yet. Next is a versioned local benchmark with clearly defined language scope and evidence labels; do not index question/reference-answer files as retrieval evidence.

## English pack received: local quality audit, 2026-10-19

The downloaded `VietStyle_Inventory_Documents_English.zip` has been extracted locally under `artifacts/evaluation/vietstyle-bilingual-20261019/sources/en/`. Read that folder's `READINESS.md` before attempting a new benchmark. The pack is incomplete English: the SOP PDF body remains substantially Vietnamese with broken glyphs visible in the PDF itself; CSV SLA cells, workbook cells and slides 2/8 also retain Vietnamese. Five files parsed to 530 chunks, hashes/counts verified. No embedding/model/GPU/DB/inference API execution was performed. The archive lacks English questions/answers and README. A 20-question assistant-translated draft is saved for human review, not yet scored. An exploratory as-is run was offered as an option; absent explicit preference the recommendation is to correct the English pack first. No production code or historical results were changed. This audit does not supersede the laptop's label/chunking findings below.

## Latest update: laptop review completed

The laptop completed agreed steps 1–4 against Huy `2aa9187`: fast-forwarded
the checkout, independently replayed saved vectors, inspected representative
failures, and reviewed production chunking. Read
`artifacts/evaluation/laptop-review-20261019/REPORT.md` first, alongside the
two earlier comparison reports below. This section supersedes the instructions
below to start the laptop review; the earlier experiment descriptions remain
historical context.

- All **244 saved top-ten orders** and case metrics reproduced: 100 VietStyle
  orders (including MiniLM) and 144 financial four-direction orders. Seventeen
  file hash checks passed, six after explicitly recorded CRLF-to-LF text
  normalization on Windows. Vector-file hashes matched byte-for-byte.
- Original PDFs and cached pages were checked. Every extracted page word is
  covered by the final 525 financial chunks. Encoder execution and tokenizer
  audits were not rerun; replay uses saved vectors, not new embeddings.
- Confirmed score inflation: Q18-en and Q19-en receive full page recall for
  BGE and Qwen by retrieving only Long Hau page-8 header chunk 48, without
  the requested figures. Revenue is in chunk 49; profit before tax in chunk 51.
- Confirmed label limitation: Q14-en ranks the cover naming Ernst & Young
  first for all models, but the label only accepts audit-report page 5.
- Q01-en/Q03-en/Q06-en contain relevant text in the corpus but their first
  labeled-page hits are below ten for every model. See `gold-page-ranks.md`
  for all 48 queries; page hits still do not prove passage correctness.
- Production parser-level table chunks preserve rows and repeat headers.
  The final token splitter can cut overlong rows/sentences and does not add
  explicit original parser-chunk identity/child-part metadata. These are
  code-path risks, not demonstrated causes of every saved failure.
- Windows Git autocrlf changes frozen text checkout hashes. The current
  candidate runner requires exact raw hashes; address LF preservation before
  future Windows reruns. The review records normalization explicitly and
  does not modify historical inputs or weaken the candidate runner.

Only review artifacts were added; no application code, live model, database,
original benchmark results, or source labels were changed. No models were
downloaded/loaded, and no GPU, inference API or database access was used.
The full regression suite was not rerun; do not claim it is green.

### Next session at home

1. Pull `Huy`, check the worktree, and read the laptop review. Do not replay
   completed GPU benchmarks merely because the GPU is available.
2. The English VietStyle set had **not arrived** at the end of this session.
   If it is now available, verify fact/number/table/question/evidence alignment
   and freeze a new version before testing. Otherwise continue label and
   chunking planning using saved evidence.
3. Before implementing changes, explain file/function, old/new behavior,
   reason and verification plan to the user. Proposed order: parser-to-child
   traceability; sentence/row-aware final token fitting; a shared model input
   recipe when a model is selected; answer-bearing and alternative labels.
   These proposals are not yet implemented or benchmarked.
4. Keep dense encoder experiments separate from translated-hybrid pipeline
   tests. Do not convert the experimental 60-word rule into production policy.
5. No final model has been chosen, and no live vector migration is requested.

Offline replay (NumPy + standard library only):

```bash
.venv/bin/python artifacts/evaluation/laptop-review-20261019/review_saved.py
```

On Windows use `.venv/Scripts/python.exe -X utf8` instead. This regenerates
`verification.json` and `gold-page-ranks.md` in the review folder; it does not
load models, connect to services, or alter the original experiment folders.

## Where we are

- Project: enterprise-knowledge-ai-agent. Working branch: `Huy`.
- Last implementation/benchmark commit before this note: `fa651ccae7ca15ddcd654e9280846f750da8647d` (benchmark multilingual embeddings in four situations using old dataset). At handoff creation, local Huy and local origin/Huy both pointed to this commit and the worktree was clean.
- Main was previously merged into Huy in `f7d49e6`, based on main `298be61`. Do not assume these are still the latest remote commits; inspect before merging anything.
- Desktop project path: `/home/eroz/projects/enterprise-knowledge-ai-agent` inside Ubuntu WSL. WSL disk is `F:\WSL\Ubuntu\ext4.vhdx`. These paths are desktop-specific; locate the laptop checkout rather than assuming the same path.
- The user now owns tokenization and embedding-model comparison, in addition to retrieval. Current objective: choose a model and chunking strategy that work for Vietnamese and English queries/documents, including cross-language retrieval.
- No final embedding model has been selected. Candidate benchmarking has NOT replaced the live application's index/model.

## User preferences and agreed next step

Explain in straightforward Vietnamese or English. The user explicitly asks that every code change be explained: file/function, what the old code did, what the new code does, why, and how it was verified. Do not make unexplained changes.

The user is asking a teammate to make an English version of the existing VietStyle simulated document set. It should preserve the facts, numbers, tables, rules and content structure, with corresponding translations of the 20 questions and answer/evidence labels. A newly invented unrelated English scenario would not isolate the language effect.

While waiting, we completed a four-direction pilot using two older financial reports. Next: review the results and chunking limitations, then evaluate the new bilingual VietStyle set when it arrives. Do not keep downloading/running new models without a reason. No deployment or database replacement is currently requested.

## Read these reports first

1. `artifacts/evaluation/embedding-comparison-20261018/comparison.md` — VietStyle model comparison, code changes, metrics and limitations.
2. `artifacts/evaluation/four-direction-20261018/comparison.md` — completed four-direction dense pilot, per-case scores and limitations.
3. `artifacts/evaluation/embedding-comparison-20261018/database-restoration.md` — why/how the cleaned database was made benchmark-ready.
4. `artifacts/evaluation/embedding-comparison-20261018/four-direction-readiness.md` — historical preparation plan only; the actual four-direction test is now complete. Its original reconstruction/metric questions are resolved in report 2.

The corpora, vectors, configs and JSON results in both benchmark directories are tracked in Git, including `.npy` files. Logs matching `*.log` are ignored and may exist only on the desktop. Model weights and `.env` credentials are NOT in Git.

## Experiment A: VietStyle, 20 Vietnamese questions

Frozen folder: `artifacts/evaluation/embedding-comparison-20261018/`.

- Five documents, 532 unchanged indexed chunks; 20 VN questions from An's benchmark.
- Document types/counts: policy manual DOCX 18; SOP PDF 9; registry CSV 12; inventory planner XLSX 485; training PPTX 8.
- Inspected text samples are mainly Vietnamese with English terms. No separate verified English document set in this benchmark. All 532 frozen chunk metadata language attributes were missing when audited.
- Metric is expected-source FILE coverage in top 10 chunks, NOT exact relevant chunk recall or answer accuracy.
- README.txt is absent but remains required by labels for Q01/Q18/Q19; maximum mean source coverage with available files is 95%, not 100%.

| Model | Source-file recall@10 | Full expected-source cases |
| --- | ---: | ---: |
| sentence-transformers/all-MiniLM-L6-v2 baseline | 80.00% | 10/20 |
| intfloat/multilingual-e5-base | 93.33% | 16/20 |
| BAAI/bge-m3, dense embeddings only | 89.17% | 15/20 |
| Qwen/Qwen3-Embedding-0.6B | 86.67% | 13/20 |
| intfloat/e5-large-v2 | 78.33% | 10/20 |

E5-large-v2 is English-only per its model card; multilingual-e5-base is a DIFFERENT model. BGE-M3 and Qwen3-Embedding are multilingual too. More parameters did not guarantee a better score here. These small, source-file-labelled results did not establish cross-language quality.

All candidates ran locally on RTX 2060 in float32, cap 512; E5/BGE batch 2, Qwen batch 1. No inference API received document text. Model downloads are local Hugging Face caches. Local cosine replay reproduced all 20 original MiniLM database top-ten orders. All 80 candidate case scores/rankings (4 models x 20) were independently verified from saved vectors.

Frozen corpus SHA256: `a52fdb6efaadfe428f7c477617b4c0b8072a30d3e3b9596dbfa205b67cc01352`.

## Experiment B: completed four-direction pilot

Frozen folder: `artifacts/evaluation/four-direction-20261018/`.

- Full original PDFs: PVFCCo English annual report (96 pages) and Long Hau Vietnamese financial statements (22 pages).
- `data/raw/benchmark_data/2.BCTC da kiem toan 2008 (V).pdf` and the misleadingly named `HPT - To trinh thong qua danh sach Cong ty Kiem toan signed1.pdf` have IDENTICAL bytes/SHA256; both are the same Long Hau source.
- There was no complete retained 249-chunk old index. Partial historical retrieved contexts were recovered from local origin/QuocAn benchmark artifacts and saved in `retained-original-contexts.json`; these are used ONLY to validate old evidence, not as a ranking corpus.
- Rebuilt from complete PDFs locally: native PDF text where available; missing text OCR with Tesseract eng/vie, 200 DPI, PSM 3. Installed Tesseract in desktop WSL; not a Python dependency or an application code change. OCR noise and flattened tables remain.
- Final corpus: 118 pages, 525 common chunks (348 EN / 177 VI), 60 whitespace words per chunk with 12-word overlap, page boundaries preserved. Two English pages (2, 95) yield no text; none of the gold pages is empty. Every extracted page word is covered.
- 24 paired intents / 48 queries, NOT 48 independent intents. Source question files are `data/evaluation/long_hau_2008_cases.json` and `_en.json`; IDs and evidence labels align.
- 12 English-document-only intents yield 12 VI->EN and 12 EN->EN cases; 10 Vietnamese-document-only intents yield 10 VI->VI and 10 EN->VI. Two mixed-document intents produce four queries and are scored separately.
- Every query ranks chunks from BOTH complete reports. Target language and gold labels DO NOT restrict retrieval. No translation, BM25, reranker, generation, inference API or Supabase writes.
- Metric: fraction of labelled EVIDENCE PAGES appearing among top 10 chunks, with duplicate page hits counted once. Also MRR@10 over page hits. Original chunk indices are not reused after rechunking. Getting another chunk from the same page counts here even if that particular chunk does not contain the answer: this is a coarse metric, not answer correctness.

| Query -> evidence document | Queries | E5-base multilingual | BGE-M3 | Qwen3-0.6B |
| --- | ---: | ---: | ---: | ---: |
| VI -> VI | 10 | 80.00% | 80.00% | 70.00% |
| EN -> EN | 12 | 41.67% | 41.67% | 41.67% |
| VI -> EN | 12 | 66.67% | 41.67% | 50.00% |
| EN -> VI | 10 | 10.00% | 80.00% | 70.00% |
| Four-direction macro, equal direction weights | 44 | 49.58% | 60.83% | 57.92% |

All 144 final top-ten orders and page metrics were independently recomputed from saved passage/query vectors. Four focused candidate-runner unit checks passed. All final inputs fit 512 tokens, including required prefixes: max passage E5 234, BGE 232, Qwen 465. No silent truncation.

IMPORTANT: `preflight-100-word-attempt/` contains a SUPERSEDED, incomplete attempt. Initially 100-word chunks / 20 overlap yielded 333 chunks; Qwen rejected 11 inputs over the configured cap 512. We preserved that attempt, reduced the common chunk size, checked all three tokenizers before embedding, and reran ALL THREE models. Use only the top-level FINAL `candidates/` for the result table above. The 512 cap was an experimental setting, not Qwen's native maximum.

Limitations: English and Vietnamese reports have different topics, lengths and extraction quality; direction groups are only 10/12 cases. Chunk size and incomplete alternative-evidence labels affect scores. These are pilot findings, not proof of universal model superiority. Do not compare these percentages directly with Experiment A (file labels) or the original 249-chunk financial benchmark (chunk labels). E5's strong VietStyle score did NOT translate into winning every direction; BGE was stronger EN->VI in this pilot.

Frozen corpus SHA256: `b8e46d0776b602ace3d74efbc7cb14cfa554377294219a1f1615f7fa15f890e4`.

## Relevant code and what changed

- `scripts/retrieval/evaluate_embedding_candidates.py`: separate local benchmark runner. Model option/config, pinned revision/tokenizer, required prefixes/instructions, input token audit, normalized vectors, cosine top 10, scoped/role-visible frozen corpus. Creates per-model config, passage/query vectors, results; refuses to overwrite completed outputs. Extended with OPTIONAL gold-page scoring/grouping; prior VietStyle file scoring retained.
- `scripts/retrieval/prepare_four_direction_benchmark.py`: reconstructs complete PDFs, cached page text/OCR, common chunks, bilingual cases, page-label validation, hashes, and preflight for all three tokenizers before spending GPU time. Requires retained-original-contexts.json included in the snapshot. Cached pages avoid redoing OCR. Re-running preparation is unnecessary just to analyze saved results.
- `scripts/retrieval/evaluate_vietstyle_dense.py`: read-only live-Supabase baseline, verifies exact frozen corpus/vectors and encoder config before measuring. Requires DB credentials; not needed for offline candidate analysis.
- `scripts/retrieval/audit_embedding_tokens.py`: audits native/cached model limits. Packaged native defaults are not necessarily the app's runtime override.
- `src/core/embeddings/embedding_service.py`: earlier fix explicitly applies configured max sequence length to the local SentenceTransformers encoder and rejects unsupported caps. App setting 512 previously left the actual all-MiniLM-L6-v2 encoder at native 256, risking silent truncation. This fix is committed; do not revert it thinking candidate experiments changed the live model.
- `scripts/retrieval/retry_document_embeddings.py`: earlier recovery rewrite uses retained parser chunks and shared embedding chunker, explicit selected document IDs, refuses ready uploads, updates status ready after vector save; preserves parser text. Do not run recovery merely to repeat a benchmark.
- `tests/test_embedding_candidates.py`: four checks, including prefixes/instructions, ACL/file scoring, overlength rejection, and duplicate page/document identity.
- `scripts/README.md` and each comparison.md contain commands and before/after explanations.

Candidate input recipes: E5 uses `query: ` and `passage: `; BGE-M3 uses no prefix; Qwen queries use the English retrieval instruction recorded in config, passages unchanged. Use the same encoder/model/revision/recipe for candidate document/query vectors. Never compare vectors from different models merely because dimensions match.

## Database and live retrieval context

Last checked 2026-10-18: Supabase had only the five VietStyle uploads, all ready, 532 vectors of dimension 384. Their IDs:

- CSV: `UPLOAD-1fb7b4e78ba24519a316b544c8ec721b`
- XLSX: `UPLOAD-53956dfa17064fd9b6f42e9e01570a20`
- PDF: `UPLOAD-644eabbe7e354e76a133477b5f9f1eb2`
- DOCX: `UPLOAD-a835b48cc18c4d1baea6c2e5c3cfc54e`
- PPTX: `UPLOAD-f7d7c1fc50b1438c8902bb0d2e48337b`

Company/scope was Commerce Demo, active knowledge base, benchmark admin role. Recheck live state before database actions; teammates can change it. The old financial upload IDs in evaluate_two_document_benchmark.py are no longer in the database. Do not restore or reindex them in Supabase just to run the saved offline pilot.

The desktop ignored .env selected `sentence-transformers/all-MiniLM-L6-v2`, local, effective cap 512; do not confuse it with the older `paraphrase-multilingual-MiniLM-L12-v2`. Database restoration reused 532 retained parser chunks, left their text unchanged, and saved 532 MiniLM vectors. Baseline snapshots and hashes are in Experiment A. Candidate vectors are separate local artifacts, never uploaded to replace the working index.

Tables: `documents`, `document_parser_chunks` (retained parser output), `document_chunks` (retrieval vectors/content); extracted tables are separate. No document-language database attribute was added for these experiments. Benchmark language maps live in frozen metadata/config; English terminology inside a Vietnamese table is not proof the whole document is English.

Production retrieval already has integrated `translated_hybrid` (commit `7ce91b0`) in `src/core/retrieval/methods/translated_hybrid.py`, `query_translator.py`, the shared retrieval service/RAG/app. It combines original dense with bilingual lexical searches; optional verified `document_languages` maps scope lexical branches, and no map means bilingual searches within the same authorized document scope. Translation failures have explicit dense fallback diagnostics. Document ID, ACL, company, readiness/knowledge-base filters matter. Current embedding experiments deliberately use DENSE ONLY to isolate encoder behavior; translated hybrid has not been reevaluated with these new candidate encoders.

Main refactored document processing into readers/pipelines and split parser chunks from embedding chunks. Existing production tokenization/chunking code is under `src/core/tokenization/` (`token_counter.py`, `embedding_chunker.py`). Inspect/reuse it before designing another chunking system. Table chunking already repeats some section/table/column headers, but very long headers/rows and model-specific token limits still need care.

## Agreed production chunking direction (not newly implemented)

Do NOT turn the experimental 60-word rule into a production standard. After selecting a model, count tokens with its exact tokenizer, include model-required prefixes/special tokens, and split overlong content before encoding. Prefer sentence/section boundaries; split tables by row groups and repeat necessary table/column headers; handle a single overlong row explicitly. Keep document/page/parent/neighbor metadata so retrieval can expand context after selecting a small chunk. Detect/reject silent truncation. Changing chunking means rebuilding vectors and revisiting relevance labels, not reusing stale chunk IDs.

## Laptop: what can be done without GPU/credentials

Start by pulling Huy and reading both saved comparison reports/JSON. The corpus, results and vectors are committed, so inspect/recompute saved cosine rankings locally without downloading model weights or connecting to Supabase. Do not assume the laptop has the desktop's HF caches, GPU, Python environment, Tesseract or .env. Do not copy secrets into a note or commit them.

If actually running code, inspect the existing environment first. Project uses uv/uv.lock, Python >=3.11 (`uv sync --frozen` if a new environment is needed). On Linux/WSL, focused checks:

```bash
.venv/bin/python -m unittest discover -s tests -p test_embedding_candidates.py
```

The candidate runner supports `--device cpu` explicitly if no CUDA; CPU can be slow. `HF_HUB_OFFLINE=1` only works after the required pinned models/tokenizers have been cached on THAT machine. Without it, Hugging Face downloads are allowed by the runner, so explain storage/network impact before initiating optional heavy reruns. No model-inference API is needed. Use fresh `--output-dir` for repeats to preserve committed evidence.

Example AFTER the model is cached, not a command to run automatically:

```bash
HF_HUB_OFFLINE=1 OMP_NUM_THREADS=4 MKL_NUM_THREADS=4 .venv/bin/python scripts/retrieval/evaluate_embedding_candidates.py --snapshot artifacts/evaluation/four-direction-20261018 --model multilingual-e5-base --revision d128750597153bb5987e10b1c3493a34e5a4502a --device cpu --batch-size 2 --output-dir artifacts/evaluation/four-direction-20261018/laptop-rerun-e5
```

Other pinned revisions: BGE-M3 `5617a9f61b028005a4858fdac845db406aefb181`; Qwen3-0.6B `97b0c614be4d77ee51c0cef4e5f07c00f9eb65b3`; English E5-large-v2 `f169b11e22de13617baa190a028a32f3493550b6`.

Known inherited main test failures previously reproduced on clean main include stale imports of removed processors/app models and stale SQL expectations; do not claim the full suite is green. Target checks relevant to the actual changes are documented in the reports.

## Next session checklist

1. Read this and the two reports; check branch/worktree before edits. Avoid replaying completed benchmarks by default.
2. If the English VietStyle set has arrived, verify its semantic/numeric/table alignment, question translations and evidence labels against VN. Preserve a versioned frozen dataset. Decide scope explicitly so a same-language duplicate cannot mask cross-language failure.
3. Inspect existing production token-aware/table chunking and propose the smallest justified change. Explain it before/after for the user.
4. Run a controlled four-direction comparison on equivalent data, record chunking/tokenizer/prefixes/model revisions and metric definitions. Separate encoder-only dense tests from translated-hybrid pipeline tests.
5. Choose a model only after assessing both language directions, retrieval evidence quality, latency/VRAM and deployment constraints. Any live vector migration is a separate authorized task.
