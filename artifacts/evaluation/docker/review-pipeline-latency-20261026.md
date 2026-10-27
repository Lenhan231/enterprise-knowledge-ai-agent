# Local Docker pipeline latency report ? 26 October 2026

**E5 is not the main latency bottleneck in this run.** Warm query embedding had a median of **117.28 ms**, compared with **16.71 s** for CPU reranking and **3.27 s** for database retrieval. Provider generation also produced one large outlier. These are observed measurements, not a production capacity claim.

## Setup and measurement boundaries

- Started 2026-10-26T00:29:36.097153+07:00 (Asia/Saigon). Benchmark elapsed time: 473.36 seconds.
- Ten inventory questions: four Knowledge, three Analytics, three mixed; repeated in the same order for 20 requests. All explicitly used Agentic routing and translated hybrid retrieval with BGE reranking.
- Benchmark concurrency: one. One additional non-benchmark chat request was observed in the shared container during the first pass; the server was not isolated. Do not attribute all between-pass changes to warming.
- Current Docker: 16 CPUs, 7.381 GiB available RAM, CPU-only. Models: multilingual E5-base, BGE-reranker-v2-m3 (FP32), Groq-hosted GPT-OSS-120B.
- Compose recreation through HTTP readiness took **62.67 s**, including loading cached models. This is separate from request timing.
- Both models were preloaded. The first pass is not ten cold starts; only the first relevant invocation is first inference. The warm pass also uses the existing query-translation cache.
- HTTP E2E excludes login but includes authentication, transport, handler execution and existing event persistence. Server request_total_ms ends before event persistence and excludes authentication.
- Stage values are wall-clock milliseconds. A skipped stage is null and is excluded from that stage?s distribution. Nested totals and concurrent branch times overlap, so the rows must not be added to infer E2E.
- One citation-rejected request did not return response metadata. Its timings were recovered from the unique failed Docker timing record between its two matching adjacent successful requests. Executed-stage summaries below include that failure; no failed result was rerun or discarded.

## Request latency

| Pass | Requests | HTTP 200 / 503 | Median HTTP E2E | Range |
|---|---:|---:|---:|---:|
| First after restart | 10 | 9 / 1 | 29.08 s | 4.27?42.76 s |
| Warm repeat | 10 | 10 / 0 | 22.76 s | 4.88?62.22 s |

| Question group | First-pass median [range] | Warm median [range] |
|---|---:|---:|
| Knowledge | 34.53 s [19.17?42.76], n=4 | 23.55 s [18.10?28.93], n=4 |
| Analytics | 6.49 s [4.27?7.13], n=3 | 6.63 s [4.88?8.42], n=3 |
| Mixed | 29.94 s [28.38?39.09], n=3 | 27.88 s [22.52?62.22], n=3 |

## Stage latency

Values: median [minimum?maximum], milliseconds. Sample counts differ because SQL-only requests skip E5/retrieval, and non-success SQL payloads can skip execution and generation.

| Stage | First pass (ms) | Warm pass (ms) |
|---|---:|---:|
| Router selection | 858.80 [394.02?3,731.32], n=10 | 562.82 [444.18?1,014.52], n=10 |
| E5 query embedding | 173.23 [131.97?916.02], n=7 | 117.28 [83.78?135.89], n=7 |
| Database retrieval (dense + lexical calls) | 3,340.60 [3,315.67?4,613.32], n=7 | 3,270.62 [3,017.58?3,972.92], n=7 |
| RRF scoring / fusion | 0.79 [0.53?1.42], n=7 | 0.67 [0.59?2.44], n=7 |
| Query translation (including cache lookup) | 666.77 [574.30?689.43], n=7 | 0.01 [0.01?0.02], n=7 |
| BGE reranking | 20,198.44 [10,976.29?29,596.98], n=7 | 16,708.64 [10,857.62?20,616.17], n=7 |
| Answer generation (sum of calls per request) | 1,357.64 [667.95?11,697.69], n=8 | 924.06 [506.11?58,126.42], n=9 |
| SQL planning / repair calls | 6,221.92 [802.87?15,634.68], n=6 | 1,684.48 [808.57?2,049.81], n=6 |
| Approved SQL execution | 1,781.09 [1,546.95?1,841.00], n=3 | 1,690.64 [1,521.80?3,612.52], n=4 |
| Mixed-answer synthesis | 537.30 [406.43?684.80], n=3 | 425.27 [327.17?684.42], n=3 |
| Retrieval total (includes child stages) | 24,383.90 [15,012.79?34,626.67], n=7 | 19,937.02 [13,963.86?24,696.73], n=7 |
| LangGraph workflow total | 26,620.95 [1,900.23?36,879.97], n=10 | 20,238.25 [2,512.77?59,848.05], n=10 |

## Outcomes and limitations

- **19/20 HTTP 200; 1/20 HTTP 503.** The 503 was K4 on the first pass: generated answer lacked source citations and the existing validation guard rejected it. The timing runner exited nonzero to preserve this detected failure; it completed all 20 requests.
- **5 HTTP-200 responses reported application_ok=false**, and **7 HTTP-200 responses returned no citations**. These groups overlap. HTTP completion is not a quality pass or evidence of a correct answer.
- The intended route matched all 19 returned route fields. The failed response did not expose its selected route. This small, deliberately selected set does not establish general router accuracy.
- The warm M2 request took **62.22 s** HTTP E2E, with **58.13 s** summed answer-generation calls. This is retained. Model inference, provider/network delay and SDK retries were not separately measured, so its provider-side cause is unverified.
- Cached query translation fell to about 0.01 ms on repeats. E5 still encoded each query; no answer cache or embedding-result cache was added.
- OCR, upload and ingestion were not run. Existing OCR/quality results retain their original date, workload and hardware. No concurrency stress test, isolated-server benchmark, quality re-evaluation or production p95 estimate was performed.

## Container resource samples

| Container | Samples | Maximum sampled RAM | Maximum sampled Docker CPU |
|---|---:|---:|---:|
| enterprise-knowledge-ai-agent-web-1 | 101 | 1.871 GiB | 1522.46% |
| enterprise-knowledge-ai-agent-db-1 | 101 | 0.033 GiB | 0.86% |

Docker CPU percentages count approximately 100% per logical CPU: 1,522.46% is about 15.22 busy cores, not 1,522% of the 16-core engine. Samples were taken roughly every five seconds, including monitor overhead and the observed extra request. These are sampled maxima, not exact peaks or per-stage attribution. Local PostgreSQL container usage does not measure any external database services; hosted LLM RAM/GPU usage is unavailable.

## Implementation and validation

- Request-local ContextVar collection propagates through asyncio tasks and asyncio.to_thread workers. Timings appear in metadata.latency and structured agent_latency Docker log records; logs contain timings/status, not questions or credentials.
- Database event telemetry still stores total elapsed_ms only. There is no schema migration, monitoring dashboard, routing-policy change, model change or Vercel frontend deployment.
- Five new timing/report tests pass, covering request/thread isolation, failure recording, repeated-call aggregation, missing-evidence response timing, and exclusion of skipped stages from distributions.
- Full suite: 234 tests, 9 failures and 47 errors; all 56 failing IDs match the previously verified pre-change baseline. The subsequently added report-summary test passed separately. Compileall and diff whitespace checks pass.
- The rebuilt instrumented image is sha256:e377ac16f9985fcd5b5206b3a4bd1d195eb976c507b6b5f52b72153d98400efc.

## Evidence files

- [Raw requests, events, resource samples and summaries](review-pipeline-latency-20261026.json)
- [Structured Docker timing events, including the rejected request](review-pipeline-latency-20261026-server-events.json)
- [Stage summary CSV](review-pipeline-latency-20261026-stages.csv)
- [Startup measurement](latency-startup-20261026.json)
- Reproduce with `python scripts/operations/measure_pipeline_latency.py` after restarting the web service. Archive the current JSON before rerunning, because the default output path is reused.
