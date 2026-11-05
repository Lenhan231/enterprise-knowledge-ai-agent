# Production Performance: Reranking, Claim Verification and Latency (Huy)

Date: 3 November 2026. Deployed revision: `main` at `74bdfb2`. Draft section for *VI. Results and Discussion* and *V.3–V.4 Deployment / Scalability* of the group report.

## 1. Setting

- **Deployment.** The Docker Compose stack runs on a CPU-only Contabo VPS (12 GB RAM). It has separate backend, embedding, reranker, document-processing and chunking containers.
- **External services.** PostgreSQL/pgvector is hosted on Supabase. Generation, query translation, search planning and claim verification use Groq `qwen/qwen3.8-27b`.
- **Corpus.** The production knowledge corpus is *VietStyle Enterprise Operating Policy v1.0* (Vietnamese, 50 policy pages, 2,729 indexed chunks in total).
- **Live test set.** Six fixed Vietnamese procurement questions (V1–V6) are sent through the authenticated `/api/agents/chat` route with `scripts/operations/measure_pipeline_latency.py`.
  - The six questions cover approval thresholds, boundary values (5,000,000 / 5,000,001 and 50,000,000 / 50,000,001 VND), a requisition precondition, a receipt-quantity check and one multi-part question (V6).
  - All six reference answers were checked manually against the policy.
  - Each run uses a 15 s pause between requests. Raw JSON and logs are kept on the VPS under `artifacts/local/knowledge-latency/<run>.{json,log}`.
- **What these measurements are.** They are *sequential* single-user measurements on a small, fixed question set. They measure latency and whether known-correct answers survive. They do not measure answer accuracy on unseen questions or throughput.

## 2. Reranker profiling on CPU

The draft's earlier recommendation was to "profile representative CPU reranking before changing models or candidate counts". This section reports that profiling.

### 2.1 Live latency on the VPS (V1–V6, 10 passes)

| Configuration | Successful requests | Reranking time | V6 end-to-end | Outcome |
|---|---|---|---|---|
| BGE-reranker-v2-m3, FP32 | 59/60 | ~29 s per call | 79.7 s | Baseline |
| BGE-reranker-v2-m3, dynamic INT8 | 60/60 | 19.8–26.6 s (per-pass medians) | ~59 s | About 1.75× faster on the VPS CPU |
| BGE INT8, rerank top-20 instead of 30 | V6 lost all citations (0/10) | No measurable gain | — | **Rejected and reverted** |
| mMiniLMv2-L12 (mMARCO), FP32 | 52/52 valid (8 excluded, see note) | 3.4–8.8 s (per-pass medians) | 19–31 s | **Selected for production** |

- **Note on the mMiniLM run.** The eight failed requests were HTTP 503 responses caused by Groq's daily token limit (TPD) in the last passes, as confirmed in the backend logs. They are excluded as provider failures, not reranker failures.
- **Answer quality with mMiniLM.** In a manual review of the mMiniLM answers, V2 and V5 cited one more supporting source each, and V6 was complete. No regression was observed on these six cases.
- **Why top-20 failed.** An offline replay of top-20 using saved scores had predicted no loss. The replay ranked dense-E5 candidates, while production ranks the translated-hybrid fusion order, so the offline simulation was not representative of production for this change.

### 2.2 Offline quality on the frozen VietStyle benchmark (80 cases)

Inputs are the same frozen E5 top-30 candidates per case. Each model rescored the same 2,400 query–passage pairs on a local Intel i5-12400F CPU.

| Reranker | Full evidence@5 (/76) | Evidence components@5 (/244) | Full evidence@10 (/76) | Evidence components@10 (/244) | Median local time per case (30 pairs) |
|---|---|---|---|---|---|
| BGE-reranker-v2-m3 FP32 | 47 | 183 | 55 | 208 | 16.6 s |
| BGE-reranker-v2-m3 INT8 | 47 | 183 | 57 | 209 | 10.8 s |
| mMiniLMv2-L12 FP32 | 47 | 182 | 53 | 203 | 7.1 s |
| mMiniLMv2-L12 INT8 | 45 | 175 | 54 | 208 | 3.6 s |
| AITeamVN Vietnamese reranker FP32 | 47 | 185 | 52 | 197 | 38.0 s |

How to read the table:

- **Denominators.** 4 query–document language directions × 19 eligible intents give 76. The question excluded from the earlier benchmark's full-intent denominator stays excluded. There are 244 required evidence components (61 × 4).
- **Production relevance.** Production passes the top 5 reranked chunks per search branch to generation, so the @5 columns matter most for this deployment.
- **Decision.** mMiniLM FP32 matches BGE at @5 (47 vs 47 cases, 182 vs 183 components) and is several times faster on the VPS. mMiniLM INT8 lost evidence at @5, so it was not adopted.
- **Timing caveat.** The local per-case times come from two harness runs: BGE from one, the other models from another. Their thread settings were not recorded identically, so they indicate relative cost only. The VPS figures in 2.1 are the deployment evidence.
- **Not compared.** `gte-multilingual-reranker-base` was dropped because its remote model code is incompatible with the installed `transformers` 5.17. The proposal's Qwen reranker was not re-run here; only an earlier smoke test exists.

The model is selected with `RERANKER_MODEL` (`mminilm` by default in Compose; `bge` remains available) and the optional `RERANKER_QUANTIZE=int8`. Code default and model revisions are pinned in `src/core/retrieval/reranker.py`.

## 3. Claim verification in production

When `KNOWLEDGE_CLAIM_VERIFICATION_ENABLED=1`, an answer is checked before it is returned:

1. **Arithmetic.** Literal equalities in the answer (for example `90 + 15 = 105`) are evaluated exactly.
2. **Claim splitting.** The answer is split into cited claims.
3. **Claim review.** One Groq call judges each claim against numbered evidence units from the cited sources.

The check is fail-closed: if any step fails, the user receives a "cannot verify" message instead of the draft answer.

| Run | Change | Correct answers kept | Verification time (median / max) |
|---|---|---|---|
| `verifier-mminilm-01` (2 passes) | First live run | 10/12 (V5 blocked twice) | 0.50 s / 1.43 s |
| `verifier-mminilm-02` (1 pass) | After the arithmetic fix | 6/6 | 0.65 s / 1.16 s |

- **Root cause of the V5 false block.** V5 asks whether a receipt with 100 delivered, 90 accepted and 15 rejected is valid. The model wrote the equality inside parentheses: `(90 + 15 = 105)`.
  - The checker split the expression at `=` into `(90 + 15` and `105)`. Neither side parsed, so the answer was rejected as `unverified_arithmetic` before any model call.
  - The fix removes an outer parenthesis that a side does not close (commit `0b55910`, with regression tests).
  - After the fix, V5's equality was checked (`arithmetic_checked: 1`) and the answer was kept.
- **Production status.** The verifier was enabled in production on 3 November 2026.
- **Limits.**
  - The live check covers only six known-correct answers, so it measures false blocking, not detection.
  - The "should block" evidence remains the earlier offline set (28 cases: 11 supported answers kept, 17 unsupported answers blocked).
  - A production hallucination rate has not been measured.
  - Because the check is fail-closed, a Groq outage or quota exhaustion turns into "cannot verify" responses rather than unverified answers.

## 4. End-to-end latency optimisation

Stage timings come from the request-local latency events that each response returns. All runs below use mMiniLM FP32 with the verifier enabled.

| Run | Change | HTTP median | HTTP max | Retrieval median | Correct |
|---|---|---|---|---|---|
| `verifier-mminilm-02` | Starting point | 12.6 s | 23.0 s | 6.8 s | 6/6 |
| `telemetry-bg-01` | Telemetry insert moved off the response path | 9.0 s | 20.3 s | 6.6 s | 6/6 |
| `parallel-db-01` (warm pass) | Dense and BM25 searches run concurrently on reused connections | **6.7 s** | **9.1 s** | **4.4 s** | 12/12 (both passes) |

### Diagnosis

- **Telemetry.** Before the change, every request waited a constant ~3.4 s (`telemetry_persistence`) to open a new Supabase session and insert one monitoring row. The insert now runs on the event loop's executor after the response is ready, on one reused connection that is reopened after a failure.
- **Database.** Read-only probes from the backend container measured:

| Probe (median) | Time | Approximate composition |
|---|---|---|
| `SELECT 1` round trip | 376 ms | Network |
| Dense query | 822 ms | ~376 ms network + ~450 ms execution |
| BM25 query (English / Vietnamese) | 671 / 643 ms | ~376 ms network + ~270–300 ms execution |

- **What dominated retrieval.** Retrieval was dominated by sequential network round trips, not by SQL execution over the 2,729 chunks.
- **Change made.** Translated-hybrid retrieval now starts the dense query before the translation call, then runs the English and Vietnamese BM25 queries concurrently.
  - The repository keeps at most two extra pooled connections and returns broken ones for replacement.
  - Fusion order and the queries themselves are unchanged, so ranking quality is unchanged.

### Remaining warm-pass budget (`parallel-db-01`, medians)

| Stage | Time |
|---|---|
| Database wait after translation | 2.7 s |
| Reranking (mMiniLM) | 1.5 s |
| Answer generation (Groq) | 0.84 s |
| Claim verification (Groq) | 0.59 s |
| Search planning (Groq) | 0.41 s |
| Query embedding | 0.06 s |

- **Changed meaning of `database_retrieval`.** Since `parallel-db-01`, `database_retrieval` is the database wait remaining after translation, not the sum of the individual queries. It is therefore not directly comparable with earlier runs; HTTP and retrieval totals are.
- **First request after a restart.** It is slower (23.7 s for V1 in the first pass) because the pooled connections must be opened.

## 5. Coverage of the proposal's system-performance metrics

| Proposal metric | Status |
|---|---|
| Average response time | Measured, sequential: 6.7 s median warm, 9.1 s max on V1–V6 |
| Retrieval latency | Measured: 4.4 s median, including reranking |
| Throughput / scalability | **Not measured.** All runs are sequential. The reranker serves one request at a time (process-wide lock), and each backend process allows at most 10 Supabase connections |
| GPU utilisation | Not applicable to the deployment, which is CPU-only. GPU timings exist only for earlier offline benchmarks (RTX 2060 / T4) |

## 6. Limitations

- **Small live set.** The live set has six questions, all procurement-focused, with known answers. It is a regression and latency check, not an accuracy estimate.
- **Single user only.** No concurrent load was applied, so behaviour under several simultaneous users is unknown.
- **Network-bound database.** The remaining database cost is mostly network round trips to Supabase (~0.4 s each). The VPS and database regions were not verified in this work.
- **Provider dependence.** Groq quota limits caused the excluded requests in one run. Latency and availability also depend on Groq.
- **Telemetry loss on hard kill.** The background telemetry insert can be lost if the backend process is killed abruptly. A clean shutdown waits for it.

## 7. Recommendations

1. **Run a concurrency test next.** Send 3–5 simultaneous requests and measure throughput, tail latency and errors. This fills the proposal's throughput and scalability metrics.
2. **Co-locate the VPS and the Supabase project, or move the database closer.** This is the largest remaining latency lever for every agent, not only retrieval.
3. **Watch production verifier outcomes.** Track kept and blocked counts and block reasons, and add each new false-block pattern as a regression test, as was done for V5.
4. **Re-run the Qwen reranker** on the same 80-case harness if the report must cover every reranker named in the proposal.
