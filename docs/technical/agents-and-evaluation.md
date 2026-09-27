# Agents, dashboard and evaluation

## Agent routes

`AgentRouter` is a compiled LangGraph graph with classify and conditional
specialist nodes. Current destinations are knowledge QA, verified-metric
analytics, hybrid document-plus-analytics, dashboard data, and report summary.
Routing and specialist implementations live in `src/core/agents/`.

Analytics generates a SELECT for a narrow allowlisted schema using SQLGlot AST
validation. The database repository validates it again, exposes only
role- and trusted-company-filtered CTEs for verified metrics or visible
document metadata, then executes in a read-only transaction with a three-second
statement timeout and 100-row cap. Mutations, joins, nested queries, arbitrary
tables/columns and non-allowlisted functions are rejected. Results must return
evidence document IDs. Financial results must also preserve `metric_name` and
`fiscal_year` in each row; citations are matched against those dimensions and
the source document before returning. If exact evidence cannot be matched, the
agent abstains instead of attaching another KPI from the same report. This
implements a bounded form of proposal SQL generation, not unrestricted
cross-domain SQL; multi-source joins and broader BI calculations remain
unimplemented.
The bilingual metric ontology in `src/core/analytics/metric_ontology.py`
normalizes revenue, cost of sales, gross and after-tax profit, assets, cash,
inventory, employee count and state-budget contribution labels. The report
processor uses the same source labels to create at most one page-linked
candidate per metric/report. It first pairs prominent PDF number spans with
nearby labels for infographic KPIs, then uses structured table rows and nearby
text when they are not ratio or obvious narrative matches. Layout matching uses
native text spans (font size at least 28 points and within 36 PDF points of the
label); it does not OCR scans. The
2026-09-26 annual-report dry run produced 35 candidates with source quotes
across 2020–2024; it wrote nothing to the database. The run summary is
`artifacts/evaluation/vinamilk-metric-candidate-smoke.json`. Coverage measures
candidate availability, not extraction accuracy: comparative columns and
report-specific units still require admin review, and layout-heavy 2024 pages
produce fewer candidates. Only an admin-verified value enters dashboard
analytics. This finance-focused mapping does not define the full enterprise
entity/domain ontology or sustainability and governance metric tables.
The dashboard is database-backed and role-scoped. KPI evidence enters the
admin review queue only after document processing reaches `ready`; the review
write checks the status again before publishing. Public source documents do
not become private merely because demo RBAC is applied. The company/year
selectors filter the role-scoped analytics snapshot; the domain aggregate
retains fiscal year so those filters remain meaningful. Indexed-passage counts
include chunks only for ready documents, matching retrieval eligibility.

## Proposal evaluation master matrix

The proposal defines five baseline-comparison groups and additional system,
document, and business-case evaluation. They are separate dimensions; a model
comparison does not by itself establish that the whole system meets the
proposal. A result counts only when its dataset/case hash, settings, run
artifact, and limitations are recorded. `Pending` means no comparable evidence
exists; proxy/smoke results are not final evaluation.

| Proposal item | Dataset and protocol | Metrics / evidence | Current status | Run / next action |
| --- | --- | --- | --- | --- |
| OCR: PaddleOCR, EasyOCR, Surya | Identical rendered pages, including scanned Vietnamese, tables and mixed layouts; manually checked transcription/layout labels | CER/WER, table/layout extraction accuracy, pages/minute, peak RAM/VRAM | Still incomplete. Human-reviewed v2 has three crops: Vietnamese financial infographic, English sustainability passage, and a Vietnamese raster-embedded product poster (not a physical scan). Tesseract at 180 DPI scored micro CER/WER .1627/.3815 and macro CER/WER .3124/.5415; the poster alone scored .6688/.9375. This is Tesseract-only; PaddleOCR 2.10 CPU was OS-killed (137), EasyOCR was killed at model load, and Surya is unrun. Current host has no GPU and limited available memory. The unreviewed 10-page diagnostic remains ineligible for selection. | Run Paddle/EasyOCR/Surya on a higher-memory/GPU host against the same three manual crops, then add reviewed physical scans, harder layouts and cell/layout labels. This three-crop transcription pilot is not model-selection evidence. |
| Embeddings: BGE-M3, Qwen3 Embedding, e5-large-v2 | Same sample across all 25 ready documents and twelve labeled queries, role-filtered | Precision@1, Recall@3, MRR, nDCG@3, embedding/query time, peak RSS | On the refreshed corpus, BGE and e5 completed on the same 173-chunk sample: MRR 0.606/0.706, Recall@3 0.750/0.833, nDCG@3 0.616/0.719. Qwen3 did not finish: its first CPU batch took 200 s, so no score is reported. The sample is only 173/4,750 chunks, with document labels and no passage judgments. | Run Qwen on a faster/GPU host with the same sample/hash; then expand and independently review labels before selecting a model. Artifacts and exact limits are in `vinamilk-embedding-three-model-expanded-25docs-12cases-20260927.json`. |
| LLM: Qwen3, Llama 3, GPT | Same five Vinamilk QA cases, retrieved contexts, prompts and output cap; context and prompt hashes paired across runs | Grounded source/fact/RBAC smoke, labeled context precision, line citation coverage and latency; semantic quality still needs blinded review | Expanded proxy comparison: GPT-OSS-20B, Qwen3.8-27B and GPT-OSS-120B each pass five automated source/fact/denial checks; mean answer latency 11.72/15.38/9.88 s. GPT-OSS-120B adds a wrong unit conversion despite the expected headlines, showing these checks do not measure faithfulness. No human ratings. Exact Qwen3-32B/Llama3.1/3.3 are retired for Groq developer accounts; proprietary OpenAI GPT key is absent. | See the paired reports and limits in [LLM evaluation](llm.md); secure exact proposal checkpoints where available, then collect blinded human ratings. |
| Retrieval: dense, BM25, hybrid, parent-document | Same 25-document live corpus snapshot, 12 labeled questions/roles and selected passage labels; parent expands bounded child windows. | Document- and passage/context-level Recall@K, Precision@K, MRR, nDCG, retrieval latency | The 12-case run reports document MRR 1.000/0.958/0.944/1.000 for dense/BM25/hybrid/parent. Passage MRR is 0.412/0.403/0.464 for dense/BM25/hybrid; hybrid leads passage MRR and ties dense for passage Recall@5 (0.444). Parent context MRR is 0.469 with gold-passage coverage Recall@5 0.458. Three new governance cases include a weak conflict-of-interest passage rank (MRR 0.111 under hybrid), despite the relevant document ranking first. Labels remain selected and need independent review. | Expand and independently review passage judgments, include harder/denied cases, and repeat runs before drawing a winner. Artifact: `vinamilk-retrieval-12cases-expanded-corpus-20260927.json`. |
| Reranking: BGE, Qwen | Identical role-filtered dense top-30 candidates, same case hash and reviewed passage judgments | Before/after passage Precision@K, Recall@K, MRR, nDCG, rerank latency, memory; downstream answer quality | BGE full-depth run completed on all nine cases at CPU/max length 256/batch 2: passage MRR 0.429→0.459 and Recall@2 0.241→0.259, while document MRR fell 1.000→0.917; mean rerank 29.67 s/query, peak RSS 2,820 MiB. Qwen remains top-2 only: passage MRR 0.389→0.444 at 15.74 s/query. A fresh Qwen top-30 CPU pilot loaded the model but still had no score after >2 minutes for its first 30-candidate case at max length 256/batch 2 (2 CPU threads); it was stopped before result generation. The current host has no CUDA GPU and swap is exhausted, so a nine-case CPU run is not viable within this environment. No full-depth paired model comparison; labels remain selected/non-exhaustive. | Run Qwen top-30 against the same candidate set/hash on a GPU/adequate-memory host; expand independently reviewed passage judgments and evaluate downstream answer quality. |
| OCR/layout and document understanding | Real PDF, DOCX, XLSX, PPTX, scanned/image, table, figure, invoice and formula samples with reviewed expected content | Text CER/WER, table cell F1, field exact match, layout/figure-caption accuracy, metadata accuracy, processing failure rate and time | Partial: two visually reviewed financial pages/5 fields. 2020 infographic native/PDF-OCR/image-upload OCR each score 2/2 exact. On 2024, native text scores 3/3 exact; PDF-raster OCR 0/3 exact and image-upload OCR 2/3 exact. Raster PDF and image upload each detect 2/2 table regions; normalized structured anchors are 3/3 and 2/3 respectively. Native-PDF table extraction matches 3/3 exactly. OCR v2 adds three manually transcribed regions, including a raster-embedded poster, but no physical scan. Real scans, broad formats, invoices, figures, formulas and metadata labels remain absent. | `uv run python scripts/evaluate_document_extraction.py`; expand reviewed fixtures to actual scans and multi-format tables, invoices, figures, formulas and metadata before reporting document-level quality. |
| Generation and grounded QA | Labeled answerable and unanswerable cases across finance/product/sustainability plus role-denial controls | Faithfulness, answer relevancy, context precision, hallucination rate, source/fact accuracy, abstention and citation coverage | The refreshed live authenticated `/api/ask` suite passes 5/5 cases over finance (2020/2024), sustainability, product and employee-denial paths; checks cover expected agent, facts, cited document, citation consistency and abstention. Mean latency is 26.405 s. A browser rerun confirmed 2024 consolidated revenue/profit are answered from the explicitly matching report excerpt; financial summary prompts no longer require unrelated statement figures or unsupported reconciliation. Blinded review packet still has 0/10 ratings in each reviewer file; semantic quality, agreement, faithfulness and hallucination scoring remain unmeasured. | Complete two independent blinded reviews against cited source pages, import via `scripts/qa_human_review.py`, and report per-model ratings plus reviewer agreement. |
| System performance and scalability | Same deployment/corpus; warm-up then repeated requests at increasing concurrency and corpus sizes | Average/p50/p95 response time, retrieval latency, throughput, error rate, CPU/RAM/VRAM and scaling curve | In-process repeated run completed 70/70 endpoint requests across concurrency 1/2/4; throughput 0.430/0.804/1.441 req/s and p95 latency 4.53/4.11/4.92 s. This is more repeatable evidence than the earlier 21-request smoke, but is not deployed load or a scalability curve. No CUDA GPU on the measured host. | `uv run python scripts/evaluate_api_load.py`; add an external deployed load run, larger corpus/concurrency steps and resource telemetry before capacity/scalability claims. |
| Optimization / deployment | Paired baseline vs one change at a time on the same cases and load; include fixed-vs-semantic/context-aware chunking, prompt and retrieval variants | Retrieval/generation quality delta plus latency/throughput/resource delta | Shared fixed and sentence-aware chunking is configurable. A five-year/five-question read-only dense diagnostic compares 1,912 live fixed chunks with 1,978 in-memory sentence-aware chunks: document MRR 1.0 for both (restricted candidate corpus), passage MRR 0.2715 vs 0.2648 and Recall@5 0.10 for both. Alternate passage labels use unreviewed trigram transfer, so this is preliminary and does not compare QA. A same-snapshot four-setting hybrid RRF sweep was added; default 1:2, k=60 had the best passage MRR/nDCG@5 among tested settings, while 2:1 restored document MRR to 1.0. Nine selected cases are insufficient to tune/select weights. Prompt, query rewriting, context compression, embedding optimization, response caching and GPU acceleration are not established. Docker/CI config exists; deployed CI/CD evidence remains. | Independently review/expand queries and passage labels, rerun paired weights with QA; then test remaining optimizations one at a time. Validate Docker/Nginx/CI on a deployment target. |
| Business cases / agents | Twelve proposal cases: knowledge management, internal search, HR, contracts, financial reports, invoices, manufacturing, customer service, technical docs, compliance, executive decisions and business intelligence analytics | Per-case success, grounded answer/citations, correct route/tool, access-denial behavior, latency and human usefulness | `scripts/evaluate_agent_routes.py` measured the live classifier/router against 12 manually mapped route labels: effective routing 12/12; 9 used provider output and 3 correctly used fallback after rate limits. The pre-prompt direct run scored 11/12, misrouting document-count aggregation; after clarifying metadata counts/grouping, a direct recheck routed that case to analytics. Artifacts: [full route run](../../artifacts/evaluation/proposal-business-route-evaluation.json), [direct BI recheck](../../artifacts/evaluation/proposal-business-route-analytics-recheck.json), and [pre-prompt run](../../artifacts/evaluation/proposal-business-route-evaluation-pre-prompt.json). Dashboard has no label in these twelve cases. Routing scores do not establish agent execution or answer quality; private HR, contracts, invoices, manufacturing and customer-service source evidence is absent. | Add authorized domain documents and grounded tasks; add reviewed dashboard cases and evaluate tool/task completion, answer quality and denials by role. |
| Agent workflow and monitoring | Representative routed QA, analytics, report, dashboard and failure cases | Route accuracy, tool success, task completion, trace completeness, latency/errors | LangGraph route wiring and authenticated QA are implemented. Live `/api/ask` evaluation passes five supported source/fact/route/RBAC cases with mean latency 26.405 s (`artifacts/evaluation/vinamilk-app-qa-suite.json`). The separate 12-case route benchmark measures routing only. The QA run caught a text/integer fiscal-year mismatch in document analytics; the role-filtered CTE now normalizes valid years safely. SQL allowlist/read-only behavior has unit tests; live role-filtered read-only SQL returns expected empty-data results for analyst/employee. Authenticated WebSocket QA, bounded SQL generation and admin monitoring are implemented. Browser verification covered analyst login, database-backed dashboard, dynamic filters, cited business question, and admin processing/access/monitoring screens. Live uploader-authenticated XLSX was read back from PostgreSQL and private Storage. A second live smoke injected embedding initialization failure after parsing newline-terminated TXT, retried the saved chunk, verified document `ready`/parsed `embedded`/one vector, and confirmed BM25 returned it to `finance_analyst` but not `employee`; both fixtures were removed and cleanup verified. Nginx proxy runtime remains unverified. Human answer-quality scoring and agent task completion quality remain. | Expand live upload/retry/RBAC checks to representative real files; expand human-reviewed QA by role/domain and verify deployment-proxy flows. |


## Proposal acceptance checklist

This is the concise completion view; measured values and methodology stay in
the matrix above and linked technical notes. `Partial` means implementation
or limited evidence exists, but the proposal's acceptance condition is not met.

### Five baseline benchmark groups

| Group | Required comparison | Status | Acceptance gap |
| --- | --- | --- | --- |
| OCR | PaddleOCR, EasyOCR, Surya | Partial | Tesseract-only scores exist; cloud notebook now pins PaddleOCR/EasyOCR and Surya v1 on identical manually transcribed crops. No Kaggle run or model scores have been verified yet; physical scans and reviewed layout/table labels remain required. |
| Embeddings | BAAI BGE-M3, Qwen3 Embedding, e5-large-v2 | Partial | Local BGE/e5 results exist; cloud notebook now compares all three on the same manifest-allowlisted 4,750-passage corpus and 12 cases with one GPU/batch configuration. Run it and bring back reports; labels remain sparse for selection. |
| LLMs | Qwen3, Llama 3, GPT | Partial | Current paired results use explicitly labeled proxies, not exact requested checkpoints; collect blinded semantic-quality ratings and exact models where accessible. |
| Retrieval | Dense, BM25, hybrid, parent-document | Partial | Four methods have a refreshed 12-query run on the 25-document corpus; selected passage labels remain sparse and need independent review and expansion. |
| Rerankers | BGE Reranker, Qwen Reranker | Partial | BGE top-30 and Qwen top-2 are measured; run Qwen top-30 on the same candidate set/hardware class and compare downstream QA. |

### Evaluation and optimization beyond the five groups

| Requirement | Status | Evidence / remaining acceptance work |
| --- | --- | --- |
| Document preparation and understanding | Partial | The latest read-only manifest-to-database audit finds 0 mismatches across 350 document-row metadata checks and 52,250 chunk metadata checks for all 25 ready documents (4,750 chunks). This validates propagation of curated metadata, not automatic extraction accuracy. PDF/Office/image parsing and narrow financial/table anchors are checked; reviewed scan OCR, metadata-extraction, cleaning, table-cell, figure/caption, invoice and formula labels across formats remain. Artifact: [2026-09-27 metadata audit](../../artifacts/evaluation/vinamilk-corpus-metadata-audit-20260927.json). |
| Retrieval quality | Partial | Recall@K, Precision@K, MRR and nDCG are implemented/reported; selected labels remain small and non-exhaustive. |
| Generation quality | Partial | Source/fact/citation and abstention checks run through the authenticated app; faithfulness, answer relevancy, hallucination and reviewer agreement need blinded human scoring. |
| System performance | Partial | Local API latency/throughput run exists; deployed response time, GPU utilization and corpus/concurrency scalability are unmeasured. |
| Chunking and prompt optimization | Partial | Fixed vs sentence-aware retrieval and prompt regressions have diagnostics; expand paired cases and measure answer quality. |
| Hybrid retrieval tuning | Partial | Four RRF settings were paired over the same 9 queries and current corpus snapshot. The existing 1:2, k=60 setting led passage MRR/nDCG@5; 2:1 led document metrics. This is too small/non-exhaustive for selection; artifact: [hybrid weight sweep](../../artifacts/evaluation/vinamilk-hybrid-weight-sweep-20260927.json). |
| Query rewriting, context compression, embedding optimization, response caching, GPU acceleration | Pending | Proposal experiments not yet run as controlled same-input comparisons. Instruction tuning is optional. |
| Twelve proposal business cases and agent task completion | Partial | 12/12 route labels are measured, but three used fallback; five supported QA cases run end to end. Dashboard labeling, domain source evidence, task success and quality remain incomplete for most cases. |

### Application, deployment, and deliverables

| Requirement | Status | Evidence / remaining acceptance work |
| --- | --- | --- |
| Document upload, knowledge search, grounded QA, analytics/dashboard, report and multi-agent UI/API | Partial | Core authenticated flows and selected browser/live DB paths work; add repeatable demo acceptance through proxy and source-backed business tasks. |
| Authentication, document RBAC, secure PostgreSQL/pgvector | Partial | Server-side role filters, SQL constraints and selected live role checks exist; validate full role matrix with representative restricted documents and deployment setup. |
| Docker, Nginx, WebSocket and CI/CD | Partial | Configuration and local app paths exist; container/proxy runtime and hosted CI/CD on this feature branch remain unverified. |
| Monitoring / experiment infrastructure | Partial | Privacy-minimized agent events and admin console exist; proposal-listed LangSmith, MLflow, Prometheus and Grafana are not integrated. |
| Technical documentation, user manual, deployment guide, demo, research report | Partial | Drafts and setup flows exist; independent operator walkthrough, deployment-backed demo, and final evidence-complete report remain. |

## Corpus metadata audit

`uv run python scripts/evaluate_corpus_metadata.py` compares exact manifest
metadata with persisted document rows and every chunk for ready manifest
sources. The 2026-09-27 read-only run checked all 25 ready documents, 350
document fields and 52,250 chunk fields across 4,750 chunks with zero
mismatches; none of the 25 manifest documents is missing or not ready. This
catches propagation defects such as missing HTML language/source/type tags;
the four local HTML sources were re-ingested after such mismatches were found.
The audit measures manifest propagation, not automatic metadata extraction
quality, content cleaning, or metadata correctness against the original source.
Its manifest/source hashes and per-document coverage are in
`artifacts/evaluation/vinamilk-corpus-metadata-audit-20260927.json`.

## Benchmark protocol and proposal cross-check

The five comparison groups above are exactly the proposal's baseline list:
PaddleOCR/EasyOCR/Surya OCR; BAAI BGE-M3/Qwen3 Embedding/e5-large-v2;
Qwen3/Llama 3/GPT; dense/BM25/hybrid/parent-document retrieval; and BGE/Qwen
rerankers. Rows marked smoke or partial have runnable code or limited artifacts,
not final comparative evidence. In particular, do not rename an available proxy
as the requested model family or treat a failed model load as a score.

Proposal traceability beyond the five comparison groups is in
[`docs/README.md`](../README.md): requirements are grouped by pipeline,
application, security, evaluation, deployment and deliverables. The proposal's
named quality measures are kept explicit here: retrieval Recall@K,
Precision@K, MRR and nDCG; generation faithfulness, answer relevancy, context
precision and hallucination; system average response time, throughput,
retrieval latency, GPU utilization and scalability. Missing labels, unavailable
hardware, or unverified deployment are recorded as gaps rather than inferred
successes.

The proposal also calls for evaluations outside those five groups. The matrix
tracks OCR/layout and extraction quality, grounded generation, system
performance and scalability, controlled optimization/deployment, business-case
coverage, and agent workflows. Before calling evaluation complete, also close
these explicit proposal requirements:

- **Data preparation:** verify metadata extraction and data cleaning on labeled
  examples; evaluate PDF, DOCX, XLSX, PPTX, scans/images, tables, figures,
  invoices and formulas with real, authorized samples. Table persistence alone
  does not establish cell or field accuracy.
- **Optimization:** run paired, same-input tests for query rewriting, context
  compression, hybrid retrieval tuning, embedding optimization, response
  caching and GPU acceleration. These are proposal experiments, not completed
  merely because the baseline pipeline runs. Instruction tuning is optional.
- **Deployment and deliverables:** validate Docker/Nginx/WebSocket, CI/CD and
  production observability on a deployment target; finish the user manual,
  deployment guide, demo flows and research report with measured evidence.
- **Business cases:** evaluate the twelve listed use cases only where real
  source material is available. Mark uncovered domains untested; do not
  synthesize documents or claim a public Vinamilk corpus proves private HR,
  contract, invoice or manufacturing coverage.

For every benchmark, freeze the input corpus/case IDs and SHA-256, role, model
checkpoint/revision, prompt and decoding settings, retrieval candidates,
software/config versions, hardware, warm-up policy and repeat count. Keep raw
per-case outputs plus aggregate metrics and failures. Change one variable at a
time; compare the same cases and contexts when evaluating generation models.
Report mean and spread (or confidence intervals where sample size permits),
latency/resource cost and limitations. A smoke run is a plumbing check; it is
not a model-selection result. Maintain the status here and link each completed
run artifact from `docs/README.md` so the proposal checklist and evidence stay
in one place.

## Additional proposal evaluation

The proposal also calls for system response time, retrieval latency,
throughput, GPU utilization and scalability. Retrieval latency is recorded in
the comparison artifact. `scripts/evaluate_api_load.py` measures `/health`,
`/api/dashboard` and `/api/analytics` through an in-process ASGI transport
against the configured database. The repeated 2026-09-27 local-date run
completed 70/70 requests (10 per worker at concurrency 1/2/4), all HTTP 200.
Throughput was 0.430, 0.804 and 1.441 requests/s; p95 latency was 4.53, 4.11
and 4.92 seconds, respectively. The earlier 21-request smoke measured 0.372,
0.803 and 1.465 requests/s, showing similar throughput at these light levels.
Both are single-host ASGI checks, not deployed or production scalability
evidence. They exclude document processing and LLM generation. The host has no
CUDA GPU, so utilization is unavailable. The repeated artifact is
`artifacts/evaluation/vinamilk-api-load-repeat10.json`; the original smoke is
preserved separately. Use a dedicated deployed load setup before capacity
claims.
Query rewriting, response caching and GPU acceleration are proposal
optimization candidates, not implemented/evaluated claims.

Current labeled data: `data/evaluation/vinamilk_retrieval_cases.json` has twelve
document-labeled cases and 24 selected, source-matched passage judgments tied
to the current chunk-index snapshot. Three governance queries were added after
checking the quoted passages and role ACLs in the live database. The labels are
not exhaustive and remain a smoke benchmark requiring independent review and
broader coverage. The pre-governance nine-case run is
`artifacts/evaluation/vinamilk-retrieval-current-passage-comparison.json`; the
expanded-corpus nine-case rerun is
`artifacts/evaluation/vinamilk-retrieval-expanded-corpus-20260927.json`; the
current four-method, twelve-case run is
`artifacts/evaluation/vinamilk-retrieval-12cases-expanded-corpus-20260927.json`.
The retrieval runner supports `--methods` and
`--case-ids`, validates passage labels against the live ready/role-filtered
corpus, and reports document and passage metrics plus per-query latency. Do
not infer answer quality from retrieval-only scores.

### Reranker memory-safe full-depth protocol

The current paired top-2 result is diagnostic only. The full comparison should
use the same top-30 dense candidates, nine case IDs, max sequence length,
batch size and device for each checkpoint. First run one case to confirm model
load and memory, then run all cases for each model and preserve distinct
artifacts:

```bash
uv run python scripts/evaluate_rerankers.py --model bge-reranker-v2-m3 --device cuda --candidate-k 30 --batch-size 8 --output artifacts/evaluation/vinamilk-reranker-bge-top30.json
uv run python scripts/evaluate_rerankers.py --model qwen3-reranker-0.6b --device cuda --candidate-k 30 --batch-size 8 --output artifacts/evaluation/vinamilk-reranker-qwen-top30.json
```

For CPU, start with `--case-ids finance-revenue-profit-2024-vi` and a small
batch/sequence length pilot, note its `peak_rss_mb` and current available RAM,
then set `--max-memory-mb` to the measured peak plus headroom on the full run.
The runner checks that budget against currently available RAM before model
loading. It does not invent a model memory estimate; pilot measurements remain
specific to the model, sequence length, batch size, process and host.
The 2026-09-27 BGE full-depth artifact is
`artifacts/evaluation/vinamilk-reranker-bge-top30-passage-cpu.json`: at
candidate-k 30, sequence length 256 and batch 2, passage MRR improved by
0.031 while document MRR declined by 0.083. Peak RSS was 2,820 MiB, mean
rerank time 29.67 seconds/query, and current swap was nearly exhausted after
the run. A fresh sequence-256/batch-2 CPU pilot still exceeded two minutes on
one query without a score, so Qwen top-30 is deferred to a higher-memory/GPU
host; compare
candidate SHA-256 before interpreting any paired result.

### Embedding model comparison

Run one model per process to keep peak-memory readings attributable and avoid
mixing the candidate vector dimensions with the app's fixed `vector(384)`:

```bash
uv run python scripts/evaluate_embeddings.py --model bge-m3 --max-chunks-per-document 3
uv run python scripts/evaluate_embeddings.py --model qwen3-embedding --max-chunks-per-document 3
uv run python scripts/evaluate_embeddings.py --model e5-large-v2 --max-chunks-per-document 3
```

Models are `BAAI/bge-m3`, `Qwen/Qwen3-Embedding-0.6B`, and
`intfloat/e5-large-v2`. The runner follows each model's query/passage format,
uses 512-token inputs, filters chunks by the labeled user's database roles,
and computes document rank from the maximum chunk cosine score. By default,
it evenly samples up to 32 passages per source from the ready corpus so CPU
runs remain practical; all models must use the same cap and corpus snapshot.
This first pass is explicitly a sampled-corpus smoke test, not a full-corpus
comparison. It re-embeds in memory and never writes candidate vectors to
Supabase. Reports include model revision, dataset hash, model-load/corpus/query
time and process peak RSS. The nine document labels are too small for a
statistically complete evaluation. The default sample is up to 32 passages per
source; the small sample below was chosen for practical CPU runtime.

Measured smoke results (2026-09-26; identical sampled corpus SHA-256
`196f7cd7b63eab4b528b025cc1d06d1dba6ee8ec1180888dc90db89beb00f75b`; 38 of
3,785 ready Vinamilk chunks; nine queries; CPU):

| Model | Precision@1 | Recall@3 | MRR | nDCG@3 | Corpus embed time | Mean query time |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| BAAI BGE-M3 | 0.222 | 0.667 | 0.479 | 0.474 | 46.09 s | 179 ms |
| Qwen3 Embedding 0.6B | 0.444 | 0.444 | 0.558 | 0.444 | 312.02 s | 1,337 ms |
| e5-large-v2 | 0.111 | 0.667 | 0.396 | 0.418 | 38.14 s | 193 ms |

Do not select a production winner from this result: three sampled passages per
report can omit a relevant section, and there are only nine queries. Model
revisions, full metrics and per-case rankings are in the JSON reports.

Prior expanded paired comparison (2026-09-27; identical corpus SHA-256
`7a4bccbf9ffb1483800e9db23b72007fbfec4590a292fe09c04f375f86854420`; 93 of
3,785 ready Vinamilk chunks, up to eight per document; same nine queries; CPU;
512-token cap):

| Model | Batch | Precision@1 | Recall@3 | MRR | nDCG@3 | Corpus embed time | Mean query time | Peak RSS |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| BAAI BGE-M3 | 1 | 0.444 | 0.889 | 0.670 | 0.710 | 102.51 s | 171 ms | 2,434 MiB |
| Qwen3 Embedding 0.6B | 8 | 0.556 | 0.778 | 0.670 | 0.667 | 1,325.40 s | 1,355 ms | 2,637 MiB |
| e5-large-v2 | 4 | 0.556 | 0.889 | 0.707 | 0.737 | 133.99 s | 219 ms | 2,189 MiB |

This expands the comparison but remains a small document-level benchmark with
nine queries and no passage judgments; it is not a production model-selection
result. Batch sizes differ due to model memory/runtime limits, so embedding
throughput is operational evidence under each recorded configuration, not a
strict batch-controlled speed ranking. Qwen CPU embedding time is notably
higher even at batch 8. Per-case rankings, hashes, settings and model revisions
are in `vinamilk-embedding-{bge-m3,qwen3-embedding,e5-large-v2}-expanded-8-per-document.json`.

After the ten governance reports were ingested, BGE-M3 and e5-large-v2 were
rerun against the same evenly spaced sample across all 25 ready documents
(173/4,750 chunks, batch 8, CPU, same 12 cases and sample SHA-256
`f24695ac0331516062b9ee7741476638ae141efbcae8b012fefd1a9c3fa224ac`). MRR is
0.606/0.706 and nDCG@3 is 0.616/0.719 for BGE/e5; corpus embedding took
223/281 seconds. On the three new governance cases, e5 ranked the right
document first for the Charter and Code of Conduct questions; BGE missed the
Charter document. Both struggled with the full-year disclosure deadline (MRR
0.125 BGE, 0.100 e5). Qwen3-Embedding was attempted with the same sample, but
its first batch took 200 seconds; it was stopped without scores. Do not present
the older Qwen score from the 15-document sample as a paired result for this
expanded corpus. The current incomplete comparison is recorded in
`vinamilk-embedding-three-model-expanded-25docs-12cases-20260927.json`; the
earlier nine-case run is preserved separately. These remain small
document-level diagnostics, not full-corpus model-selection results.

Earlier retrieval baseline (before the ten governance files were ingested) is
preserved in `vinamilk-retrieval-current-passage-comparison.json`. A rerun on
the expanded 2026-09-27 corpus (5,052 chunks/44 documents overall, 4,750
chunks/25 ready Vinamilk documents; 9 cases; 30 passage candidates/query;
parent first stage up to 100 child candidates, returning up to 30 context
windows) is in `vinamilk-retrieval-expanded-corpus-20260927.json`:

| Method | Document P@1 | Document MRR | Passage/context MRR | Passage Recall@5 or gold-passage coverage@5 | Mean latency |
| --- | ---: | ---: | ---: | ---: | ---: |
| Dense, multilingual MiniLM | 1.000 | 1.000 | Passage 0.373 | Passage Recall@5 0.259 | 2,082 ms |
| BM25, k1=1.2, b=0.75 | 0.889 | 0.944 | Passage 0.307 | Passage Recall@5 0.352 | 1,393 ms |
| Hybrid, RRF | 0.889 | 0.926 | Passage 0.384 | Passage Recall@5 0.370 | 1,422 ms |
| Parent context, dense child retrieval | 1.000 | 1.000 | Context 0.431 | Gold-passage coverage@5 0.278 | 2,236 ms |

The exact report records the case-file SHA-256, Postgres/Python versions,
corpus counts, run timestamp, per-case rankings and latency. The test set is
small, with one relevant document per question and selected non-exhaustive
passage labels; these scores are smoke evidence, not a statistical claim.
Document MRR remains high while passage/context MRR is lower, showing why
document-only evaluation is insufficient. Latency includes first-use embedding
initialization; no throughput or concurrency claim is made.

### Reranker comparison

Run one cross-encoder at a time on the same role-filtered dense top-30 passage
candidates:

```bash
uv run python scripts/evaluate_rerankers.py --model bge-reranker-v2-m3
uv run python scripts/evaluate_rerankers.py --model qwen3-reranker-0.6b
```

The runner validates passage labels against the ready, role-visible database
snapshot and records document- and passage-ranking metrics, case/candidate
hashes, model revision, retrieval/reranking time, device and peak process
memory. On the
2026-09-26 CPU run, BGE v2 m3 took 39.21 s mean reranking time per query and
changed P@1/MRR from 1.000/1.000 to 0.889/0.917 across nine document-level
cases. Dense retrieval already ranked the labeled document first in all nine,
so this small set does not show a reranker benefit. The Qwen3-Reranker
checkpoint loads at revision `e61197ed45024b0ed8a2d74b80b4d909f1255473`,
but full 30-candidate CPU inference was impractically slow (the first query
exceeded eight minutes) and was stopped. Paired nine-case top-2 CPU smokes at
max sequence length 256 used the same candidate SHA-256
`f6eafcdd6df74c562a3d43fa7d21ac67901744067cd341da2114d67b956e8e21`:
BGE averaged 2.32 s/query and Qwen 12.92 s/query. Both preserved dense P@1/MRR
at 1.0. Artifacts are
`artifacts/evaluation/vinamilk-reranker-bge-reranker-v2-m3-cpu-top2-smoke.json`
and `artifacts/evaluation/vinamilk-reranker-qwen3-reranker-0.6b-cpu-top2-smoke.json`.
The refreshed passage-level CPU top-2 runs use the same case SHA-256
`5bbd71991f06382b9c3eb7c89be267b4a4bca7551d218731e6843932de4f9c3d` and
candidate SHA-256
`6db8d6984d1587311270074b29c0bdae53167f968bd908f5e4e15a89132aebc8`:

| Model | Dense passage MRR | Reranked passage MRR | Dense nDCG@2 | Reranked nDCG@2 | Mean rerank time |
| --- | ---: | ---: | ---: | ---: | ---: |
| BGE v2 m3 | 0.389 | 0.333 | 0.290 | 0.265 | 1.73 s/query |
| Qwen3-Reranker-0.6B | 0.389 | 0.444 | 0.290 | 0.316 | 15.74 s/query |

Artifacts are
`artifacts/evaluation/vinamilk-reranker-bge-reranker-v2-m3-cpu-top2-passage.json`
and
`artifacts/evaluation/vinamilk-reranker-qwen3-reranker-0.6b-cpu-top2-passage.json`.
This is an early quality signal only: nine cases, selected/non-exhaustive
labels, and top-2 candidates cap recall. It does not establish a winner or
measure downstream answer quality. Run identical top-30 candidates on an
accelerator and expand independently reviewed judgments.

The current five-case answer run is `artifacts/evaluation/vinamilk-qa-current-smoke.json` (2026-09-26): 5/5 expected-source, expected-fact and RBAC checks passed. The two earlier model smoke runs in `artifacts/evaluation/vinamilk-qa-smoke.json` and
`artifacts/evaluation/vinamilk-qa-qwen3.8-smoke.json` each passed 5/5
expected-source, selected-fact and denial checks. Each checks four answerable
cases plus one employee denial; key-fact and source/refusal accuracy were 1.0
for both. This is a hand-picked smoke set, not an automated faithfulness or
hallucination score. Per-case human-review fields are intentionally blank.
