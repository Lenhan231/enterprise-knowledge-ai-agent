# Commerce decision-support status

This page is the current implementation and evaluation index for the Commerce demo. The transaction and operations data are synthetic; public retailer/platform documents provide attributed examples, not policies for the dataset owner.

## Current status (2026-10-05)

| Area | Verified state | Boundary |
| --- | --- | --- |
| Commerce dashboard | `/api/commerce/dashboard?domain=...` returns only the selected domain; Analytics fetches on entry, and campaign-window detail loads only when expanded. Analyst browser verification confirmed inventory (11 periods), promotion (21 rows), campaigns (50 rows, fetched on expand), and logistics (33 rows) render on demand. | The selected-domain endpoints take about 4.5–7 seconds locally; campaign detail took about 5.8 seconds. Desktop and 390px mobile interaction are verified. Snapshot values are synthetic. Promotion comparisons are observational; the gross-profit proxy is not contribution margin or ROI. Shipping data lacks route, carrier, warehouse and promised SLA. |
| Decision support | `ReportAgent` combines read-only SQL facts `[C#]` with retrieved domain references `[S#]`; policy-only questions use domain-scoped `KnowledgeAgent` retrieval. “Latest inventory snapshot” queries are server-scoped to the latest date. Explicit requests for absent dimensions (for example inventory by warehouse or logistics by carrier) now return a cited schema gap before SQL generation. | Provider outage fallback does not replace full model synthesis. External sources do not establish Commerce Demo policy. |
| Benchmark cases | [`commerce_decision_benchmark.json`](../data/evaluation/commerce_decision_benchmark.json) contains nine questions: three each for inventory allocation, promotion planning and nationwide logistics. The latest full replay passed 3/9 mechanical checks and generated question-specific SQL in 3/9; four cases hit provider limits, and two schema-gap questions abstained correctly ([full replay](../artifacts/evaluation/commerce-decision-support-live-20261005-r3.json)). Follow-up live INV-02 and PROMO-01 cases now each pass mechanical checks; PROMO-01's six year/tag groups passed after alias-aware offline rescoring ([INV-02](../artifacts/evaluation/commerce-inv02-total-snapshots-live-20261005-r1.json), [PROMO-01](../artifacts/evaluation/commerce-promo01-group-guard-rescored-20261005.json)). Both answers used deterministic fallback, so LLM-written decision quality and a fresh full nine-case replay remain open. |
| Active knowledge base | The manifest registers 13 active and 17 archived references: 3 management cookbooks, 6 attributed company-practice examples, 1 platform operating rule, and 3 synthetic Commerce Demo policies. Seven active references are PDFs. | The three internal-policy PDFs are synthetic scan-only examples, not real retailer policy. Public references remain attributed methods/examples and keep issuer scope. |
| OCR/upload | All nine current image-only policy pages score micro-CER 0.005229 / WER 0.019515 against authored HTML references; all three policy files have been re-indexed with OCR-derived section metadata. The degraded two-page Tester upload preserves table title, semantic headers, 3/3 rows and 9/9 numeric cells; persisted output and PNG previews return HTTP 200. | All PDFs are generated synthetic scans, references are not independently human-reviewed, and physical scans remain untested. See the current [policy OCR run](../artifacts/evaluation/ocr/pipeline/commerce-active-policy-scan-ocr-20261005.json) and [live OCR upload](../artifacts/evaluation/ocr/pipeline/commerce-degraded-scan-upload-live-20261005.json). |

## Proposal coverage for the Commerce demo

The proposal describes the full capstone platform. The Commerce demo is its proof-of-concept slice: operational facts come from the synthetic SQL schema; retrieved documents contribute attributed methods, not facts about a real retailer or policies for the mock dataset.

| Proposal requirement | What the Commerce demo provides | Status / remaining evidence |
| --- | --- | --- |
| Document management, parsing, OCR and metadata | Authenticated upload, PDF page rendering, text/table extraction, OCR fallback and saved parser output; common office/image formats have processor support. | PDF upload has an end-to-end smoke check. The synthetic image-only fixture has OCR ground truth; it is not representative scan-accuracy evidence. |
| Knowledge database, retrieval and RBAC | Supabase/PostgreSQL corpus with role-scoped retrieval; active references are filtered before ranking. | Commerce source metadata distinguishes cookbooks, attributed practice examples and platform rules. Do not label external references as Commerce policy. |
| QA, SQL analytics and business decision support | Selected domain bounds generated read-only SQL; ReportAgent combines SQL observations with retrieved operating methods and missing-data limits. Policy-only questions use domain-scoped KnowledgeAgent retrieval. Both paths use the same versioned knowledge base with evidence-class/domain filters; hybrid retrieval falls back to ACL/domain-filtered BM25. | Latest full replay: 3/9 mechanical passes and 3/9 question-specific SQL. Two schema-gap questions abstained correctly and LOG-02 matched expected rows. Four SQL attempts hit Groq rate limits and Hugging Face HTTP 402; two provider-generated queries omitted required comparison fields (total inventory snapshots; untagged promotion group). Prompt and INV-02 benchmark wording were updated after this replay and still need a provider-backed rerun. See the [replay](../artifacts/evaluation/commerce-decision-support-live-20261005-r3.json) and [Commerce status](commerce-decision-support.md). |
| Dashboard and visualization | `/api/commerce/dashboard` reads SQL aggregates for inventory, promotion and nationwide logistics views. | The dashboard reflects synthetic source tables; promotion comparisons are non-causal and regional shipping summaries cannot justify network redesign. |
| Admin UI scope | The Commerce demo exposes Knowledge Management, PDF/OCR processing, access control, monitoring, and collapsed per-answer token usage for SQL and answer generation. The legacy public-company KPI entry/replay UI is removed from workspace navigation; Commerce dashboard values come from SQL aggregates. | Token usage excludes embeddings and intent routing. Old metric extraction tables and endpoints remain in the migration/backend history for compatibility, but they are not an active Commerce workflow. |
| Multi-agent application | Router, document QA, analytics, report and dashboard paths are present in the local FastAPI app. | Proposal-wide agent/model comparison is not complete; validate the full authenticated flow, not only unit tests. |
| Proposal evaluation and benchmarking | Commerce has nine SQL-plus-RAG decision cases and a document-retrieval relevance set. | OCR/embedding/LLM/retrieval/reranker comparisons and human answer-quality review are not complete for the Commerce corpus. |
| Deployment and operations tooling | Local FastAPI demo and role-aware UI. | Hosted deployment is outside the current Commerce work; proposal-listed Docker/Nginx/CI and centralized experiment/monitoring tools are not a completion gate for this slice. |

Latest verification (2026-10-05): the full suite passes 738 tests (3 skipped), with JavaScript syntax, Python compilation, and `git diff --check` passing. Commerce schema-gap tests cover missing warehouse and carrier dimensions, while region remains queryable in logistics. A read-only Supabase audit found zero matching Vinamilk rows in the indexed corpus, metric tables, OCR runs, and Storage; 28 Commerce documents and 612 chunks remain. The current policy OCR report is checksum-bound to active PDFs, and policy rows were re-indexed/read back with 5/3/4 OCR-derived chunks and section metadata. Latest nine-case replay r4 is only 2/9 mechanical passes; offline rescore fixes an INV-01 evaluator false negative, while LOG-01 exposed unfiltered FY2022 SQL. The server now rejects/repairs explicit-year SQL that omits its period filter. A fresh LOG-01 replay hit HTTP 402 on both SQL providers, so live correction remains unverified. See [`commerce-decision-support.md`](commerce-decision-support.md) for current per-area status and evidence.

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
