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
