# Commerce decision support

This guide describes the active Commerce demo slice. The wider proposal is tracked in [`README`](README.md); its model benchmarks are not complete.

## Proposal coverage for this Commerce slice

| Proposal workstream | Current state | Evidence and remaining boundary |
| --- | --- | --- |
| Document upload and processing | Implemented for PDF, Office, text, and images | Admin upload stores originals and inspectable parser output; not every proposed document task (formulas/invoices) has an evaluated workflow. |
| OCR, layout, and tables | Partial | Tesseract OCR, page/layout metadata, and structured tables work on authored scan fixtures. The clean two-page fixture passes 0 CER/WER, 3/3 rows, 9/9 values, and 3/3 headers; the real platform screenshot table still fails, and no independent physical-scan set is available. |
| Knowledge database and RBAC | Implemented for the demo | PostgreSQL/pgvector stores role-filtered passages; Admin classification and Tester-isolated OCR flows are separate. |
| Retrieval and chunking | Implemented, evaluation incomplete | Dense, BM25, hybrid, parent retrieval, metadata/domain filters, and reranking are wired; proposal-wide embedding/retrieval/reranker comparisons are not complete. |
| Agents and business UI | Implemented for Commerce domains | Document QA, bounded SQL analytics, grounded report answers, and inventory/promotion/logistics dashboards are available. Broader HR, contract, invoice, manufacturing, and customer-service cases are not represented by this dataset. |
| Evaluation and deployment | Partial / deployment out of current scope | The last full repository run passed 773 tests; after the page-specific retrieval and ROI-validation changes, all 209 agent tests pass. Nine Commerce cases have mechanical checks and a targeted review of deterministic fallback answers. Provider-backed answer quality, proposal model benchmarks, and deployment stack evaluation remain open. |

This makes the current deliverable a Commerce-focused prototype, not full proposal acceptance. The source report and reproducible status evidence are in [`capstone-project-report.md`](capstone-project-report.md) and [`docs/README.md`](README.md).

## Scope and evidence

The private PostgreSQL `commerce` schema contains synthetic Kaggle Datathon 2026 Round 1 data. It is not observed data from a real retailer. Dashboard and SQL answers describe those rows; the source importer does not invent or recalculate source fields.

The knowledge base combines three evidence classes, registered in [`manifest.json`](../data/commerce_knowledge/manifest.json):

- **Management cookbooks** provide attributed general methods.
- **Company and platform examples** apply only to their named publisher or platform.
- **Commerce Demo policies** are synthetic rules for this fictional scenario. They are not real-company policies or observations.

Generic Australian Government business guides were removed from active retrieval
at the user's request; their manifest records remain archived. Active retrieval
now uses issuer-attributed company/platform sources and the clearly labeled
synthetic Commerce Demo policies.

A current search for an attributable scanned retailer procedure did not yield a
safe source to add. [DCL Logistics' inventory guide](https://dclcorp.com/resources/ecommerce-inventory-management-guide/)
is a company-authored guide, but its public page does not establish that the PDF
is an image-only scan. A relevant [LODI inbound SOP copy on Scribd](https://id.scribd.com/document/667133309/SOP-INBOUND-LODI)
is marked as user-uploaded and all-rights-reserved, so it is excluded rather
than presented as verified company policy. The existing image-only Commerce
Demo PDFs remain explicitly synthetic OCR/upload fixtures, not real-business
policy or physical-scan accuracy evidence.

Promotion decision support includes the 2025 IAB/IAB Europe incremental-measurement guide. It explains why attributed sales/ROAS do not establish incremental impact and describes holdout, counterfactual, and econometric approaches. It is a method reference, not a Commerce policy or a source of Commerce performance facts.

On 2026-10-08, Admin review found page-counter-only OCR chunks in the three scan-only synthetic policies. The parser now removes only a short final explicit `Page n/m`/`Trang n/m` line and keeps page metadata. After targeted re-indexing, each active policy is `ready` with three Tesseract passages, one for each page; all retain section titles and embeddings, and no page-counter text remains in parser chunks. The source PDFs remain unchanged.

After re-indexing, an authenticated Analyst BM25 question about requirements before increasing a promotion budget returned HTTP 200, a model-generated answer, and the promotion policy's page-2 citation (`[S1]`); citation validation passed. This checks that the cleaned OCR passage remains retrievable, not general answer quality.

An inventory question targeting the Shopee guide's replenishment-status screenshot exposed a reranking defect: BM25 ranked its OCR passage above a generic page, but the business reranker discarded the lexical score and selected the generic passage. The reranker now retains BM25 relevance, with a regression for the pair. A live Analyst request returned HTTP 200 and cited page 11 with `text_extraction_method=pymupdf+tesseract`; the provider was token-rate-limited, so the app returned a cited source excerpt instead of a synthesized answer. This verifies OCR chunk retrieval and citation, not model answer quality. The guide is a historical Shopee-only PowerPoint-exported PDF, not a physical scan or Commerce Demo policy.

Three official Vietnamese [Tiki Seller Academy](https://hocvien.tiki.vn/) guides now add platform-attributed operating context for each domain: [FBT inventory reports](https://hocvien.tiki.vn/faq/huong-dan-theo-doi-bao-cao-ton-kho-mo-hinh-fbt/) show stock by warehouse/status and aging with estimated storage cost; [Category Deal operations](https://hocvien.tiki.vn/faq/huong-dan-dang-ky-va-quan-ly-chuong-trinh-category-deal/) cover campaign overlap, allocated products, registered quantities and low-stock warnings; [FBT stock transfers](https://hocvien.tiki.vn/faq/mo-hinh-fbt-huong-dan-luan-chuyen-hang-hoa-luu-kho-tiki/) require source/destination warehouse, SKU, quantity, eligibility and route-related cost. They are Vietnamese HTML help pages, not scanned PDFs. Their screens, rules and thresholds apply only to Tiki. The Commerce schema does not contain warehouse-level SKU inventory, campaign allocation states, inventory age, or transfer-cost/route fields, so these guides identify evidence a richer operational system would need; they do not support applying Tiki rules or asserting those facts about Commerce Demo.

On 2026-10-08, the three pages were downloaded, indexed and read back through the Admin Knowledge Management API as active, `ready` records with 10, 14 and 9 chunks respectively. An `operations` role BM25 query with an exact domain filter ranked the matching Tiki page for each domain. The first named-Tiki Q&A request returned source excerpts because the retrieved prompt exceeded the account's Groq token rate limit and Hugging Face fallback returned HTTP 402. After reducing Knowledge RAG's formatted context budget, a fresh authenticated BM25 `/api/ask` request returned HTTP 200, a Groq-synthesized Vietnamese answer, and a citation to the inventory guide. This verifies one live source-to-answer path, not model answer quality across all domains.

When a promotion answer provider is rate-limited, the deterministic fallback returns cited SQL observations and the applicable measurement limits. It recognizes explicit cautions such as “do not infer ROI,” normalizes hyphenated metric names, and keeps the table to requested measures; this fallback is not model-generated analysis.

On 2026-10-08, a live Admin question asking whether FY2024 campaign evidence justified larger budgets exposed a decision-intent detection gap for “justify increasing campaign budgets.” The detector now recognizes that general action phrasing. The regression and authenticated `/api/ask` replay return HTTP 200, identify that campaign snapshots only cover 2020–2022, and withhold a budget increase recommendation while citing the synthetic Commerce Demo policy and schema limits. This replay exercised the deterministic fallback because the SQL/model provider was rate-limited; it does not establish model-generated answer quality.

An authenticated mixed inventory question asked for the highest-stockout category and the checks required by the demo policy before a transfer. With providers rate-limited, the first fallback returned SQL facts but omitted the retrieved policy because the wording asked for prerequisites rather than a direct recommendation. The operating-step detector now recognizes English and Vietnamese policy/check/condition questions. The replay returns HTTP 200 with the Streetwear count, SQL citations `[C#]`, schema limits `[L#]`, and the inventory policy at PDF page 1 `[S1]`; it explicitly labels the policy fictional and warns that its OCR passage is not verified. The deterministic fallback abstains from recommending a transfer until SKU/location, demand, lead time, cost, and service evidence are available. Two focused regression tests pass; this is fallback-path evidence, not model-generated answer quality.

A later live question combined stockout/overstock comparison with a request to move stock between locations. The SQL guard had discarded the whole question because location is not in the schema, despite available inventory aggregates. The ReportAgent now includes the bounded inventory snapshot together with the missing-dimension limitation, and recognizes “what must be verified before…” as a decision-support request. The authenticated replay returned HTTP 200 with latest-category signals, schema limits, and the synthetic policy’s transfer checks; citations validated while Groq was rate-limited and Hugging Face returned HTTP 402. The answer labels the data synthetic and does not recommend a transfer. All 205 agent tests pass.

SQL establishes what the synthetic dataset contains. Retrieved documents supply methods or explicitly synthetic decision rules. Neither source type can stand in for the other.

On 2026-10-07, an exact cleanup removed 202 orphan Apple chunks and one orphan FPT extracted table/row after saving a temporary backup. Current readback found no orphan chunks or extracted tables; shared schemas and tables remain intact.

## Request flow

```text
Commerce dashboard → read-only aggregates from the selected domain
Document question → role-filtered, domain-filtered KnowledgeAgent retrieval
Decision question → allowlisted SQL + domain-filtered RAG → cited ReportAgent answer
Chart request → DashboardAgent → cited dashboard aggregate
```

`/api/ask` is the Q&A entry point. The dedicated decision form sends the selected domain and explicitly requests SQL + RAG. Conditional-action requests use the full bounded snapshot for that domain instead of generating an arbitrary query from a generic request. Ordinary questions use routing and domain classification; questions that cannot be scoped safely should request clarification. Broad promotion outcome comparisons use the yearly tagged/untagged snapshot; campaign-level rows require an explicit campaign breakdown request. If campaign SQL is rejected, the bounded snapshot can still answer a campaign ranking from its campaign-window aggregate; the fallback must preserve the campaign window, exact source value and citation, without implying causation. If a causal-measurement question also requests observed measures, the deterministic fallback preserves those SQL values and labels them descriptive, then states the causality boundary and cited method. Questions that ask only how to test incrementality do not receive unrelated campaign rows. The UI labels deterministic fallback, which is not evidence that generated SQL or model synthesis succeeded.

On 2026-10-08, an authenticated Analyst asked in normal chat (without the dedicated decision-mode flag), “Trước khi chuyển hàng giữa các nhóm đang có stockout và overstock, cần kiểm tra dữ liệu nào trước?” The router now detects pre-action evidence questions in English and Vietnamese, auto-selects inventory allocation, and sends the request through SQL + RAG. The live response returned the latest snapshot's 285 stockout flags, 341 overstock flags and 232 overlapping rows, cited the synthetic inventory policy at PDF page 2 and schema limits, and withheld a transfer recommendation. Both generation providers were unavailable, so this verifies the cited deterministic fallback and routing, not model-generated answer quality. `tests.test_agents` passes 199 tests.

A second authenticated normal-chat smoke asked what to verify before moving delivery capacity between regions. The router auto-selected nationwide logistics; the fallback returned 2022 regional averages (4.51 Central, 4.52 East, 4.51 West days), cited missing route/carrier/SLA/capacity/cost fields, cited the synthetic policy PDF page 2, and attributed an external Amazon logistics method without treating it as Commerce Demo policy. This request also ran through the deterministic fallback while providers were rate-limited.

ROI is not a queryable promotion measure in the current Commerce schema because campaign spend is absent. ROI requests therefore use bounded snapshot evidence and a cited deterministic abstention instead of model-generated SQL; the benchmark requires missing-cost/holdout disclosure and rejects a numeric ROI column. Do not label revenue divided by discount value as ROI.

A live promotion-planning API check on 2026-10-07 compared 2022 campaign-window tagged net sales with the catalog-COGS gross-profit proxy. Query-specific SQL returned all four campaigns; Spring Sale 2022 ranked first for tagged net sales, while Fall Launch 2022 ranked first for the proxy. The response identified the different winners, disclosed the synthetic dataset, and did not infer causation or recommend budget changes. The earlier replay had used causal wording and invented a policy threshold. The root cause was treating the router's `decision_support` hybrid-intent flag as proof that the user had asked for a decision. ReportAgent now uses that flag to retrieve operating references while requiring an explicit action request before generating recommendations; descriptive questions remain factual even when they use SQL and RAG together. Its validation also rejects unsupported English and Vietnamese campaign-to-outcome causal phrasing. The corrected response is saved in [the replay artifact](../artifacts/evaluation/agents/commerce-promo-multi-metric-live-20261007.json). At the time of that replay, `tests.test_agents` had 189 passing tests; focused benchmark evaluator checks cover the ROI abstention contract. A targeted semantic review of the nine deterministic decision-case answers found them consistent with the benchmark boundaries: no unsupported inventory transfer, promotion-budget increase, ROI claim, service target, or logistics redesign. INV-02 was reviewed against its later targeted follow-up because the full replay predates the explicit trend wording. This review qualifies the fallback answers, not provider-generated answer quality. One separate Groq-backed PROMO-02 answer listed all four campaigns and ranked Spring Sale first ([replay](../artifacts/evaluation/agents/commerce-promo02-live-20261007-current.json)); one generated answer does not establish broader semantic performance.

Commerce SQL is read-only and limited to the chosen domain's approved tables and columns. SQL validation rejects unsafe or out-of-scope queries before execution. If a question asks for an unavailable dimension alongside supported measures, the agent returns the bounded domain snapshot with an explicit limitation; it does not present the snapshot as evidence for the missing slice. A question with no supporting observations still abstains. Evidence citations retain SQL observations or source passages for inspection.

When model synthesis fails, the question-specific SQL fallback keeps selected observations and citations visible and filters rows to explicitly requested years. Displayed numbers group thousands by answer locale; money-like values and averages show at most two decimals, margin proxies render as percentages, and years/IDs remain unchanged. The fallback does not add a currency symbol because the dataset does not declare one; cited SQL evidence retains the source values.

A live INV-02 `/api/ask` replay now returns localized percentage values and table headings, retains the SQL/policy citations, and refuses to set a service target from historical observations. A conflict-upsert regression test confirms the corpus importer does not overwrite existing `allowed_roles` or `knowledge_base_active` settings.

INV-02's numeric answer contract uses the displayed percentages (96.56%, 96.19%, 96.35%); its cited SQL observations retain the stored ratios (0.9656, 0.9619, 0.9635). The benchmark marks generated question-specific SQL optional because the bounded annual aggregate has the requested observations. A fresh full nine-case replay on current code passed all mechanical checks and six applicable gold-observation associations using deterministic fallbacks; document retrieval used BM25 in all nine answers after the embedding endpoint failed ([run](../artifacts/evaluation/agents/commerce-decision-support-live-20261007-post-current-code-review.json)). Answer review found INV-02 listed the history but did not explicitly state the non-monotonic fill-rate pattern or that both stockout counts and total snapshots declined. The shared fallback now reports those changes and warns that the counts alone do not prove improvement. The live dynamic-SQL path returns averages as decimal strings, so the shared trend helper now parses them with `Decimal`; sentence spacing and citation references are covered by regression tests. The latest targeted live replay passes 1/1 answer-contract, numeric, gold-observation, and citation checks ([replay](../artifacts/evaluation/agents/commerce-inv02-live-20261007-final.json)); its policy page was retrieved through hybrid search. Groq was rate-limited and Hugging Face returned HTTP 402, so this verifies deterministic fallback behavior and one hybrid retrieval path, not model-synthesized answer quality or comparative retrieval-method quality.

A separate Groq-backed PROMO-02 replay returned all four campaign-window rows and added no recommendation; the current full replay used deterministic fallback. Both ranked Spring Sale first, and fallback now labels the observed measure in Vietnamese rather than exposing a database field name. Broader model-generated answer review and comparative retrieval evaluation remain outstanding ([Groq replay](../artifacts/evaluation/agents/commerce-promo02-live-20261007-current.json), [current full run](../artifacts/evaluation/agents/commerce-decision-support-live-20261007-current-final.json)).

An untemplated Analyst question asked whether the Spring Sale budget should increase. The first live fallback mixed in Fall Launch results because it ranked the entire bounded campaign snapshot. The fallback now narrows rows to an explicitly named campaign, matching year-suffixed names across years only when the question omits a year; a specific year keeps only that campaign period. Regression tests cover both scopes. A fresh `/api/ask` replay returned only Spring Sale 2020–2022 observations, withheld a budget increase recommendation, and cited the synthetic policy plus missing cost/holdout evidence ([replay](../artifacts/evaluation/agents/commerce-promo-spring-sale-scoped-fallback-20261008.json)). This was a deterministic fallback, not model-generated answer quality; it took 45.111 seconds while both providers were rate-limited.

On 2026-10-08, a fresh authenticated full replay completed all nine SQL+RAG cases against the running API. It passed 9/9 mechanical checks, 9/9 citation/domain checks, 9/9 applicable numeric checks, and 6/6 applicable gold-observation associations. Groq was rate-limited and Hugging Face returned HTTP 402, so all answers were deterministic fallbacks; only one case used question-specific SQL. A second-pass AI review compared all nine answer texts with their gold observations and expected action limits. Separate read-only queries against Commerce base tables reconfirmed the latest inventory category counts and overlap, 2020–2022 fill rates, the 2022 campaign-window ranking, and logistics by delivery year and region. These checks found no displayed-value mismatch, unsupported causal claim, invented threshold, or unsafe transfer, promotion-budget, service-target, or network-redesign recommendation. This remains AI review of deterministic answers, not provider-generated quality evidence or an independent human-panel evaluation ([full replay](../artifacts/evaluation/agents/commerce-decision-support-live-20261008-provider-fallback.json)).

A targeted authenticated INV-01 replay later on 2026-10-08 passed all 12
mechanical checks and used Groq to generate question-specific SQL over
`commerce.inventory`. A fresh instrumented API run confirms the SQL call
succeeded (741 input / 535 output tokens), then answer synthesis received HTTP
429 (`retry-after=790s`) while the response still showed 998/1,000 daily
requests and 8,000/8,000 tokens remaining for the minute. The response does
not identify which other provider quota caused the rejection. Hugging Face
returned HTTP 402, so the app returned its deterministic safety fallback with
SQL, policy, and schema citations. This verifies the dynamic SQL path and
fallback contract, not model-generated recommendation quality; semantic review
remains required ([replay](../artifacts/evaluation/agents/commerce-inv01-groq-sql-answer-fallback-20261008.json)).

When KnowledgeAgent cannot synthesize a response or its draft lacks valid
citations, the source-only fallback now uses manifest notes for the three seeded
synthetic policies instead of repeating OCR text. It labels the note as curated
metadata, not a transcript, and cites the retrieved scan page. A role-scoped
BM25 run against Supabase with a simulated 429 returned the logistics note from
CD-POL-LOG-001 page 2; the original OCR chunk stayed out of the answer. The
focused `tests.test_rag` module has 24 passing tests. ReportAgent's SQL decision
fallback uses `notes` / `notes_en` as a clearly labeled catalog summary for all
three synthetic policies, including logistics; it still does not interpret raw
OCR as verified policy text. A live rate-limited logistics response returned
regional SQL evidence, the logistics policy summary and citations to page 2.
The fallback also recognizes an explicit “strongest delivery-delay signal” ranking: a live API answer named East's 4.52-day mean as the highest in FY2022, while withholding network redesign because route, carrier, SLA and cost evidence is absent. This is a descriptive aggregate, not proof of a service problem. At that checkpoint, `tests.test_agents` passed 189 tests.

The `commerce_decision_support` request flag now means “run domain-scoped
SQL+RAG,” not “recommend an action.” Only explicit decision language or the
suggestion control triggers recommendations. A live Analyst PROMO-02 request
after this fix returned the four campaign-window rows with SQL citation and no
recommendation. Its older answer in the combined report predates this change;
that report is not current evidence for the new answer contract.

## What decisions the data can support

| Domain | Supported analysis | Evidence boundary |
| --- | --- | --- |
| Inventory allocation | Describe product/category stock flags, latest snapshots, historical fill rate, and repeated flags only when product-level distinct snapshot dates are counted. | Annual snapshot totals do not establish recurrence. Stockout and overstock can overlap. No warehouse/location, lead time, forecast, transfer cost, or approved service target; category counts alone cannot justify moving stock. |
| Promotion planning | Compare delivered outcomes by campaign/window and promotion tag; report sales and the catalog-COGS gross-profit proxy when requested. | Tagged-versus-untagged comparisons are observational. No holdout, promotion spend, or attributable traffic; the proxy is not contribution margin or ROI. Some orders have two promotion slots, so the query must state its attribution rule. |
| Nationwide logistics | Compare observed delivery and fee summaries across the dataset's regions. | No carrier, route/origin, capacity, service type, promised SLA, or controllable lane cost; regional averages cannot justify network redesign. |

Recommendations must connect cited observations to an attributed method or the synthetic demo policy, then state the evidence needed to act. Do not invent thresholds, causes, ROI, or operational facts absent from the sources.

## Dashboard and administration

The Analyst dashboard has separate Inventory allocation, Promotion planning, and Nationwide logistics views. Its SQL aggregates are loaded for the selected domain and available year; promotion comparisons are explicitly non-causal. The Admin Knowledge Management view can edit reader roles for existing indexed documents and remove or restore those documents from retrieval. Role edits update `documents.allowed_roles` and apply on the next retrieval without reprocessing or re-embedding; activation changes `documents.knowledge_base_active`. Neither action deletes the original object or parser history.

A fresh authenticated local API check on 2026-10-08 confirmed the role boundary: Viewer can load the corpus overview but receives 403 for Commerce analytics and Admin knowledge management; Analyst can load Commerce analytics but receives 403 for Admin knowledge management; Tester can list isolated OCR runs but receives 403 for Commerce analytics and knowledge management. Admin could open all three synthetic policy PDFs and read three saved Tesseract passages per PDF. The same session returned HTTP 200 for all three dashboard domains and for INV-01; the answer contained the expected latest-snapshot values (Streetwear 134, Outdoor 95, overlapping flags 232), withheld a transfer recommendation, and cited policy page 2 with the retrieval chunk key and source hash. This is a targeted live smoke check, not a complete RBAC or answer-quality evaluation.

Every upload is available to document Q&A. Admins and Document Uploaders can optionally classify a source for Commerce decision support; this requires a source type, publisher, applicability scope, and one or more decision areas. Internal document-kind/category tags are derived automatically, while fiscal year and source URL are optional. The title follows the selected filename until edited. Before submission, the form summarizes the Q&A destination, selected reader roles, optional Commerce source type/domains, missing classification fields, and confirms that dashboard SQL data is unchanged. The original file stays private; parsed content and role-filtered chunks are searchable after synchronous processing. On success, the UI refreshes the corpus list and opens the new document's saved parser output for Admin review. If the corpus refresh fails, the upload result remains distinct and the Admin can still inspect that document's chunks and tables. External methods are attributed examples, not Commerce policy. Provider/citation-failure fallback does not interpret raw OCR; for seeded synthetic policies it may use the curated manifest note carried in chunk metadata and still asks the user to verify the original PDF. Uploaded or external OCR sources without a curated note remain source excerpts only. The Tester OCR Lab is isolated from production knowledge. It previews PDF pages, OCR text, tables, and saved chunks. The synthetic degraded-scan fixture checks layout/table handling; it must not be used as business evidence. The upload route and Tester route have different persistence and access controls.

Failed Admin or uploader submissions can retry embedding from retained parser chunks in Knowledge Management. The retry preserves the private original, structured tables, selected reader roles, and current active/inactive state; it does not rerun OCR. A live retry recovered one earlier 402-failed Admin-only degraded-scan fixture to `ready` with three indexed passages while leaving it inactive and Admin-only. This was an embedding recovery check on synthetic test material, not a business source.

## Reproduce and verify

From the repository root:

```bash
PYTHONPATH=src uv run uvicorn app.main:app --reload --env-file .env --port 8000
PYTHONPATH=src uv run python tools/agents/evaluate_commerce_decision_support.py --case-id INV-01
uv run python tools/processing/evaluate_scan_document_processing.py
```

See [`tools/README.md`](../tools/README.md) for corpus ingestion and the full nine-case replay. Inspect generated answers against their SQL rows, citations, policy scope, and decision boundary; a passing HTTP/citation check alone is not an answer-quality pass.

## Remaining acceptance gaps

- The 2026-10-07 replay passed 9/9 mechanical checks and all 6 applicable gold-observation associations after rescoring. The 2026-10-08 replay passed the same checks; a separate AI pass reviewed all nine deterministic answers, with source-table recomputation for the central inventory, campaign-ranking and logistics claims. The checks support the fallback answers only. Groq was rate-limited (HTTP 429) and Hugging Face returned HTTP 402, so provider-generated answer quality and independent human review remain open. The earlier scorer's `group_category` alias false negative is covered by a regression test. See the [2026-10-07 replay](../artifacts/evaluation/agents/commerce-decision-support-live-20261007-post-alias-rescore.json) and [2026-10-08 replay](../artifacts/evaluation/agents/commerce-decision-support-live-20261008-provider-fallback.json).
- The active scan-only policies are generated demo PDFs. The active 2019 Shopee inventory reference has three image-only PDF pages scored through the production parser, plus selected mixed-page text and screenshot-table labels. On page 11, upload defaults matched 1/4 selected text anchors and 0/2 table rows. The 3.5x/PSM 6 experiment read 4/4 text anchors and recognized both product rows, but its table structure failed: 0/7 exact headers and 10/12 exact cell values because the “Sửa” action text was joined to the final number. The scorer now rejects text-contaminated numeric cells and the unvalidated two-row table fallback was removed ([labels](../data/evaluation/ocr/commerce_shopee_inventory_grid_anchors.json), [current default](../artifacts/evaluation/document-pipelines/results/ocr/legacy-engine-runs/shopee-inventory-grid-anchor-current-after-quality-guard-20261008.json), [rejected experiment](../artifacts/evaluation/document-pipelines/results/ocr/legacy-engine-runs/shopee-inventory-grid-anchor-35x-p6-table6-rejected-20261008.json)). The parser still has a table-reconstruction gap. These PowerPoint-exported pages are not physical scans and their references have one reviewer; there is still no independently reviewed physical business scan in the corpus. Verify the original page before relying on OCR wording.
- The proposal's broader embedding, LLM, reranker, and OCR model comparisons remain outside this Commerce workflow's verified acceptance evidence.

A targeted live INV-02 replay on 2026-10-08 generated the requested year-filtered SQL and passed its numeric, observation, citation, and answer checks ([run](../artifacts/evaluation/agents/commerce-inv02-answer-guards-live-20261008.json)). Groq then returned HTTP 429 for answer generation and Hugging Face returned HTTP 402, so ReportAgent used its deterministic fallback. The fallback displays stored fill-rate ratios as percentages and states the non-monotonic trend; new validation retries or falls back when an answer leaves fill rate as a raw ratio or adds multiple unrequested actions. All 204 agent tests pass after this change. This is one live case and deterministic-fallback evidence, not provider-generated answer-quality validation.

The 2026-10-07 targeted live rerun of `INV-01` passed its 12 mechanical checks with Groq SQL and answer generation. The answer identified Streetwear's 134 stockout flags, disclosed the 232 overlapping stockout/overstock rows, and withheld a transfer recommendation because the category snapshot lacks SKU/location matching; it cited the synthetic inventory policy and named the missing operational fields. I reviewed this one answer against its SQL rows and policy scope. This is one case, not a semantic pass for the nine-case set. Reproduce with the command above.

An out-of-benchmark Analyst request on 2026-10-08 asked which 2022 category had the most stock on hand and whether that alone justified transferring inventory. The live API generated question-specific SQL (Outdoor 49,929; Streetwear 45,085; GenZ 5,126; Casual 4,095), then correctly withheld transfer because category totals do not identify matched SKU/location surplus and demand. It cited the schema limitations and the synthetic inventory policy. Groq answer generation returned HTTP 429 and Hugging Face HTTP 402, so this verifies domain detection, dynamic SQL, source retrieval, and the deterministic decision fallback—not provider-generated prose quality. The phrase “đủ căn cứ” is now recognized as a Vietnamese evidence-sufficiency decision request; a focused regression checks the detector and fallback.

A fresh untemplated Analyst question asked whether to move stock from overstocked to stockout products. The live API returned HTTP 200 through ReportAgent: on the latest snapshot (2022-12-31), it reported 285 stockout-flagged rows, 341 overstock-flagged rows, and 232 rows with both flags, then withheld a transfer recommendation until SKU/location, forecast, lead time, cost, capacity, and service constraints are checked. Citations linked the SQL observations to synthetic policy page 2, indexed with Tesseract OCR. Provider rate limiting selected the deterministic fallback. This validates one current SQL-plus-scanned-policy path for a question outside the benchmark; it does not establish model-generated answer quality.

An untemplated promotion question asked whether deeper discounts should be the default and whether 2022 evidence proves incremental profit or ROI. The live decision path returned campaign-window discount observations, declined to claim incrementality/ROI without campaign cost and a counterfactual, and cited an attributed holdout method. An explicit Q&A request for the Commerce Demo promotion policy retrieved CD-POL-PROMO-001 page 2, indexed with Tesseract. When the provider was rate-limited, the answer used the clearly labeled manifest note rather than presenting OCR text as a verified transcript. A regression now prevents the ROI abstention from being rejected merely because the user did not separately ask for the merchandise gross-profit proxy; that proxy remains required when explicitly requested and present.

A separate Analyst `/api/ask` request without a decision domain returned a KnowledgeAgent answer from the OCR-indexed inventory policy, not SQL: hybrid retrieval cited CD-POL-INV-001 page 2 with `text_extraction_method=tesseract`. I rendered that original page and confirmed the six cited transfer checks (SKU match, available stock, forecast demand, replenishment time, freight cost, and service constraints) appear in the source. This verifies one scan-to-retrieval-to-citation answer; it remains a synthetic policy and does not validate a real retailer's operating rules.

Earlier policy-only promotion and logistics requests retrieved the expected OCR pages but could only return source excerpts when Groq returned HTTP 429 and Hugging Face returned HTTP 402. The fallback now uses curated catalog notes for seeded synthetic policies; the logistics policy was re-indexed with its English note. A live KnowledgeAgent request against Supabase with a simulated 429 returned the cited logistics summary from page 2 without repeating noisy OCR. A separate `/api/ask` request synthesized the required route/lane, carrier, timestamps, SLA, capacity, and cost fields; I checked those against the cited OCR chunk. This verifies both model and source-note fallback for one domain, not answer quality across all domains or real-company policy transfer.

A targeted INV-01 replay after that fallback fix passed its answer contract,
source/domain checks, and all required numeric and gold-observation checks. The
provider was rate-limited, so this replay used the bounded inventory snapshot;
it does not live-exercise question-specific SQL. A regression test now feeds the
fallback the exact dynamic-query aliases (`group_label`, `stockout_count`, and
`overstock_count`) from the earlier failure and verifies that both category
counts and the cited snapshot date are preserved. The replay is archived at
[the current INV-01 run](../artifacts/evaluation/agents/commerce-inv01-after-dynamic-sql-fallback-fix-20261008.json).
