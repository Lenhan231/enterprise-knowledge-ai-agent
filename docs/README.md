# Proposal coverage and technical guide

This page tracks the capstone proposal against the current prototype. A row is
complete only when the linked implementation and evidence cover the stated
requirement; a passing unit test alone does not establish end-to-end coverage.
Use the technical notes below for current settings and data flow.

**Latest OCR result (v9 CPU-paired):** all four engines were rerun on 14 reviewed
regions from six PDFs at 180 DPI. The reports share the exact v9 dataset SHA
and all 14 rendered-image hashes; each processed 14/14 pages without errors.
Tesseract/PaddleOCR/EasyOCR/Surya micro-CER is
0.361902/0.073542/0.198645/0.074924 and micro-WER is
0.491573/0.181882/0.337430/0.116573. Exact table rows are 15/33, 0/33, 10/33
and 16/33; cell-text presence is 97/99, 66/99, 96/99 and 98/99. Paddle has
the lowest CER; Surya has the lowest WER and highest row recall. These labels
mix manual transcription with visually checked PDF-text-layer assistance, and
row/cell text scores do not measure spatial reconstruction. All runs used
Kaggle CPU kernels with four logical CPUs; the CPU model was not exposed, so
throughput is exploratory. The set is diagnostic, not model-selection evidence.
See the [CPU-paired comparison](../artifacts/evaluation/ocr/comparisons/vinamilk-ocr-v9-cpu-four-engine-comparison-20260929.json),
[raw reports](../artifacts/evaluation/ocr/comparisons/ocr-kaggle-v9-cpu/), [v9 labels](../data/evaluation/ocr/vinamilk_ocr_ground_truth_v9.json),
and the earlier [cached cross-layout rescore](../artifacts/evaluation/ocr/comparisons/vinamilk-ocr-v9-four-engine-comparison-20260929.json).
**Supplemental real Vietnamese scan (2011 CafeF capture, v2):** a corrected
bounded income-statement crop was run through all four engines on identical
dataset/source/render hashes. Tesseract/PaddleOCR/EasyOCR/Surya CER is
0.171683/0.279070/0.511628/0.493160 and WER is
0.288462/0.475275/0.659341/0.678571. They matched 1/7, 0/7, 4/7, and 0/7
ordered label/value rows and 14/21, 14/21, 19/21, and 17/21 selected cell
strings. Tesseract/Paddle ran on CPU; Easy/Surya ran on a Tesla T4, so runtime
is not directly comparable. These labels were adapted from a duplicate capture
and visually checked, not independently double-entered; this remains one
third-party scan of one filing and cannot select a production engine. The v1
full-page scores are superseded: its reference covered only part of the page
and contained mismatched prior-year figures. See the [v2 comparison](../artifacts/evaluation/ocr/comparisons/vinamilk-ocr-2011-cafef-scan-v2-four-engine-comparison-20260929.json),
[labels](../data/evaluation/ocr/vinamilk_ocr_2011_cafef_scan_v2.json), and
[raw reports](../artifacts/evaluation/ocr/comparisons/ocr-kaggle-vinamilk-2011-cafef-scan-v2/).
The row metric now requires label and value strings in sequence while
permitting intervening code/note columns; it does not measure spatial row or
column assignment, and historical counts use the older contiguous-text rule.
The separate [upload-parser
replay](../artifacts/evaluation/ocr/pipeline/vinamilk-upload-document-processor-v9-14regions-20260929.json)
measures table reconstruction and OCR-only behavior; its 2024 born-digital
table was rasterized and missed, so it does not measure native-PDF extraction.
A follow-up v4 scan check adds 14 raster-derived value-cell boxes for seven
rows on the 2011 income statement; the 20 balance-sheet boxes remain the older
visually checked, text-layer-derived labels. Across all three pages, the upload
parser matched 17/17 rows and 34/34 values, with 33/34 cell boxes at IoU >= 0.3.
The one miss is the small 2011 dash, for which the parser returned no useful
location. This is still a single-reviewer, one-source diagnostic. See the
[v4 labels](../data/evaluation/ocr/tuning/vinamilk_ocr_ground_truth_2011_scan_diagnostic_v4.json)
and [full processor report](../artifacts/evaluation/ocr/pipeline/vinamilk-scan-document-processor-2011-v4-coordinate-evaluation-20260929.json).

The v8 labels were also replayed through the local upload parser (PSM 11,
108 DPI): micro-CER/WER 0.055009/0.175768. This is a separate parser-path
diagnostic, not a Kaggle engine comparison. It exposed and fixed a native-text
balance-sheet table that upload parsing had left unstructured; see the
[processing guide](technical/document-processing.md) and
[replay artifact](../artifacts/evaluation/vinamilk-upload-processor-v8-20260929.json).
The annual-report diagnostic also carries parser outputs through KPI candidate
extraction: 11/11 reviewed fields matched on native PDF text, versus 3/11 on
synthetic raster-PDF OCR and 2/11 on raster-image OCR. These are born-digital
pages rendered as synthetic scans, not real scanned reports. See the
[OCR-to-KPI artifact](../artifacts/evaluation/ocr/pipeline/vinamilk-document-extraction-ocr-to-kpi-20260929.json).
A no-write OCR-to-LLM run on the reviewed 2023 income statement had four
suggested metrics, two accepted by verbatim-source validation, and one of two
reviewed targets matched. Revenue remained unrecovered because OCR corrupted
its label. Reproduce with the documented `--llm --case-id` command; its result
is in the [LLM artifact](../artifacts/evaluation/ocr/pipeline/vinamilk-document-extraction-ocr-to-kpi-llm-20260929.json).
On the original real 2011 Vietnamese scan PDF, the LLM returned four
suggestions, two passed verbatim quote validation, and one matched a reviewed
target (profit after tax, with unit); revenue was not recovered. This is one
third-party source page and does not establish representative scan accuracy.
The run is in the [real-scan artifact](../artifacts/evaluation/ocr/comparisons/vinamilk-ocr-2011-real-scan-kpi-llm-20260929.json), reproducible with the documented `--cases ... --llm` command.

**Earlier OCR result (v7):** v7 pairs five settings on ten source/render-hash-matched
regions at 180 DPI. Micro-CER/WER for Tesseract PSM 3/11, EasyOCR, PaddleOCR
and Surya is 0.272556/0.263561, 0.127318/0.197497, 0.110025/0.248261,
0.043609/0.108484 and 0.043233/0.090403. Paddle ran on CPU; EasyOCR and
Surya used a Tesla T4, so throughput and memory are not controlled comparisons.
The sample contains six English physical-scan regions (four added in v7) and
one born-digital Vietnamese financial table. A separate 2011 Vietnamese
financial-scan diagnostic now covers three pages from one third-party packet:
Tesseract recovered 17/17 selected rows and 34/34 selected numeric cells, but
also matched 20/20 visually checked value-cell boxes across the two balance-
sheet pages. Version 2 had full text CER/WER (0.443667/0.582524) only for the
income-statement page; v3 adds full-page transcriptions for the two balance
sheets. The coordinate boxes come from the PDF text layer and
were visually checked, not independently click-annotated. A paired 180-DPI
four-engine run on the same three pages scored CER/WER 0.840715/1.126214 for
Tesseract PSM 3, 0.162611/0.330275 for PaddleOCR, 0.449397/0.540367 for
EasyOCR, and 0.166705/0.182569 for Surya after visually reviewing full-page
transcriptions for all three pages. Surya has the best WER and matched 51/51
selected cell strings; PaddleOCR has the best CER and EasyOCR matched the most
complete rows (9/17). The two balance-sheet transcriptions used PDF text as an
aid and were visually reviewed; this third-party packet still cannot select a
production engine. See the [rescored paired scan comparison](../artifacts/evaluation/ocr/comparisons/vinamilk-ocr-2011-v3-four-engine-comparison-20260929.json),
the [raw reports](../artifacts/evaluation/ocr/comparisons/ocr-kaggle-v2/), the
[v7 comparison](../artifacts/evaluation/ocr/comparisons/vinamilk-ocr-v7-five-configuration-comparison-20260928.json)
and [processing protocol](technical/document-processing.md#current-boundaries).

| Proposal requirement | Status | Evidence / remaining work |
| --- | --- | --- |
| Regression suite | Verified locally | `PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -q` passed 535 tests on 2026-10-01. This is repository regression coverage only; provider, visual, human-review and proposal evaluation gaps remain. |
| Enterprise document Q&A with grounded citations | Partial | [RAG and agents](technical/agents-and-evaluation.md); small live corpus and retrieval checks exist. Expand QA cases and evaluate answer quality. |
| PDF, Word, Excel, PowerPoint, scans and images | Partial | [Processing](technical/document-processing.md); PDF/DOCX/XLSX/PPTX/TXT/MD/images parse; DOCX tables and high-overlap PyMuPDF/Tesseract PDF tables become key/value retrieval chunks while structured review tables stay separately persisted. Low-overlap PDF tables are added without deleting source text. Live DOCX upload/Storage/table readback and a real three-page Vietnamese scanned-PDF upload both reached `ready`; the latter persisted 9 OCR chunks and 3 tables/58 rows, verified private-source SHA-256, allowed finance-analyst visibility and denied employee visibility, then cleaned up all rows and the Storage object ([scan upload artifact](../artifacts/evaluation/vinamilk-scan-upload-live-e2e-20260929.json)). Office ZIP expansion is bounded. Legacy XLS, broader real-file/layout coverage and user verification remain. |
| Layout, tables, figures, invoices, formulas, metadata | Partial | XLSX formulas and DOCX Office Math text runs are included in retrieval chunks with parser metadata; PDF tables persist as structured rows. Optional Paddle parsing now supports chart and formula recognition (`DOCUMENT_PADDLE_FORMULA_RECOGNITION=true` also enables layout) and retains returned text/LaTeX, page coordinates and labels. It remains off by default and has adapter-mock coverage only; real formula extraction and chart accuracy are unmeasured. Standalone image uploads and prominent embedded PDF raster figures now support opt-in Groq vision captions (up to three PDF figures per document), with generated-content provenance; source images are sent to Groq and no human quality review exists. PPTX figures, vector-only charts, paired real-scan/layout labels, formula accuracy/equation evaluation, invoices and representative multi-format quality evaluation remain. The latest [manifest metadata audit](../artifacts/evaluation/vinamilk-corpus-metadata-audit-access-policy-20260928.json) checks 26 ready sources (4,753 chunks, 52,283 chunk-field checks) with no metadata mismatches. The [multi-year extraction diagnostic](../artifacts/evaluation/ocr/pipeline/vinamilk-document-extraction-multiyear-v3-20260928.json) visually checks 11 financial anchors on five report pages: born-digital rule candidates match 11/11 with 1.00 precision; synthetic Tesseract raster conditions match exact text anchors 1/11 and normalized text/table anchors 3/11 each. It is a small diagnostic, not broad OCR accuracy evidence. |
| Semantic/context-aware chunking and parent-child retrieval | Partial | [Chunking](technical/chunking.md); seed-PDF and upload paths share configurable sentence/paragraph-aware chunks with a fixed-overlap baseline and tokenizer bound. Numbered OCR headings now produce `section_title`; exact-content metadata-only backfills updated 388 chunks across eight governance reports without changing vectors/ACL. The 25-document corpus now has 4,666/4,750 titled chunks; 84 remain null, while persisted section hierarchy and paired answer-quality evaluation remain open. After correcting the 2022 net-revenue reference to audited income-statement chunks, a five-year diagnostic has 1,912 fixed vectors and 1,979 alternate chunks: passage MRR 0.2615/0.2626. The case hash differs from older runs, and sentence labels remain heuristic, so this is not evidence of improvement. Seven annual/sustainability PDFs could not be safely backfilled because reparsed chunk counts differed. See the [corrected-label diagnostic](../artifacts/evaluation/vinamilk-chunking-retrieval-source-reviewed-20260928.json), [corpus coverage audit](../artifacts/evaluation/section-title-corpus-coverage-post-backfill-20260928.json), [2020–2024 governance apply audit](../artifacts/evaluation/section-title-backfill-governance-2020-2024-applied.json), [earlier scan audit](../artifacts/evaluation/section-title-backfill-governance-scans-applied.json), [native report audit](../artifacts/evaluation/section-title-backfill-cgr-2025-applied.json), and [annual/sustainability dry-run](../artifacts/evaluation/section-title-backfill-annual-sustainability-dry-run-20260928.json). |
| Five proposal benchmark groups | Partial | OCR has a same-CPU v9 four-engine run on 14 regions/six PDFs with matched dataset/render hashes; its mixed labels and CPU-only profile remain diagnostic, not model-selection evidence. A paired Kaggle run now covers one issuer-hosted, image-only Charter scan page: Tesseract/Paddle/Easy/Surya CER 0.0111/0.0029/0.0043/0.0180 and WER 0.0309/0.0077/0.0193/0.0521 on identical hashes. The single-annotator English reference is not independently reviewed, and CPU/GPU runtime is uncontrolled; Vietnamese physical-scan coverage remains limited to the 2011 packet. The prior v8/v7 results and scan labels remain linked in the technical matrix. A hash replay verifies the three Tesla T4 embedding reports covered all 4,750 chunks; BGE-M3/Qwen3/e5 document MRR is 0.7759/0.8028/0.7583. A paired Tesla T4 top-30 reranker run covers 12 identical cases/candidates. Exact proposal LLM checkpoints and blinded human answer-quality review remain incomplete. See [benchmark acceptance](technical/agents-and-evaluation.md#proposal-acceptance-checklist), [Charter scan comparison](../artifacts/evaluation/ocr/comparisons/vinamilk-ocr-charter-scan-page8-four-engine-comparison-20260929.json), [Charter scan labels](../data/evaluation/ocr/vinamilk_ocr_charter_scan_en_v1.json), [v9 CPU-paired OCR comparison](../artifacts/evaluation/ocr/comparisons/vinamilk-ocr-v9-cpu-four-engine-comparison-20260929.json), [v8 OCR comparison](../artifacts/evaluation/ocr/comparisons/vinamilk-ocr-v8-four-engine-comparison-20260929.json), [embedding audit](../artifacts/evaluation/vinamilk-embedding-three-model-full-corpus-hash-verified-20260928.json) and [paired reranker report](../artifacts/evaluation/vinamilk-reranker-kaggle-top30-paired-20260928.json). |
| Other proposal evaluation requirements | Partial | See the [acceptance checklist](technical/agents-and-evaluation.md#proposal-acceptance-checklist) for extraction, retrieval/generation quality, system performance, optimization and all 12 business cases. The authenticated app evaluator checks routes, citations, unsupported-case abstention, financial facts and dynamic BI result shape. Selected earlier business-case batches pass invoice/manufacturing (2/2), customer-service/technical (2/2), compliance (1/1), HR and abstention cases, but those artifacts omit the model ID and are not model-specific benchmark evidence. A current model-provenanced GPT-OSS-20B BI run passes 1/1 ([artifact](../artifacts/evaluation/proposal-business-app-gptoss20b-bi-provenance-20260928.json)). The role-aware proposal evaluator now logs in as the employee for `internal-document-search`; its authenticated rerun passes 1/1 after the Knowledge path quotes Code of Conduct access clauses and discloses that the retrieved text does not include the separately referenced Information System Policy ([employee run](../artifacts/evaluation/proposal-business-app-employee-access-rbac-rerun-20260929.json)). The full 12-case run is still incomplete: an earlier pre-fix pass stopped after 3 cases, and the role-aware full rerun was rate-limited on its first case ([latest attempt](../artifacts/evaluation/proposal-business-app-role-aware-full-rerun-20260929.json)). Earlier focused employee access, customer-service and finance QA artifacts record Qwen3.8 explicitly. The 2024 headline financial summary is routed through the guarded Report agent, with English retrieval augmented by the report's Vietnamese KPI labels. The authenticated GPT-OSS-20B rerun passed 1/1 with expected values, annual-report page 12, correct route and citation integrity ([financial QA](../artifacts/evaluation/proposal-business-app-financial-report-guarded-rerun3-20260929.json)). The executive case now passes a stricter check that rejects framing reported initiatives as options leadership considered; the answer cited 2024/2025 reports and disclosed that no decision alternatives were provided ([executive QA](../artifacts/evaluation/proposal-business-app-executive-report-guarded-rerun5-20260929.json)). Human QA, private-domain evidence and representative local performance measurements remain incomplete. |
| Retrieval baseline on refreshed corpus | Evaluated, preliminary | All four proposal methods were rerun twice on the live snapshot of 25 ready Vinamilk documents/4,750 chunks with 12 cases and 24 selected passage labels, including three governance cases. A third run after section-title backfills reproduced the exact per-case rankings and document/passage/context metrics. Hybrid passage MRR is 0.464; dense 0.412 and BM25 0.403; parent context MRR is 0.469. Latency varied between runs, and sparse labels preclude a winner claim. See the [post-backfill run](../artifacts/evaluation/vinamilk-retrieval-post-section-title-backfill-12cases-20260928.json), [first run](../artifacts/evaluation/vinamilk-retrieval-live-12cases-20260928.json), and [repeat](../artifacts/evaluation/vinamilk-retrieval-live-12cases-repeat2-20260928.json). |
| Proposal business cases and corpus diversity | Partial | Current corpus contains 27 public Vinamilk sources, including the official Vinamilk Shop returns policy and the Code of Conduct's employee access clauses. The 12-case source-coverage audit classifies 2 tasks supported, 6 partial and 4 unsupported; selected routed tasks have authenticated end-to-end runs, but full case completion is not established. The dedicated Information System Policy, general invoice policy, private HR details, executed contracts, manufacturing and server instructions remain absent. RBAC labels are synthetic demo controls over public documents. |
| Enterprise prompt, metadata-aware reasoning and knowledge ontology | Partial | Metadata-aware role filtering, grounded prompts, bounded parent-context retrieval and a bilingual finance KPI ontology exist. Full enterprise entities/domains, persistent hierarchy, query rewriting and context compression need implementation and evaluation. Instruction tuning is optional in the proposal. |
| Secure PostgreSQL/pgvector knowledge base | Partial | [Retrieval and RBAC](technical/retrieval-rbac.md); role filtering is applied before candidate ranking. The active company is read from `data/vietnam_enterprises/manifest.json` and scopes dashboard, analytics, upload, QA and KPI review writes; existing out-of-manifest FPT rows remain stored but are excluded from this Vinamilk demo. The 2026-09-28 read-only integration check verifies exact local/remote migration history (13/13) and vector schema/repository mapping across 5,052 rows. A fresh full manifest audit after employee access ACL re-index finds 26/26 ready documents and 0 metadata mismatches over 4,753 chunks/52,283 fields ([artifact](../artifacts/evaluation/vinamilk-corpus-metadata-audit-access-policy-20260928.json)). A five-account live API matrix confirms employee 3 docs/analytics denied, finance 7, sustainability 11, admin 26, and uploader 0 visible docs/upload allowed ([artifact](../artifacts/evaluation/vinamilk-dashboard-rbac-live-api-20260928.json)). A live finance-query BM25 probe confirms no employee candidates and finance-only annual-report passages, all matching stored ACLs ([artifact](../artifacts/evaluation/vinamilk-live-retrieval-rbac-isolation-20260928.json)). It does not establish private-document isolation or rendered-browser behavior; those checks remain. |
| Multi-agent QA, analytics/SQL, report, dashboard | Partial | [Agents and evaluation](technical/agents-and-evaluation.md); LangGraph routes current intents. SQL analytics reads verified, role-filtered CTEs, validates SELECTs, executes read-only, and returns source citations. Live `/api/analytics` currently has 12 verified financial observations and 140 verified business observations across 90 metric types/7 decision domains, with 6 business candidates pending admin review. A live authenticated report question comparing FY2024–25 domestic/overseas revenue returned 8 source citations and the verified scales and absolute changes; it recommended diligence and disclosed missing margin, selling-cost, working-capital, capacity and return data. Admin review of all pending candidates and broader decision-question evaluation remain open. |
| Web chatbot, upload portal, search and interactive dashboard | Partial | QA UI uses authenticated `/ws/ask` with a processing event and REST fallback; Nginx forwards WebSocket upgrades. Local browser checks verified analyst login, Business analysis filters/database coverage/live cited answer, and admin processing, access and monitoring screens. Live authenticated XLSX upload reached `ready` and its parsed table/formula/chunk data and private Storage bytes were read back. An injected embedding failure on newline-terminated TXT then verified saved-output retry and role-filtered retrieval (analyst sees it, employee does not). Both test fixtures were cleaned and absence verified. Local authenticated WebSocket and hosted Docker/Nginx reverse-proxy runtime checks passed in CI; broader browser QA remains; Render/Vercel hosting is out of scope. |
| Retrieval, generation and system evaluation | Partial | The last complete finance/product/sustainability/RBAC QA suite passed 5/5; focused employee return-policy and FY2024 financial cases separately passed 1/1 each with Qwen3.8 ([customer-service artifact](../artifacts/evaluation/customer-service-employee-qwen38-20260928.json), [finance artifact](../artifacts/evaluation/finance-2024-qwen38-20260928.json)). A repeated 70-request in-process API load run exists. OCR v7 has hash-matched reports for five settings on ten regions, including six English physical-scan regions (four added in v7). A separate four-engine diagnostic compares Tesseract, PaddleOCR, EasyOCR and Surya on three pages from one Vietnamese financial scan packet; full-text CER/WER is now available for all three after image-checked transcriptions, while 20 value-cell boxes remain visually checked labels derived from the PDF text layer. This improves evidence for Vietnamese scans but does not establish broad representative accuracy or controlled engine runtime. Semantic human QA review, larger local workload measurements and broader business-case evaluation remain incomplete. See the [evaluation master matrix](technical/agents-and-evaluation.md#proposal-evaluation-master-matrix); higher-concurrency and corpus-scale behavior remain unmeasured. |
| Local prototype runtime, monitoring, manuals and research report | Partial | Local Compose and the FastAPI/Nginx path are documented. Hosted [CI run 36423572195](https://github.com/Lenhan231/enterprise-knowledge-ai-agent/actions/runs/36423572195) passed the full test suite, Compose validation, image build, `nginx -t`, and authenticated HTTP/WebSocket smoke through Docker Nginx. Render/Vercel deployment is explicitly out of scope. Monitoring decisions, an operator walkthrough, representative local performance measurements and final evidence-complete report remain. |

### Required handoff deliverables

| Proposal deliverable | Current evidence | Remaining acceptance evidence |
| --- | --- | --- |
| Enterprise AI Agent, RAG QA, chatbot and REST API | FastAPI app, authenticated chat, cited answers, upload/search endpoints and role-filtered retrieval | Stable demo flow covering sign-in, upload/process, search, grounded QA, denial by role and recovery from provider/database errors |
| Document-processing and knowledge database | PDF/Office/image parsers, pre-embedding parser-stage persistence with admin inspection and vector retry, PostgreSQL/pgvector migrations and source-linked metric candidates | Representative real-file quality checks, real scan/OCR/layout labels, and clean setup from migrations plus corpus instructions |
| Multi-agent workflow and business dashboard | LangGraph routes; role-scoped dashboard/analytics and admin monitoring UI | Grounded business-case tasks, user-visible KPI backed by reviewed evidence, route-quality evaluation, and browser verification through the local proxy |
| Technical documentation, user manual and deployment guide | Technical notes, [user guide](user-guide.md), and [deployment guide](deployment-guide.md) | Walkthrough verified by a new operator; proxy/container and CI/CD run evidence |
| Comprehensive research report | [Evidence-backed draft](research-report.md) covers methodology, architecture, corpus scope, benchmark results, known failures, limitations and prioritized future experiments with links to run artifacts | Complete missing proposal experiments, add blinded human evaluations and representative local runtime evidence, then revise this draft as the final thesis report |

## Proposal technology choices

The proposal names several candidate tools. This prototype records the selected
implementation and the remaining evaluation work rather than adding
every named package by default.

| Proposal technology | Current implementation | Status / follow-up |
| --- | --- | --- |
| Python, FastAPI, PostgreSQL, pgvector | Python API with Supabase-hosted PostgreSQL/pgvector | Implemented; migrations and role-filtered data paths have tests and selected live checks. |
| LangChain, Hugging Face Transformers, PyTorch | LangChain core interfaces, Sentence Transformers/Hugging Face embeddings; PyTorch is the model runtime | Implemented in retrieval/embedding paths; candidate embedding models remain under evaluation. |
| LangGraph | Conditional multi-agent router | Implemented for knowledge QA, analytics, hybrid, report and dashboard routes; route/task coverage is still partial. |
| PaddleOCR, Docling, Unstructured, PyMuPDF, OpenCV | PyMuPDF native PDF extraction; Tesseract fallback; optional PaddleOCR layout path | PyMuPDF/Tesseract are active. PaddleOCR is optional and not enabled on normal upload. Docling, Unstructured and OpenCV are not integrated; paired OCR text pilot is complete, while OCR/layout quality evaluation remains incomplete. |
| Docker, Docker Compose, Nginx, WebSocket | Compose web/proxy definitions, Nginx config, authenticated WebSocket QA | Hosted CI built the image, validated Compose and `nginx -t`, then exercised authenticated HTTP and WebSocket through the Nginx proxy. Local container runtime is unavailable. Hosted deployment is outside the current scope. |
| LangSmith, MLflow, Prometheus, Grafana | Privacy-minimized `agent_run_events` and an admin monitoring console | Those four proposal-listed tools are not integrated; current monitoring is application-level, not centralized tracing, experiment tracking or infrastructure metrics. |
| Pytest | Existing regression suite uses Python `unittest` | Tests pass under `unittest`; Pytest is not installed or configured. Treat the proposal's tool list as an implementation choice to resolve, not as evidence of test coverage by itself. |

## Technical notes

- [Repository ownership and navigation](technical/repository-ownership.md)
- [Document parsing, OCR and tables](technical/document-processing.md)
- [Chunking and section metadata](technical/chunking.md)
- [Embedding model and tokenization](technical/embeddings-tokenization.md)
- [LLM provider and answer evaluation](technical/llm.md)
- [Retrieval and RBAC](technical/retrieval-rbac.md)
- [Database connection limits](technical/database-connections.md)
- [Agents, dashboard and evaluation](technical/agents-and-evaluation.md)
- [User guide](user-guide.md)
- [Deployment guide](deployment-guide.md)

## Current validation snapshot

- Corpus metadata audit: `uv run python scripts/analytics/evaluate_corpus_metadata.py`; latest read-only artifact checks all 26 ready manifest sources (364 document fields and 52,283 chunk fields) with zero propagation mismatches, across 4,753 chunks. This is not automatic extraction accuracy.
- Automated suite: `uv run python -m unittest discover -s tests -q` (**462
  passed on 2026-09-29**; includes processing, evaluation, retrieval, agent,
  API and dashboard checks, including OCR benchmark packaging, the separate
  2011 scan diagnostic notebook, and OCR/embedding Kaggle setup
  validation and authenticated upload/admin-processing RBAC regressions).
- Proposal corpus-coverage audit: `uv run python scripts/agents/evaluate_proposal_case_coverage.py` validates all 12 case labels against the active route set and 26-document manifest; current counts are 2 supported, 6 partial and 4 unsupported. The public Code of Conduct supports a narrow employee-access answer, while its referenced dedicated Information System Policy is absent; the synthetic demo ACL lets employees retrieve it, but not finance analysts. The employee app QA passed 1/1 with Qwen3.8 ([artifact](../artifacts/evaluation/employee-access-policy-qwen38-rerun-20260928.json)). The authenticated invoice task passed its grounded-answer checks in [the final evaluation](../artifacts/evaluation/proposal-business-app-invoice-narrow-quote-final-20260928.json). Use `scripts/agents/evaluate_app_qa.py --case-id <id>` for focused role-specific QA.
- Embedding comparison: the paired Tesla T4 reports and independent hash audit cover all 4,750 passages in the 25-source snapshot for BGE-M3, Qwen3 Embedding and e5-large-v2. The separate 173-chunk CPU run has only BGE/e5 results because Qwen was stopped at its first slow batch. The two protocols and the raw artifact metadata discrepancy are described in [the evaluation matrix](technical/agents-and-evaluation.md#proposal-evaluation-master-matrix).
- Query rewriting: `uv run python scripts/agents/evaluate_query_rewriting.py --output artifacts/evaluation/vinamilk-query-rewriting-metric-labels-20260928.json` compares raw and ontology-expanded queries on identical role-filtered retrieval inputs. The small paired result was mixed, so rewriting remains evaluation-only; other optimization experiments remain open.
- Response cache: `uv run python scripts/agents/evaluate_response_cache.py --output artifacts/evaluation/vinamilk-response-cache-api-smoke-20260928.json` verified two identical authenticated, cited `/api/ask` responses with one answer-generation call and live role-filtered retrieval. The deterministic answer stub isolates cache wiring; embedding and DB retrieval still execute on cache hits, so recorded latency is not a real-provider speedup benchmark.
- Context compression: `uv run python scripts/agents/evaluate_context_compression.py --output artifacts/evaluation/vinamilk-context-compression-20260928.json` performs query-term extractive sentence selection against the blinded QA packet. Fifteen responses (five distinct questions) have a mean 0.3976 character ratio; responses with all expected fact groups present remained 6/15 before and after, with baseline indicators unchanged in 15/15. These repeated contexts and character counts are preliminary; answer quality and tokenizer savings remain unmeasured, so compression stays off in production.
- Python syntax: `python -m compileall -q src tests scripts`.
- Frontend syntax: `node --check src/app/static/app.js`.
- Hosted CI: commit `5c135ce` passed `uv sync --locked`, Python compile, all 252
  unit tests, frontend syntax, Compose proxy configuration, Docker image build,
  and `nginx -t`; see [run 36287481142](https://github.com/Lenhan231/enterprise-knowledge-ai-agent/actions/runs/36287481142).
- Local app: `http://127.0.0.1:8000/health` returned `200 {"status":"ok"}`
  during the same validation session. The authenticated proxy path was exercised in CI; hosted deployment is out of scope.
- Local HTTP load through Uvicorn:

  ```bash
  uv run python scripts/operations/evaluate_api_load.py --base-url http://127.0.0.1:8000 \
    --concurrency 1 2 4 --iterations 10
  ```

  This passed 70/70 authenticated health/dashboard/analytics requests. Throughput
  was 0.463/0.831/1.648 req/s and p95 latency 3.75/3.74/3.69 s. Artifact:
  [`vinamilk-api-load-http-localhost-20260927.json`](../artifacts/evaluation/vinamilk-api-load-http-localhost-20260927.json).
  A 35-request diagnostic separately reports latency by endpoint in
  [`vinamilk-api-load-http-route-details-20260927.json`](../artifacts/evaluation/vinamilk-api-load-http-route-details-20260927.json);
  at concurrency 4, mean latency was 3.64 s for analytics, 3.35 s for dashboard,
  and 2.42 ms for health (6–7 samples per route). These use loopback and do not
  establish higher-load local scalability.
- A small loopback stress smoke at concurrency 8/16 passed 40/40 at level 8;
  level 16 had one analytics 503 in 80 requests, while a 32-request repeat
  passed. Captured logs identified Supavisor's 15-session pool cap. The app now
  queues repository connections behind a 10-per-process bound; after the fix,
  the same concurrency-16 workload passed 80/80 (3.784 req/s, p95 7.06 s).
  This validates the fix, not capacity. See the [pre-fix stress artifact](../artifacts/evaluation/vinamilk-api-load-http-stress-20260928.json)
  and [post-fix run](../artifacts/evaluation/vinamilk-api-load-http-bounded-20260928.json).
- Seed corpus headings: after re-ingesting the 11 annual/sustainability PDFs,
  Supabase reports `section_title` on 3,773/3,780 chunks (99.8%); all 3,780
  report chunks have `allowed_roles`. No stored report chunk exceeds the
  configured 512-token model sequence limit. Heading counts measure presence,
  not correctness.
- The original paired retrieval report
  `artifacts/evaluation/vinamilk-retrieval-current-passage-comparison.json`
  captures the 15-document pre-governance baseline. Its same nine questions
  and 21 selected passage labels were rerun on all 25 ready Vinamilk documents
  in `artifacts/evaluation/vinamilk-retrieval-expanded-corpus-20260927.json`.
  On 4,750 chunks, document MRR is 1.0/0.944/0.926/1.0 for dense/BM25/hybrid/
  parent; passage MRR is 0.373/0.307/0.384 for dense/BM25/hybrid, and parent
  context MRR is 0.431. Hybrid still leads passage MRR but dropped from 0.440
  after corpus expansion. Sparse, non-exhaustive labels require independent
  review before drawing a method-selection conclusion.
  Three governance questions were added from verified source passages and
  role-scoped chunk metadata; their earlier 12-case four-method run is
  `artifacts/evaluation/vinamilk-retrieval-12cases-expanded-corpus-20260927.json`.
  The 2026-09-28 live run and exact-ranking repeat are linked in the retrieval
  status row above.
  Parent windows use separate context metrics. See
  [retrieval evaluation](technical/retrieval-rbac.md).
- Retrieval reproducibility rerun
  `artifacts/evaluation/vinamilk-retrieval-current-four-methods.json` used the
  same 9-case hash and 4,087-chunk database snapshot. It reproduced document
  MRR 1.000/0.944/0.926/1.000 and passage MRR 0.429/0.363/0.440 for
  dense/BM25/hybrid/parent (parent uses separate context MRR 0.431). Dense's
  first query included a 12.7 s model cold start; warm dense cases were
  0.3–0.6 s. This confirms metric repeatability for this snapshot, not broader
  generalization; the 9-case judgments remain selected and non-exhaustive.
- Current authenticated app-route QA suite
  `artifacts/evaluation/vinamilk-app-qa-suite.json` passed 5/5 finance,
  sustainability, product and employee-denial cases through `/api/ask`; the
  runner verifies expected agent, fact anchors, source document, citation
  consistency and abstention. The artifact's hash matches the preserved
  [`v1 case snapshot`](../data/evaluation/archive/qa/vinamilk_qa_cases-app-qa-v1.json),
  not the subsequently strengthened current case labels. The refreshed run
  averaged 26.405 s. A rerun against stronger case labels plus retention
  abstention was rate-limited on its first three requests and produced no full
  result; the current expected-unit labels remain unverified end to end. This
  small public-corpus smoke does not measure semantic faithfulness or human
  usefulness; exact model behavior and human QA scores remain unreviewed. The
  runner now stops at the first HTTP 429 and records unrun case IDs.
- A separate live authenticated `/api/ask` smoke for the unsupported document
  retention-standard case correctly routed to Knowledge, abstained, and cited
  no source. Its case label and result are recorded in
  `data/evaluation/archive/qa/vinamilk_unsupported_abstention_case.json` and
  `artifacts/evaluation/vinamilk-unsupported-retention-abstention-smoke.json`.
- Current route rerun [`proposal-business-route-current-12-20260928.json`](../artifacts/evaluation/proposal-business-route-current-12-20260928.json)
  scored all 12 manually mapped cases through the effective router (12/12):
  two provider classifications plus ten correct deterministic fallbacks after
  `RateLimitError`. A separate no-fallback three-case run
  [`proposal-business-route-current-three-20260928.json`](../artifacts/evaluation/proposal-business-route-current-three-20260928.json)
  directly classified financial report, executive report, and BI analytics
  correctly (3/3). These are routing results only; both artifacts use agent
  stubs and do not measure task execution, answer quality, or corpus coverage.
  The earlier pre-prompt run misrouted document-count aggregation (11/12).
- Paired LLM proxy reports in `artifacts/evaluation/*-facts-v2.json` compare
  GPT-OSS-20B, Qwen3.8-27B and GPT-OSS-120B on the same five source/context and
  prompt fingerprints: each passes the automated source/fact/denial checks.
  The 120B answer also contains an incorrect unit conversion, so deterministic
  checks do not establish faithfulness. Exact proposal model access and blind
  human scoring remain incomplete; see [LLM evaluation](technical/llm.md).
- Earlier authenticated QA smoke `artifacts/evaluation/vinamilk-app-qa-smoke.json`
  is retained as a historical 2-case run. Use the 5-case app-route suite above
  for the current finance/sustainability/product and RBAC-denial evidence.
- Embedding scaling run `artifacts/evaluation/vinamilk-embedding-e5-large-v2-expanded-16-per-document.json`
  sampled 181/3,785 ready Vinamilk chunks (max 16/document) on CPU: MRR 0.624,
  Recall@5 1.0, mean query 207 ms, peak RSS 2,228 MiB. This is a separate
  scaling measurement, not a paired model comparison; see
  [embedding notes](technical/embeddings-tokenization.md).
- Expanded paired embedding comparison uses the same 93-chunk sample and case
  hash for BGE-M3, Qwen3 Embedding and e5-large-v2. MRR: 0.670/0.670/0.707;
  Qwen CPU corpus embedding took 1,325 s versus 103 s for BGE and 134 s for e5
  (batch sizes 1/8/4 respectively). Throughput reflects those settings. These
  nine-case document-level smoke scores do not establish a model winner.
- QA proxy-metric report `artifacts/evaluation/vinamilk-qa-metrics-smoke.json`
  adds labeled-document context precision and non-empty-line citation coverage;
  these do not replace semantic faithfulness, answer relevancy or human review.
- API load repeat `artifacts/evaluation/vinamilk-api-load-repeat10.json` completed
  70/70 health, dashboard and analytics requests at concurrency 1/2/4 (10 per
  worker); see
  [evaluation](technical/agents-and-evaluation.md) for throughput, latency and
  in-process benchmark limits.
- Hybrid RRF tuning `artifacts/evaluation/vinamilk-hybrid-weight-sweep-20260927.json`
  compares dense/BM25 baselines and four hybrid settings on the same nine
  manually labeled queries and database snapshot. Default 1:2, k=60 had the
  highest passage MRR (0.440) and nDCG@5 (0.329); dense-weight 2:1 restored
  document MRR/nDCG@5 to 1.0. Selected passage labels and nine queries are too
  small to select new weights; see [evaluation notes](technical/agents-and-evaluation.md).
- BGE reranker report `artifacts/evaluation/vinamilk-reranker-bge-reranker-v2-m3.json`
  compares the same dense top-30 passages on nine labeled cases. Qwen reranker
  checkpoint loaded at revision `e61197ed45024b0ed8a2d74b80b4d909f1255473`,
  but CPU inference exceeded eight minutes on its first 30-candidate query and
  was stopped. Paired top-2 CPU smokes completed at max sequence length 256:
  BGE 2.32 s/query, Qwen 12.92 s/query, both with unchanged document ranking.
  Artifacts are `vinamilk-reranker-bge-reranker-v2-m3-cpu-top2-smoke.json`
  and `vinamilk-reranker-qwen3-reranker-0.6b-cpu-top2-smoke.json` in that
  directory. Refreshed passage-level top-2 CPU runs share identical case and
  candidate hashes: BGE passage MRR changed 0.389→0.333 (1.73 s/query), while
  Qwen changed 0.389→0.444 (15.74 s/query). See
  [reranker evaluation](technical/agents-and-evaluation.md); this small,
  non-exhaustively labeled top-2 smoke does not replace full top-30 evaluation.
- Paired chunking report `artifacts/evaluation/vinamilk-chunking-retrieval-finance-five-year.json`
  compares fixed live vectors with in-memory sentence-aware vectors across five
  annual reports and five finance questions. Passage MRR is 0.2715/0.2648 and
  Recall@5 is 0.10/0.10; sentence labels are heuristic transfers, so this is a
  preliminary diagnostic, not a strategy selection or QA result. It performs
  no database writes.
- Refreshed BGE top-30 passage run
  `artifacts/evaluation/vinamilk-reranker-bge-top30-passage-cpu.json` uses all
  nine current cases and 21 selected passage labels at CPU, batch 2 and sequence
  length 256. Passage MRR improved 0.429→0.459 and Recall@2 0.241→0.259;
  document MRR declined 1.000→0.917. Mean rerank time was 29.67 s/query and
  peak RSS 2,820 MiB. The previously missing paired full-depth comparison now
  exists on Tesla T4: BGE/Qwen passage MRR 0.5167/0.4348, document MRR
  0.8958/0.9583 and rerank latency 1.17/2.74 s/query over the same 12 cases
  and top-30 candidate bundle. See
  [paired report](../artifacts/evaluation/vinamilk-reranker-kaggle-top30-paired-20260928.json).
  Labels remain selected and non-exhaustive; neither model is selected.
- OCR paired text pilot: reports under `artifacts/evaluation/ocr/ocr-kaggle-{easy,paddle,surya}/` plus `artifacts/evaluation/ocr/pipeline/ocr-tesseract-v2-current-labels.json`; same three-crop dataset hash, not eligible for model selection.
  records per-page edit counts and macro/micro CER/WER, but uses an unreviewed
  PDF text reference. Manual-label pilots are
  `artifacts/evaluation/ocr/comparisons/vinamilk-ocr-human-reviewed-tesseract.json` (v1, two
  crops), v2 (three crops), and v4 (three non-scan crops plus two image-only
  scanned governance regions). Tesseract v4 initially provided a scan-only pilot, and the paired EasyOCR run
  now covers all five v4 regions; neither has cell/layout scoring; the Tesseract v4 run measured 31.085 pages/minute
  (inference, excluding initialization) and 409 MiB CPU process/child peak RSS.
  A completed EasyOCR 1.7.2/Tesla T4 v4 run on the same five 180-DPI regions
  scores micro-CER/WER 0.097521/0.260700 vs Tesseract 0.399339/0.297665.
  EasyOCR initialization was 9.746 s, mean OCR time 1.213 s/page, process peak
  RSS 1,543.852 MiB and PyTorch CUDA peak allocated/reserved memory 1,800.277/
  2,570 MiB. On Charter and governance contents scans respectively, EasyOCR
  CER/WER is 0.039735/0.112676 and 0.126115/0.285185; Tesseract is
  0.037528/0.084507 and 0.654140/0.300000. On the two scans combined,
  EasyOCR micro-CER/WER is 0.106772/0.249267 vs Tesseract 0.516065/0.255132.
  A same-hash PaddleOCR 3.7.0 CPU run now scores 0.078017/0.173152 across all
  five regions (2.818 pages/minute, 3,937.254 MiB process peak RSS); the paired
  artifact also compares it with EasyOCR and Tesseract. OCR v5 adds a manually
  checked Vietnamese balance-sheet table from Vinamilk 2024 (16 labeled rows,
  both reporting-year values). The six-region v5 all-page CER/WER values below
  are historical and superseded by corrected v6 labels. On the unchanged table
  crop, Tesseract CER/WER is
  0.080207/0.140625 and exact row recall is 8/16 (0.5). This is one
  born-digital table and does not establish general table-layout quality.
  EasyOCR v5 completed on the same six hashes: micro-CER/WER 0.175882/0.348442
  and exact table row recall 2/16 (0.125). Its output grouped numeric columns
  apart from row labels. The hash-paired Tesseract/EasyOCR comparison is
  `artifacts/evaluation/ocr/comparisons/vinamilk-ocr-easy-tesseract-v5-comparison.json`.
  Surya v5 completed on the same hashes with micro-CER/WER 0.075829/0.151558,
  exact table row recall 14/16 (0.875), 3.962 s mean inference/page and
  4,395.629 MiB peak process RSS; GPU allocation/reservation was
  2,354.048/2,670 MiB. PaddleOCR v5 completed at CER/WER 0.087941/0.211048,
  0/16 exact rows and 32/48 cell-text matches. Cell-text recall is Tesseract
  40/48, EasyOCR 47/48, Surya 47/48, and PaddleOCR 32/48; it ignores row/column
  association. The hash-paired four-engine artifact is
  `artifacts/evaluation/ocr/comparisons/vinamilk-ocr-paddle-easy-surya-tesseract-v5-comparison.json`.
  These v5 all-page CER/WER aggregates are superseded by corrected v6 labels;
  the table-only metrics remain historical. Surya v6 is complete, while the
  older v4 kernel is no longer a pending run. The corrected v6 six-page
  comparison reports all four engines on identical labels and image hashes;
  see `vinamilk-ocr-four-engine-v6-cpu-comparison.json`. The one-table pilot
  does not select a production engine. Dataset and
  baseline report:
  `data/evaluation/ocr/archive/vinamilk_ocr_ground_truth_v5.json` and
  `artifacts/evaluation/ocr/comparisons/vinamilk-ocr-human-reviewed-tesseract-v5.json`.
  See [document processing](technical/document-processing.md) and the
  hash-verified pair `vinamilk-ocr-governance-scans-v4-comparison.json`.
- OCR scan expansion v7 provides ten visually reviewed regions, including four image-only English scans. PaddleOCR 3.7.0, EasyOCR 1.7.2, Surya 0.17.1, and Tesseract 5.5.3 PSM 3/11 now have results on identical source/render hashes at 180 DPI. In engine order Paddle/Easy/Surya/Tesseract PSM 3/11, micro-CER is 0.043609/0.110025/0.043233/0.272556/0.127318 and micro-WER is 0.108484/0.248261/0.090403/0.263561/0.197497. Paddle ran CPU; EasyOCR and Surya ran on a Tesla T4. Surya has the best CER/WER and 14/16 exact financial-table rows, while EasyOCR/Surya report 47/48 cell strings; those cell counts do not measure row/column association. A supplemental Vietnamese scan comparison now covers three pages from a third-party 2011 packet with full text labels on every page, rescored from cached OCR output on exact source/render hashes: Tesseract/Paddle/Easy/Surya micro-CER 0.6932/0.1626/0.4494/0.1667 and micro-WER 0.9128/0.3303/0.5404/0.1826. Paddle has the lowest CER, Surya the lowest WER; neither is selected because the packet is small and from one source. The two balance-sheet transcriptions use PDF text as an aid and were visually reviewed. The 20 coordinate boxes derive from the PDF text layer, not independent click annotations. See the [v7 comparison](../artifacts/evaluation/ocr/comparisons/vinamilk-ocr-v7-five-configuration-comparison-20260928.json), the [three-page scan labels](../data/evaluation/ocr/archive/2011-scan/vinamilk_ocr_ground_truth_2011_scan_diagnostic_v3.json), the [rescored comparison](../artifacts/evaluation/ocr/comparisons/vinamilk-ocr-2011-v3-four-engine-comparison-20260929.json) and [production-parser report](../artifacts/evaluation/ocr/pipeline/vinamilk-scan-document-processor-2011-three-pages-v2-20260929.json). Kaggle results are linked from the [processing protocol](technical/document-processing.md#current-boundaries).
- Extraction anchor report
  `artifacts/evaluation/ocr/pipeline/vinamilk-document-extraction-scan-table-v9.json` uses five
  manually checked financial fields on two official annual-report pages
  (2020 infographic and 2024 balance sheet). It compares native PDF, PDF OCR,
  and the actual image-upload OCR path. It remains a small synthetic-raster
  diagnostic. The born-digital 2024 path detected 2/2 table regions and retained
  all three labeled table rows exactly after the new borderless-table fallback.
  The synthetic raster-PDF and image-upload OCR paths now each detect both
  table regions and recover all three rows after normalization; OCR punctuation
  errors still prevent exact table-anchor matches. The evaluator maps a
  one-page image's table metadata to page 1 even though image text chunks have
  no PDF page number. On the 2024 page, raster-PDF OCR matches 3/3 normalized
  table anchors; image-upload OCR with table PSM 3 matches 2/3 normalized table
  anchors and 3/3 normalized text anchors. The follow-up [table PSM 6 report]
  (`artifacts/evaluation/ocr/tuning/vinamilk-document-extraction-compact-table-psm6-20260928.json`)
  raises normalized table-anchor recall to 3/3 on both raster-PDF and
  image-upload routes; exact table-anchor recall remains 1/3 and 0/3,
  respectively. Production defaults now use PSM 3 for PDF table word boxes and
  PSM 6 for direct image uploads; text OCR remains PSM 11. This comparison
  uses two born-digital source pages rasterized synthetically, so it does not
  replace review on real scanned reports.
- Expanded multi-year extraction report
  `artifacts/evaluation/ocr/pipeline/vinamilk-document-extraction-multiyear-v3-20260928.json`
  supersedes the narrow five-field candidate count below for native financial
  statement coverage. It contains 11 visually checked fields over five report
  pages (2020–2024); born-digital candidate extraction matched 11/11 with
  1.00 precision. Synthetic Tesseract raster OCR matched 1/11 exact text
  anchors and 3/11 after normalization. These are not real-scan or
  document-wide accuracy estimates.
- Financial candidate extraction report
  `artifacts/evaluation/ocr/pipeline/vinamilk-document-extraction-candidates-20260927.json`
  adds candidate-level scoring on those same five labeled fields. The rule-based
  extractor produced 5 candidates, with 5/5 labeled-value precision and 5/5
  field recall across two pages (2/2 infographic fields; 3/3 balance-sheet
  fields). These results cover only those selected, born-digital pages and do
  not establish corpus-wide accuracy or LLM extraction quality.
- Table strategy sweep `artifacts/evaluation/ocr/tuning/vinamilk-document-extraction-table-strategy-v4.json`
  reran the two-page extraction fixture on 2026-09-27. On the manually labeled
  2024 balance sheet, PyMuPDF default found 0/2 expected table regions;
  text/text found one fragmented 75x15 table and matched 3/3 financial anchors
  after normalization, while text/lines and lines/text matched 0/3. This was
  the exploratory result that led to the current borderless-table fallback;
  see the v9 extraction report for its measured production-path result.
- Metric review persistence: on 2026-09-27, the source-backed 2024 report
  refresh left six candidates in `needs_review` and preserved 39 unmatched
  older candidates as `superseded`; no 2024 row is `verified`, so the dashboard
  correctly waits for an admin to confirm the source value and unit. The
  headline revenue/profit candidates are on page 2 (61.824 and 9.453 tỷ đồng).
  A later live review found five verified KPI rows. The FY2020 profit-after-tax
  row had been stored as `11.236` instead of `11236`; the original annual report
  page 2 states `11,236` VND billion. Both the verified metric and its reviewed
  candidate were corrected in Supabase, and the authenticated analytics API
  now returns profit `11236` and consolidated revenue `59723` billion VND.
- Business-analysis evidence refresh (2026-10-01): the locally held official
  2024 Vietnamese annual-report PDF was re-ingested after detecting a source-version
  mismatch with the old chunks. All 438 new chunks carry its SHA-256; parser v8
  now yields review candidates for domestic/export growth, product portfolio,
  raw-milk supply, customer satisfaction, purchasing/production savings, OEE
  and headcount. Live evidence is 129 observations (91 verified, 38 pending),
  80 metric types across 9 domains at that time. Exact quote/page matches were relinked without changing
  verified values; 2 old source-research rows remain unlinked and pending. The
  [decision-metrics note](technical/vinamilk-milk-supply-metrics.md) maps these
  sources to business questions and states which internal data is still needed.
  A CLI re-download of Vinamilk’s PDF URL returned 403, so the local SHA is not a
  hash check against the live HTTP response.
- HTTP/browser runtime smoke: local `/` and `/static/app.js` returned 200,
  `/health` returned `{"status":"ok"}`, and Chrome verified analyst sign-in,
  workspace rendering, the Knowledge/Business analysis tabs, and the 2024
  analytics filter. Admin sign-in exposed processing, access and monitoring
  tabs; the processing screen rendered pending source-linked metric evidence and
  upload controls, and Access showed the role permission matrix. These screens
  were inspected without publishing or uploading. No browser console errors
  appeared. At that earlier read-only check, the dashboard showed zero verified
  KPIs; the later source-checked FY2020 KPI correction and current five-row
  state are recorded above. The load runner exercised authenticated dashboard/
  analytics routes. Upload submission, review mutation, employee/uploader
  browser flows, and Nginx proxy rendering remain unverified.
- See [`data/README.md`](../data/README.md) for corpus provenance, ingestion,
  and database data flow.
## Metric extraction and decision analytics

The dashboard reads verified values from PostgreSQL; it does not calculate from a local JSON fixture. Financial observations use `extracted_financial_metrics`; business observations use `business_metric_evidence`. Pending candidates stay out of analytics until an admin checks the source, period, value, unit and scope.

Business metric extraction in `src/core/analytics/business_metric_extraction.py` sends parser-produced table and narrative chunks to the configured Groq model only when upload or batch processing explicitly selects one `BUSINESS_DECISION_PROFILES` domain. The catalog currently defines 91 metric types; the LLM prompt receives only the selected domain's primary metrics and management question. Server validation rejects every metric outside that selected profile, and each accepted value must match an exact source quote, unit and period. Without a selected business decision domain, upload skips business KPI extraction while retaining parsed/searchable content and its separate financial pipeline. Provenance stores selected profile, model, prompt version, parser selection signals, token usage and source chunk. Admin can replay extraction on a ready uploaded PDF's saved parser chunks and choose one primary metric after choosing its domain; the audit records that metric, and the existing domain-filtered review queue handles any new candidates. Uploaded source bytes and parser chunks remain available for inspection/replay; metric evidence links to the indexed chunk and content hash used by SQL citations. Reproduce a no-write run with:

```bash
PYTHONPATH=src .venv/bin/python scripts/processing/process_vinamilk_business_metrics.py --ids VNM-AR-2025-EN --decision-domain milk_supply --max-chunks 3
```

This parses the whole PDF with the same layout-parser setting as upload, then caps model calls at three selected chunks. Output is JSON on stdout; add `--save-candidates` only when you intend to write review-only candidates. The domain profiles are first-pass, management-question-oriented scopes and still need review with domain owners; they are not proof that every chosen KPI is decision-useful. The chunk-based path has not yet been benchmarked across all reports, and a real Groq smoke request on 2026-10-01 returned HTTP 429 before producing candidates. Unit and upload-flow tests use a fake provider. Conflicting values for one metric/year are withheld rather than silently choosing one; source-specific scope still needs admin review.

Financial extraction remains separate: `scripts/processing/process_vinamilk_financial_reports.py` ranks financial pages, requests strict JSON and stores candidates for review. Both pipelines preserve source pages and chunks; only verified rows enter the SQL agent's authorized views.

The authenticated SQL/report path was exercised against the live local app on 2026-10-01. A read-only request using the configured analyst login returned 56 role-visible verified business observations across five domains, all with source-chunk IDs and content hashes. `/api/dashboard` returned the corpus/processing view; `/api/analytics` supplied the financial and business observations used by the interactive KPI view. A milk-supply decision question completed through `/api/ask` as the report agent with HTTP 200 and three metric citations: it compared 2023–2025 farmer milk purchases, calculated the reported change, qualified the approximate FY2024 value, and identified the supplier, quality, price and cost evidence needed before procurement changes. This is one live decision-path smoke, not broad answer-quality evidence. The current admin database snapshot has 12 verified financial observations and 140 verified business observations across 90 metric types/7 decision domains, with 6 review candidates; the profile regrouping changed only domain labels and left source evidence untouched. Broader role/domain coverage and reviewed decision-task evaluation remain open.

A bug found during that live check had added revenue-scale metrics to the decision-answer expectation but omitted them from the generated SQL metric filter. `SQLAnalyticsAgent` now includes both revenue series and prior-year values; an exact-code regression assertion and a report-agent test cover scales, deltas and citations. The remaining work is to benchmark the new business extractor across the report set, review its candidates against source pages, resolve ambiguous metric scopes, and finish the proposal's human/provider/browser evaluation. See [the metric evidence and domain note](technical/vinamilk-milk-supply-metrics.md) and [the proposal evaluation matrix](technical/agents-and-evaluation.md#proposal-evaluation-master-matrix).

The domain review keeps the focused market, milk supply, farm, product, manufacturing, environmental and workforce decisions, while merging distribution reach into market performance and manufacturing quality into manufacturing efficiency. Official 2023–2024 reports contain earlier farm, workforce, retail-network and TPM evidence that is not yet fully represented in the metric table; process and verify those pages before dropping a domain for sparse database history. See [Vinamilk business-domain review](technical/vinamilk-business-domain-review.md).
