# Proposal coverage and technical guide

This page tracks the capstone proposal against the current prototype. A row is
complete only when the linked implementation and evidence cover the stated
requirement; a passing unit test alone does not establish end-to-end coverage.
Use the technical notes below for current settings and data flow.

**OCR result correction:** v6 visual review found that the two image-only
governance scan crops in v3–v5 omitted printed text included in the references.
Their scan-page CER/WER and all-page aggregates are superseded. The unchanged
v5 financial-table crop and its cell/row-only diagnostics remain valid. V6 has
corrected crops and Tesseract, EasyOCR, Surya and PaddleOCR now have
hash-matched v6 reports on six pages. Their CER/WER are 0.325961/0.259207,
0.176672/0.361190, 0.071090/0.143059 and 0.088994/0.209632; CPU hosts
differ, and Surya is slow on CPU. No production winner is claimed.
Only hash-matched v6 reports may be compared.

| Proposal requirement | Status | Evidence / remaining work |
| --- | --- | --- |
| Regression suite | Verified locally | `uv run python -m unittest discover -s tests -q` passed 422 tests on 2026-09-28. This is repository regression coverage only; it does not close proposal rows whose live/provider or human-review evidence is still pending. |
| Enterprise document Q&A with grounded citations | Partial | [RAG and agents](technical/agents-and-evaluation.md); small live corpus and retrieval checks exist. Expand QA cases and evaluate answer quality. |
| PDF, Word, Excel, PowerPoint, scans and images | Partial | [Processing](technical/document-processing.md); PDF/DOCX/XLSX/PPTX/TXT/MD/images parse; DOCX table chunks keep column labels and row relationships for RAG while preserving structured review tables. A live one-fixture DOCX upload/Storage/table-readback and analyst-vs-employee retrieval smoke passed and cleaned up its data ([artifact](../artifacts/evaluation/vinamilk-docx-table-live-e2e-20260928.json)). Office ZIP expansion is bounded. Legacy XLS, paired OCR across real scans, broader real-file tests and user verification remain. |
| Layout, tables, figures, invoices, formulas, metadata | Partial | XLSX formulas and DOCX Office Math text runs are included in retrieval chunks with parser metadata; PDF tables persist as structured rows. Optional Paddle parsing now supports chart and formula recognition (`DOCUMENT_PADDLE_FORMULA_RECOGNITION=true` also enables layout) and retains returned text/LaTeX, page coordinates and labels. It remains off by default and has adapter-mock coverage only; real formula extraction and chart accuracy are unmeasured. The latest [manifest metadata audit](../artifacts/evaluation/vinamilk-corpus-metadata-audit-access-policy-20260928.json) checks 26 ready sources (4,753 chunks, 52,283 chunk-field checks) with no metadata mismatches. The [multi-year extraction diagnostic](../artifacts/evaluation/vinamilk-document-extraction-multiyear-v3-20260928.json) visually checks 11 financial anchors on five report pages: born-digital rule candidates match 11/11 with 1.00 precision; synthetic Tesseract raster conditions match exact text anchors 1/11 and normalized text/table anchors 3/11 each. It is a small diagnostic, not broad OCR accuracy evidence. Paired real-scan/layout labels, formula accuracy/equation evaluation, generated figure captions, invoices and representative multi-format quality evaluation remain. |
| Semantic/context-aware chunking and parent-child retrieval | Partial | [Chunking](technical/chunking.md); seed-PDF and upload paths share configurable sentence/paragraph-aware chunks with a fixed-overlap baseline and tokenizer bound. Numbered OCR headings now produce `section_title`; exact-content metadata-only backfills updated 388 chunks across eight governance reports without changing vectors/ACL. The 25-document corpus now has 4,666/4,750 titled chunks; 84 remain null, while persisted section hierarchy and paired answer-quality evaluation remain open. After correcting the 2022 net-revenue reference to audited income-statement chunks, a five-year diagnostic has 1,912 fixed vectors and 1,979 alternate chunks: passage MRR 0.2615/0.2626. The case hash differs from older runs, and sentence labels remain heuristic, so this is not evidence of improvement. Seven annual/sustainability PDFs could not be safely backfilled because reparsed chunk counts differed. See the [corrected-label diagnostic](../artifacts/evaluation/vinamilk-chunking-retrieval-source-reviewed-20260928.json), [corpus coverage audit](../artifacts/evaluation/section-title-corpus-coverage-post-backfill-20260928.json), [2020–2024 governance apply audit](../artifacts/evaluation/section-title-backfill-governance-2020-2024-applied.json), [earlier scan audit](../artifacts/evaluation/section-title-backfill-governance-scans-applied.json), [native report audit](../artifacts/evaluation/section-title-backfill-cgr-2025-applied.json), and [annual/sustainability dry-run](../artifacts/evaluation/section-title-backfill-annual-sustainability-dry-run-20260928.json). |
| Five proposal benchmark groups | Partial | OCR v6 compares Tesseract/EasyOCR/Surya/PaddleOCR on six hash-matched labeled regions; their CER is 0.325961/0.176672/0.071090/0.088994. A local hash replay verifies three Tesla T4 embedding reports covered all 4,750/4,750 chunks with identical inputs; BGE-M3/Qwen3/e5 document MRR is 0.7759/0.8028/0.7583. A paired Tesla T4 top-30 reranker run now covers 12 identical cases/candidates: passage MRR BGE 0.5167 vs Qwen 0.4348; document MRR BGE 0.8958 vs Qwen 0.9583. Both label sets are sparse; no model winner is selected. Exact proposal LLM checkpoints and blinded human answer-quality review remain incomplete. See [benchmark acceptance](technical/agents-and-evaluation.md#proposal-acceptance-checklist), [OCR comparison](../artifacts/evaluation/vinamilk-ocr-four-engine-v6-cpu-comparison.json), [embedding audit](../artifacts/evaluation/vinamilk-embedding-three-model-full-corpus-hash-verified-20260928.json) and [paired reranker report](../artifacts/evaluation/vinamilk-reranker-kaggle-top30-paired-20260928.json). |
| Other proposal evaluation requirements | Partial | See the [acceptance checklist](technical/agents-and-evaluation.md#proposal-acceptance-checklist) for extraction, retrieval/generation quality, system performance, optimization and all 12 business cases. The authenticated app evaluator checks routes, citations, unsupported-case abstention, financial facts and dynamic BI result shape. Selected earlier business-case batches pass invoice/manufacturing (2/2), customer-service/technical (2/2), compliance (1/1), HR and abstention cases, but those artifacts omit the model ID and are not model-specific benchmark evidence. A current model-provenanced GPT-OSS-20B BI run passes 1/1 ([artifact](../artifacts/evaluation/proposal-business-app-gptoss20b-bi-provenance-20260928.json)). Focused employee access, customer-service and finance QA artifacts record Qwen3.8 explicitly. The 2024 headline financial summary is now routed through the guarded Report agent, and English retrieval is augmented with the report's Vietnamese KPI labels. The [pre-change live run](../artifacts/evaluation/proposal-business-app-financial-post-20260928.json) selected differently labelled statement values. The [post-change retrieval audit](../artifacts/evaluation/vinamilk-financial-summary-retrieval-post-query-rewrite-20260928.json) places headline KPI passages on pages 12 and 2 in the top five; the [post-change report attempt](../artifacts/evaluation/proposal-business-app-financial-report-guarded-20260928.json) returned HTTP 429, so the fix still needs a passing live answer. A fresh executive run reached report generation but cited a relevant 2025 sustainability report omitted from the previous gold-source list and stated inferred risks as report conclusions. The gold labels now include that official source, and the report prompt distinguishes documented initiatives from unsupported alternatives/risks; the post-change rerun hit HTTP 429, so no passing answer is claimed. Human QA, private-domain evidence and representative local performance measurements remain incomplete. |
| Retrieval baseline on refreshed corpus | Evaluated, preliminary | All four proposal methods were rerun twice on the live snapshot of 25 ready Vinamilk documents/4,750 chunks with 12 cases and 24 selected passage labels, including three governance cases. A third run after section-title backfills reproduced the exact per-case rankings and document/passage/context metrics. Hybrid passage MRR is 0.464; dense 0.412 and BM25 0.403; parent context MRR is 0.469. Latency varied between runs, and sparse labels preclude a winner claim. See the [post-backfill run](../artifacts/evaluation/vinamilk-retrieval-post-section-title-backfill-12cases-20260928.json), [first run](../artifacts/evaluation/vinamilk-retrieval-live-12cases-20260928.json), and [repeat](../artifacts/evaluation/vinamilk-retrieval-live-12cases-repeat2-20260928.json). |
| Proposal business cases and corpus diversity | Partial | Current corpus contains 26 public Vinamilk sources, including the official Vinamilk Shop returns policy and the Code of Conduct's employee access clauses. The 12-case source-coverage audit classifies 2 tasks supported, 6 partial and 4 unsupported; selected routed tasks have authenticated end-to-end runs, but full case completion is not established. The dedicated Information System Policy, general invoice policy, private HR details, executed contracts, manufacturing and server instructions remain absent. RBAC labels are synthetic demo controls over public documents. |
| Enterprise prompt, metadata-aware reasoning and knowledge ontology | Partial | Metadata-aware role filtering, grounded prompts, bounded parent-context retrieval and a bilingual finance KPI ontology exist. Full enterprise entities/domains, persistent hierarchy, query rewriting and context compression need implementation and evaluation. Instruction tuning is optional in the proposal. |
| Secure PostgreSQL/pgvector knowledge base | Partial | [Retrieval and RBAC](technical/retrieval-rbac.md); role filtering is applied before candidate ranking. The active company is read from `data/vietnam_enterprises/manifest.json` and scopes dashboard, analytics, upload, QA and KPI review writes; existing out-of-manifest FPT rows remain stored but are excluded from this Vinamilk demo. The 2026-09-28 read-only integration check verifies exact local/remote migration history (13/13) and vector schema/repository mapping across 5,052 rows. A fresh full manifest audit after employee access ACL re-index finds 26/26 ready documents and 0 metadata mismatches over 4,753 chunks/52,283 fields ([artifact](../artifacts/evaluation/vinamilk-corpus-metadata-audit-access-policy-20260928.json)). A five-account live API matrix confirms employee 3 docs/analytics denied, finance 7, sustainability 11, admin 26, and uploader 0 visible docs/upload allowed ([artifact](../artifacts/evaluation/vinamilk-dashboard-rbac-live-api-20260928.json)). A live finance-query BM25 probe confirms no employee candidates and finance-only annual-report passages, all matching stored ACLs ([artifact](../artifacts/evaluation/vinamilk-live-retrieval-rbac-isolation-20260928.json)). It does not establish private-document isolation or rendered-browser behavior; those checks remain. |
| Multi-agent QA, analytics/SQL, report, dashboard | Partial | [Agents and evaluation](technical/agents-and-evaluation.md); LangGraph routes current intents. Analytics generates bounded SELECT SQL over role-filtered CTEs, with AST validation, read-only execution and source citations. Financial chart requests now render role-filtered verified observations as a year trend only when periods and units are unambiguous. A fresh authenticated read-only audit on 2026-09-28 found 7 verified observations and 29 pending candidates; all seven published observations matched the cited official PDF page on metric label, year, amount, and unit ([source audit](../artifacts/evaluation/verified-financial-metric-source-audit.json)). Parser-only reruns added nine FY2021 and 18 FY2022–24 candidates. The FY2021 total consolidated revenue of 61,012 billion VND and the FY2022–24 comparison-table values remain pending review. See the [FY2021 parser artifact](../artifacts/evaluation/vinamilk-financial-candidates-2021-column-aligned-20260928.json), the [FY2022–24 parser artifact](../artifacts/evaluation/vinamilk-financial-candidates-2022-2024-column-aligned-20260928.json) and the earlier [analytics/RBAC smoke](../artifacts/evaluation/vinamilk-live-analytics-rbac-smoke-20260928.json), whose metric counts are superseded by the fresh audit. One FY2020 profit value was corrected against the cited annual-report page after a thousands-separator input error. Selected source-grounded invoice and BI app cases now pass; domain-wide multi-source BI analysis and admin review of pending KPI candidates remain. Admin monitoring reads privacy-minimized Supabase traces. |
| Web chatbot, upload portal, search and interactive dashboard | Partial | QA UI uses authenticated `/ws/ask` with a processing event and REST fallback; Nginx forwards WebSocket upgrades. Local browser checks verified analyst login, Business analysis filters/database coverage/live cited answer, and admin processing, access and monitoring screens. Live authenticated XLSX upload reached `ready` and its parsed table/formula/chunk data and private Storage bytes were read back. An injected embedding failure on newline-terminated TXT then verified saved-output retry and role-filtered retrieval (analyst sees it, employee does not). Both test fixtures were cleaned and absence verified. Local authenticated WebSocket and hosted Docker/Nginx reverse-proxy runtime checks passed in CI; broader browser QA remains; Render/Vercel hosting is out of scope. |
| Retrieval, generation and system evaluation | Partial | The last complete finance/product/sustainability/RBAC QA suite passed 5/5; focused employee return-policy and FY2024 financial cases separately passed 1/1 each with Qwen3.8 ([customer-service artifact](../artifacts/evaluation/customer-service-employee-qwen38-20260928.json), [finance artifact](../artifacts/evaluation/finance-2024-qwen38-20260928.json)). A repeated 70-request in-process API load run exists. OCR v6 has hash-matched reports for four engines on six labeled regions; v7 adds four reviewed English physical-scan regions and a hash-replayable Tesseract expansion. Vietnamese physical scans, cell-coordinate/layout labels, and controlled hardware comparisons remain absent. Semantic human QA review, larger local workload measurements and broader representative business-case evaluation remain incomplete. See the [evaluation master matrix](technical/agents-and-evaluation.md#proposal-evaluation-master-matrix); higher-concurrency and corpus-scale behavior remain unmeasured. |
| Local prototype runtime, monitoring, manuals and research report | Partial | Local Compose and the FastAPI/Nginx path are documented. Hosted [CI run 36406443751](https://github.com/Lenhan231/enterprise-knowledge-ai-agent/actions/runs/36406443751) passed the full test suite, image build, `nginx -t`, and authenticated HTTP/WebSocket smoke through Docker Nginx. Render/Vercel deployment is explicitly out of scope; provider configs and hosting notes are optional. Monitoring decisions, an operator walkthrough, representative local performance measurements and final evidence-complete report remain. |

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

- Corpus metadata audit: `uv run python scripts/evaluate_corpus_metadata.py`; latest read-only artifact checks all 26 ready manifest sources (364 document fields and 52,283 chunk fields) with zero propagation mismatches, across 4,753 chunks. This is not automatic extraction accuracy.
- Automated suite: `uv run python -m unittest discover -s tests -q` (**420
  passed on 2026-09-28**; includes processing, evaluation, retrieval, agent,
  API and dashboard checks, including OCR/embedding Kaggle notebook setup
  validation and authenticated upload/admin-processing RBAC regressions).
- Proposal corpus-coverage audit: `uv run python scripts/evaluate_proposal_case_coverage.py` validates all 12 case labels against the active route set and 26-document manifest; current counts are 2 supported, 6 partial and 4 unsupported. The public Code of Conduct supports a narrow employee-access answer, while its referenced dedicated Information System Policy is absent; the synthetic demo ACL lets employees retrieve it, but not finance analysts. The employee app QA passed 1/1 with Qwen3.8 ([artifact](../artifacts/evaluation/employee-access-policy-qwen38-rerun-20260928.json)). The authenticated invoice task passed its grounded-answer checks in [the final evaluation](../artifacts/evaluation/proposal-business-app-invoice-narrow-quote-final-20260928.json). Use `scripts/evaluate_app_qa.py --case-id <id>` for focused role-specific QA.
- Embedding comparison: the paired Tesla T4 reports and independent hash audit cover all 4,750 passages in the 25-source snapshot for BGE-M3, Qwen3 Embedding and e5-large-v2. The separate 173-chunk CPU run has only BGE/e5 results because Qwen was stopped at its first slow batch. The two protocols and the raw artifact metadata discrepancy are described in [the evaluation matrix](technical/agents-and-evaluation.md#proposal-evaluation-master-matrix).
- Query rewriting: `uv run python scripts/evaluate_query_rewriting.py --output artifacts/evaluation/vinamilk-query-rewriting-metric-labels-20260928.json` compares raw and ontology-expanded queries on identical role-filtered retrieval inputs. The small paired result was mixed, so rewriting remains evaluation-only; other optimization experiments remain open.
- Response cache: `uv run python scripts/evaluate_response_cache.py --output artifacts/evaluation/vinamilk-response-cache-api-smoke-20260928.json` verified two identical authenticated, cited `/api/ask` responses with one answer-generation call and live role-filtered retrieval. The deterministic answer stub isolates cache wiring; embedding and DB retrieval still execute on cache hits, so recorded latency is not a real-provider speedup benchmark.
- Context compression: `uv run python scripts/evaluate_context_compression.py --output artifacts/evaluation/vinamilk-context-compression-20260928.json` performs query-term extractive sentence selection against the blinded QA packet. Fifteen responses (five distinct questions) have a mean 0.3976 character ratio; responses with all expected fact groups present remained 6/15 before and after, with baseline indicators unchanged in 15/15. These repeated contexts and character counts are preliminary; answer quality and tokenizer savings remain unmeasured, so compression stays off in production.
- Python syntax: `python -m compileall -q src tests scripts`.
- Frontend syntax: `node --check src/app/static/app.js`.
- Hosted CI: commit `5c135ce` passed `uv sync --locked`, Python compile, all 252
  unit tests, frontend syntax, Compose proxy configuration, Docker image build,
  and `nginx -t`; see [run 36287481142](https://github.com/Lenhan231/enterprise-knowledge-ai-agent/actions/runs/36287481142).
- Local app: `http://127.0.0.1:8000/health` returned `200 {"status":"ok"}`
  during the same validation session. The authenticated proxy path was exercised in CI; hosted deployment is out of scope.
- Local HTTP load through Uvicorn:

  ```bash
  uv run python scripts/evaluate_api_load.py --base-url http://127.0.0.1:8000 \
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
  [`v1 case snapshot`](../data/evaluation/vinamilk_qa_cases-app-qa-v1.json),
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
  `data/evaluation/vinamilk_unsupported_abstention_case.json` and
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
- OCR paired text pilot: reports under `artifacts/evaluation/ocr-kaggle-{easy,paddle,surya}/` plus `artifacts/evaluation/ocr-tesseract-v2-current-labels.json`; same three-crop dataset hash, not eligible for model selection.
  records per-page edit counts and macro/micro CER/WER, but uses an unreviewed
  PDF text reference. Manual-label pilots are
  `artifacts/evaluation/vinamilk-ocr-human-reviewed-tesseract.json` (v1, two
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
  `artifacts/evaluation/vinamilk-ocr-easy-tesseract-v5-comparison.json`.
  Surya v5 completed on the same hashes with micro-CER/WER 0.075829/0.151558,
  exact table row recall 14/16 (0.875), 3.962 s mean inference/page and
  4,395.629 MiB peak process RSS; GPU allocation/reservation was
  2,354.048/2,670 MiB. PaddleOCR v5 completed at CER/WER 0.087941/0.211048,
  0/16 exact rows and 32/48 cell-text matches. Cell-text recall is Tesseract
  40/48, EasyOCR 47/48, Surya 47/48, and PaddleOCR 32/48; it ignores row/column
  association. The hash-paired four-engine artifact is
  `artifacts/evaluation/vinamilk-ocr-paddle-easy-surya-tesseract-v5-comparison.json`.
  These v5 all-page CER/WER aggregates are superseded by corrected v6 labels;
  the table-only metrics remain historical. Surya v6 is complete, while the
  older v4 kernel is no longer a pending run. The corrected v6 six-page
  comparison reports all four engines on identical labels and image hashes;
  see `vinamilk-ocr-four-engine-v6-cpu-comparison.json`. The one-table pilot
  does not select a production engine. Dataset and
  baseline report:
  `data/evaluation/vinamilk_ocr_ground_truth_v5.json` and
  `artifacts/evaluation/vinamilk-ocr-human-reviewed-tesseract-v5.json`.
  See [document processing](technical/document-processing.md) and the
  hash-verified pair `vinamilk-ocr-governance-scans-v4-comparison.json`.
- OCR scan expansion v7 adds four visually transcribed image-only English
  regions from pages 3 and 5 of the 2026 Charter and Governance Rules PDFs.
  Tesseract 5.5.3 at 180 DPI/PSM 3 reproduces the original six page CER/WER
  values exactly when checked by source-PDF and rendered-crop hashes; the four
  new scans score micro-CER/WER 0.224055/0.267760. This is a single-engine
  expansion smoke, not a new cross-engine comparison. A paired Tesseract PSM 11
  run on the same ten source/render hashes scores micro-CER/WER 0.127318/0.197497
  overall and 0.111908/0.137978 on the four added scans; this is configuration
  evidence only and does not select a production setting. The current Vinamilk PDF
  subset still lacks a Vietnamese physical scan and reviewed table-cell
  coordinates. See [v7 references](../data/evaluation/vinamilk_ocr_ground_truth_v7.json)
  and paired Tesseract [PSM 3](../artifacts/evaluation/vinamilk-ocr-tesseract-scan-expansion-v7-180dpi-psm3-20260928.json)/[PSM 11](../artifacts/evaluation/vinamilk-ocr-tesseract-scan-expansion-v7-180dpi-20260928.json) runs.
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
  table anchors; image-upload OCR with table PSM 3 matches 2/3 normalized table
  anchors and 3/3 normalized text anchors. The follow-up [table PSM 6 report]
  (`artifacts/evaluation/vinamilk-document-extraction-compact-table-psm6-20260928.json`)
  raises normalized table-anchor recall to 3/3 on both raster-PDF and
  image-upload routes; exact table-anchor recall remains 1/3 and 0/3,
  respectively. Production defaults now use PSM 3 for PDF table word boxes and
  PSM 6 for direct image uploads; text OCR remains PSM 11. This comparison
  uses two born-digital source pages rasterized synthetically, so it does not
  replace review on real scanned reports.
- Expanded multi-year extraction report
  `artifacts/evaluation/vinamilk-document-extraction-multiyear-v3-20260928.json`
  supersedes the narrow five-field candidate count below for native financial
  statement coverage. It contains 11 visually checked fields over five report
  pages (2020–2024); born-digital candidate extraction matched 11/11 with
  1.00 precision. Synthetic Tesseract raster OCR matched 1/11 exact text
  anchors and 3/11 after normalization. These are not real-scan or
  document-wide accuracy estimates.
- Financial candidate extraction report
  `artifacts/evaluation/vinamilk-document-extraction-candidates-20260927.json`
  adds candidate-level scoring on those same five labeled fields. The rule-based
  extractor produced 5 candidates, with 5/5 labeled-value precision and 5/5
  field recall across two pages (2/2 infographic fields; 3/3 balance-sheet
  fields). These results cover only those selected, born-digital pages and do
  not establish corpus-wide accuracy or LLM extraction quality.
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
  A later live review found five verified KPI rows. The FY2020 profit-after-tax
  row had been stored as `11.236` instead of `11236`; the original annual report
  page 2 states `11,236` VND billion. Both the verified metric and its reviewed
  candidate were corrected in Supabase, and the authenticated analytics API
  now returns profit `11236` and consolidated revenue `59723` billion VND.
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
## Financial dashboard extraction progress

Implemented parser/keyword-based financial-page selection (maximum 10 pages
per report), one strict-JSON Groq request per selected page, quote/value/unit/
year validation, provenance columns, and the existing admin review gate. LLM
candidates remain `needs_review`; analytics reads only verified metrics. LLM
candidates replace parser candidates only for the same document/metric/year/
page, preserving parser evidence for metrics the LLM did not return. Provider
errors keep parser candidates from the shortlisted finance pages.

Run `.venv/bin/python scripts/process_vinamilk_financial_reports.py
--page-selection-only --ids VNM-AR-2020-VI VNM-AR-2024-VI` to inspect selection
without model calls, or add `--llm --dry-run` to inspect extraction output
without saving. `--save-candidates` saves review-only candidates.

The current live admin analytics API returns seven verified KPI observations and
29 pending review candidates; only verified rows affect analytics. An admin must
check each candidate's source page, fiscal year, unit, and reported value
before it can be published. Historical pending rows are retained as
superseded evidence rather than deleted.

Rule-based candidates now prefer structured rows and prominent KPI cards;
free-text fallback is limited to high-confidence summary pages to avoid
turning unrelated narrative figures into dashboard values. Unit hints come
from the selected page and table headers and remain admin-review suggestions.

The first selection diagnostic chose 10/100 pages in the 2020 report and
10/95 in 2024 (90% and 89.5% fewer pages sent). Both currently labeled anchor
pages (2020 p.8, 2024 p.91) were selected (2/2); this two-page check is too
small to establish recall. Rule-based candidate coverage is evaluated against
the five manually labeled fields in
`data/evaluation/vinamilk_document_extraction_cases.json`. A no-write 2024 LLM
run accepted three values from PDF page 48 and two from page 92 after returning
no values on page 15; one output per later page failed quote validation. The
repeat run hit provider rate limits, so those accepted values still require
manual value/unit/year scoring before use. Do not use unreviewed candidates as
KPIs.

### Current extraction limits and next validation

The staged path is implemented: parser/layout and finance keywords shortlist
pages, the LLM returns source-quoted candidates with provenance, and an admin
must verify the value, unit, fiscal year, and cited source before publication.
Candidates are stored separately from verified `extracted_financial_metrics`;
export to XLSX is optional and is not the system of record.

The suggested 5–10 pages and 98% request reduction are hypotheses, not measured
results. Current selection caps at 10 pages; the 2020/2024 diagnostic selected
10/100 and 10/95 pages. Measure page recall across available report years,
request/token counts, latency, field/value/unit exact match, invalid-candidate
rate, and admin review effort. Provider quota currently limits repeat runs.
