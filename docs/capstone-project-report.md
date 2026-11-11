# Enterprise Knowledge AI Agent for Business Decision Support

## Capstone project implementation report

- **Vietnamese title:** Xây dựng AI Agent quản lý tri thức doanh nghiệp sử dụng Retrieval-Augmented Generation hỗ trợ hỏi đáp thông minh, phân tích dữ liệu và hỗ trợ ra quyết định
- **Reporting date:** 8 October 2026
- **Project period:** September 2026 – March 2027
- **Project team:** Lê Trọng Nhân (leader), Nguyễn Hoàng Gia Huy, Nông Quốc An
- **Supervisors:** Nguyễn Xuân Huy, Nguyễn Trọng Tài
- **Status:** Commerce-focused prototype implementation report. Proposal-wide evaluation and final acceptance are still in progress.

## Abstract

Organizations store operational knowledge in reports, procedures, manuals, spreadsheets, and scanned documents, while decision data often remains in relational databases. This capstone develops an enterprise knowledge assistant that joins these evidence sources through document processing, role-filtered retrieval, read-only SQL analytics, and a web application. The current demonstrator uses a synthetic e-commerce dataset from Kaggle Datathon 2026 Round 1 and three decision domains: inventory allocation, promotion planning, and nationwide logistics. Public operating guides are attributed external examples; three generated, explicitly fictional policy PDFs exercise the internal-policy and OCR workflow. None of these materials is presented as real retailer policy or transaction history.

The application accepts PDF, Office, text, and image files; extracts born-digital text and tables; applies page-level Tesseract OCR when PDF text is unavailable; stores private originals and parser output; creates searchable chunks; and applies document-role access controls before retrieval. A LangGraph router directs requests to knowledge, analytics, hybrid, report, or dashboard agents. Commerce analytics are read from domain-bounded SQL aggregates rather than hard-coded dashboard values. Decision reports combine cited SQL observations with domain-filtered document evidence and must disclose missing fields when the evidence cannot support an action.

The local prototype has working upload/OCR, document Q&A, RBAC, three SQL-backed dashboard views, and a guarded decision-support path. Admins can choose reader roles at upload and edit them later in Knowledge Management; server-side retrieval applies the saved `documents.allowed_roles` value. A reversible Admin API round-trip confirmed a role update persisted to Supabase and the original roles were restored on an inactive OCR-only test document. The last full unit-suite run passed 773 tests in 91.255 seconds on 8 October 2026 (`PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -q`). After that run, explicit-page retrieval and ROI-validation fixes were added; the complete `tests.test_agents` module passes 209 tests. Live `/api/ask` checks now cite the requested Shopee PDF page 11 with `pymupdf+tesseract`, answer an untemplated inventory decision with SQL plus OCR-policy evidence, and retrieve the promotion policy's OCR-indexed page 2. A separate promotion decision check withheld ROI/incrementality claims and cited an attributed holdout method. The nine-case API replay and later targeted reviews verify mechanical and deterministic-fallback behavior, not provider-generated answer quality. Groq was rate-limited and Hugging Face returned HTTP 402 during recent checks. OCR scores remain based mainly on generated scans with authored references; the public Shopee guide is a PowerPoint export, not a physical scan or complete page ground truth. This report distinguishes verified behavior from open proposal requirements.

**Keywords:** enterprise knowledge management, retrieval-augmented generation, OCR, role-based access control, SQL analytics, decision support, e-commerce.

## 1. Introduction

### 1.1 Background and problem

Enterprise knowledge is distributed across unstructured files and structured business systems. Keyword search can find matching words but does not by itself preserve document context, enforce user-specific access, reconcile a table with its headers, or combine a policy with current business observations. A language model without retrieved evidence may also state unsupported facts or recommendations.

The project proposal therefore calls for document parsing and OCR, metadata-aware chunking, a PostgreSQL/pgvector knowledge base, hybrid retrieval, multiple specialized agents, role-based access control, analytics, dashboards, and evaluation of retrieval and generation. The current capstone demonstrator narrows the business example to a Commerce schema so the complete path can be exercised with a manageable dataset.

### 1.2 Objectives

The implementation objectives are to:

1. Ingest heterogeneous enterprise-style files and preserve page, section, layout, and source metadata.
2. Make parsed content searchable with role- and domain-scoped retrieval.
3. Answer document questions with source citations and abstain when evidence is insufficient.
4. Query Commerce data using bounded, read-only SQL and present aggregates in an interactive dashboard.
5. Combine structured observations with retrieved operating methods for conditional decision support.
6. Inspect parser output and manage knowledge files through an authenticated web interface.
7. Evaluate the implemented slice and document the boundary between verified behavior and remaining proposal work.

### 1.3 Scope and data boundary

The Commerce transaction and operations records are synthetic competition data. They are not observations from a real retailer. The current prototype covers inventory allocation, promotion planning, and nationwide logistics. The active knowledge corpus includes public management and operating references plus three generated, fictional Commerce Demo policies. Public company practices and platform rules are attributed to their issuers and are not represented as policy for the synthetic dataset.

The dashboard reads the private `commerce` PostgreSQL schema. Uploaded documents provide question-answering and decision-method context; they do not create or modify dashboard observations. The current slice is a local prototype, not a production deployment. Hosted infrastructure and proposal-wide model comparisons are outside the verified implementation described here.

## 2. Technical background

### 2.1 Retrieval-augmented generation

Retrieval-augmented generation (RAG) combines parametric language generation with retrieved non-parametric knowledge. The original RAG formulation by Lewis et al. evaluates this architecture on knowledge-intensive language tasks [1]. In this project, retrieval supplies passages from the authorized corpus, while citations expose where an answer came from. The application also uses SQL evidence for live Commerce observations; SQL results and document passages remain distinct evidence types.

### 2.2 OCR and layout-aware document processing

Scanned pages contain pixels rather than a usable text layer, so OCR is required before chunking and retrieval. Tesseract is the current default OCR engine for page-level fallback [2]. The parser records the extraction method, page number, and available layout metadata so users can inspect output against the original source page. Native PDF text and OCR text are handled separately to avoid replacing readable source text unnecessarily.

### 2.3 Vector search and orchestration

PostgreSQL stores document metadata and chunks; pgvector supports vector similarity search within the database [3]. The application combines dense and lexical retrieval with role, active-document, source-class, and domain filters. LangGraph's `StateGraph` provides the request-routing structure [4]. For Commerce decisions, `ReportAgent` coordinates `SQLAnalyticsAgent` and `KnowledgeAgent` sequentially: it obtains bounded SQL observations, retrieves role- and domain-filtered references, then validates and synthesizes the cited evidence. The top-level graph still routes each request to one execution path; general multi-step handoffs between agents and proposal-wide comparative agent evaluation remain unimplemented.

## 3. System design

### 3.1 End-to-end architecture

```text
Admin / seed source
        │
        ├── private file storage (user uploads)
        │
        ▼
Format dispatch ──> PDF text/layout + page-level OCR fallback
        │              Office / text / image processors
        ▼
Parser chunks + structured tables + provenance metadata
        │
        ├── document_parser_chunks (model-neutral parser output)
        └── chunking → token counting → embedding → document_chunks
                                              │
User question ─> authenticated router ─> ACL/domain-filtered retrieval
                                      ├── KnowledgeAgent ─> cited answer
                                      ├── ReportAgent ────> bounded SQL + RAG
                                      ├── SQLAnalyticsAgent
                                      └── DashboardAgent ─> Commerce aggregates
```

The ingestion and retrieval boundaries are documented in the repository's [document-processing guide](../src/document_processing/docs/document-processing.md), [retrieval and RBAC guide](technical/retrieval-rbac.md), and [Commerce agent guide](technical/agents-and-evaluation.md).

### 3.2 Document ingestion and data model

The upload endpoint accepts PDF, DOCX, PPTX, XLSX, CSV, TXT, Markdown, PNG, JPEG, and TIFF. CSV files are parsed into structured rows and searchable row-aware text. Original user files are stored in a private Supabase Storage bucket. PostgreSQL keeps the document record, processing state, role assignments, and parser/index metadata. `document_parser_chunks` stores parser output independently of embedding configuration; `document_chunks` stores the active retrieval representation and vector. Structured table data is persisted separately from its retrieval text so that a table can remain inspectable as rows and columns without embedding an opaque JSON object as a single passage.

For PDFs, PyMuPDF extracts usable text and tables. Pages without usable text can fall back to Tesseract (`vie+eng`). Native-text table extraction and OCR-word-box reconstruction retain page and bounding-box context where available. DOCX, PPTX, and XLSX are parsed from Open XML. Chunking and token limits are applied before embedding; model-neutral parser output allows future embedding experiments without repeating document parsing.

### 3.3 Security and access control

The application exposes demo roles including Viewer, Analyst, Tester, Document Uploader, and Admin. The upload route requires a role with upload permission and at least one permitted document role. Admins can change reader roles on existing indexed files through Knowledge Management. Retrieval applies document access controls and knowledge-base activation filters server-side before ranking. Tester OCR runs use a separate test persistence path and are not added to the production knowledge corpus. Admins can also inspect parser results and deactivate or restore a source from retrieval through Knowledge Management.

### 3.4 Agent routing and decision workflow

The LangGraph router classifies the request and dispatches it to a specialized path:

- **KnowledgeAgent** handles document-only questions using role- and domain-filtered sources.
- **SQLAnalyticsAgent** produces bounded analytics from approved Commerce tables and columns.
- **ReportAgent** combines structured SQL observations with retrieved operating references for business questions.
- **DashboardAgent** supplies the chart series and source-backed aggregate used by the dashboard.
- **HybridAgent** handles requests that require both document and structured evidence.

Commerce SQL is read-only and restricted to domain allowlists. Generated SQL is parsed and validated before execution, with row and time limits. When a model provider is unavailable or generates invalid SQL, the system uses a bounded deterministic fallback or reports a schema gap. Answers distinguish observed data from external methods and synthetic demo rules. A source citation is not treated as proof that a recommendation is profitable. OCR-derived source text is not quoted by deterministic fallback unless verified against the original page.

## 4. User interface and dashboard

The FastAPI web application provides a document Q&A workspace, a Commerce dashboard, Admin knowledge management, parser/OCR inspection, access control, and monitoring. The upload form previews the Q&A destination, selected reader roles, optional decision-support domains, and any missing classification fields before submission. Admins can edit reader roles on indexed documents without reprocessing or re-embedding their chunks. The Analyst dashboard has separate views for inventory allocation, promotion planning, and nationwide logistics. Each view loads curated aggregates from the selected domain. Dashboard indicators are computed from SQL queries rather than fixed UI constants.

The dashboard supports trend and category/region comparisons available in the source schema. Current readback includes 11 annual sales-context rows, 21 promotion rows, and 33 logistics region-year rows. Promotion comparisons are observational: the data does not prove causal lift or return on investment. The logistics schema does not include route, carrier, warehouse, capacity, or promised delivery SLA. Inventory flags do not identify SKU-level surplus/shortage at paired locations, lead times, or transfer costs. These gaps constrain the actions the agents can responsibly recommend.

After upload, Admins are taken to the saved parser output to inspect chunks and tables. The OCR Lab compares source-page rendering with extracted text and structured table output using isolated test records. It is a document-processing review surface, not a business evidence source.

## 5. Evaluation and results

### 5.1 Software verification

On 8 October 2026, the last full regression suite passed 773 tests in 91.255 seconds (`PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -q`). After that run, all 209 agent tests passed following explicit-page retrieval and ROI-validation changes. Provider rate-limit and connection-error logs exercise fallback paths and are not evidence of model-generated quality. Current live Analyst, upload, OCR, and Admin API checks are listed in the [Commerce status guide](commerce-decision-support.md); historical runs should be interpreted with their provider and fixture limitations.

These tests establish implementation behavior for covered cases. They do not establish the quality of every model-generated answer or prove the whole proposal is complete.

### 5.2 OCR and parser checks

The active OCR fixtures include three generated image-only policy PDFs and a degraded two-page table fixture. On 8 October 2026, the nine active-policy pages were reprocessed through the upload parser and achieved micro-CER 0.003297 and WER 0.014558 against authored reference text, at a mean 5.527 seconds per page ([run artifact](../artifacts/evaluation/document-pipelines/results/ocr/legacy-engine-runs/commerce-active-policy-scan-ocr-20261008.json)). References omit the page-counter footer because the parser intentionally removes it. These values measure the generated fixture pipeline; they are not estimates of OCR accuracy on real business scans.

A separate fresh run of the clean two-page scan fixture achieved 0 CER/WER, 3/3 table rows, 9/9 exact values, and 3/3 exact headers; the stricter evaluator rejects values that contain extra OCR text ([run artifact](../artifacts/evaluation/document-pipelines/results/ocr/legacy-engine-runs/commerce-synthetic-clean-scan-current-after-quality-guard-20261008.json)). This is a useful upload-parser demonstration, not evidence of physical-scan accuracy.

On 8 October, synthetic regression coverage was added for a three-degree skewed scan. The upload path estimates and corrects small page skew before text and table OCR, records the chosen angle, and maps extracted table bounding boxes back to source-page coordinates. The test requires lower character error than the uncorrected path and checks that all four table columns and their cell boxes remain available after correction. This verifies the implemented case only; it does not establish performance on physical scans or justify arbitrary-angle correction.

The PDF processor now honors an OCR-language override while keeping `vie+eng` as the web-upload default. The evaluator passes the source language for each labeled fixture and records the setting. English clean and degraded synthetic scans each scored 0 CER/WER and recovered 9/9 numeric table cells; these authored fixtures demonstrate correct language configuration, not general OCR accuracy. On one real-source embedded screenshot, the same English configuration still recovered only 3/6 numeric cells at 3.5× and is not sufficient for business extraction. Mixed-page handling now inspects large embedded images even when native text is present, but rejects OCR when mean Tesseract word confidence is below 60/100. The Sam's Club page's screenshot crop scored 26.3/100, so a fresh parser run retained its native text and emitted no OCR chunk or structured table. This is safe abstention, not successful table extraction. The 3/6 score came from manually rasterizing the screenshot crop and remains diagnostic rather than end-to-end upload evidence; forced full-page OCR still yielded no structured table. A clean synthetic mixed-page fixture verifies native-text preservation and all three labeled table rows; a low-confidence regression verifies rejection. A Tester OCR Lab upload of the public PDF's page 7 saved the rejected-region diagnostic (26.3/100 against a 60/100 threshold) with its parser chunk, returned the page preview over HTTP 200, and created no production document or embedding. This verifies upload-to-isolated-persistence and review payload, not table recovery or browser-rendered appearance. The 62 focused PDF/document-processor tests passed on 8 October 2026.

A manually reviewed and rasterized page from the public 2019 Shopee Uni inventory guide yielded 4/4 screenshot phrase anchors with PSM 11 and PSM 3 at scale 1.5; PSM 11 at scale 1.5 was the faster of those full-recall settings. Two selected regions on that page were then visually transcribed by one reviewer and rasterized to force OCR: the heading/instruction and replenishment-status callouts scored micro-CER 0.015873 and micro-WER 0.041096 under current upload settings. This measures the selected regions only; it is not a full-page transcription, an independently adjudicated reference, a physical scan, or evidence for a general engine-setting choice. The parsed public guide has persisted OCR passages across 11 of its 17 pages; its seller-center screenshot text still requires page-level review.

The OCR/upload API has been exercised with a generated degraded scan. A read-only audit of the live Commerce schema found three parser/index passages for the test upload, including one row-aware table passage with four named columns and three rows; all three indexed passages have embeddings. The same table is stored separately as structured rows for inspection, and the persisted source bytes matched the uploaded SHA-256. A read-only headless Firefox Admin session loaded that saved document in Processing and rendered its three passages, all four table columns and three rows, and links to each of its three source pages. At 500 pixels, the table remained readable within the page without horizontal overflow. The explicitly labeled `[OCR test only]` document is inactive for retrieval. At the time of this first check, active Commerce guidance had no persisted structured tables; a later parser fix and targeted reindex of the active IAB incrementality PDF are recorded below. The upload form itself was not submitted through the browser in this check. The later IAB reindex persisted three tables (13 rows) from pages 3–5 and added ten row-aware table chunks; a live readback confirmed the document remained active and kept its existing role list. A BM25 retrieval smoke for promotion measurement ranked the page-4 comparison-matrix chunks first for an employee role. The source is born-digital guidance, so this does not validate scanned table OCR.

A separate authenticated live-API readback on 7 October 2026 verified an existing Admin-only upload of the degraded scan fixture. The stored original returned HTTP 200 and its SHA-256 matched the two-page image-only fixture (zero native text characters; one raster image per page). The parser endpoint returned three Tesseract passages, all with `embedded` status and no processing error, plus one structured table whose four columns and three rows matched the synthetic reference exactly. The document remains inactive for retrieval and visible only to Admin. The matching OCR evaluation run recorded overall micro-CER 0.000831, micro-WER 0.010309, and 9/9 exact numeric cells for the same PDF bytes ([evaluation](../artifacts/evaluation/document-pipelines/results/ocr/legacy-engine-runs/commerce-degraded-scan-current-20261007.json)). This verifies the stored-source-to-parser/index readback path for this fixture; it is not an independently reviewed physical scan or a fresh browser-form submission.

On 8 October, an isolated headless Firefox Tester session reviewed the persisted Sam’s Club screenshot run and the two-page synthetic degraded-scan run. At a 1440-pixel viewport, the OCR Lab displayed the source page above the extracted output, text chunks before structured tables, and the 26.3/100 OCR rejection beside its 60/100 threshold. The successful fixture displayed its four named columns and three extracted rows beneath its page text. The source-page previews loaded in the UI. This verifies the review layout and both successful extraction and safe abstention states; the structured rows are synthetic, not Commerce database records.

An earlier Admin-only copy of the same fixture failed when Hugging Face Inference returned HTTP 402 during embedding; its OCR passages and structured table remained saved. The Admin Knowledge Management UI now offers an embedding-only retry for failed user uploads, guarded by the existing `manage_knowledge` permission and same-origin check. On 7 October 2026, the saved parser output for `UPLOAD-23d8e8bb2c574943b089b14eb15ffc26` was retried through the live API with local embeddings: the document returned to `ready` with three indexed passages, all three parser passages reported `embedded`, and the extracted table remained present. The original private PDF still returned 234,323 bytes with SHA-256 `86383a8a65d42791d05549369dcd9f3ebc0b597b846ca7fa06e351e8a1c9fd7d`, matching the fixture. Its reader ACL remained Admin-only and `knowledge_base_active` remained false. This verifies embedding recovery without rerunning OCR, changing access, or activating the test source.

An Admin UI inspection of a persisted three-page, image-only inventory-policy upload found five saved Tesseract passages across pages 1–3, page-specific links to the original PDF, and visible OCR/parser metadata. Fetching the linked original returned HTTP 200 with `application/pdf` (2,325,065 bytes). The source was marked removed from Q&A, so this inspection did not make the fixture available to decision retrieval. It verifies that the UI exposes saved output and provenance for this upload; it does not establish OCR accuracy on a physical scan.

On 8 October, an Admin submitted the same three-page image-only policy through the browser Upload Documents form, classified it as synthetic inventory guidance, and restricted its reader ACL to Admin. The UI reported `ready`, 5 parser passages, 5 indexed passages, 5 OCR passages, and 0 tables, then opened those saved passages in Document Processing with a page-specific original-PDF link for each. An authenticated readback confirmed pages 1–3, Tesseract extraction, HTTP 200 for the stored original, and an exact SHA-256 match to the submitted PDF. Knowledge Management then marked this upload inactive; it remains an Admin-only test record and is not used for retrieval. This closes the earlier browser-form submission gap for the synthetic scan path, but does not establish accuracy on an independently reviewed physical scan.

### 5.3 Retrieval and agent checks

The repository contains nine SQL-plus-RAG decision cases: three per Commerce domain, plus a 12-case document-retrieval relevance set. Dense, BM25, Hybrid, and Parent retrieval have been compared on a fixed snapshot. A fresh authenticated Admin replay through `POST /api/ask` on 8 October completed all nine cases: 9/9 mechanical checks, citation/domain checks, required numeric coverage, and all six applicable gold-observation associations passed ([run](../artifacts/evaluation/agents/commerce-decision-support-live-20261008-provider-fallback.json)). Groq returned HTTP 429 and Hugging Face returned HTTP 402; all nine final answers therefore came from deterministic fallbacks, not model-generated synthesis. Only one case produced question-specific SQL; other cases used the bounded domain snapshot or declared an unavailable measure/dimension.

I reviewed all nine fallback answers against the benchmark observations and decision limits. The displayed inventory and promotion values matched their gold rows; the answers withheld unsupported inventory transfers, service targets, promotion ROI/budget increases, and logistics redesign, and did not invent thresholds or causal effects. This is a single reviewer check of deterministic fallback behavior, not an independent human evaluation or evidence of provider-generated answer quality. Semantic review with available providers and a second human reviewer remains open.

After the SQL fallback formatter was corrected to accept the live `group_category` alias and calendar-year labels, two authenticated requests to the running `/api/ask` route returned HTTP 200. Groq answered an inventory-category question in Vietnamese with the `Nhóm hàng` label and Streetwear's 134 stockout flags; the logistics trend used deterministic fallback and described 2020–2022 endpoints as `Năm`, without implying causality. The SQL-fallback alias path is covered by a regression test; the successful Groq response did not exercise that fallback branch. These are two targeted checks, not a nine-case semantic review.

A fresh out-of-benchmark reallocation question on the running Admin API returned HTTP 200 while the provider was rate-limited. The deterministic answer now cites the latest snapshot and ranks the highest stockout and overstock category counts separately (Streetwear: 134 and 162), labels them as review cues, and withholds transfer advice until SKU/location demand, lead time, cost, capacity, and service constraints are available. The aggregate overlap count is cited separately; these rows are not treated as distinct incidents or transferable inventory. This check exercises one more unseen question, not general language coverage.

### 5.4 Dashboard checks

Authenticated Analyst API checks returned HTTP 200 for all three dashboard domains in this session: inventory returned 11 annual, 11 inventory, and 44 year-end category rows; promotions returned 11 annual and 21 promotion rows; logistics returned 11 annual and 33 region-year rows. A fresh Selenium/Firefox UI run rendered all three dashboard views at 1440 pixels without page-wide horizontal overflow. The workspace navigation is a persistent left sidebar on desktop and a two-column menu above the content at 500 pixels; all eight Admin tabs fit at both widths. The Commerce domain navigation is a left rail on desktop and horizontal tabs at mobile width; its arrow-key behavior follows the current orientation, and each domain renders its data rows and chart. The Analyst UI exposes only Knowledge Q&A and Commerce Dashboard. Values are synthetic and descriptive. The dashboard must not be interpreted as actual retailer performance or as causal proof for promotion actions.

## 6. Proposal coverage and remaining work

| Proposal area | Current implementation | Remaining work before a complete claim |
| --- | --- | --- |
| Multi-format document management | Authenticated upload, private file storage, parsing, chunking, metadata, Admin inspection | Test representative physical scans and validate image/diagram/formula extraction where required |
| OCR and layout analysis | PyMuPDF native text plus Tesseract fallback; optional Paddle layout path; structured table persistence | Human-reviewed ground truth for real scanned pages and cross-engine comparison on a balanced corpus |
| RAG and hybrid retrieval | Dense, BM25, Hybrid and Parent paths; source/domain filters; citations and RBAC | Larger passage-level relevance labels and full proposal-scale retrieval evaluation |
| Specialized agents | Router dispatches to knowledge, SQL analytics, report, hybrid and dashboard paths; `ReportAgent` coordinates SQL and knowledge specialists for Commerce decisions | General multi-step LangGraph handoffs and proposal-wide agent comparison are not implemented |
| SQL analytics and business support | Read-only, domain-bounded SQL; dashboard aggregates; SQL-plus-RAG report fallback; one reviewer checked all nine deterministic fallbacks against gold observations and decision limits | Independent/provider-backed answer-quality review; add schema fields needed for stronger inventory, promotion and logistics actions |
| Interactive dashboard | Three domain views backed by Commerce SQL | Business meanings remain limited by synthetic data and missing operational dimensions |
| Evaluation | Unit/integration coverage, OCR fixtures, retrieval cases, decision cases | Provider-backed generation evaluation, human answer-quality scoring, broader model benchmarks, latency/throughput/scalability and GPU measurements |
| Deployment and operations | Local FastAPI application and optional database container profile | Proposal-listed Docker/Nginx/CI deployment pipeline is not implemented as a verified hosted deployment |

The most important limits are data and evaluation, rather than a missing chart. Inventory data is aggregate-level; promotion data lacks experimental controls and full campaign economics; logistics aggregates do not identify physical routes or carrier performance. Until those data are available, the agent should give conditional guidance, identify missing evidence, or abstain instead of inventing thresholds.

## 7. Conclusion

The Commerce demonstrator implements a connected path from document ingestion to OCR and parsing, role-filtered retrieval, SQL analytics, decision-oriented answers, and a dashboard. Its key design boundary is explicit: SQL supplies synthetic Commerce observations; public PDFs supply attributed methods or issuer-specific rules; generated policy PDFs are fictional test artifacts. This separation lets the application demonstrate how document knowledge can inform a business question without pretending that external examples are internal policy.

The prototype is suitable for continued capstone development and supervised demonstration. The available evidence does not justify calling it a completed proposal evaluation or a production-ready decision system. The next acceptance work is to review OCR on representative physical scans, complete human-reviewed answer evaluation, and close the remaining agent and model benchmark requirements. A read-only database audit on 7 October 2026 confirmed zero orphan document chunks, zero orphan extracted tables, and zero remaining Vinamilk documents or chunks; the earlier legacy-data cleanup is complete.

## References

1. P. Lewis et al., “Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks,” *Advances in Neural Information Processing Systems 33*, 2020. [https://doi.org/10.48550/arXiv.2005.11401](https://doi.org/10.48550/arXiv.2005.11401).
2. Tesseract OCR, *Tesseract User Manual*. [https://tesseract-ocr.github.io/tessdoc/](https://tesseract-ocr.github.io/tessdoc/).
3. pgvector contributors, *pgvector: Open-source vector similarity search for Postgres*. [https://github.com/pgvector/pgvector](https://github.com/pgvector/pgvector).
4. LangChain, *LangGraph Graphs reference: StateGraph*. [https://reference.langchain.com/python/langgraph/graphs](https://reference.langchain.com/python/langgraph/graphs).
5. *Enterprise Knowledge AI Agent using Retrieval-Augmented Generation for Intelligent Question Answering, Data Analytics and Business Decision Support*, capstone project proposal, September 2026.

## Reproduction commands

Run the application locally:

```bash
PYTHONPATH=src uv run uvicorn app.main:app --reload --env-file .env --port 8000
```

Run focused upload/OCR and agent checks:

```bash
PYTHONPATH=src uv run python -m unittest tests.test_document_processor tests.test_pdf_upload_processing tests.test_upload_processing_flow -q
PYTHONPATH=src uv run python -m unittest tests.test_agents -q
```

Replay the Commerce decision cases when model-provider quotas are available:

```bash
PYTHONPATH=src uv run python tools/agents/evaluate_commerce_decision_support.py
```
