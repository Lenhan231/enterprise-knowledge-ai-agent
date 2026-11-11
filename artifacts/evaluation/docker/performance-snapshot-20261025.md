# Docker pipeline performance snapshot — 2026-10-25

Measured around 13:58–14:07 UTC (20:58–21:07 Asia/Saigon). This is a bounded inspection, not a continuous monitor. No application code or Docker configuration changed. Model downloads were avoided.

## Stage measurements

| Stage | Latency | Model / size | Resource evidence and limits |
|---|---|---|---|
| Parsing/OCR | Historical Docling runs: 7.787–28.505 s for one-page documents (7 samples, October 20); no fresh OCR run | Docling layout-heron + TableFormer; Tesseract vie/eng. Tesseract directory: 15,211,203 bytes including auxiliary files. Docling model caches not found in default cache. | No stage-specific CPU/RAM measurement. Historical records may come from a different runtime. |
| Embedding/Retrieval | Unmeasured | Configured intfloat/multilingual-e5-base, default local backend. Cached config absent in default Hugging Face cache; weight size not measured. | No live embedding/retrieval run; did not trigger downloads. This does not prove no cache exists at a custom location. |
| Reranking | Two short query/document pairs: 3497.90 ms first inference, then 362.05 and 335.61 ms. Separate-process model load: 20462.47 ms. | BAAI/bge-reranker-v2-m3: 567,755,777 parameters; 2,271,023,108 bytes FP32 parameter storage; 2,293,242,108 bytes cached repository files (resolved paths deduplicated). | CPU, 8 PyTorch threads; separate probe peak RSS 2361.55 MiB. App already preloads this model, so probe load is not normal request overhead. Not a production 30-candidate benchmark. |
| Generation | 10126.03 ms, one short successful request; 78 input tokens / 24 output tokens | Groq-hosted openai/gpt-oss-120b. Remote weights, RAM and GPU usage not accessible from local Docker. | Includes provider/network latency. Probe ran concurrently with dashboard probe. Not representative document-answer length. |
| E2E request | Live authenticated POST /api/agents/chat in dashboard mode: HTTP 200, 8981.68 ms, n=1. Earlier dashboard event: 12990 ms, October 25 12:39 UTC. | Dashboard flow uses database queries; it does not exercise OCR, embedding, reranking or generation. | Loopback HTTP from inside container; login excluded. Full document Q&A E2E unmeasured. |

Health-only HTTP samples inside container: 124.35, 2.63, 2.31, 2.30, 1.97 ms; HTTP 200. These are not agent E2E timings. Do not add independent stage probes to estimate E2E, or infer p95 from these small samples.

## Docker resource snapshots

| Container | Initial CPU | Initial RAM | Later RAM | Notes |
|---|---|---|---|---|
| web | 0.43% | 1.032 GiB | 1.475 GiB | During probe setup: 82.87% CPU and 1.320 GiB RAM in one sample; not a recorded peak. |
| db (postgres:15) | 0.00% | 32.96 MiB | 33.14 MiB | Running image differs from current compose declaration pgvector/pgvector:pg15. |

Docker engine: 16 CPUs, 7,924,772,864 bytes RAM (~7.381 GiB). Neither container has an explicit CPU or RAM limit. Web has no GPU device requests; probe reports CUDA unavailable. Docker CPU percentages count approximately 100% per busy logical CPU. Resource snapshots are container-wide, not stage attribution.

Web image size reported by Docker: 10.5 GB; PostgreSQL image: 633 MB. Image size includes dependencies and layers and is not model size or runtime RAM. Initial cumulative web network I/O: 1.63 GB received / 36 MB sent; block I/O: 1.51 GB read / 2.42 GB written. These are cumulative counters, not current throughput.

## Operational observations

- Web has no mounted volumes. Models downloaded into its writable filesystem will not persist when the container is replaced. The compose embedding_model_cache volume is attached only to embedding-check, not web.
- Full pipeline profiling still needs provisioned embedding/Docling assets, a representative document and query, and concurrent resource sampling. Existing stored agent telemetry provides total handler elapsed time; retrieval and reranker timings are not a complete persisted per-stage trace.
- No load/concurrency benchmark or continuous background monitor was started. No p95 capacity claim is supported. The dashboard probe added its normal agent telemetry event; generation used 102 provider tokens.

## Agent router addendum — October 25, 15:30 UTC (22:30 Asia/Saigon)

Verified router.py and agents/main.py SHA-256 hashes match the running container. The /api/agents/chat runtime uses _FallbackClassifier (local deterministic rules) for auto mode. Explicit knowledge/sql/dashboard modes bypass classification. Agentic selection calls Groq; agentic hybrid synthesis may add another provider call after both agents finish.

Measured the real AgentRouter and classifier in a separate process inside the existing web container. Leaf agents were immediate stubs to isolate router overhead; these are not live request latency measurements. Each route received one graph warm-up, 100 selection samples and 50 graph invocations. Assertions verified selected destinations and returned agent names for every measured invocation.

| Auto destination | Mean selection (ms) | Mean graph + stub agents (ms) | Graph sample p95 (ms) |
|---|---:|---:|---:|
| Knowledge | 0.3751 | 5.8997 | 7.1152 |
| Analytics | 0.2877 | 8.2963 | 10.9951 |
| Dashboard | 0.2712 | 8.3383 | 10.5353 |
| Hybrid | 0.3489 | 8.3251 | 10.8045 |
| Report | 0.3211 | 8.4332 | 12.0981 |

One real agentic selection for a returns-policy question chose knowledge successfully in 2058.48 ms using Groq openai/gpt-oss-120b (128 input / 51 output tokens). No downstream agents or synthesis were invoked in this provider probe. Auto routing needs no model weights; agentic routing uses the hosted model and has no local model-weight allocation.

Local probe resource evidence: 500 selections + 250 graph invocations + 5 graph warm-ups took 2194.97 ms wall time and 2419.42 ms process CPU time. Whole-probe process high-water RSS rose from 141.06 to 164.61 MiB (~23.55 MiB); this includes graph execution, temporary stub results, runtime allocation and tracing machinery, and is not an exact router allocation. Baseline already includes imports. Remote provider resources were not measured. No continuous resource sampling or load benchmark was run.

Routing correctness observations (unfixed): both "How many documents are there?" and "Count documents by domain." selected knowledge. The first wording is absent from the explicit document-count matching rules. The second is recognized by IntentClassifier.fallback as analytics, but _FallbackClassifier's subsequent document-keyword override changes it to knowledge. This can send document-count questions to the wrong agent. No application code was changed.

Existing persisted agent telemetry records total handler latency and final agent, not isolated router selection, graph overhead, or provider selection timing. This addendum is a bounded measurement, not persistent instrumentation. The earlier 8.98-second explicit dashboard request bypassed automatic classification. The sample p95 values above describe only this isolated microbenchmark and do not establish production p95.

## Startup preload and agentic default deployed — October 25, ~15:45–15:49 UTC

This section supersedes the earlier cache-availability snapshot. E5 was already stored in the unattached embedding_model_cache Docker volume; it was absent from the old web container's filesystem. The web service now mounts that volume. Existing BGE files were copied into it before the container was replaced.

- Rebuilt image and recreated only web with docker compose up -d --no-deps web. Database unchanged.
- Docker image sets EMBEDDING_PRELOAD=1. App lifespan initializes EmbeddingService before yielding to accept requests. Missing weights use the existing loader's download behavior; loading failures abort startup. The shared cached backend is reused by retrieval. RERANKER_PRELOAD=1 remains enabled.
- Startup logs show both E5 (199 weight tensors) and BGE (393 tensors) loaded before Application startup complete. Health probe: HTTP 200.
- Default /api/agents/chat agent_mode is now agentic. Served UI has Agentic selected. Auto remains an explicit alternative. Existing role restrictions hide SQL/agentic and select Knowledge for users without analytics access.
- E5 cache files: 1,134,534,380 bytes. BGE cache files: 2,293,242,108 bytes. These are repository cache totals, not exact parameter bytes.

One authenticated live request omitted agent_mode and used the default retrieval method. It returned HTTP 200, agent=agentic, two cited evidence sources, and took 51,245.80 ms over container loopback. Evidence details confirmed intfloat/multilingual-e5-base and translated_hybrid_rerank with BGE applied to 30 candidates. Translation took 3150.51 ms; reranking took 33156.37 ms. No dense fallback or translation error was recorded. Isolated embedding, routing and generation durations were not exposed in this response. This is one first-request sample after restart, not a p95 estimate.

After this request the web container used 1.503 GiB RAM at a sampled 0.60% CPU; PostgreSQL used 33.09 MiB. These are post-request snapshots, not execution peaks.

Validation: new startup success/failure and default-dispatch tests pass. Full suite: 230 tests, 9 failures and 47 errors. A comparison run using HEAD versions of the changed API/startup modules and excluding the three new regression tests ran 227 tests with the same 9 failures and 47 errors; all 56 failing test IDs matched, no new failing IDs. Existing embedding service tests include two failures caused by 1-dimensional fake vectors against the configured 768-dimensional E5 validation. Compileall, JavaScript syntax, Compose validation, and diff whitespace checks passed. Browser automation was unavailable; the deployed HTML default was verified over HTTP. No fresh empty-cache model download was forced because the existing volume already contained E5.
