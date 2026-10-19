# Handoff for Codex on another machine

Updated: 2026-10-19, Asia/Saigon. Read this before continuing the user's work.

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