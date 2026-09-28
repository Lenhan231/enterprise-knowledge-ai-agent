# Enterprise Knowledge AI Agent for Vietnamese Enterprise Documents

**Status:** evidence-backed research draft, 28 September 2026
**Scope:** Vinamilk public-document prototype; not a completed thesis or production evaluation.
**Proposal:** [docs/proposal.docx](proposal.docx) · **Evidence index:** [proposal coverage and evaluation protocol](README.md)

## Abstract

This report describes an enterprise knowledge assistant prototype for Vietnamese corporate documents. The system combines document parsing and OCR, persisted processing output, role-filtered PostgreSQL/pgvector retrieval, hybrid search, grounded question answering, multi-agent routing, source-backed analytics and an interactive web interface. The evaluated corpus is restricted to public Vinamilk reports and product/policy material; role labels are synthetic demonstration controls. On twelve labeled retrieval questions, document-level ranking is high while selected passage-level recall remains modest. Three embedding models were compared on all 4,750 passages from the 25-source snapshot on a Tesla T4; document MRR ranged from 0.758 to 0.803, with sparse document-level judgments that do not establish a production winner. A five-case authenticated app QA suite passed deterministic source, fact, route and abstention checks; two focused post-guard Qwen3.8 cases for employee return-policy access and FY2024 financial values also passed. **OCR correction:** visual review found that both image-only scan crops in v3–v5 clipped printed text while their references retained the full lines, so the scan CER/WER and six-region aggregates reported below are superseded. The v5 financial-table crop was unchanged; its one-table cell-presence and row-recall diagnostics remain valid. Dataset v6 corrects the scan crops and has hash-matched reports for all four engines on six pages. Tesseract/EasyOCR/Surya/PaddleOCR micro-CER/WER is 0.325961/0.259207, 0.176672/0.361190, 0.071090/0.143059 and 0.088994/0.209632. All ran on CPU across local and Kaggle hosts; throughput is not controlled and these results do not select a production engine. These runs show an operational prototype and a reproducible evaluation path, not generalizable model superiority: representative Vietnamese scan/layout quality, human QA scoring, realistic private business cases, deployed scalability and several proposal experiments remain incomplete.

## 1. Problem and objectives

Vietnamese enterprises hold knowledge in annual reports, policies, product documents and operational files. Keyword search alone misses paraphrases; vector retrieval can return a relevant document but an irrelevant passage; generated answers can also misstate values or expose documents to unauthorized roles. The prototype therefore targets a traceable flow from source file to parsed text, retrieval, answer citation and dashboard evidence.

The objectives in the proposal are to provide: (1) multi-format ingestion and document understanding, (2) enterprise knowledge retrieval with RBAC, (3) a grounded conversational and multi-agent interface, (4) source-backed analytics/dashboard, and (5) measured evaluation and deployment documentation. The implementation and remaining proposal coverage are tracked in [the coverage matrix](README.md#proposal-coverage).

## 2. Background

Retrieval-Augmented Generation (RAG) combines a non-parametric retriever with a language model to ground generation in retrieved documents [Lewis et al.](https://arxiv.org/abs/2005.11401). Dense Passage Retrieval established a dual-encoder approach for retrieving passages by semantic similarity [Karpukhin et al.](https://arxiv.org/abs/2004.04906). For multilingual corpora, BGE-M3 reports multilingual dense, sparse and multi-vector retrieval capabilities [Chen et al.](https://arxiv.org/abs/2402.03216); Qwen3 Embedding reports multilingual embedding and reranking model families [Zhang et al.](https://arxiv.org/abs/2506.05176). These papers motivate candidate methods but do not substitute for evaluation on this corpus.

OCR quality is especially consequential for scanned reports, tables and mixed layouts. PaddleOCR 3.0 describes an OCR/document-parsing toolkit spanning text recognition and layout-related components [PaddleOCR team](https://arxiv.org/abs/2507.05595). The paired three-crop pilot has no table-cell/layout labels. A later five-region v4 set adds two physical scans and hash-paired EasyOCR/Tesseract scores, but is still too small and text-only to support general engine selection or document-level quality claims. For RAG evaluation, automated component metrics can help diagnose retrieval/context/generation stages, but do not establish semantic faithfulness by themselves; RAGAS is one published evaluation framework [Es et al.](https://arxiv.org/abs/2309.15217).

## 3. System and data flow

The current flow is:

```text
Official/public source or authenticated upload
  -> parser selection (PDF native text / OCR, Office, text, image)
  -> parsed pages, layout/table metadata and chunks persisted for inspection
  -> token-aware chunking and embedding
  -> PostgreSQL + pgvector document/chunk records
  -> authenticate user -> resolve role -> filter authorized candidates
  -> dense, BM25, hybrid or parent-context retrieval -> optional reranking
  -> agent route -> grounded answer / SQL analytics / dashboard / report
  -> source citations and privacy-minimized processing/agent trace
```

The staged processing table allows administrators to inspect parser output and retry embedding without repeating OCR. KPI candidates retain source document, page and quote evidence and remain pending until an administrator verifies the value and unit. The dashboard reads processed/verified data through API/database logic; it does not use fixed chart values. See [processing](technical/document-processing.md), [chunking](technical/chunking.md), [embeddings](technical/embeddings-tokenization.md), [retrieval and RBAC](technical/retrieval-rbac.md), and [agents](technical/agents-and-evaluation.md).

Authorization is applied before retrieval ranking and reranking. Public source documents carry synthetic role classifications for demonstrating access boundaries; these do not describe Vinamilk's actual internal permissions. Data artifacts and download provenance are documented in [data/README.md](../data/README.md).

## 4. Experimental method

Experiments use versioned JSON artifacts under `artifacts/evaluation/`. Where paired comparisons are reported, the case file, its SHA-256, and (where applicable) candidate/sample fingerprints are recorded. Retrieval uses nine queries with manually selected, non-exhaustive passage labels. Embedding comparison uses the same nine cases and evenly sampled 93 chunks (at most eight per document) from the 3,785 ready Vinamilk chunks. LLM proxy comparison uses five paired questions/contexts. Live app QA runs through authenticated `/api/ask`. Load testing exercises local in-process ASGI endpoints, not a deployed proxy or remote production stack.

Metrics include document/passage MRR, Recall@k and nDCG; embedding query time and peak process RSS; OCR character/word error rates against manual transcriptions; deterministic answer-source/fact/citation checks; request latency, throughput and error count. Evaluation scripts and exact configuration are indexed in [agents-and-evaluation.md](technical/agents-and-evaluation.md#proposal-evaluation-master-matrix). Latencies are hardware- and warm-up-dependent. CPU runs below were on a host with no available CUDA GPU.

## 5. Results

### 5.1 Corpus and retrieval

The initial retrieval/embedding comparison snapshot contained 34 documents and 4,087 chunks overall. The expanded-corpus snapshot contains 44 documents and 5,052 chunks overall, with all 25 Vinamilk manifest documents ready and 4,750 chunks. The first expanded-corpus retrieval run used nine questions; it has since been superseded by a 12-case run after adding governance queries. Passage judgments are selected rather than exhaustive.

| Method | Document MRR | Passage MRR | Passage Recall@5 | Mean latency (ms) |
| --- | ---: | ---: | ---: | ---: |
| Dense | 1.000 | 0.429 | 0.259 | 1,954 |
| BM25 | 0.944 | 0.363 | 0.352 | 1,251 |
| Hybrid (RRF) | 0.926 | 0.440 | 0.370 | 1,266 |
| Parent context | 1.000 | context MRR 0.431 | gold passage coverage 0.278 | 1,703 |

Dense and parent ranking retrieved the expected document for all nine baseline cases, but passage retrieval was substantially harder. The current 12-case expanded-corpus rerun reports document MRR 1.000/0.958/0.944/1.000 and passage MRR 0.412/0.403/0.464 for dense/BM25/hybrid/parent (parent context MRR 0.469). Hybrid had the best ordinary passage MRR; the conflict-of-interest passage ranked poorly, demonstrating room to improve. Parent is reported with context metrics because it returns expanded context, not a passage-level list equivalent to the other methods. First-query dense/hybrid/parent measurements include model initialization; BM25 does not. These remain small baselines, not a stable winner. Historical artifacts are [`vinamilk-retrieval-current-passage-comparison.json`](../artifacts/evaluation/vinamilk-retrieval-current-passage-comparison.json) and [`vinamilk-retrieval-expanded-corpus-20260927.json`](../artifacts/evaluation/vinamilk-retrieval-expanded-corpus-20260927.json); the current artifact is [`vinamilk-retrieval-12cases-expanded-corpus-20260927.json`](../artifacts/evaluation/vinamilk-retrieval-12cases-expanded-corpus-20260927.json).

### 5.2 Embeddings

| Model | Sample | Document MRR | Recall@5 | Corpus embedding seconds | Mean query seconds | Peak RSS (MiB) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| BAAI/bge-m3 | 93 chunks | 0.670 | 1.000 | 102.51 (batch 1) | 0.171 | 2,434 |
| Qwen/Qwen3-Embedding-0.6B | 93 chunks | 0.670 | 0.889 | 1,325.40 (batch 8) | 1.355 | 2,637 |
| intfloat/e5-large-v2 | 93 chunks | 0.707 | 1.000 | 133.99 (batch 4) | 0.219 | 2,189 |

The nine-case point estimates are close and the sample is small. Different batch sizes and model-specific instructions mean observed embedding times are not a controlled throughput ranking. No model is selected as a general winner from this run. Paired artifacts are [`BGE-M3`](../artifacts/evaluation/vinamilk-embedding-bge-m3-expanded-8-per-document.json), [`Qwen3 Embedding`](../artifacts/evaluation/vinamilk-embedding-qwen3-embedding-expanded-8-per-document.json), and [`e5-large-v2`](../artifacts/evaluation/vinamilk-embedding-e5-large-v2-expanded-8-per-document.json); configuration is in [embedding notes](technical/embeddings-tokenization.md).

On the refreshed 173-chunk CPU sample and current 12 cases, BGE/e5 MRR is
0.606/0.706 and nDCG@3 is 0.616/0.719. Qwen was attempted but no score was
produced because its first batch took about 200 seconds on CPU. Separately, a
paired Tesla T4 run scored all three models on the same 4,750-chunk, 25-source
snapshot and all twelve role-labeled cases; this is full-corpus document-level
retrieval evidence, not passage-level judgment or a production model selection.
See the [paired 12-case summary](../artifacts/evaluation/vinamilk-embedding-three-model-expanded-25docs-12cases-20260927.json)
and [T4 hash audit](../artifacts/evaluation/vinamilk-embedding-three-model-full-corpus-hash-verified-20260928.json).

A separate Tesla T4 comparison reported all 4,750 ready corpus chunks for BGE-M3,
Qwen3 Embedding and e5-large-v2. A local replay of its committed corpus JSONL,
case file, 1,000-chunk-per-document cap and sampled-content hash confirms that
all 4,750 chunks were selected and that all three reports used identical inputs.
The raw reports retain an inaccurate evenly-spaced sampling label and stale
sampled-data limitation text; the [hash audit](../artifacts/evaluation/vinamilk-embedding-three-model-full-corpus-hash-verified-20260928.json)
records the mismatch and independent verification. Document MRR was
0.7759/0.8028/0.7583 for BGE/Qwen/e5, respectively. This full-corpus coverage
does not address sparse, document-level labels, passage relevance or human QA,
and it is not a model-selection result.

### 5.3 Reranking

On nine cases, the paired top-2 CPU comparison (sequence length 256) found BGE Reranker v2 M3 changed selected-passage MRR from 0.389 to 0.333 at 1.73 seconds mean rerank time; Qwen3-Reranker-0.6B changed it from 0.389 to 0.444 at 15.74 seconds. A refreshed BGE top-30 run on the same nine current cases and 21 selected passage labels (CPU, batch 2, sequence length 256) improved passage MRR from 0.429 to 0.459 and Recall@2 from 0.241 to 0.259, while document MRR declined from 1.000 to 0.917. Mean rerank time was 29.67 seconds/query and peak RSS 2,820 MiB. This reveals a trade-off: a small passage-level gain coincided with worse document ranking. Qwen top-30 has not been measured on this exact candidate set; the host's swap was nearly exhausted after the BGE run, so no full-depth paired model selection is claimed. Artifacts: [BGE top-30](../artifacts/evaluation/vinamilk-reranker-bge-top30-passage-cpu.json), [BGE top-2](../artifacts/evaluation/vinamilk-reranker-bge-reranker-v2-m3-cpu-top2-passage.json), and [Qwen top-2](../artifacts/evaluation/vinamilk-reranker-qwen3-reranker-0.6b-cpu-top2-passage.json).

### 5.4 OCR and document extraction

The original human-transcribed three-crop pilot includes a raster-embedded product poster but no physical scan. At 180 DPI, paired micro CER/WER were EasyOCR 1.7.2 0.078842/0.283237, PaddleOCR 3.7.0 0.079840/0.300578, Surya 0.17.1 0.083832/0.156069, and Tesseract 5.5.3 0.163673/0.381503. EasyOCR had the lowest micro-CER; Surya had the lowest micro-WER. PaddleOCR ran on CPU; EasyOCR and Surya used a Tesla T4; Tesseract ran locally on CPU. These three-crop reports used the same dataset hash and had no resource or table/layout scoring.

**Dataset correction:** v6 visual review found both image-only governance scan crops in v3–v5 clipped printed text while the references retained the complete lines. The historical scan CER/WER and any all-six-region aggregates below are superseded and are not valid paired comparisons. The v5 balance-sheet table crop did not change, so table-only cell/row diagnostics remain valid. V6 widens the scans; the corrected Tesseract baseline is recorded in the [processing notes](technical/document-processing.md#current-boundaries) and [hash-paired comparison](../artifacts/evaluation/vinamilk-ocr-four-engine-v6-cpu-comparison.json). All four v6 engine reports now match the dataset, source-PDF and rendered-image hashes. Tesseract/EasyOCR/Surya/PaddleOCR micro-CER/WER is 0.325961/0.259207, 0.176672/0.361190, 0.071090/0.143059 and 0.088994/0.209632. The three neural OCR engines ran on Kaggle CPU and Tesseract on local CPU; latency and memory are not controlled across hosts.

V7 adds four manually transcribed image-only English scans from the 2026 Charter and Governance Rules (pages 3 and 5). Two Tesseract 5.5.3 runs at 180 DPI use identical source-PDF and rendered-image hashes across all ten pages. PSM 3/11 micro-CER is 0.272556/0.127318 and micro-WER is 0.263561/0.197497 overall; on the four added scans, micro-CER is 0.224055/0.111908 and micro-WER is 0.267760/0.137978. This is a page-segmentation configuration comparison, not a cross-engine result or production-setting selection. The four new scans are English and include no cell-coordinate labels. A v7 four-engine run remains pending: the available Kaggle asset bundle and notebook are still v6, Kaggle CLI authentication currently fails, and the local host has no GPU and insufficient free memory for another neural OCR model run. See the [v7 references](../data/evaluation/vinamilk_ocr_ground_truth_v7.json) and paired [PSM 3](../artifacts/evaluation/vinamilk-ocr-tesseract-scan-expansion-v7-180dpi-psm3-20260928.json)/[PSM 11](../artifacts/evaluation/vinamilk-ocr-tesseract-scan-expansion-v7-180dpi-20260928.json) artifacts.

**Historical v4/v5 diagnostics (superseded for scan CER/WER by v6):** a v4 run expanded to five manually checked regions, including an image-only Charter introduction and governance table-of-contents page. At 180 DPI and identical PDF/page/image hashes, EasyOCR 1.7.2 on a Kaggle Tesla T4, PaddleOCR 3.7.0 CPU on a T4-assigned runtime, and Tesseract 5.5.3 local CPU scored micro-CER 0.097521/0.078017/0.399339 and micro-WER 0.260700/0.173152/0.297665. Paddle averaged 21.292 s/page at 2.818 pages/minute after 37.852 s initialization, with 3,937.254 MiB process peak RSS. EasyOCR averaged 1.213 s/page after 9.746 s initialization at 49.472 pages/minute; process peak RSS was 1,543.852 MiB and PyTorch CUDA peak allocated/reserved memory was 1,800.277/2,570 MiB. Tesseract averaged 1.930 s/page at 31.085 pages/minute with 409.066 MiB process peak RSS. Across the two scans alone, EasyOCR/Tesseract micro-CER/WER was 0.106772/0.249267 vs 0.516065/0.255132. EasyOCR slightly trails on the Charter scan (CER/WER 0.039735/0.112676 vs 0.037528/0.084507) and improves markedly on governance contents (0.126115/0.285185 vs 0.654140/0.300000). The Paddle run used the CPU wheel/device, so its throughput is not a same-hardware comparison; Surya has completed the hash-matched v6 run. Dataset v5 adds one manually transcribed 16-row Vietnamese balance-sheet table rendered from a born-digital PDF page. Strict row recall requires the label and both period values contiguously in OCR output; it does not measure cell association or layout. On the 48 expected text cells, Tesseract, EasyOCR, Surya and PaddleOCR match 40, 47, 47 and 32 respectively. Their strict row recall is 8/16, 2/16, 14/16 and 0/16; cell-text presence does not require row/column association. Micro-CER/WER on all six regions is 0.334387/0.254958, 0.175882/0.348442, 0.075829/0.151558 and 0.087941/0.211048, respectively. Surya v5 mean inference is 3.962 s/page after 156.223 s initialization, peak RSS 4,395.629 MiB and CUDA allocated/reserved memory 2,354.048/2,670 MiB; PaddleOCR v5/CPU averaged 30.537 s/page after 45.849 s initialization with 3,437.094 MiB peak RSS. Hardware conditions differ, and these small pilot results cannot select a production engine. See the [v4 comparison](../artifacts/evaluation/vinamilk-ocr-paddle-easy-tesseract-v4-comparison.json), [v5 labels](../data/evaluation/vinamilk_ocr_ground_truth_v5.json), [Tesseract v5 report](../artifacts/evaluation/vinamilk-ocr-human-reviewed-tesseract-v5.json), [four-engine v5 comparison](../artifacts/evaluation/vinamilk-ocr-paddle-easy-surya-tesseract-v5-comparison.json), [EasyOCR/Tesseract scan comparison](../artifacts/evaluation/vinamilk-ocr-governance-scans-v4-comparison.json) and [OCR protocol](technical/document-processing.md#current-boundaries).

On two manually reviewed financial-report pages and five anchor fields, born-digital 2024 PDF extraction matched all three balance-sheet anchors exactly and detected 2/2 table regions. Synthetic raster-PDF OCR matched 0/3 anchors exactly but 3/3 after numeric normalization; image-upload OCR matched 2/3 exactly and 3/3 normalized. The 2020 infographic path matched 2/2 anchors. These are narrow page-level diagnostics, not document-wide quality claims; no representative physical scan, invoice, formula or figure benchmark exists. See [extraction artifact](../artifacts/evaluation/vinamilk-document-extraction-scan-table-v9.json).

### 5.5 LLM and application QA

The refreshed live authenticated application suite passed 5/5 automated cases covering 2020/2024 finance, sustainability, product information and employee financial-data denial. Checks covered expected agent, expected fact anchors, cited document, citation consistency and abstention; mean end-to-end latency was 26.405 seconds. During browser verification, a 2024 financial summary initially mixed two differently labelled figures and invented a reconciliation because the report prompt explicitly required both. The report agent now returns the requested consolidated headline metrics, avoids unsupported accounting-basis claims, and withholds answers with unverified citations. The rerun answered with 61,824 billion VND consolidated revenue and 9,453 billion VND after-tax profit, both cited to the matching annual-report excerpt. Analyst dashboard filters and admin processing/access/monitoring screens rendered in browser. A live authenticated XLSX upload reached `ready`; parser table/formula metadata, one indexed chunk and private Storage bytes were read back before test data was removed. A second live smoke injected embedding initialization failure after parsing newline-terminated TXT, retried the saved chunk to `ready`, and verified role-filtered BM25 retrieval for `finance_analyst` with no employee result. It exposed and fixed a trailing-newline chunking bug and a transaction issue that left parsed retry status stale; both fixtures were removed and cleanup verified. These are one-file integration checks; broader format coverage and deployed proxy behavior remain open. The QA suite verifies route behavior on its examples, not semantic faithfulness or user usefulness. Artifact: [`vinamilk-app-qa-suite.json`](../artifacts/evaluation/vinamilk-app-qa-suite.json).

A later single-case authenticated smoke for the unsupported document-retention request returned the Knowledge route, explicit insufficient-information response and no citations. A full suite rerun after this check hit Groq rate limits on its first three requests and was stopped; it did not replace the complete 5/5 artifact. The one-case result is preserved separately at [`vinamilk-unsupported-retention-abstention-smoke.json`](../artifacts/evaluation/vinamilk-unsupported-retention-abstention-smoke.json).

A previous five-case proxy evaluation marked all three models 5/5 because it checked financial numbers without their units. The updated labels require amount-plus-unit consistency and the re-run retains the complete cited chunks. Per-case retrieval-context and prompt hashes match across all three runs. GPT-OSS-20B and GPT-OSS-120B each score 3/4 answerable fact cases; both misstate 2024 consolidated revenue magnitude (as millions, or as 61.8 billion). Qwen3.8-27B scores 4/4. All three correctly abstain for the employee financial-denial case and cite the expected source document on the four answerable cases. Mean literal expected-fact support in cited evidence is 0.875, 1.000 and 0.875 respectively; these checks do not establish semantic faithfulness. The exact proposal Qwen3/Llama 3/proprietary GPT baselines remain unevaluated; these are available-provider proxies. A new 15-response blind packet is ready, but no human ratings have yet been returned. See [LLM evaluation](technical/llm.md) and the [paired artifacts](../artifacts/evaluation/).

After observing the unit failures, the financial report prompt was strengthened and `ReportAgent` now withholds values whose numbers, magnitude or currency do not appear in their cited evidence. Unit tests cover correct values, rescaling and rounding. A post-change live GPT-OSS-20B run hit Groq's daily token cap before producing the 2024 answer, so the correction is not yet verified end to end; the partial attempt is not part of the model comparison.

A prior scorer pass on facts-v2 also exposed the 500-character evidence-preview cap; missing literals in those legacy previews remain marked unverifiable in the diagnostic [v3 artifacts](../artifacts/evaluation/). The full-evidence rerun above supersedes those legacy scores for the paired QA smoke, while blinded human ratings remain necessary.

### 5.6 API load and dashboard data

The repeated local ASGI run completed 70/70 health, dashboard and analytics requests across concurrency levels 1, 2 and 4. Throughput was 0.430, 0.804 and 1.441 requests/second; p95 latency was 4.53, 4.11 and 4.92 seconds. Peak RSS was 625.9 MiB. A subsequent loopback run at concurrency 16 reproduced an analytics failure: Supavisor rejected session 16 because the session-mode pool allows 15 clients. Repository connections are now bounded at ten per app process, with excess requests queued. After this change, the local Uvicorn path completed 80/80 requests at concurrency 16 (3.784 requests/second, aggregate p95 7.058 seconds, analytics p95 7.323 seconds); the load artifact records 145.6 MiB client-process peak RSS. This verifies the connection-limit fix for this workload, not system capacity. Server/database resource telemetry is unavailable; uploads and concurrent LLM generation remain untested. See the [original ASGI run](../artifacts/evaluation/vinamilk-api-load-repeat10.json), [pre-fix stress run](../artifacts/evaluation/vinamilk-api-load-http-stress-20260928.json) and [post-fix run](../artifacts/evaluation/vinamilk-api-load-http-bounded-20260928.json).

Dashboard KPI candidates are extracted from report text with source/page/quote evidence and stay unpublished until administrative review. The FY2020 profit-after-tax value was initially stored as `11.236`; inspection of the cited annual-report page confirmed `11,236` billion VND, so both the verified metric and its reviewed candidate were corrected to `11236`. To prevent the same separator ambiguity at review time, numeric input now follows the dashboard's Vietnamese locale: dots group thousands (`11.236`) and commas mark decimals (`11.236,5`); the form previews the parsed value before publication. The dashboard API returns numeric values and the UI applies one `vi-VN` formatter across KPI cards, charts and changes. The live API currently returns seven verified KPI observations; source values and units still require comparison only within like-for-like metrics. Candidate extraction and review are documented in [agents and evaluation](technical/agents-and-evaluation.md).

### 5.7 Hybrid retrieval weight diagnostic

A read-only paired sweep evaluated the current dense and BM25 baselines alongside four reciprocal-rank-fusion settings over the same nine questions, role filters, corpus snapshot (3,785 ready Vinamilk chunks) and manually reviewed selected passage labels. Default dense:BM25 weights 1:2 with `k=60` had document MRR 0.926, passage MRR 0.440 and passage nDCG@5 0.329. Equal weights 1:1 produced document MRR 0.944, passage MRR 0.384 and nDCG@5 0.322. Dense-heavy 2:1 produced document MRR 1.000 but passage MRR 0.393 and nDCG@5 0.314. Lowering `k` to 20 at 1:2 yielded document MRR 0.944 and passage MRR 0.426. BM25 alone had passage Recall@5 0.352; dense alone had document MRR 1.000. These small, non-exhaustive labels show a metric trade-off, not a stable winner, so production weights remain unchanged. Artifact: [`vinamilk-hybrid-weight-sweep-20260927.json`](../artifacts/evaluation/vinamilk-hybrid-weight-sweep-20260927.json).

### 5.8 Chunking comparison

Seed-PDF and upload parsers share sentence-aware and fixed-window strategies. On native text from 96 pages of the 2024 report, the boundary diagnostic produced 428 fixed chunks (mean 970 characters; 10.5% sentence-ending boundaries) and 438 sentence-aware chunks (mean 857; 81.7% sentence-ending boundaries), both below the 1,100-character ceiling. A separate paired diagnostic compared the five live fixed annual-report indexes (1,912 chunks) with 1,978 sentence-aware chunks built in memory from the same five reports. Across five finance questions, document MRR was 1.0 for both strategies because the candidate corpus was restricted to those five reports. Passage MRR was 0.2715 fixed and 0.2648 sentence-aware; Recall@5 was 0.10 for both. The alternate passage labels were transferred by page and trigram overlap rather than independently reviewed, so this small dense-only result is preliminary and cannot select a strategy or establish answer quality. Parsing took 48.48 s, alternate embedding 94.77 s, and peak RSS was 2,140.7 MiB on CPU. Both runs are read-only against the live database. Artifacts: [`vinamilk-chunking-2024-boundary-diagnostic.json`](../artifacts/evaluation/vinamilk-chunking-2024-boundary-diagnostic.json) and [`vinamilk-chunking-retrieval-finance-five-year.json`](../artifacts/evaluation/vinamilk-chunking-retrieval-finance-five-year.json); see [chunking notes](technical/chunking.md) for reproduction.

### 5.9 Agent route evaluation

The latest twelve-case route run selected all expected destinations, but only two cases used direct provider classification and ten used deterministic fallbacks after rate limits. A separate no-fallback run directly classified finance, executive and BI destinations 3/3. These are route checks with stub agents, not task-completion evidence. The authenticated business-task batches now pass enterprise-management abstention, HR scope-limited response, contract abstention, invoice, manufacturing abstention, customer-service policy, technical-document abstention, compliance and BI; employee access also passes as a focused role-specific case. The BI scorer initially rejected the valid `doc_count` alias and was corrected before the passing rerun. The 2024 financial business-case request remains unscored after HTTP 429. Executive decision support previously failed because `ReportAgent` invoked SQL unnecessarily; the report path now retrieves role-visible passages directly, but Qwen3.8 and GPT-OSS executive reruns both hit provider rate limits. No full twelve-case authenticated task run exists yet. See [route-only current reports](../docs/technical/agents-and-evaluation.md#proposal-evaluation-master-matrix), the [passing BI run](../artifacts/evaluation/proposal-business-app-qwen38-bi-rerun-20260928.json), and the [executive rate-limited run](../artifacts/evaluation/proposal-business-app-qwen38-executive-report-path-rerun-20260928.json).

### 5.10 Manifest metadata propagation audit

A read-only check compared curated manifest fields with persisted document rows
and every ready chunk. The latest run checks all 26 ready sources: all 364
document-level and 52,283 chunk-level field checks matched across 4,753 chunks.
No manifest entries were missing or not ready. This verifies metadata
propagation; it does not measure automatic metadata extraction or validate the
curated labels against source-document content. See the
[2026-09-28 metadata audit artifact](../artifacts/evaluation/vinamilk-corpus-metadata-audit-access-policy-20260928.json).

### 5.11 Proposal business-case corpus coverage

The proposal's twelve example tasks were separately reviewed against the
current 26-document public Vinamilk manifest and source text. Two requests are
supported (2024 financial analysis and document-count analytics), six are
partially supported (reported annual-leave increments, employee network-access
clauses, a limited related-party payment-term disclosure, store returns,
governance controls and report-based strategy/risk summaries), and four request
material absent from the corpus (retention standard, executed contracts,
maintenance procedures and server setup instructions). The Code of Conduct
grants employees access appropriate to their duties, requires manager and IT
approval for exceptions, and points to a separate Information System Policy
that is not in the corpus. A role-filtered employee `/api/ask` test cited the
Code, stated this limitation and passed its route/fact/source/scope checks. The
invoice case has only a related-party disclosure in the 2020 annual report;
there is no invoice or general invoice policy. Partial or missing coverage
should lead to a limited source-backed response or abstention, not inferred
answers.
This is a manual source-coverage audit, not evidence of task success; synthetic
role labels do not supply missing policy text. Reproduce label/manifest
consistency with `uv run python scripts/evaluate_proposal_case_coverage.py`;
artifact: [`proposal-business-case-corpus-coverage.json`](../artifacts/evaluation/proposal-business-case-corpus-coverage.json).
The current employee access answer was evaluated end to end with an authenticated
employee account using Qwen3.8-27B; its citation, supported clauses, and missing
dedicated-policy disclosure passed in
[`employee-access-policy-qwen38-rerun-20260928.json`](../artifacts/evaluation/employee-access-policy-qwen38-rerun-20260928.json).

Selected current authenticated task checks are recorded in separate case
artifacts; they are not aggregated into a full 12-case pass. The invoice and
manufacturing cases passed 2/2, customer-service and technical-document cases
passed 2/2, compliance passed 1/1, and the dynamic BI case passed 1/1 after
allowing both `doc_count` and `document_count` SQL aliases. The 2024 business
finance case and executive decision-support case remain blocked by provider
HTTP 429 responses. The first executive attempt's SQL-path 503 is fixed by
retrieving report evidence directly from the role-filtered knowledge agent;
the new app-wiring regression checks that the report route never calls hybrid
SQL. The earlier batched business-case artifacts do not record their model ID,
so they cannot support model-specific scores. A new BI rerun records
`openai/gpt-oss-20b` and passes its route, dynamic grouped results and source
checks in [`proposal-business-app-gptoss20b-bi-provenance-20260928.json`](../artifacts/evaluation/proposal-business-app-gptoss20b-bi-provenance-20260928.json).
These pass counts verify only the exact rubric and source/task slice in each
artifact, not broad domain readiness.

## 6. Security and operational behavior

The application enforces role-aware retrieval before ranking; tests include employee denial and authenticated upload authorization. Parsed upload output is persisted before embedding to support inspection and embedding retry. KPI review requires admin verification. Trace records are privacy-minimized. Public Vinamilk documents and synthetic role labels mean the current demonstration does not validate real company confidentiality policy or private-document segregation. The migration/data-flow details and setup steps are in the [deployment guide](deployment-guide.md) and [data guide](../data/README.md).

Local app HTTP/WebSocket and selected browser flows have previously been checked. Hosted CI validated configuration and image builds, but a deployed Nginx/container path and release workflow have not been verified. The environment and validation snapshot is maintained in [docs/README.md](README.md#current-validation-snapshot).

## 7. Limitations and threats to validity

1. **Small, selected corpus and labels.** Retrieval uses nine questions, and passage labels are pooled/non-exhaustive. Metrics are sensitive to query and judgment selection.
2. **Public-only access-control demonstration.** Synthetic role metadata cannot establish suitability for real HR, legal, supplier or customer documents.
3. **OCR coverage.** The corrected v6 six-region set includes one Vietnamese financial table, but the two actual image-only scans are English. The table is born-digital, only one page is labeled, and cell-text presence ignores position; broad table/layout quality is unmeasured. GPU/CPU conditions differ. The separate production PDF parser test is Tesseract-only at another DPI/path; its same-dataset repeat reproduced text scores but varied from 1.918 to 5.718 seconds. Add Vietnamese image-only scans and cell-coordinate labels before model selection. See the [production parser baseline and repeat](../docs/technical/document-processing.md#current-boundaries).
4. **Embedding and reranker comparison.** Only 93 of 3,785 chunks were used for paired embedding evaluation; rerankers saw top two candidates and no GPU. Batch sizes differed.
5. **Generation evaluation.** Automated exact anchors and citation checks miss semantic errors, as demonstrated by the wrong unit conversion. No blinded reviewers, inter-rater agreement or adequately sized human rubric are present.
6. **Performance.** In-process local endpoint testing is not deployed load testing; no GPU utilization or multi-host scalability curve is available.
7. **Business cases.** Route wiring covers proposal categories, but the current 26-source coverage audit finds four requests unsupported and six only partially supported in this public corpus. Employee access evidence is limited to the Code of Conduct; it references a missing dedicated Information System Policy. The customer-service source covers Vinamilk Shop returns only; real evidence for other private domains remains absent. Route existence is not business-task completion.
8. **Unfinished optimization experiments.** Controlled chunking, prompt, query-rewrite, context-compression, hybrid-weight, embedding-optimization and cache comparisons remain.

These limits mean the results support feasibility and identify follow-up work; they do not establish production readiness or broad superiority over alternative models.

## 8. Conclusion and remaining work

The prototype demonstrates a source-backed path from public Vietnamese enterprise documents through staged parsing, role-filtered retrieval and cited Q&A to reviewable dashboard metrics. Small paired runs show that document-level retrieval can succeed while finding the exact evidence passage remains difficult; embedding and reranker rankings vary by metric and have not been tested at proposal scale. The authenticated five-case app suite and local API smoke provide useful integration evidence. A captured Supavisor session-cap failure led to a 10-connection per-process queue; a post-fix loopback run passed 80/80 requests at concurrency 16, which verifies the fix but not capacity. V7 adds four English scans and a paired Tesseract PSM comparison, while four-engine v7 OCR, representative Vietnamese OCR/layout quality, human QA review, private-domain corpus, deployed scaling and controlled optimization remain open. The four-engine v6 results still use unlike CPU hosts and do not establish a production winner.

The next acceptance work is recorded in the [proposal matrix](README.md#proposal-coverage) and the concise [proposal acceptance checklist](technical/agents-and-evaluation.md#proposal-acceptance-checklist). That checklist separates the five baseline groups (OCR, embeddings, LLMs, retrieval and reranking) from document/QA/system evaluations, optimization experiments, the twelve business cases, and delivery/deployment requirements. The highest-value experiments are: (1) add manually reviewed Vietnamese image-only scans and table-cell coordinates, then compare engines under controlled resource conditions; (2) expand judged queries/passages and paired embedding runs; (3) complete candidate reranking at a practical accelerator or optimized batch configuration; (4) collect blinded human QA ratings; (5) add authorized documents and tasks for unsupported business domains; and (6) verify Docker/Nginx/CI and external load behavior. This document remains an evidence-backed draft; submit the final thesis report only after the remaining experiments and review requirements are closed or explicitly scoped as limitations.

## References

1. P. Lewis et al., “Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks,” 2020. [arXiv:2005.11401](https://arxiv.org/abs/2005.11401).
2. V. Karpukhin et al., “Dense Passage Retrieval for Open-Domain Question Answering,” 2020. [arXiv:2004.04906](https://arxiv.org/abs/2004.04906).
3. J. Chen et al., “BGE M3-Embedding: Multi-Lingual, Multi-Functionality, Multi-Granularity Text Embeddings Through Self-Knowledge Distillation,” 2024. [arXiv:2402.03216](https://arxiv.org/abs/2402.03216).
4. Y. Zhang et al., “ Qwen3 Embedding: Advancing Text Embedding and Reranking Through Foundation Models,” 2025. [arXiv:2506.05176](https://arxiv.org/abs/2506.05176).
5. PaddleOCR team, “PP-OCRv5: A Practical Ultra- lightweight OCR System,” 2025. [arXiv:2507.05595](https://arxiv.org/abs/2507.05595).
6. L. Es et al., “RAGAS: Automated Evaluation of Retrieval Augmented Generation,” 2023. [arXiv:2309.15217](https://arxiv.org/abs/2309.15217).
