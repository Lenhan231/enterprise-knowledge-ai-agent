# Proposal coverage and technical guide

This page tracks the capstone proposal against the current prototype. A row is
complete only when the linked implementation and evidence cover the stated
requirement; a passing unit test alone does not establish end-to-end coverage.
Use the technical notes below for current settings and data flow.

## Proposal coverage

| Proposal requirement | Status | Evidence / remaining work |
| --- | --- | --- |
| Enterprise document Q&A with grounded citations | Partial | [RAG and agents](technical/agents-and-evaluation.md); small live corpus and retrieval checks exist. Expand QA cases and evaluate answer quality. |
| PDF, Word, Excel, PowerPoint, scans and images | Partial | [Processing](technical/document-processing.md); PDF/DOCX/XLSX/PPTX/TXT/MD/images parse; Office ZIP expansion is bounded. Uploaded parser output and tables now persist before embedding for inspection/retry. Legacy XLS, physical-scan OCR benchmarking, broader real-file tests and user verification remain. |
| Layout, tables, figures, invoices, formulas, metadata | Partial | XLSX cell formulas and PDF tables persist with parser metadata. The [manifest metadata audit](../artifacts/evaluation/vinamilk-corpus-metadata-audit-20260927.json) reports 0 mismatches across 350 document and 52,250 chunk field checks for all 25 ready manifest sources (4,750 chunks). This confirms metadata propagation only, not automatic extraction accuracy. Financial OCR/table anchors remain narrow; reviewed real scans, math formulas, figures/captions, invoices and representative multi-format quality evaluation remain. |
| Semantic/context-aware chunking and parent-child retrieval | Partial | [Chunking](technical/chunking.md); seed-PDF and upload paths now share configurable sentence/paragraph-aware chunks with a fixed-overlap baseline and tokenizer bound; parent context remains role-filtered. A five-year paired dense retrieval diagnostic exists, but its five questions and heuristic alternate passage labels are too small for selection; paired answer-quality evaluation and persistent section hierarchy remain open. |
| Five proposal benchmark groups | Partial | The exact model/method groups remain visible in the [acceptance checklist](technical/agents-and-evaluation.md#proposal-acceptance-checklist); refreshed-corpus retrieval is rerun, and BGE/e5 embeddings were paired on a 173-chunk sample across all 25 documents and 12 cases. OCR, exact LLMs, Qwen embedding on this host and Qwen top-30 reranking remain incomplete or proxy-only. Small labels still limit model-selection claims. |
| Other proposal evaluation requirements | Partial | See the [acceptance checklist](technical/agents-and-evaluation.md#proposal-acceptance-checklist) for extraction, retrieval/generation quality, system performance, optimization and all 12 business cases. The [hybrid weight sweep](../artifacts/evaluation/vinamilk-hybrid-weight-sweep-20260927.json) compares four RRF settings on the same nine queries, but is preliminary; the [route evaluation](../artifacts/evaluation/proposal-business-route-evaluation.json) measures 12/12 effective routes (9 provider, 3 fallback), which is routing evidence only, not task completion. Human QA, domain evidence and deployed-scale measurements remain incomplete. |
| Retrieval baseline on refreshed corpus | Evaluated, preliminary | All four proposal methods were rerun on 25 ready Vinamilk documents/4,750 chunks with 12 cases and 24 selected passage labels, including three governance cases. Hybrid passage MRR is 0.464; dense 0.412 and BM25 0.403; parent context MRR is 0.469. The conflict-of-interest query shows the relevant passage can rank poorly despite retrieving the right document. Labels remain sparse; no winner claim. See the [12-case artifact](../artifacts/evaluation/vinamilk-retrieval-12cases-expanded-corpus-20260927.json). |
| Proposal business cases and corpus diversity | Partial | Current corpus contains public Vinamilk annual/sustainability reports, policies and product information. This supports finance, sustainability, operations and some compliance questions; it does not yet cover representative private HR, contract, invoice, manufacturing, customer-service or supplier records. RBAC labels are synthetic demo controls over public documents. |
| Enterprise prompt, metadata-aware reasoning and knowledge ontology | Partial | Metadata-aware role filtering, grounded prompts, bounded parent-context retrieval and a bilingual finance KPI ontology exist. Full enterprise entities/domains, persistent hierarchy, query rewriting and context compression need implementation and evaluation. Instruction tuning is optional in the proposal. |
| Secure PostgreSQL/pgvector knowledge base | Partial | [Retrieval and RBAC](technical/retrieval-rbac.md); role filtering is applied before candidate ranking. The active company is read from `data/vietnam_enterprises/manifest.json` and scopes dashboard, analytics, upload, QA and KPI review writes; existing out-of-manifest FPT rows remain stored but are excluded from this Vinamilk demo. Reconcile remote/local migration history and verify every format/role end to end. |
| Multi-agent QA, analytics/SQL, report, dashboard | Partial | [Agents and evaluation](technical/agents-and-evaluation.md); LangGraph routes current intents. Analytics generates bounded SELECT SQL over role-filtered CTEs, with AST validation, read-only execution and source citations. Live document-role SQL was checked; verified KPI rows are currently absent, and multi-source BI workflows and invoice cases remain. Admin monitoring reads privacy-minimized Supabase traces. |
| Web chatbot, upload portal, search and interactive dashboard | Partial | QA UI uses authenticated `/ws/ask` with a processing event and REST fallback; Nginx forwards WebSocket upgrades. Local browser checks verified analyst login, Business analysis filters/database coverage/live cited answer, and admin processing, access and monitoring screens. Live authenticated XLSX upload reached `ready` and its parsed table/formula/chunk data and private Storage bytes were read back. An injected embedding failure on newline-terminated TXT then verified saved-output retry and role-filtered retrieval (analyst sees it, employee does not). Both test fixtures were cleaned and absence verified. Nginx reverse-proxy runtime remains. |
| Retrieval, generation and system evaluation | Incomplete | The refreshed authenticated app suite passes 5/5 source/fact/route/citation/denial checks and a repeated 70-request in-process API load run exists. OCR uses a three-region manually transcribed Tesseract pilot, not a physical scan, and remains too small for model selection. The proposal also requires OCR/layout and document-field quality, semantic human QA review, GPU utilization, deployed scalability, optimization comparisons, and representative business-case/agent workflow evaluation. See the [evaluation master matrix](technical/agents-and-evaluation.md#proposal-evaluation-master-matrix); deployed load and corpus-scale behavior remain unmeasured. |
| Docker/Nginx/CI-CD, monitoring, manuals and research report | Partial | [Deployment guide](deployment-guide.md) and [user guide](user-guide.md) cover current setup. The admin agent-monitoring console and RLS-protected event table exist. Hosted [CI run 36286844731](https://github.com/Lenhan231/enterprise-knowledge-ai-agent/actions/runs/36286844731) passed the 251-test suite, Compose configuration, application image build and Nginx configuration check. The local app health endpoint also returned HTTP 200. This proves build/config validation, not a deployed proxy or production CI/CD release. Production observability, operator walkthrough, deployed proxy/load evidence and final report revision remain. |

### Required handoff deliverables

| Proposal deliverable | Current evidence | Remaining acceptance evidence |
| --- | --- | --- |
| Enterprise AI Agent, RAG QA, chatbot and REST API | FastAPI app, authenticated chat, cited answers, upload/search endpoints and role-filtered retrieval | Stable demo flow covering sign-in, upload/process, search, grounded QA, denial by role and recovery from provider/database errors |
| Document-processing and knowledge database | PDF/Office/image parsers, pre-embedding parser-stage persistence with admin inspection and vector retry, PostgreSQL/pgvector migrations and source-linked metric candidates | Representative real-file quality checks, real scan/OCR/layout labels, and clean setup from migrations plus corpus instructions |
| Multi-agent workflow and business dashboard | LangGraph routes; role-scoped dashboard/analytics and admin monitoring UI | Grounded business-case tasks, user-visible KPI backed by reviewed evidence, route-quality evaluation, and browser verification through deployment proxy |
| Technical documentation, user manual and deployment guide | Technical notes, [user guide](user-guide.md), and [deployment guide](deployment-guide.md) | Walkthrough verified by a new operator; proxy/container and CI/CD run evidence |
| Comprehensive research report | [Evidence-backed draft](research-report.md) covers methodology, architecture, corpus scope, benchmark results, known failures, limitations and prioritized future experiments with links to run artifacts | Complete missing proposal experiments, add blinded human evaluations and deployed runtime evidence, then revise this draft as the final thesis report |

## Proposal technology choices

The proposal names several candidate tools. This prototype records the selected
implementation and the remaining deployment/evaluation work rather than adding
every named package by default.

| Proposal technology | Current implementation | Status / follow-up |
| --- | --- | --- |
| Python, FastAPI, PostgreSQL, pgvector | Python API with Supabase-hosted PostgreSQL/pgvector | Implemented; migrations and role-filtered data paths have tests and selected live checks. |
| LangChain, Hugging Face Transformers, PyTorch | LangChain core interfaces, Sentence Transformers/Hugging Face embeddings; PyTorch is the model runtime | Implemented in retrieval/embedding paths; candidate embedding models remain under evaluation. |
| LangGraph | Conditional multi-agent router | Implemented for knowledge QA, analytics, hybrid, report and dashboard routes; route/task coverage is still partial. |
| PaddleOCR, Docling, Unstructured, PyMuPDF, OpenCV | PyMuPDF native PDF extraction; Tesseract fallback; optional PaddleOCR layout path | PyMuPDF/Tesseract are active. PaddleOCR is optional and not enabled on the normal upload path. Docling, Unstructured and OpenCV are not integrated; the OCR/layout comparison remains incomplete. |
| Docker, Docker Compose, Nginx, WebSocket | Compose web/proxy definitions, Nginx config, authenticated WebSocket QA | App source-only import and local WebSocket were checked; this host has no container engine, so image/proxy runtime and hosted CI result remain unverified. |
| LangSmith, MLflow, Prometheus, Grafana | Privacy-minimized `agent_run_events` and an admin monitoring console | Those four proposal-listed tools are not integrated; current monitoring is application-level, not centralized tracing, experiment tracking or infrastructure metrics. |
| Pytest | Existing regression suite uses Python `unittest` | Tests pass under `unittest`; Pytest is not installed or configured. Treat the proposal's tool list as an implementation choice to resolve, not as evidence of test coverage by itself. |

## Technical notes

- [Document parsing, OCR and tables](technical/document-processing.md)
- [Chunking and section metadata](technical/chunking.md)
- [Embedding model and tokenization](technical/embeddings-tokenization.md)
- [LLM provider and answer evaluation](technical/llm.md)
- [Retrieval and RBAC](technical/retrieval-rbac.md)
- [Agents, dashboard and evaluation](technical/agents-and-evaluation.md)
- [User guide](user-guide.md)
- [Deployment guide](deployment-guide.md)

## Current validation snapshot

- Corpus metadata audit: `uv run python scripts/evaluate_corpus_metadata.py`; latest read-only artifact checks all 25 ready manifest sources (350 document fields and 52,250 chunk fields) with zero propagation mismatches, across 4,750 chunks. This is not automatic extraction accuracy.
- Automated suite: `uv run python -m unittest discover -s tests -q` (**251
  passed on 2026-09-27**; includes processing, evaluation, retrieval, agent,
  API and dashboard checks, including an authenticated HTTP regression proving
  employee upload requests are denied before any Storage/database write).
- Python syntax: `python -m compileall -q src tests scripts`.
- Frontend syntax: `node --check src/app/static/app.js`.
- Hosted CI: commit `56471e2` passed `uv sync --locked`, Python compile, all 251
  unit tests, frontend syntax, Compose proxy configuration, Docker image build,
  and `nginx -t`; see [run 36286844731](https://github.com/Lenhan231/enterprise-knowledge-ai-agent/actions/runs/36286844731).
- Local app: `http://127.0.0.1:8000/health` returned `200 {"status":"ok"}`
  during the same validation session. The proxy was validated in CI but not
  launched as a local or hosted deployment.
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
  role-scoped chunk metadata; their 12-case four-method run is
  `artifacts/evaluation/vinamilk-retrieval-12cases-expanded-corpus-20260927.json`.
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
  consistency and abstention. The refreshed run averaged 26.405 s. This small
  public-corpus smoke does not measure semantic faithfulness or human
  usefulness; exact model behavior and human QA scores remain unreviewed.
- Proposal route evaluation `artifacts/evaluation/proposal-business-route-evaluation.json`
  scored all 12 manually mapped cases through the effective router: 9 direct
  model classifications and 3 correct fallbacks after provider rate limits.
  The pre-prompt direct run misrouted document-count aggregation (11/12); a
  targeted post-prompt direct recheck routed that BI case to analytics. This
  measures routing only, not agent task completion or answer quality.
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
  peak RSS 2,820 MiB. Qwen top-30 on the identical candidate hash remains
  outstanding; host swap is nearly full. This run alone does not select a
  reranker.
- OCR diagnostic `artifacts/evaluation/vinamilk-ocr-tesseract-diagnostic-v3.json`
  records per-page edit counts and macro/micro CER/WER, but uses an unreviewed
  PDF text reference. Manual-label pilots are
  `artifacts/evaluation/vinamilk-ocr-human-reviewed-tesseract.json` (v1, two
  crops) and `artifacts/evaluation/vinamilk-ocr-human-reviewed-tesseract-v2.json`
  (v2, three crops). V2 measured Tesseract only and remains too small for model
  selection; its raster-embedded product poster is not a physical scan. See
  [document processing](technical/document-processing.md).
- Extraction anchor report
  `artifacts/evaluation/vinamilk-document-extraction-scan-table-v9.json` uses five
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
  table anchors; image-upload OCR matches 2/3 normalized table anchors and 3/3
  normalized text anchors.
- Table strategy sweep `artifacts/evaluation/vinamilk-document-extraction-table-strategy-v4.json`
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
- HTTP/browser runtime smoke: local `/` and `/static/app.js` returned 200,
  `/health` returned `{"status":"ok"}`, and Chrome verified analyst sign-in,
  workspace rendering, the Knowledge/Business analysis tabs, and the 2024
  analytics filter. Admin sign-in exposed processing, access and monitoring
  tabs; the processing screen rendered pending source-linked metric evidence and
  upload controls, and Access showed the role permission matrix. These screens
  were inspected without publishing or uploading. No browser console errors
  appeared. The dashboard correctly showed zero verified KPIs and the admin-
  review explanation. The load runner exercised authenticated dashboard/
  analytics routes. Upload submission, review mutation, employee/uploader
  browser flows, and Nginx proxy rendering remain unverified.
- See [`data/README.md`](../data/README.md) for corpus provenance, ingestion,
  and database data flow.
