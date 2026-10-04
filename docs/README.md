# Commerce decision-support status

This page is the current implementation and evaluation index for the Commerce demo. The transaction and operations data are synthetic; public retailer/platform documents provide attributed examples, not policies for the dataset owner.

## Current status (2026-10-05)

| Area | Verified state | Boundary |
| --- | --- | --- |
| Commerce dashboard | `/api/commerce/dashboard?domain=...` returns only the selected domain; Analytics fetches on entry, and campaign-window detail loads only when expanded. Analyst browser verification confirmed inventory (11 periods), promotion (21 rows), campaigns (50 rows, fetched on expand), and logistics (33 rows) render on demand. | The selected-domain endpoints take about 4.5–7 seconds locally; campaign detail took about 5.8 seconds. Desktop and 390px mobile interaction are verified. Snapshot values are synthetic. Promotion comparisons are observational; the gross-profit proxy is not contribution margin or ROI. Shipping data lacks route, carrier, warehouse and promised SLA. |
| Decision support | `ReportAgent` combines read-only SQL facts `[C#]` with retrieved domain references `[S#]`; policy-only questions use domain-scoped `KnowledgeAgent` retrieval. “Latest inventory snapshot” queries are server-scoped to the latest date. Explicit requests for absent dimensions (for example inventory by warehouse or logistics by carrier) now return a cited schema gap before SQL generation. | Provider outage fallback does not replace full model synthesis. External sources do not establish Commerce Demo policy. |
| Benchmark cases | [`commerce_decision_benchmark.json`](../data/evaluation/commerce_decision_benchmark.json) contains nine questions: three each for inventory allocation, promotion planning and nationwide logistics. The latest full replay r5 passed 3/9 mechanical checks and generated question-specific SQL in 1/9; six cases hit provider limits, and two schema-gap questions abstained correctly ([full replay](../artifacts/evaluation/commerce-decision-support-live-20261005-r5.json)). A focused LOG-02 replay now gives cited FY2020-to-FY2022 direction by region; citation, endpoint-number and SQL-row checks pass, while question-specific SQL remains unverified because of provider rate limits ([LOG-02](../artifacts/evaluation/commerce-log02-live-20261005-r1.json)). A focused LOG-01 replay generated FY2022-only SQL and passed mechanical checks; answer drafting used deterministic fallback ([LOG-01](../artifacts/evaluation/commerce-log01-live-20261005-r5.json)). The benchmark contract now matches LOG-02's endpoint-only expected behavior. |
| Active knowledge base | The manifest registers 13 active and 17 archived references: 3 management cookbooks, 6 attributed company-practice examples, 1 platform operating rule, and 3 synthetic Commerce Demo policies. Seven active references are PDFs. | The three internal-policy PDFs are synthetic scan-only examples, not real retailer policy. Public references remain attributed methods/examples and keep issuer scope. |
| OCR/upload | All nine current image-only policy pages score micro-CER 0.005229 / WER 0.019515 through the production upload processor against authored HTML references; all three policy files have been re-indexed with OCR-derived section metadata. The degraded two-page Tester upload preserves table title, semantic headers, 3/3 rows and 9/9 numeric cells; persisted output and PNG previews return HTTP 200. A separate paired Kaggle run compared Tesseract, PaddleOCR, EasyOCR and Surya on the same 9 active policy pages: Tesseract was fastest, EasyOCR lowest CER, Surya lowest WER. | All PDFs are generated synthetic scans, references are not independently human-reviewed, and physical scans remain untested. The engine comparison is not sufficient to select a production model: it has no tables, and CPU/GPU speed results are not directly comparable. See the [OCR comparison and limitations](../data/evaluation/ocr/README.md#ocr-engine-comparison-active-commerce-policy-pdfs), [paired report](../artifacts/evaluation/ocr/comparisons/commerce-active-policy-scan-20261005/comparison.json), [policy OCR run](../artifacts/evaluation/ocr/pipeline/commerce-active-policy-scan-ocr-20261005.json), and [live OCR upload](../artifacts/evaluation/ocr/pipeline/commerce-degraded-scan-upload-live-20261005.json). |

## Proposal coverage for the Commerce demo

The proposal describes the full capstone platform. The Commerce demo is its proof-of-concept slice: operational facts come from the synthetic SQL schema; retrieved documents contribute attributed methods, not facts about a real retailer or policies for the mock dataset.

| Proposal requirement | What the Commerce demo provides | Status / remaining evidence |
| --- | --- | --- |
| Document management, parsing, OCR and metadata | Authenticated upload, PDF page rendering, text/table extraction, OCR fallback and saved parser output; common office/image formats have processor support. | PDF upload has an end-to-end smoke check. The synthetic image-only fixture has OCR ground truth; it is not representative scan-accuracy evidence. |
| Knowledge database, retrieval and RBAC | Supabase/PostgreSQL corpus with role-scoped retrieval; active references are filtered before ranking. | Commerce source metadata distinguishes cookbooks, attributed practice examples and platform rules. Do not label external references as Commerce policy. |
| QA, SQL analytics and business decision support | Selected domain bounds generated read-only SQL; ReportAgent combines SQL observations with retrieved operating methods and missing-data limits. Policy-only questions use domain-scoped KnowledgeAgent retrieval. Both paths use the same versioned knowledge base with evidence-class/domain filters; hybrid retrieval falls back to ACL/domain-filtered BM25. | Fresh replay r6 repeats 3/9 mechanical passes: six question-specific SQL requests hit Groq's token/day limit, while two unavailable-schema cases abstained correctly. Groq's configured Hugging Face fallback also returned 402 because monthly included credits were depleted. Required numeric values appear in all nine answers and all six applicable SQL-observation groups are present, but question-specific query coverage and semantic recommendation quality remain unverified. See [r6](../artifacts/evaluation/commerce-decision-support-live-20261005-r6.json), [Commerce status](commerce-decision-support.md), [Groq limits](https://console.groq.com/docs/rate-limits), and [Hugging Face credits](https://huggingface.co/docs/inference-providers/pricing). |
| Dashboard and visualization | `/api/commerce/dashboard` reads SQL aggregates for inventory, promotion and nationwide logistics views. | The dashboard reflects synthetic source tables; promotion comparisons are non-causal and regional shipping summaries cannot justify network redesign. |
| Admin UI scope | The Commerce demo exposes Knowledge Management, PDF/OCR processing, access control, monitoring, and collapsed per-answer token usage for SQL and answer generation. The legacy public-company KPI entry/replay UI is removed from workspace navigation; Commerce dashboard values come from SQL aggregates. | Token usage excludes embeddings and intent routing. Old metric extraction tables and endpoints remain in the migration/backend history for compatibility, but they are not an active Commerce workflow. |
| Multi-agent application | Router, document QA, analytics, report and dashboard paths are present in the local FastAPI app. | Proposal-wide agent/model comparison is not complete; validate the full authenticated flow, not only unit tests. |
| Proposal evaluation and benchmarking | Commerce has nine SQL-plus-RAG decision cases and a 12-case document-retrieval relevance set; Dense, BM25, Hybrid, and Parent retrieval have been compared on the same database snapshot. A narrow 4-engine OCR smoke comparison is also recorded for the synthetic policy PDFs. | OCR comparison needs human-reviewed references and real scan/table examples before model selection; embedding-model, LLM, and learned-reranker comparisons plus human answer-quality review remain incomplete for the Commerce corpus. Retrieval labels are document-level and too small for tuning. |
| Deployment and operations tooling | Local FastAPI demo and role-aware UI. | Hosted deployment is outside the current Commerce work; proposal-listed Docker/Nginx/CI and centralized experiment/monitoring tools are not a completion gate for this slice. |

Latest full-suite verification (2026-10-05): 740 tests passed (3 skipped), with JavaScript syntax, Python compilation, and `git diff --check` passing. Commerce schema-gap tests cover missing warehouse and carrier dimensions, while region remains queryable in logistics. A read-only Supabase audit found zero matching Vinamilk rows in the indexed corpus, metric tables, OCR runs, and Storage; the Admin API currently lists 28 ready Commerce documents (13 active) and 612 chunks. The current policy OCR report is checksum-bound to active PDFs, and policy rows were re-indexed/read back with 5/3/4 OCR-derived chunks and section metadata. Fresh full decision replay r6 is 3/9 mechanically passed; six SQL requests exhausted the Groq token/day quota, and the Hugging Face fallback reported depleted monthly credits. Two schema-gap cases abstained correctly. This provider state prevents a complete dynamic-SQL and LLM evaluation; it is not a clean pass. Targeted LOG-01 previously executed FY2022-only SQL and passed mechanical checks, while answer generation fell back deterministically. The 12-case retrieval rerun fixed negated service-target and broad logistics-comparison regressions; reranked MRR is 0.5694 and Recall@3 0.9167. All four retrieval methods have also been compared; hybrid leads MRR, but document labels are too small for tuning. See [`commerce-decision-support.md`](commerce-decision-support.md) for current evidence and caveats.

## Data and recommendation limits

- Inventory flags are aggregate snapshots; they do not identify SKU overlap, location, demand forecast, lead time, transfer cost or an approved service target.
- Promotion tags do not provide a holdout or campaign cost, so they cannot establish causal uplift or ROI. Catalog COGS permits a merchandise gross-profit proxy, but that is not contribution margin and depends on the catalog cost assumption.
- Regional shipping summaries do not identify carrier, route, warehouse origin, capacity, service class or promised delivery target.
- Recommendations must separate SQL observations from document-derived methods. They should name missing evidence instead of inventing thresholds or claiming an external guide is Commerce Demo policy.

## Reproduce locally

```bash
uv sync
PYTHONPATH=src .venv/bin/uvicorn app.main:app --reload --env-file .env --host 127.0.0.1 --port 8000
```

Run the Commerce knowledge seed pipeline:

```bash
PYTHONPATH=src .venv/bin/python scripts/ingestion/ingest_commerce_knowledge.py --download-only
PYTHONPATH=src .venv/bin/python scripts/ingestion/ingest_commerce_knowledge.py
```

Set `DOCUMENT_OCR_RENDER_SCALE` and `DOCUMENT_OCR_TABLE_RENDER_SCALE` to `1.5`, `2.5`, or `3.5` to control OCR fallback for scanned/image-heavy PDF pages. The defaults reflect current small-sample evidence, not universal best settings.

## Technical guides

- [Document processing and OCR](technical/document-processing.md)
- [Chunking](technical/chunking.md)
- [Embeddings and tokenization](technical/embeddings-tokenization.md)
- [Retrieval and RBAC](technical/retrieval-rbac.md)
- [Agents and evaluation](technical/agents-and-evaluation.md)
- [Database connections](technical/database-connections.md)
- [Repository ownership](technical/repository-ownership.md)
- [Commerce data, references, benchmark and live checks](commerce-decision-support.md)

## Focused verification

```bash
PYTHONPATH=src .venv/bin/python -m unittest tests.test_document_processor tests.test_seed_ingestion tests.test_pdf_upload_processing tests.test_upload_processing_flow -q
PYTHONPATH=src .venv/bin/python -m unittest tests.test_agents.AgentFlowTest.test_commerce_platform_rule_requires_platform_named_and_active_reference tests.test_agents.AgentFlowTest.test_commerce_inventory_ranking_prefers_operating_steps_over_table_of_contents -q
```

The focused OCR/upload commands above provide a smaller regression loop; use the full-suite result in the verification note when reporting current status.
