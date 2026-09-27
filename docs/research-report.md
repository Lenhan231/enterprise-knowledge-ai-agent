# Enterprise Knowledge AI Agent for Vietnamese Enterprise Documents

**Status:** evidence-backed research draft, 27 September 2026
**Scope:** Vinamilk public-document prototype; not a completed thesis or production evaluation.
**Proposal:** [docs/proposal.docx](proposal.docx) · **Evidence index:** [proposal coverage and evaluation protocol](README.md)

## Abstract

This report describes an enterprise knowledge assistant prototype for Vietnamese corporate documents. The system combines document parsing and OCR, persisted processing output, role-filtered PostgreSQL/pgvector retrieval, hybrid search, grounded question answering, multi-agent routing, source-backed analytics and an interactive web interface. The evaluated corpus is restricted to public Vinamilk reports and product/policy material; role labels are synthetic demonstration controls. On nine labeled retrieval questions, document-level ranking is high while selected passage-level recall remains modest. Three embedding models were evaluated on a paired 93-chunk sample; their document-level MRR ranged from 0.670 to 0.707. A five-case authenticated app QA suite passed its deterministic source, fact, route and abstention checks. These runs show an operational prototype and a reproducible evaluation path, not generalizable model superiority: OCR model coverage, human QA scoring, realistic private business cases, deployed scalability and several proposal experiments remain incomplete.

## 1. Problem and objectives

Vietnamese enterprises hold knowledge in annual reports, policies, product documents and operational files. Keyword search alone misses paraphrases; vector retrieval can return a relevant document but an irrelevant passage; generated answers can also misstate values or expose documents to unauthorized roles. The prototype therefore targets a traceable flow from source file to parsed text, retrieval, answer citation and dashboard evidence.

The objectives in the proposal are to provide: (1) multi-format ingestion and document understanding, (2) enterprise knowledge retrieval with RBAC, (3) a grounded conversational and multi-agent interface, (4) source-backed analytics/dashboard, and (5) measured evaluation and deployment documentation. The implementation and remaining proposal coverage are tracked in [the coverage matrix](README.md#proposal-coverage).

## 2. Background

Retrieval-Augmented Generation (RAG) combines a non-parametric retriever with a language model to ground generation in retrieved documents [Lewis et al.](https://arxiv.org/abs/2005.11401). Dense Passage Retrieval established a dual-encoder approach for retrieving passages by semantic similarity [Karpukhin et al.](https://arxiv.org/abs/2004.04906). For multilingual corpora, BGE-M3 reports multilingual dense, sparse and multi-vector retrieval capabilities [Chen et al.](https://arxiv.org/abs/2402.03216); Qwen3 Embedding reports multilingual embedding and reranking model families [Zhang et al.](https://arxiv.org/abs/2506.05176). These papers motivate candidate methods but do not substitute for evaluation on this corpus.

OCR quality is especially consequential for scanned reports, tables and mixed layouts. PaddleOCR 3.0 describes an OCR/document-parsing toolkit spanning text recognition and layout-related components [PaddleOCR team](https://arxiv.org/abs/2507.05595). This prototype's three manually transcribed crops are insufficient to compare OCR engines. For RAG evaluation, automated component metrics can help diagnose retrieval/context/generation stages, but do not establish semantic faithfulness by themselves; RAGAS is one published evaluation framework [Es et al.](https://arxiv.org/abs/2309.15217).

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

On the refreshed 173-chunk sample and current 12 cases, BGE/e5 MRR is
0.606/0.706 and nDCG@3 is 0.616/0.719. Qwen was attempted but no score was
produced because its first batch took about 200 seconds on CPU. This new
comparison is also sampled/document-level and does not establish a winner.
See the [paired 12-case summary](../artifacts/evaluation/vinamilk-embedding-three-model-expanded-25docs-12cases-20260927.json).

### 5.3 Reranking

On nine cases, the paired top-2 CPU comparison (sequence length 256) found BGE Reranker v2 M3 changed selected-passage MRR from 0.389 to 0.333 at 1.73 seconds mean rerank time; Qwen3-Reranker-0.6B changed it from 0.389 to 0.444 at 15.74 seconds. A refreshed BGE top-30 run on the same nine current cases and 21 selected passage labels (CPU, batch 2, sequence length 256) improved passage MRR from 0.429 to 0.459 and Recall@2 from 0.241 to 0.259, while document MRR declined from 1.000 to 0.917. Mean rerank time was 29.67 seconds/query and peak RSS 2,820 MiB. This reveals a trade-off: a small passage-level gain coincided with worse document ranking. Qwen top-30 has not been measured on this exact candidate set; the host's swap was nearly exhausted after the BGE run, so no full-depth paired model selection is claimed. Artifacts: [BGE top-30](../artifacts/evaluation/vinamilk-reranker-bge-top30-passage-cpu.json), [BGE top-2](../artifacts/evaluation/vinamilk-reranker-bge-reranker-v2-m3-cpu-top2-passage.json), and [Qwen top-2](../artifacts/evaluation/vinamilk-reranker-qwen3-reranker-0.6b-cpu-top2-passage.json).

### 5.4 OCR and document extraction

The human-transcribed OCR pilot contains three crops, including a raster-embedded product poster but no physical scan. Tesseract 5.5.3 scored micro CER 0.163 / WER 0.382 and macro CER 0.312 / WER 0.542; the poster alone scored CER 0.669 / WER 0.938. PaddleOCR initialization was OS-killed, EasyOCR was killed during model loading, and Surya was not run in the measured environment. Thus none of the three proposal OCR candidates has a valid paired comparison yet; the Tesseract pilot is diagnostic only. See [OCR report](../artifacts/evaluation/vinamilk-ocr-human-reviewed-tesseract-v2.json).

On two manually reviewed financial-report pages and five anchor fields, born-digital 2024 PDF extraction matched all three balance-sheet anchors exactly and detected 2/2 table regions. Synthetic raster-PDF OCR matched 0/3 anchors exactly but 3/3 after numeric normalization; image-upload OCR matched 2/3 exactly and 3/3 normalized. The 2020 infographic path matched 2/2 anchors. These are narrow page-level diagnostics, not document-wide quality claims; no representative physical scan, invoice, formula or figure benchmark exists. See [extraction artifact](../artifacts/evaluation/vinamilk-document-extraction-scan-table-v9.json).

### 5.5 LLM and application QA

The refreshed live authenticated application suite passed 5/5 automated cases covering 2020/2024 finance, sustainability, product information and employee financial-data denial. Checks covered expected agent, expected fact anchors, cited document, citation consistency and abstention; mean end-to-end latency was 26.405 seconds. During browser verification, a 2024 financial summary initially mixed two differently labelled figures and invented a reconciliation because the report prompt explicitly required both. The report agent now returns the requested consolidated headline metrics, avoids unsupported accounting-basis claims, and withholds answers with unverified citations. The rerun answered with 61,824 billion VND consolidated revenue and 9,453 billion VND after-tax profit, both cited to the matching annual-report excerpt. Analyst dashboard filters and admin processing/access/monitoring screens rendered in browser. A live authenticated XLSX upload reached `ready`; parser table/formula metadata, one indexed chunk and private Storage bytes were read back before test data was removed. A second live smoke injected embedding initialization failure after parsing newline-terminated TXT, retried the saved chunk to `ready`, and verified role-filtered BM25 retrieval for `finance_analyst` with no employee result. It exposed and fixed a trailing-newline chunking bug and a transaction issue that left parsed retry status stale; both fixtures were removed and cleanup verified. These are one-file integration checks; broader format coverage and deployed proxy behavior remain open. The QA suite verifies route behavior on its examples, not semantic faithfulness or user usefulness. Artifact: [`vinamilk-app-qa-suite.json`](../artifacts/evaluation/vinamilk-app-qa-suite.json).

A separate five-case model proxy comparison found expected source/fact/denial checks passing for GPT-OSS-20B, Qwen3.8-27B and GPT-OSS-120B. One 120B response included an incorrect unit conversion despite passing headline checks. The requested Qwen3/Llama 3/GPT comparison is therefore not complete: exact proposal checkpoints were unavailable in the tested provider. A blinded packet exists, but each of its two reviewer files has 0/10 completed ratings, so no human quality score or inter-reviewer agreement is available. Automated scores are not a substitute for human faithfulness, answer relevance or hallucination ratings. See [LLM evaluation](technical/llm.md) and the [paired artifacts](../artifacts/evaluation/).

### 5.6 API load and dashboard data

The repeated local ASGI run completed 70/70 health, dashboard and analytics requests across concurrency levels 1, 2 and 4. Throughput was 0.430, 0.804 and 1.441 requests/second; p95 latency was 4.53, 4.11 and 4.92 seconds. Peak RSS was 625.9 MiB. The run was in-process, excluded a network/proxy/deployment hop, had no GPU telemetry and did not load-test uploads or concurrent LLM generation. It is a smoke test, not a deployment capacity/scalability study. Artifact: [`vinamilk-api-load-repeat10.json`](../artifacts/evaluation/vinamilk-api-load-repeat10.json).

Dashboard KPI candidates are extracted from report text with source/page/quote evidence and are not published until an administrator verifies value and unit. The latest refresh created 35 candidates; six remain `needs_review`, 39 stale unmatched candidates are superseded, and zero metrics are verified. Therefore the KPI dashboard correctly has no verified metric series to plot; showing an empty state is preferable to inventing values. Candidate extraction is documented in [agents and evaluation](technical/agents-and-evaluation.md).

### 5.7 Hybrid retrieval weight diagnostic

A read-only paired sweep evaluated the current dense and BM25 baselines alongside four reciprocal-rank-fusion settings over the same nine questions, role filters, corpus snapshot (3,785 ready Vinamilk chunks) and manually reviewed selected passage labels. Default dense:BM25 weights 1:2 with `k=60` had document MRR 0.926, passage MRR 0.440 and passage nDCG@5 0.329. Equal weights 1:1 produced document MRR 0.944, passage MRR 0.384 and nDCG@5 0.322. Dense-heavy 2:1 produced document MRR 1.000 but passage MRR 0.393 and nDCG@5 0.314. Lowering `k` to 20 at 1:2 yielded document MRR 0.944 and passage MRR 0.426. BM25 alone had passage Recall@5 0.352; dense alone had document MRR 1.000. These small, non-exhaustive labels show a metric trade-off, not a stable winner, so production weights remain unchanged. Artifact: [`vinamilk-hybrid-weight-sweep-20260927.json`](../artifacts/evaluation/vinamilk-hybrid-weight-sweep-20260927.json).

### 5.8 Chunking comparison

Seed-PDF and upload parsers share sentence-aware and fixed-window strategies. On native text from 96 pages of the 2024 report, the boundary diagnostic produced 428 fixed chunks (mean 970 characters; 10.5% sentence-ending boundaries) and 438 sentence-aware chunks (mean 857; 81.7% sentence-ending boundaries), both below the 1,100-character ceiling. A separate paired diagnostic compared the five live fixed annual-report indexes (1,912 chunks) with 1,978 sentence-aware chunks built in memory from the same five reports. Across five finance questions, document MRR was 1.0 for both strategies because the candidate corpus was restricted to those five reports. Passage MRR was 0.2715 fixed and 0.2648 sentence-aware; Recall@5 was 0.10 for both. The alternate passage labels were transferred by page and trigram overlap rather than independently reviewed, so this small dense-only result is preliminary and cannot select a strategy or establish answer quality. Parsing took 48.48 s, alternate embedding 94.77 s, and peak RSS was 2,140.7 MiB on CPU. Both runs are read-only against the live database. Artifacts: [`vinamilk-chunking-2024-boundary-diagnostic.json`](../artifacts/evaluation/vinamilk-chunking-2024-boundary-diagnostic.json) and [`vinamilk-chunking-retrieval-finance-five-year.json`](../artifacts/evaluation/vinamilk-chunking-retrieval-finance-five-year.json); see [chunking notes](technical/chunking.md) for reproduction.

### 5.9 Agent route evaluation

The live classifier/router was measured on twelve manually mapped proposal business tasks. The effective router selected all twelve expected agents; nine cases used direct provider classifications, while three hit provider rate limits and correctly used the existing deterministic fallback. A pre-prompt run without fallbacks scored 11/12 and misrouted “Compare document counts by business domain” to knowledge. The prompt now explicitly describes metadata counts and group-by requests as analytics; a separate direct-provider recheck routed that case to analytics in 36.3 seconds. This is a narrow routing benchmark: the labels contain no dashboard case, and stub agents mean it does not measure tools, grounded task completion, answer quality, or unsupported private domains. See the [full route report](../artifacts/evaluation/proposal-business-route-evaluation.json), [pre-prompt run](../artifacts/evaluation/proposal-business-route-evaluation-pre-prompt.json), and [targeted recheck](../artifacts/evaluation/proposal-business-route-analytics-recheck.json).

### 5.10 Manifest metadata propagation audit

A read-only check compared curated manifest fields with persisted document rows
and every ready chunk. Across all 25 ready sources, all 350 document-level and
52,250 chunk-level field checks matched exactly across 4,750 chunks. No
manifest entries were missing or not ready. This verifies metadata
propagation; it does not measure automatic metadata extraction or validate the
curated labels against source-document content. See the
[2026-09-27 metadata audit artifact](../artifacts/evaluation/vinamilk-corpus-metadata-audit-20260927.json).

## 6. Security and operational behavior

The application enforces role-aware retrieval before ranking; tests include employee denial and authenticated upload authorization. Parsed upload output is persisted before embedding to support inspection and embedding retry. KPI review requires admin verification. Trace records are privacy-minimized. Public Vinamilk documents and synthetic role labels mean the current demonstration does not validate real company confidentiality policy or private-document segregation. The migration/data-flow details and setup steps are in the [deployment guide](deployment-guide.md) and [data guide](../data/README.md).

Local app HTTP/WebSocket and selected browser flows have previously been checked; Nginx/container runtime and hosted CI/CD are not verified in the current evidence set. The environment and validation snapshot is maintained in [docs/README.md](README.md#current-validation-snapshot).

## 7. Limitations and threats to validity

1. **Small, selected corpus and labels.** Retrieval uses nine questions, and passage labels are pooled/non-exhaustive. Metrics are sensitive to query and judgment selection.
2. **Public-only access-control demonstration.** Synthetic role metadata cannot establish suitability for real HR, legal, supplier or customer documents.
3. **OCR coverage.** Three crops and a synthetic raster are not representative physical scans. Two proposal engines did not complete in the constrained CPU environment; Surya is unmeasured.
4. **Embedding and reranker comparison.** Only 93 of 3,785 chunks were used for paired embedding evaluation; rerankers saw top two candidates and no GPU. Batch sizes differed.
5. **Generation evaluation.** Automated exact anchors and citation checks miss semantic errors, as demonstrated by the wrong unit conversion. No blinded reviewers, inter-rater agreement or adequately sized human rubric are present.
6. **Performance.** In-process local endpoint testing is not deployed load testing; no GPU utilization or multi-host scalability curve is available.
7. **Business cases.** Route wiring covers proposal categories, but the corpus lacks real evidence for many private enterprise domains. Route existence is not business-task completion.
8. **Unfinished optimization experiments.** Controlled chunking, prompt, query-rewrite, context-compression, hybrid-weight, embedding-optimization and cache comparisons remain.

These limits mean the results support feasibility and identify follow-up work; they do not establish production readiness or broad superiority over alternative models.

## 8. Conclusion and remaining work

The prototype demonstrates a source-backed path from public Vietnamese enterprise documents through staged parsing, role-filtered retrieval and cited Q&A to reviewable dashboard metrics. Small paired runs show that document-level retrieval can succeed while finding the exact evidence passage remains difficult; embedding and reranker rankings vary by metric and have not been tested at proposal scale. The authenticated five-case app suite and local API smoke provide useful integration evidence, while OCR, human quality review, private-domain corpus, deployed scaling and controlled optimization remain open. On the measured host, only about 3.6 GiB RAM was available, swap was nearly exhausted, and CUDA was unavailable; heavyweight OCR engines were not installed or rerun because those constraints previously caused OS kills. The benchmark is documented for a better-provisioned host.

The next acceptance work is recorded in the [proposal matrix](README.md#proposal-coverage) and the concise [proposal acceptance checklist](technical/agents-and-evaluation.md#proposal-acceptance-checklist). That checklist separates the five baseline groups (OCR, embeddings, LLMs, retrieval and reranking) from document/QA/system evaluations, optimization experiments, the twelve business cases, and delivery/deployment requirements. The highest-value experiments are: (1) obtain reviewed physical scans and run PaddleOCR, EasyOCR and Surya under the same environment; (2) expand judged queries/passages and paired embedding runs; (3) complete candidate reranking at a practical accelerator or optimized batch configuration; (4) collect blinded human QA ratings; (5) add authorized documents and tasks for unsupported business domains; and (6) verify Docker/Nginx/CI and external load behavior. The final thesis report should be revised only after those evidence gaps close.

## References

1. P. Lewis et al., “Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks,” 2020. [arXiv:2005.11401](https://arxiv.org/abs/2005.11401).
2. V. Karpukhin et al., “Dense Passage Retrieval for Open-Domain Question Answering,” 2020. [arXiv:2004.04906](https://arxiv.org/abs/2004.04906).
3. J. Chen et al., “BGE M3-Embedding: Multi-Lingual, Multi-Functionality, Multi-Granularity Text Embeddings Through Self-Knowledge Distillation,” 2024. [arXiv:2402.03216](https://arxiv.org/abs/2402.03216).
4. Y. Zhang et al., “ Qwen3 Embedding: Advancing Text Embedding and Reranking Through Foundation Models,” 2025. [arXiv:2506.05176](https://arxiv.org/abs/2506.05176).
5. PaddleOCR team, “PP-OCRv5: A Practical Ultra- lightweight OCR System,” 2025. [arXiv:2507.05595](https://arxiv.org/abs/2507.05595).
6. L. Es et al., “RAGAS: Automated Evaluation of Retrieval Augmented Generation,” 2023. [arXiv:2309.15217](https://arxiv.org/abs/2309.15217).
