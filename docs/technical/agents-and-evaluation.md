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
The bilingual metric ontology in `src/core/analytics/metric_ontology.py` is
the source of truth for 11 canonical KPI names, English/Vietnamese aliases,
definitions and unit guidance. It currently covers revenue, cost of sales,
gross and pre-/after-tax profit, assets, cash, inventory, employee count and
state-budget contribution. These are application definitions; when a source
distinguishes consolidated from parent-only results or uses a special basis,
the source scope and unit remain part of the evidence and require review. The report
processor uses the same source labels to create at most one page-linked
candidate per metric/report. It first pairs prominent PDF number spans with
nearby labels for infographic KPIs, then uses structured table rows and nearby
text when they are not ratio or obvious narrative matches. Layout matching uses
native text spans (font size at least 28 points and within 36 PDF points of the
label); it does not OCR scans. Query aliases may be generic, but candidate
`source_labels` omit ambiguous report labels such as “Revenue”, “Doanh thu” and
“Lợi nhuận thuần”. For comparative tables, the extractor selects the report
year only when the table column or same-page year/unit header identifies it;
otherwise it leaves multiple values for human review. Source quotes preserve
the year-to-value mapping when the header is recoverable. The
2026-09-26 annual-report dry run produced 35 candidates with source quotes
across 2020–2024; it wrote nothing to the database. The run summary is
`artifacts/evaluation/vinamilk-metric-candidate-smoke.json`. Coverage measures
candidate availability, not extraction accuracy: comparative columns and
report-specific units still require admin review, and layout-heavy 2024 pages
produce fewer candidates. Only an admin-verified value enters dashboard
analytics. It remains a finance ontology rather than a full enterprise
entity/domain ontology. Milk-supply operations now use a separate catalog and
`business_metric_evidence` review table with public-report candidates; see the
[Vinamilk milk-supply metric pack](vinamilk-milk-supply-metrics.md). Other
operations, sustainability and governance metric domains still need their own
reviewed evidence contracts.
Manual KPI entry is a separate workflow on the Metrics tab: an administrator
chooses a canonical metric, year, value, unit, viewer roles and source context.
It is stored as a `manual` candidate with no fabricated document/page citation,
then enters the same admin review queue as extracted candidates. Verification
publishes it into `extracted_financial_metrics`, retaining `verified_by`,
`verified_at`, `source_reference`, `source_note` and `entry_method`; dashboard
and SQL analytics read only role-visible verified rows and cite the metric row
itself. One verified metric per company/year/name is enforced. A human-entered
value should include enough source context to audit the underlying publication.
The report-summary agent retrieves role-visible knowledge passages directly;
for financial change explanations it combines those passages with cited,
role-visible verified KPI rows and says when the documents do not establish a
cause. Deterministic intent routing skips the classifier LLM for those
questions; the report synthesizer still validates citations. The dashboard is
database-backed and role-scoped. KPI evidence enters the
admin review queue only after document processing reaches `ready`; the review
write checks the status again before publishing. Public source documents do
not become private merely because demo RBAC is applied. The company/year
selectors filter the role-scoped analytics snapshot; the domain aggregate
retains fiscal year so those filters remain meaningful. Indexed-passage counts
include chunks only for ready documents, matching retrieval eligibility.

When a dashboard request names a financial metric and asks for a chart/trend,
`DashboardAgent` delegates to the bounded SQL analytics agent. The chart uses
only cited rows from verified, role-visible metrics and keeps each source
observation separate. The UI renders a fiscal-year line chart only when one
unit and at least two unambiguous years are available; mixed units, duplicate
metric/year observations or sparse data keep the cited text response without
a potentially misleading plot. General corpus-dashboard requests continue to
use the persisted coverage snapshot.

## Proposal evaluation master matrix

The proposal defines five baseline-comparison groups and additional system,
document, and business-case evaluation. They are separate dimensions; a model
comparison does not by itself establish that the whole system meets the
proposal. A result counts only when its dataset/case hash, settings, run
artifact, and limitations are recorded. `Pending` means no comparable evidence
exists; proxy/smoke results are not final evaluation.

| Proposal item | Dataset and protocol | Metrics / evidence | Current status | Run / next action |
| --- | --- | --- | --- | --- |
| OCR: PaddleOCR, EasyOCR, Surya (Tesseract baseline) | Same ten manually reviewed regions, 180 DPI, exact dataset/PDF/render hashes | CER/WER, table-row/cell text, throughput and memory | V7 paired five-setting comparison: Tesseract PSM 3/11, EasyOCR 1.7.2, PaddleOCR 3.7.0, and Surya 0.17.1 score micro-CER 0.272556/0.127318/0.110025/0.043609/0.043233 and micro-WER 0.263561/0.197497/0.248261/0.108484/0.090403. Surya GPU has the lowest text error and 14/16 exact table rows; Paddle ran CPU (2.229 pages/minute), while EasyOCR and Surya ran on T4 GPUs, so throughput and memory are not controlled comparisons. EasyOCR and Surya each detect 47/48 table-cell strings; Paddle 32/48; cell presence ignores row/column association. The ten-region v7 pilot still has six English physical-scan regions and one born-digital Vietnamese financial table. Latest v8 pairs Tesseract 4.1.1, PaddleOCR 3.7.0, EasyOCR 1.7.2 and Surya 0.17.1 on 11 reviewed regions from five issuer-hosted PDFs, including a manually transcribed full-page 2026 governance scan. Micro-CER is 0.217257/0.034654/0.089266/0.034654 and micro-WER is 0.230375/0.089875/0.211035/0.075085; Paddle/Surya tie CER and Surya has the lowest WER. Exact table rows are 15/16, 0/16, 2/16 and 14/16; cell strings are 47/48, 32/48, 47/48 and 47/48. Paddle ran CPU while EasyOCR/Surya used a Tesla T4, so runtime is not controlled. The latest paired artifact rescored cached runs after page hashes and source-count metadata were added; it records both the original run-label hash and final label hash. This remains an English-heavy diagnostic, not representative model-selection evidence. A separate three-page 2011 production-parser run covers one third-party Vietnamese financial-scan packet: Tesseract PSM 11 matched 17/17 selected rows, 34/34 numeric cells and 6/6 period headers. A v3 reference refresh adds visually checked full text for both balance-sheet pages using PDF text-layer assistance; rescoring the cached four-engine predictions across all three pages gives Tesseract/Paddle/Easy/Surya CER 0.693200/0.162611/0.449397/0.166705 and WER 0.912844/0.330275/0.540367/0.182569. Paddle has lowest CER, Surya lowest WER, and EasyOCR matches 9/17 complete selected rows. This small single-packet diagnostic is not representative and selects no engine. The parser follow-up also matches 20/20 source value-cell boxes on its two balance-sheet pages; boxes were located from the PDF text layer and visually checked, not independently click-annotated. The v7 and six-engine scan comparisons have no cell-coordinate labels. | Raw reports: [EasyOCR](../../artifacts/evaluation/ocr/comparisons/vinamilk-ocr-v7/easyocr.json), [PaddleOCR](../../artifacts/evaluation/ocr/comparisons/vinamilk-ocr-v7/paddleocr.json), [Surya](../../artifacts/evaluation/ocr/comparisons/vinamilk-ocr-v7/surya.json), and Tesseract [PSM 3](../../artifacts/evaluation/ocr/tuning/vinamilk-ocr-tesseract-scan-expansion-v7-180dpi-psm3-20260928.json)/[PSM 11](../../artifacts/evaluation/ocr/comparisons/vinamilk-ocr-tesseract-scan-expansion-v7-180dpi-20260928.json). The [hash-checked comparison](../../artifacts/evaluation/ocr/comparisons/vinamilk-ocr-v7-five-configuration-comparison-20260928.json) verifies the ten identical images. See the separate [multi-engine one-page diagnostic](../../artifacts/evaluation/ocr/comparisons/vinamilk-ocr-2011-scan-diagnostic/paired-comparison.json), [three-page parser labels](../../data/evaluation/ocr/archive/2011-scan/vinamilk_ocr_ground_truth_2011_scan_diagnostic_v2.json), [visually reviewed references](../../data/evaluation/ocr/archive/2011-scan/vinamilk_ocr_ground_truth_2011_scan_diagnostic_v3.json), [rescored comparison](../../artifacts/evaluation/ocr/comparisons/vinamilk-ocr-2011-v3-four-engine-comparison-20260929.json), [v8 labels](../../data/evaluation/ocr/archive/vinamilk_ocr_ground_truth_v8.json), [v8 four-engine comparison](../../artifacts/evaluation/ocr/comparisons/vinamilk-ocr-v8-four-engine-comparison-20260929.json), and [production-parser run](../../artifacts/evaluation/ocr/pipeline/vinamilk-scan-document-processor-2011-three-pages-v2-20260929.json). A reproducible v9 cross-layout rescore combines the 11 v8 regions with all three 2011 Vietnamese scan pages (four-engine micro-CER 0.361902/0.073542/0.198714/0.074786; exact row recall 15/33, 0/33, 11/33, 16/33). It reuses cached predictions after engine/settings/device and exact render-hash checks. V9 splits eight English and six Vietnamese pages; Vietnamese CER/WER favors Paddle for CER (0.161454) and Surya for WER (0.179017). Mixed visual/text-layer-assisted labels remain diagnostic. See the [v9 labels](../../data/evaluation/ocr/vinamilk_ocr_ground_truth_v9.json), [merged reports](../../artifacts/evaluation/ocr/comparisons/ocr-kaggle-v9/), and [comparison](../../artifacts/evaluation/ocr/comparisons/vinamilk-ocr-v9-four-engine-comparison-20260929.json).  A paired CPU-only v9 rerun processes the same 14 English/Vietnamese regions at 180 DPI with identical source/render hashes: Tesseract/Paddle/Easy/Surya micro-CER 0.361902/0.073542/0.198645/0.074924, micro-WER 0.491573/0.181882/0.337430/0.116573, and exact table rows 15/33, 0/33, 10/33, 16/33. Paddle has lowest CER; Surya lowest WER and highest row recall. CPU model identification was unavailable, so runtime is descriptive; mixed text-layer-assisted labels remain diagnostic. See the [paired CPU comparison](../../artifacts/evaluation/ocr/comparisons/vinamilk-ocr-v9-cpu-four-engine-comparison-20260929.json) and [raw reports](../../artifacts/evaluation/ocr/comparisons/ocr-kaggle-v9-cpu/).  A separate single-page upload-parser replay adds raster-derived labels to seven visually reviewed 2011 income-statement rows: all 7 rows and 14/14 values match, with 13/14 cell boxes reaching IoU >= 0.3. This is one page from one third-party packet and a single-reviewer label set, not paired OCR-engine evidence or model-selection evidence; see the [report](../../artifacts/evaluation/ocr/pipeline/vinamilk-scan-document-processor-2011-raster-cell-labels-20260929.json) and [v4 labels](../../data/evaluation/ocr/tuning/vinamilk_ocr_ground_truth_2011_scan_diagnostic_v4.json). Broaden issuer-traceable scan coverage and add independently reviewed spatial cell labels. |
| Embeddings: BGE-M3, Qwen3 Embedding, e5-large-v2 | Same snapshot of all 25 ready documents/4,750 chunks and twelve labeled queries, role-filtered | Precision@1, Recall@3, MRR, nDCG@3, embedding/query time, peak RSS/VRAM | Proposal models have a paired Tesla T4 run: BGE/Qwen/e5 document MRR 0.7759/0.8028/0.7583 on all 4,750/4,750 selected passages, identical case/corpus hashes, 512-token cap and batch size 4. This is document-level evidence with 12 sparse labels, not passage retrieval or production model selection. A separate CPU comparison on 173/4,750 chunks completed for BGE/e5 (MRR 0.606/0.706); Qwen was stopped after a 200 s first batch, so that CPU comparison has no Qwen result. The raw T4 reports contain stale sample-strategy/limitation text; the independent hash audit confirms actual full-corpus selection. | Expand and independently review passage labels before model selection; add a separate current 26-document snapshot when refreshed corpus packaging is available. See the [CPU sample comparison](../../artifacts/evaluation/vinamilk-embedding-three-model-expanded-25docs-12cases-20260927.json) and [T4 hash audit](../../artifacts/evaluation/vinamilk-embedding-three-model-full-corpus-hash-verified-20260928.json). |
| LLM: Qwen3, Llama 3, GPT | Same five Vinamilk questions, identical per-case retrieved-context and prompt hashes, same output cap; full cited chunks retained | Grounded source/fact/RBAC, amount-plus-unit accuracy, literal evidence support, latency; semantic quality still needs blinded review | Pre-guard unit-aware re-score: GPT-OSS-20B, Qwen3.8-27B and GPT-OSS-120B score 3/4, 4/4 and 3/4 expected fact cases; all correctly refuse the employee denial. Both GPT-OSS runs give the wrong 2024 revenue magnitude (million VND / 61.8 billion instead of 61,824 billion). Expected source accuracy is 1.00 for all; literal expected-fact support is 0.875/1.000/0.875. The amount/unit guard is implemented and unit-tested. Focused post-guard Qwen3.8 authenticated cases pass for FY2024 revenue/profit and employee Vinamilk Shop return policy (1/1 each; [`finance`](../../artifacts/evaluation/finance-2024-qwen38-20260928.json), [`customer service`](../../artifacts/evaluation/customer-service-employee-qwen38-20260928.json)); these are targeted proxy checks, not an exact proposal model comparison. GPT-OSS post-guard FY2024 rerun remains rate-limited. The 15-response blind packet and validated dual-review importer calculate exact agreement and quadratic-weighted Cohen's kappa per rating dimension; both reviewer packets remain unrated (0/10 each). Exact Qwen3-32B/Llama3.1/3.3 and proprietary GPT baselines remain unavailable in the tested provider. | Collect/import two independent blind reviews and obtain exact proposal checkpoints where available; rerun GPT-OSS when provider quota permits. |
| Retrieval: dense, BM25, hybrid, parent-document | Same 25-document live corpus snapshot, 12 labeled questions/roles and selected passage labels; parent expands bounded child windows. | Document- and passage/context-level Recall@K, Precision@K, MRR, nDCG, retrieval latency | Three runs have identical per-case rankings/metrics, including a follow-up after section-title metadata backfills: document MRR 1.000/0.958/0.944/1.000 for dense/BM25/hybrid/parent. Passage MRR is 0.412/0.403/0.464 for dense/BM25/hybrid; hybrid leads passage MRR and ties dense for passage Recall@5 (0.444). Parent context MRR is 0.469 with gold-passage coverage Recall@5 0.458. Three governance cases include a weak conflict-of-interest passage rank (MRR 0.111 under hybrid), despite the relevant document ranking first. Latency varies; the selected labels remain sparse and need independent review. | Expand and independently review passage judgments and include harder/denied cases before drawing a winner. See the [post-backfill live run](../../artifacts/evaluation/vinamilk-retrieval-post-section-title-backfill-12cases-20260928.json), [first live run](../../artifacts/evaluation/vinamilk-retrieval-live-12cases-20260928.json), and [repeat](../../artifacts/evaluation/vinamilk-retrieval-live-12cases-repeat2-20260928.json). |
| Reranking: BGE, Qwen | Identical role-filtered dense top-30 candidates, same case hash and selected passage judgments | Before/after passage Precision@K, Recall@K, MRR, nDCG, rerank latency, memory; downstream answer quality | Paired Tesla T4 top-30 run covers 12 identical cases/candidates at max length 256. BGE passage MRR 0.4117→0.5167, Recall@2 0.2639→0.375; document MRR 1.000→0.8958. Qwen passage MRR 0.4117→0.4348, Recall@2 0.2639→0.375; document MRR 1.000→0.9583. Mean rerank latency 1.1736/2.7415 s/query and peak process RSS 3,656/2,484 MiB (BGE/Qwen). Candidate SHA-256 is `521a56b77485b67b5082d93263dcdb148480a2f20d393473bc1bb3f061a9ad1d`; both ran on Tesla T4. Twelve selected/non-exhaustive judgments are insufficient for model selection; no downstream QA comparison is present. | Expand independently reviewed passage judgments and run same-context downstream answer quality comparison. Paired report: [`vinamilk-reranker-kaggle-top30-paired-20260928.json`](../../artifacts/evaluation/vinamilk-reranker-kaggle-top30-paired-20260928.json). |
| OCR/layout and document understanding | Real PDF, DOCX, XLSX, PPTX, scanned/image, table, figure, invoice and formula samples with reviewed expected content | Text CER/WER, table cell F1, field exact match, layout/figure-caption accuracy, metadata accuracy, processing failure rate and time | Partial: comparison exposed configuration drift, not unexplained OCR variance. The tracked baseline and prior v9 report used PSM 3; the active processing configuration uses PSM 11. A fresh PSM 3 run restores 2/2 exact OCR anchors on the 2020 financial infographic; on the 2024 balance sheet it gets 0/3 exact on raster-PDF and 2/3 exact on image upload, with 3/3 normalized text anchors on both. PSM 11 gets 0/2 exact on the 2020 OCR paths and 1/3 exact on the 2024 OCR paths. Native parsing and rule-based KPI candidates remain 2/2 (2020) and 3/3 (2024); both table modes detect 2/2 regions. A paired table-only PSM 6 run (text PSM 3) improves normalized table-anchor recall from 2/3 to 3/3 on image uploads and retains 3/3 on raster PDFs, though exact OCR strings still fail for some rows. PDF table-word extraction now defaults to PSM 3 and image uploads to PSM 6; text OCR stays on PSM 11 by default. A paired PSM 3/11 run on the same two image-only English scans favors PSM 11 on micro-CER/WER (0.038557/0.155425 vs 0.065744/0.167155); the set is too small and not Vietnamese, so it does not validate financial-scan OCR. Compact artifacts record Tesseract/model hashes and explicit text/table PSM and render scale. The [table PSM 6 financial-page run](../../artifacts/evaluation/ocr/tuning/vinamilk-document-extraction-compact-table-psm6-20260928.json) is a two-page synthetic-scan diagnostic, not a production accuracy claim. OCR v4 adds two manually labeled image-only governance scans with paired EasyOCR/Tesseract CER/WER; no cell/layout scores exist yet. Broad-format extraction, invoices, figure-caption and metadata labels remain absent. PDF formula recognition is now an opt-in Paddle adapter path covered by a mock; real formula-label accuracy is still unevaluated. | Reproduce paired runs with `uv run python scripts/processing/evaluate_document_extraction.py --compact --tesseract-psm 3 --output artifacts/evaluation/ocr/tuning/vinamilk-document-extraction-compact-psm3-20260928.json` and the equivalent PSM 11 command; compare table settings with `--tesseract-psm 3 --tesseract-table-psm 6`; scan comparison artifacts are [`PSM 11`](../../artifacts/evaluation/ocr/tuning/vinamilk-scan-document-processor-psm11-v6-20260928.json) and [`PSM 3`](../../artifacts/evaluation/ocr/tuning/vinamilk-scan-document-processor-psm3-v6-20260928.json). Expand reviewed Vietnamese scans before choosing page/domain-specific OCR settings. |
| Generation and grounded QA | Labeled answerable and unanswerable cases across finance/product/sustainability plus role-denial controls | Faithfulness, answer relevancy, context precision, hallucination rate, source/fact accuracy, abstention and citation coverage | The live authenticated `/api/ask` suite passed 5/5 route/source/fact/RBAC smoke checks (mean 26.405 s), with separate post-guard Qwen3.8 checks for the employee return policy and FY2024 finance also passing 1/1 each. Unsupported-retention separately routed to Knowledge, abstained and cited no source. A six-case GPT-OSS full-suite rerun stopped after provider rate limits. Paired model reports use identical per-case context and prompt hashes and complete cited chunks. Expected fact-case accuracy is GPT-OSS-20B 3/4, Qwen3.8-27B 4/4, and GPT-OSS-120B 3/4; both GPT-OSS answers gave the 2024 revenue in the wrong magnitude. Mean literal expected-fact evidence support is 0.875/1.000/0.875; this is a deterministic proxy, not semantic entailment. The blinded packet has 15 responses across three models, but both reviewer files are still unrated (0/10 each), so human agreement and semantic QA are pending. The exact proposal LLM baselines are not represented by these provider proxies. | Complete two independent blinded reviews from `artifacts/evaluation/qa-review-packet-full-evidence.json`, import them with `scripts/agents/qa_human_review.py`, then report reviewer scores/agreement. |
| System performance and scalability | Same local runtime/corpus; warm-up then repeated requests at increasing concurrency and corpus sizes | Average/p50/p95 response time, retrieval latency, throughput, error rate, CPU/RAM/VRAM and scaling curve | The in-process ASGI run completed 70/70 requests across concurrency 1/2/4 at 0.430/0.804/1.441 req/s, p95 4.53/4.11/4.92 s. A localhost HTTP run through the active Uvicorn server also completed 70/70: 0.463/0.831/1.648 req/s and p95 3.75/3.74/3.69 s (`vinamilk-api-load-http-localhost-20260927.json`). A 35-request route-detail run had zero failures; at concurrency 4 (6–7 samples/route), mean latency was 3.64 s for analytics, 3.35 s for dashboard, and 2.42 ms for health (`vinamilk-api-load-http-route-details-20260927.json`). Before connection limiting, an 80-request concurrency-16 run returned one analytics 503; captured Uvicorn logs proved Supavisor rejected session 16 (`EMAXCONNSESSION`, pool size 15). The app now bounds all repository connections to 10 per process and queues requests; a post-change loopback run passed 80/80 at concurrency 16 (3.784 req/s, aggregate p95 7.058 s; analytics p95 7.323 s). This validates the failure fix under this local workload, not a capacity threshold. The artifact records 145.6 MiB client-process peak RSS; server/DB resource telemetry and GPU telemetry are unavailable. | `uv run python scripts/operations/evaluate_api_load.py` for ASGI or add `--base-url http://127.0.0.1:8000` for a running server; continue with repeated controlled runs, server/database resource telemetry and larger corpus steps before capacity/scalability claims. See the [pre-fix](../../artifacts/evaluation/vinamilk-api-load-http-stress-20260928.json) and [bounded-connection run](../../artifacts/evaluation/vinamilk-api-load-http-bounded-20260928.json). |
| Optimization / reproducibility | Paired baseline vs one change at a time on the same cases and load; include fixed-vs-semantic/context-aware chunking, prompt and retrieval variants | Retrieval/generation quality delta plus latency/throughput/resource delta | Shared fixed and sentence-aware chunking is configurable. A five-year/five-question read-only dense diagnostic compares 1,912 live fixed chunks with 1,978 in-memory sentence-aware chunks: document MRR 1.0 for both (restricted candidate corpus), passage MRR 0.2715 vs 0.2648 and Recall@5 0.10 for both. Alternate passage labels use unreviewed trigram transfer, so this is preliminary and does not compare QA. A same-snapshot four-setting hybrid RRF sweep was added; default 1:2, k=60 had the best passage MRR/nDCG@5 among tested settings, while 2:1 restored document MRR to 1.0. A 12-query ontology-label rewrite comparison produced mixed, negligible retrieval changes; no production optimization is selected. Extractive query-term compression reached 0.3976 mean character ratio in the blind QA packet, but full fact coverage was only 6/15 both before and after, with repeated contexts; answer-quality and tokenizer-savings tests remain necessary ([artifact](../../artifacts/evaluation/vinamilk-context-compression-20260928.json)). A 60-second response cache is implemented and integration-smoke-tested, but retrieval remains on cache hits; provider latency and load savings are unmeasured. Prompt comparison, embedding optimization, cache load testing and GPU acceleration remain open. Docker/CI is verified by [run 36423572195](https://github.com/Lenhan231/enterprise-knowledge-ai-agent/actions/runs/36423572195), including the authenticated HTTP/WebSocket Nginx smoke; Render/Vercel hosting is out of scope. | Independently review/expand queries and passage labels, then compare compression with model answers on paired contexts before activation; evaluate remaining optimizations one at a time. Continue paired optimization experiments on reproducible local inputs. See the [query rewrite run](../../artifacts/evaluation/vinamilk-query-rewriting-metric-labels-20260928.json). |
| Business cases / agents | Twelve proposal cases: knowledge management, internal search, HR, contracts, financial reports, invoices, manufacturing, customer service, technical docs, compliance, executive decisions and business intelligence analytics | Per-case success, grounded answer/citations, correct route/tool, access-denial behavior, latency and human usefulness | `scripts/agents/evaluate_agent_routes.py` latest full run scored effective routing 12/12, but only 2 cases used direct model classification and 10 used correct deterministic fallback after `RateLimitError`. A separate no-fallback run directly classified financial report, executive report and BI analytics 3/3. Artifacts: [current 12-case run](../../artifacts/evaluation/proposal-business-route-current-12-20260928.json), [direct three-case run](../../artifacts/evaluation/proposal-business-route-current-three-20260928.json), [earlier 12-case run](../../artifacts/evaluation/proposal-business-route-evaluation.json), [direct BI recheck](../../artifacts/evaluation/proposal-business-route-analytics-recheck.json), and [pre-prompt run](../../artifacts/evaluation/proposal-business-route-evaluation-pre-prompt.json). Dashboard has no label in these twelve cases. Routing scores do not establish agent execution or answer quality; private HR, contracts, invoices, manufacturing and customer-service source evidence is absent. | Add authorized domain documents and grounded tasks; add reviewed dashboard cases and evaluate tool/task completion, answer quality and denials by role. |
| Agent workflow and monitoring | Representative routed QA, analytics, report, dashboard and failure cases | Route accuracy, tool success, task completion, trace completeness, latency/errors | LangGraph route wiring and authenticated QA are implemented. Live `/api/ask` evaluation passes five supported source/fact/route/RBAC smoke cases with mean latency 26.405 s (`artifacts/evaluation/vinamilk-app-qa-suite.json`); a separate live unsupported-retention case correctly abstains with no citation. A current 12-case route run scores 12/12, though ten classifications used deterministic fallback after provider limits; a separate direct run classifies finance/report, executive/report and BI/analytics 3/3. These route reports use stubs. Authenticated Qwen3.8 case batches now pass invoice/manufacturing 2/2, customer-service/technical 2/2, compliance 1/1 and BI 1/1; employee access, HR and abstention cases have separate evidence. The executive 500 caused by an unnecessary SQL call is fixed and covered by an app-wiring regression. A fresh executive run reached report generation but cited a relevant 2025 sustainability report omitted from the old gold-source list and stated inferred risks as report conclusions. Gold labels now include that official source, and the report prompt distinguishes documented initiatives from unsupported alternatives/risks; the post-change authenticated rerun hit HTTP 429, so no passing answer is claimed. The financial business case remains unscored. The QA run caught a text/integer fiscal-year mismatch in document analytics; the role-filtered CTE now normalizes valid years safely. SQL allowlist/read-only behavior has unit tests; live role-filtered SQL returns expected results. A fresh five-account read-only API matrix returns 3 employee-visible documents (analytics 403), 7 finance documents, 11 sustainability documents, 26 admin documents, and zero visible documents for the uploader while upload capability is enabled; see the [live dashboard/RBAC artifact](../../artifacts/evaluation/vinamilk-dashboard-rbac-live-api-20260928.json). This public-corpus check does not establish private-document isolation or rendered-browser behavior. Authenticated WebSocket QA, bounded SQL generation and admin monitoring are implemented. Browser verification covered analyst login, database-backed dashboard, dynamic filters, cited business question, and admin processing/access/monitoring screens. Live uploader-authenticated XLSX was read back from PostgreSQL and private Storage. A second live smoke injected embedding initialization failure after parsing newline-terminated TXT, retried the saved chunk, verified document `ready`/parsed `embedded`/one vector, and confirmed BM25 returned it to `finance_analyst` but not `employee`; both fixtures were removed and cleanup verified. Hosted CI now also verifies authenticated WebSocket behavior through Docker/Nginx. Human answer-quality scoring and full agent task completion remain. | Expand live upload/retry/RBAC checks to representative real files; rerun the rate-limited cases after provider quota reset; expand human-reviewed QA by role/domain and verify repeatable local proxy flows. |


## Proposal acceptance checklist

This is the concise completion view; measured values and methodology stay in
the matrix above and linked technical notes. `Partial` means implementation
or limited evidence exists, but the proposal's acceptance condition is not met.

### Five baseline benchmark groups

| Group      | Required comparison                       | Status  | Acceptance gap                                                                                                                                                                                                                                                                                                                              |
| ---------- | ----------------------------------------- | ------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| OCR        | PaddleOCR, EasyOCR, Surya (Tesseract baseline) | Partial | V7 paired comparison uses ten identical hash-matched regions at 180 DPI: Paddle/Easy/Surya/Tesseract PSM 3/11 micro-CER 0.043609/0.110025/0.043233/0.272556/0.127318 and micro-WER 0.108484/0.248261/0.090403/0.263561/0.197497. Surya (T4 GPU) has the lowest text error and exact row recall 14/16; Paddle (CPU) gets 0/16 rows; EasyOCR and Surya each detect 47/48 cell strings. Six English physical scans (four added in v7) and one born-digital table remain in the main set. A separate one-page six-engine 2011 Vietnamese scan comparison and a three-page production-parser run are third-party sourced and non-selective; the latter matches 17/17 selected rows, 34/34 numeric cells, 6/6 period headers and 20/20 visually checked balance-sheet value-cell boxes. These coordinates were located from the PDF text layer and visually checked, not independently click-annotated; broader coordinate coverage remains absent, and throughput spans CPU/T4 devices. Supplemental table-path evidence: the 2011 scan reaches 14/14 reviewed numeric cells with 180 DPI table-only rendering; the official 2024 balance-sheet page preserves two side-by-side tables and 3/3 normalized anchors (2/3 exact) on raster PDF and image input. At 180 DPI, ordered amount-cell pairs score 2/2 on the 2021 raster PDF (1/2 image), 0/2 on the 2022 PDF (1/2 image), and 0/2 on 2023 PDF/image; full label-plus-value anchors remain missed on 2021–23. See the paired [108 DPI](../../artifacts/evaluation/ocr/tuning/vinamilk-document-extraction-table-render-sweep-108dpi-20260929.json) and [180 DPI](../../artifacts/evaluation/ocr/tuning/vinamilk-document-extraction-table-render-sweep-180dpi-20260929.json) reports. See the [three-page production-parser run](../../artifacts/evaluation/ocr/pipeline/vinamilk-scan-document-processor-2011-three-pages-v2-20260929.json), [v2 labels](../../data/evaluation/ocr/archive/2011-scan/vinamilk_ocr_ground_truth_2011_scan_diagnostic_v2.json), and [supplemental comparison](../../artifacts/evaluation/ocr/comparisons/vinamilk-ocr-2011-scan-diagnostic/paired-comparison.json), [v7 comparison](../../artifacts/evaluation/ocr/comparisons/vinamilk-ocr-v7-five-configuration-comparison-20260928.json), [raw outputs](../../artifacts/evaluation/ocr/comparisons/vinamilk-ocr-v7/) and [v7 references](../../data/evaluation/ocr/archive/vinamilk_ocr_ground_truth_v7.json). Paired CPU-only v9 adds 14 hash-matched English/Vietnamese regions: micro-CER 0.361902/0.073542/0.198645/0.074924 and WER 0.491573/0.181882/0.337430/0.116573 for Tesseract/Paddle/Easy/Surya; Paddle leads CER, Surya WER and exact rows (16/33). CPU model was unavailable; labels remain diagnostic. See the [comparison](../../artifacts/evaluation/ocr/comparisons/vinamilk-ocr-v9-cpu-four-engine-comparison-20260929.json). The v4 processor replay covers three pages: 17/17 rows, 34/34 values, 33/34 cell locations at IoU >= 0.3. Fourteen income-statement boxes are raster-derived; 20 balance-sheet boxes still use text-layer-assisted placement. This is one source packet and one reviewer, so broader independent scan labels remain necessary. See the [processor report](../../artifacts/evaluation/ocr/pipeline/vinamilk-scan-document-processor-2011-v4-coordinate-evaluation-20260929.json) and [v4 labels](../../data/evaluation/ocr/tuning/vinamilk_ocr_ground_truth_2011_scan_diagnostic_v4.json). |
| Embeddings | BAAI BGE-M3, Qwen3 Embedding, e5-large-v2 | Full-corpus coverage verified; model selection preliminary | The hash-verified audit replays the public 4,750-row corpus with the reported 1,000-per-document cap and the exact twelve-case file; all corpus, sampled-corpus and case hashes match all three Tesla T4 reports. No document exceeds 452 chunks, so the cap selects every row. BGE/Qwen/e5 document MRR is 0.7759/0.8028/0.7583; Recall@5 is 0.9167 each and nDCG@5 0.8041/0.8239/0.7917. The raw `sample_strategy=evenly spaced passages` and limitation text are stale and remain flagged in the audit artifact. Twelve document-level labels are sparse and there are no passage judgments; expand independently reviewed queries/labels before selecting a model. See the [hash-verified audit](../../artifacts/evaluation/vinamilk-embedding-three-model-full-corpus-hash-verified-20260928.json) and [original summary](../../artifacts/evaluation/vinamilk-embedding-three-model-full-corpus-t4-20260927.json). |
| LLMs       | Qwen3, Llama 3, GPT                       | Partial | Current paired results use explicitly labeled proxies, not exact requested checkpoints; collect blinded semantic-quality ratings and exact models where accessible.                                                                                                                                                                         |
| Retrieval  | Dense, BM25, hybrid, parent-document      | Partial | Four methods have a refreshed 12-query run on the 25-document corpus; selected passage labels remain sparse and need independent review and expansion.                                                                                                                                                                                      |
| Rerankers  | BGE Reranker, Qwen Reranker               | Partial | Paired Tesla T4 top-30 reports now use identical candidates for 12 cases; passage/document MRR BGE 0.5167/0.8958 and Qwen 0.4348/0.9583. Sparse labels prevent model selection; downstream QA and expanded independent judgments remain. See the [paired report](../../artifacts/evaluation/vinamilk-reranker-kaggle-top30-paired-20260928.json). |

### Evaluation and optimization beyond the five groups

| Requirement | Status | Evidence / remaining acceptance work |
| --- | --- | --- |
| Financial dashboard extraction | Partial | Parser/layout and finance-keyword ranking selects at most 10 pages/report; strict page-grounded JSON validation and provenance feed admin review. On the real Vinamilk 2024 report, a no-write three-page run returned no metrics on PDF 15, accepted three metrics from PDF 48 and two from PDF 92; one proposed metric on each later page was rejected because its quote/label/value/year did not validate. A repeat after the selector change hit Groq rate limits on PDF 15, so the accepted values have not been rechecked against reviewed anchors. Fresh authenticated API read on 2026-09-28: seven verified observations and 29 pending candidates. A read-only verifier matched all seven published values to their cited official PDF pages for label, year, amount and unit; it records source PDF and page-text hashes in the [audit artifact](../../artifacts/evaluation/verified-financial-metric-source-audit.json). The earlier [analytics/RBAC smoke](../../artifacts/evaluation/vinamilk-live-analytics-rbac-smoke-20260928.json) is an older snapshot (5/31 counts) and its metric counts are superseded. Parser-only reruns saved nine FY2021 and 18 FY2022–24 candidates. Comparative table headers now select current-year values for the real FY2021, FY2023 and FY2024 statements; ambiguous source labels and a FY2022 domestic-segment gross-profit figure are excluded. The FY2021 page-10 total consolidated revenue candidate is 61,012 billion VND, with its comparative row preserved in the source quote; it remains `needs_review`. The 2022–24 dry-run artifact records the remaining candidates and period/source quotes. No dashboard KPI was published by these parser runs. See the [FY2021 parser artifact](../../artifacts/evaluation/vinamilk-financial-candidates-2021-column-aligned-20260928.json) and the [FY2022–24 parser artifact](../../artifacts/evaluation/vinamilk-financial-candidates-2022-2024-column-aligned-20260928.json). The upload integration test uses a fake provider and verifies candidate persistence/review gating, not provider quality. | Review each candidate against the cited source page, year, metric scope, amount and unit before publication. Run `uv run python scripts/analytics/audit_verified_financial_metrics.py` to recheck already published values without changing Admin review state. After provider quota resets, rerun a no-write shortlist extraction and validate LLM suggestions before saving them for review. Continue to publish only admin-verified rows. |
| Document preparation and understanding | Partial | The latest read-only manifest-to-database audit finds zero mismatches across 364 document metadata fields and 52,283 chunk metadata fields for all 26 ready documents (4,753 chunks). This validates propagation of curated metadata, not automatic extraction accuracy. PDF/Office/image parsing and narrow financial/table anchors are checked; reviewed scan OCR, metadata-extraction, cleaning, table-cell, figure/caption, invoice and formula labels across formats remain. Artifact: [2026-09-28 metadata audit](../../artifacts/evaluation/vinamilk-corpus-metadata-audit-access-policy-20260928.json). |
| Retrieval quality | Partial | Recall@K, Precision@K, MRR and nDCG are implemented/reported; selected labels remain small and non-exhaustive. |
| Generation quality | Partial | Source/fact/citation and abstention checks run through the authenticated app; faithfulness, answer relevancy, hallucination and reviewer agreement need blinded human scoring. |
| System performance | Partial | Local ASGI/HTTP tests cover concurrency 1/2/4 and 16. Captured the pre-fix cause (Supavisor session pool cap 15), added a 10-connection per-process queue, and verified 80/80 requests at concurrency 16 after the change. Server/database telemetry, repeated controlled load, GPU utilization and corpus/concurrency scaling remain unmeasured. See the [bounded-connection run](../../artifacts/evaluation/vinamilk-api-load-http-bounded-20260928.json). |
| Chunking and prompt optimization | Partial | Fixed vs sentence-aware retrieval and prompt regressions have diagnostics; expand paired cases and measure answer quality. |
| Hybrid retrieval tuning | Partial | Four RRF settings were paired over the same 9 queries and current corpus snapshot. The existing 1:2, k=60 setting led passage MRR/nDCG@5; 2:1 led document metrics. This is too small/non-exhaustive for selection; artifact: [hybrid weight sweep](../../artifacts/evaluation/vinamilk-hybrid-weight-sweep-20260927.json). |
| Query rewriting, context compression, embedding optimization, response caching, GPU acceleration | Partial | A paired read-only query-rewrite experiment compares raw and ontology-expanded queries on the same 12 queries, role filters, case hash and DB snapshot; only 4/12 changed. Document metrics were unchanged (MRR 0.9444, Recall@5 1.0000); passage MRR rose 0.4277→0.4356 while nDCG@5 fell 0.3529→0.3494, so expansion remains evaluation-only. Mean latency was 1,343.65 vs 1,349.71 ms. See [rewrite artifact](../../artifacts/evaluation/vinamilk-query-rewriting-metric-labels-20260928.json). An extractive sentence-selection diagnostic on the blind QA packet reduced source text to a mean 0.3976 character ratio. In 15 responses/five unique questions, the number with all expected fact groups present was 6 before and 6 after; baseline fact-coverage indicators were unchanged in 15/15. This does not establish answer quality or tokenizer savings, and the repeated contexts are not independent. See [compression artifact](../../artifacts/evaluation/vinamilk-context-compression-20260928.json) and [`evaluate_context_compression.py`](../../scripts/agents/evaluate_context_compression.py). The authenticated `/api/ask` cache smoke confirms two identical cited answers with one answer-generation call; retrieval and embedding still execute on hits, so recorded 25.30/11.46 s is not provider savings. See [cache artifact](../../artifacts/evaluation/vinamilk-response-cache-api-smoke-20260928.json). Lazy-loading the local backend preserves the same hosted vector and cuts its one-query isolated peak RSS from 576.2 to 76.7 MiB; the live authenticated analyst ask returned HTTP 200 with one citation at 185,012 KiB Uvicorn high-water RSS. This remains a single-query resource smoke, not a concurrent-load benchmark ([artifact](../../artifacts/evaluation/vinamilk-embedding-hosted-lazy-import-20260928.json)). Context-compression answer-quality evaluation, broader embedding quality/load tests, cache load testing, GPU acceleration remain open; Render/Vercel deployment experiments are out of scope and instruction tuning is optional. |
| Twelve proposal business cases and agent task completion | Partial | The current 26-document audit classifies 2 tasks supported, 6 partial and 4 unsupported. Earlier authenticated case batches pass enterprise-management abstention, HR scope-limited answer, contract abstention, invoice, manufacturing abstention, customer-service policy, technical-doc abstention and compliance; those JSON artifacts omit model provenance and must not be used for model-specific scores. A current [`GPT-OSS-20B BI run`](../../artifacts/evaluation/proposal-business-app-gptoss20b-bi-provenance-20260928.json) passes route, dynamic domain-count result shape and source-citation checks. The BI scorer accepts `doc_count` and `document_count` aliases while requiring every row's evidence IDs to match citations. Focused Qwen3.8 employee-access, customer-service and finance QA artifacts record the model explicitly; the older business batch's employee case used a stale unsupported coverage label. The financial case targets headline consolidated revenue and profit after tax through the unit-guarded Report agent; the authenticated GPT-OSS-20B run passes 1/1 for facts, source page, route and citation integrity ([artifact](../../artifacts/evaluation/proposal-business-app-financial-report-guarded-rerun3-20260929.json)). ReportAgent now makes one evidence-bounded repair attempt when a draft omits citations or changes cited values/units, then still withholds any draft that fails validation. The executive case passes 1/1 with a grounded distinction between reported initiatives and unreported decision alternatives; its scorer rejects claims that initiatives were options considered by leadership ([artifact](../../artifacts/evaluation/proposal-business-app-executive-report-guarded-rerun5-20260929.json)). The employee access case now declares `actor_role=employee`; its authenticated viewer-account replay passes 1/1 with exact Code of Conduct page citations and a policy-absence disclosure. The answer uses a guarded source-extraction path after retrieval. The pre-fix 12-case run stopped after 3 attempts; a later role-aware full attempt hit provider rate limiting on its first case (11 unrun; [artifact](../../artifacts/evaluation/proposal-business-app-role-aware-full-rerun-20260929.json)). No blinded human usefulness review exists. |

### Application, local runtime, and deliverables

| Requirement | Status | Evidence / remaining acceptance work |
| --- | --- | --- |
| Document upload, knowledge search, grounded QA, analytics/dashboard, report and multi-agent UI/API | Partial | Core authenticated flows and selected browser/live DB paths work; add repeatable demo acceptance through proxy and source-backed business tasks. |
| Authentication, document RBAC, secure PostgreSQL/pgvector | Partial | Server-side role filters, SQL constraints and selected live role checks exist; validate the full role matrix with representative restricted documents and clean migration/bootstrap setup. |
| Local Docker, Nginx, WebSocket and CI path | Verified for prototype | [Hosted CI run 36423572195](https://github.com/Lenhan231/enterprise-knowledge-ai-agent/actions/runs/36423572195) passed the full tests, Compose validation, image build, `nginx -t`, and authenticated HTTP/WebSocket smoke through Docker/Nginx. Render/Vercel hosting is out of scope; it is not an acceptance gap. |
| Monitoring / experiment infrastructure | Partial | Privacy-minimized agent events and admin console exist; proposal-listed LangSmith, MLflow, Prometheus and Grafana are not integrated. |
| Technical documentation, user manual, local setup guide, demo, research report | Partial | Drafts and setup flows exist; independent operator walkthrough, reproducible local demo, and final evidence-complete report remain. |

## Corpus metadata audit

`uv run python scripts/analytics/evaluate_corpus_metadata.py` compares exact manifest
metadata with persisted document rows and every chunk for ready manifest
sources. The historical 2026-09-27 run checked 25 ready documents with zero
mismatches. The latest 2026-09-28 read-only run checks all 26 ready documents,
364 document fields and 52,283 chunk fields across 4,753 chunks with zero
mismatches; no manifest document is missing or not ready. This
catches propagation defects such as missing HTML language/source/type tags;
the four local HTML sources were re-ingested after such mismatches were found.
The audit measures manifest propagation, not automatic metadata extraction
quality, content cleaning, or metadata correctness against the original source.
Its manifest/source hashes and per-document coverage are in
`artifacts/evaluation/vinamilk-corpus-metadata-audit-access-policy-20260928.json`.

## Benchmark protocol and proposal cross-check

The five comparison groups above are exactly the proposal's baseline list:
PaddleOCR/EasyOCR/Surya OCR; BAAI BGE-M3/Qwen3 Embedding/e5-large-v2;
Qwen3/Llama 3/GPT; dense/BM25/hybrid/parent-document retrieval; and BGE/Qwen
rerankers. Rows marked smoke or partial have runnable code or limited artifacts,
not final comparative evidence. In particular, do not rename an available proxy
as the requested model family or treat a failed model load as a score.

Proposal traceability beyond the five comparison groups is in
[`docs/README.md`](../README.md): requirements are grouped by pipeline,
application, security, evaluation, local reproducibility and deliverables. The proposal's
named quality measures are kept explicit here: retrieval Recall@K,
Precision@K, MRR and nDCG; generation faithfulness, answer relevancy, context
precision and hallucination; system average response time, throughput,
retrieval latency, GPU utilization and scalability. Missing labels, unavailable
hardware or external hosting are recorded as out of scope rather than inferred
successes.

The proposal also calls for evaluations outside those five groups. The matrix
tracks OCR/layout and extraction quality, grounded generation, system
performance and scalability, controlled optimization, business-case
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
- **Local reproducibility and deliverables:** validate Docker/Nginx/WebSocket and
  CI; document the prototype monitoring approach; finish the user manual, local
  setup guide, demo flows and research report with measured evidence.
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
the comparison artifact. `scripts/operations/evaluate_api_load.py` measures `/health`,
`/api/dashboard` and `/api/analytics` through an in-process ASGI transport
against the configured database. The repeated 2026-09-27 local-date run
completed 70/70 requests (10 per worker at concurrency 1/2/4), all HTTP 200.
Throughput was 0.430, 0.804 and 1.441 requests/s; p95 latency was 4.53, 4.11
and 4.92 seconds, respectively. The earlier 21-request smoke measured 0.372,
0.803 and 1.465 requests/s, showing similar throughput at these light levels.
Both are single-host ASGI checks, not representative scalability evidence. They exclude document processing and LLM generation. The host has no
CUDA GPU, so utilization is unavailable. The repeated artifact is
`artifacts/evaluation/vinamilk-api-load-repeat10.json`; the original smoke is
preserved separately. Expand local concurrency and corpus sizes before capacity
claims.
Query rewriting, response caching and GPU acceleration are proposal
optimization candidates, not implemented/evaluated claims.

Current labeled data: `data/evaluation/archive/retrieval/vinamilk_retrieval_cases.json` has twelve
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
uv run python scripts/retrieval/evaluate_rerankers.py --model bge-reranker-v2-m3 --device cuda --candidate-k 30 --batch-size 8 --output artifacts/evaluation/vinamilk-reranker-bge-top30.json
uv run python scripts/retrieval/evaluate_rerankers.py --model qwen3-reranker-0.6b --device cuda --candidate-k 30 --batch-size 8 --output artifacts/evaluation/vinamilk-reranker-qwen-top30.json
```

For CPU, start with `--case-ids finance-revenue-profit-2024-vi` and a small
batch/sequence length pilot, note its `peak_rss_mb` and current available RAM,
then set `--max-memory-mb` to the measured peak plus headroom on the full run.
The runner checks that budget against currently available RAM before model
loading. It does not invent a model memory estimate; pilot measurements remain
specific to the model, sequence length, batch size, process and host. The
earlier 2026-09-27 BGE full-depth artifact is
`artifacts/evaluation/vinamilk-reranker-bge-top30-passage-cpu.json`: at
candidate-k 30, sequence length 256 and batch 2, passage MRR improved by
0.031 while document MRR declined by 0.083. Peak RSS was 2,820 MiB, mean
rerank time 29.67 seconds/query, and current swap was nearly exhausted after
the run. A fresh sequence-256/batch-2 CPU pilot exceeded two minutes on one
query without a score; the later paired Tesla T4 top-30 comparison is recorded
below and must not be conflated with this earlier CPU attempt.

### Embedding model comparison

Run one model per process to keep peak-memory readings attributable and avoid
mixing the candidate vector dimensions with the app's fixed `vector(384)`:

```bash
uv run python scripts/retrieval/evaluate_embeddings.py --model bge-m3 --max-chunks-per-document 3
uv run python scripts/retrieval/evaluate_embeddings.py --model qwen3-embedding --max-chunks-per-document 3
uv run python scripts/retrieval/evaluate_embeddings.py --model e5-large-v2 --max-chunks-per-document 3
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
uv run python scripts/retrieval/evaluate_rerankers.py --model bge-reranker-v2-m3
uv run python scripts/retrieval/evaluate_rerankers.py --model qwen3-reranker-0.6b
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
measure downstream answer quality. The paired full-depth GPU run is now
available; see the results below. Expand independently reviewed judgments.

To run the full-depth pair without sending credentials or private uploads to a
notebook, export the current role-filtered public candidates once:

```bash
uv run python scripts/retrieval/evaluate_rerankers.py \
  --export-candidates artifacts/evaluation/vinamilk-reranker-candidates-top30-20260928.json \
  --candidate-k 30
```

The bundle freezes the 12 query/candidate sets, labels, and their SHA-256. The
`--candidate-input` mode checks the label hash, candidate hash, case IDs, roles,
and passage IDs before loading either reranker; it does not connect to the
database. The paired Kaggle runner is
[`notebooks/kaggle_reranker_benchmark/kaggle_reranker_benchmark.ipynb`](../../notebooks/kaggle_reranker_benchmark/kaggle_reranker_benchmark.ipynb)
and uses a private dataset containing only this role-filtered public-source
bundle and the minimal evaluator. Do not interpret the run as complete until
both CUDA reports have the same candidate and case hashes and are saved under
`artifacts/evaluation/`.

The completed paired run is summarized in
[`vinamilk-reranker-kaggle-top30-paired-20260928.json`](../../artifacts/evaluation/vinamilk-reranker-kaggle-top30-paired-20260928.json).
It confirms the same 12 cases, candidate SHA-256
`521a56b77485b67b5082d93263dcdb148480a2f20d393473bc1bb3f061a9ad1d`, max
sequence length 256, Python 3.12.13 and Tesla T4 CUDA environment. BGE v2 m3
scores passage MRR 0.5167 and document MRR 0.8958 at 1.1736 s/query; Qwen3
Reranker 0.6B scores 0.4348 and 0.9583 at 2.7415 s/query. Dense passage MRR
was 0.4117 for both. These 12 selected, non-exhaustive passage labels make
this a preliminary paired ranking result, not a model-selection or answer
quality result. Retrieval time was measured before candidate export on the
source host and is excluded from the model latency comparison. The raw reports
and model revisions are retained under
`artifacts/evaluation/kaggle-reranker-output/reranker-results/`.

The current five-case answer run is `artifacts/evaluation/vinamilk-qa-current-smoke.json` (2026-09-26): 5/5 expected-source, expected-fact and RBAC checks passed. The two earlier model smoke runs in `artifacts/evaluation/vinamilk-qa-smoke.json` and
`artifacts/evaluation/vinamilk-qa-qwen3.8-smoke.json` each passed 5/5
expected-source, selected-fact and denial checks. Each checks four answerable
cases plus one employee denial; key-fact and source/refusal accuracy were 1.0
for both. This is a hand-picked smoke set, not an automated faithfulness or
hallucination score. Per-case human-review fields are intentionally blank.
