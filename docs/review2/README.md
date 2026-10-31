# Review 2 — Retrieval Evidence Guide

Use this guide when a reviewer asks **“Where did this number come from?”** All links point to existing repository evidence. This guide covers Huy's tokenization, embedding, and retrieval work; it does not certify the other members' experiments.

## Open these first

- [Latest Vietnamese presentation script](huy-speaking-notes-20261026.vi.md): slide 10–14 speaking notes, backup explanations, and current-main versus benchmark boundaries; saved from the private Notion preparation page.

- [Current chunking and Canva audit (Vietnamese)](chunking-and-slides-audit-20261025.vi.md): text/table splitting, token and memory limits, headers/footers, measured resources, and material slide corrections.

- [Vietnamese question-by-question checklist assessment](checklist-evidence-assessment.vi.md): what Huy can answer, what remains partial, and suggested checklist entries for the shared Review 2 document.

- [Final benchmark report](../../artifacts/evaluation/heldout-review2-v1/runs/review2-reviewed-r1-sql-20261022/REPORT.vi.md): results, language/category breakdowns, latency, failures, confidence intervals, and limitations.
- [Measured metrics CSV](../../artifacts/evaluation/heldout-review2-v1/runs/review2-reviewed-r1-sql-20261022/metrics.csv): exact values behind the results tables. Filter `group = all` for the main comparison; other rows contain language and question-category breakdowns.
- [Detailed Huy report](huy-retrieval-report.vi.md): explanations of tokenization, model selection, provenance, integration, and experimental boundaries.
- [English Canva content](huy-canva-content.en.md): slide copy and source footers. This is presentation material, not the primary measurement record. Slide numbers may differ from the current Canva deck.
- [Vietnamese speaking notes and Q&A](huy-speaking-notes.vi.md).
- [Shared Canva presentation](https://canva.link/jp3t3fxx0rtidj0).

## Main results: the numbers to defend

Dataset: **20 intents / 40 VI–EN question texts / 80 directional cases**, using **1,063 frozen chunks from 10 simulated documents**. Each case searches all five target-language documents with admin access. These are 20 intent clusters, not 80 independent questions.

| Slide method | CSV method key | Full evidence@10 | Recall@10 | MRR@10 | nDCG@10 | Mean warm latency |
|---|---|---:|---:|---:|---:|---:|
| Dense E5 | `dense` | 52/80 (65.00%) | 0.6563 | 0.5586 | 0.5594 | 546 ms |
| Dense E5 + BGE | `dense_bge` | 62/80 (77.50%) | 0.7875 | 0.8213 | 0.7731 | 1,691 ms |
| Translated hybrid | `translated_hybrid_raw` | 63/80 (78.75%) | 0.7917 | 0.6590 | 0.6694 | 2,437 ms |
| Translated hybrid + BGE | `translated_hybrid_bge` | **69/80 (86.25%)** | **0.8823** | **0.9000** | **0.8635** | 3,609 ms |

Source: [metrics.csv](../../artifacts/evaluation/heldout-review2-v1/runs/review2-reviewed-r1-sql-20261022/metrics.csv), `group = all`. Final-method P@10 is 0.13375; macro component coverage is 0.89375, with 208/244 components met. The component ratio and macro coverage use different aggregation rules.

**Full evidence@10 means all required evidence components are present in the top 10 chunks. It is not generated-answer accuracy.** The gain over dense is **17 cases / 21.25 percentage points**. Translated hybrid means original-query E5 dense + translated-query BM25, combined through RRF; the raw arm does not include BGE reranking.

## Question-to-evidence lookup

| If asked… | Open this evidence | What to show |
|---|---|---|
| Where are the individual questions and expected evidence? | [Readable question/evidence review](../../artifacts/evaluation/heldout-review2-v1/REVIEW.md), [questions.json](../../artifacts/evaluation/heldout-review2-v1/questions.json), [cases.json](../../artifacts/evaluation/heldout-review2-v1/cases.json), [evidence.json](../../artifacts/evaluation/heldout-review2-v1/evidence.json) | Question text, direction, required components, exact source spans, and accepted alternatives. |
| What documents were searched? | [Frozen corpus JSONL](../../artifacts/evaluation/heldout-review2-v1/inputs/corpus.jsonl), [VI parser output](../../artifacts/evaluation/heldout-review2-v1/inputs/parser_vi.jsonl), [EN parser output](../../artifacts/evaluation/heldout-review2-v1/inputs/parser_en.jsonl) | Corpus content and document IDs; the detailed report gives counts by format/language. |
| Which settings and hardware were used? | [Protocol](../../artifacts/evaluation/heldout-review2-v1/protocol.json), [actual run configuration](../../artifacts/evaluation/heldout-review2-v1/runs/review2-reviewed-r1-sql-20261022/config.json), [environment](../../artifacts/evaluation/heldout-review2-v1/environment.json) | Pinned E5/BGE revisions, RTX 2060, FP32, batch 4, pool 30, final 10, scope and timing boundaries. Use run configuration for actual execution; the preparation protocol contains historical status fields. |
| Where are predictions and rankings? | [results.json](../../artifacts/evaluation/heldout-review2-v1/runs/review2-reviewed-r1-sql-20261022/results.json), [gold-chunk map](../../artifacts/evaluation/heldout-review2-v1/runs/review2-reviewed-r1-sql-20261022/gold-chunk-map.json) | Saved per-case retrieval output and annotated chunk mapping. |
| How are the metrics calculated? | [Retrieval metric implementation](../../artifacts/evaluation/heldout-review2-v1/code/core/evaluation/retrieval_metrics.py), [evidence scoring implementation](../../artifacts/evaluation/heldout-review2-v1/code/core/evaluation/evidence_metrics.py), [detailed report, §4](huy-retrieval-report.vi.md#4-thiết-kế-đánh-giá) | Chunk relevance versus complete evidence; source alternatives and partial spans. Mean label-based P@10 ceiling is 15.5%, so low P@10 is not an answer-error rate. |
| Where are the actual translations? | [Saved translations](../../artifacts/evaluation/heldout-review2-v1/prepared/translations.json), [prepared-input manifest](../../artifacts/evaluation/heldout-review2-v1/prepared/manifest.json) | Frozen automatic query translations and preparation records; no reference answers/evidence were supplied to translation. |
| What supports the token totals and model sizes? | [Token/model/resource statistics](retrieval-report-stats.json), [detailed report](huy-retrieval-report.vi.md) | 449,203 E5 input tokens including prefixes/special tokens; longest 476/512; zero overlength inputs. E5/BGE cached weight files: 1,060.68 / 2,165.86 MiB. |
| What failed, and why? | [Candidate diagnostics](../../artifacts/evaluation/heldout-review2-v1/runs/review2-reviewed-r1-sql-20261022/candidate-diagnostics.json), [analysis](../../artifacts/evaluation/heldout-review2-v1/runs/review2-reviewed-r1-sql-20261022/analysis.json), [final report](../../artifacts/evaluation/heldout-review2-v1/runs/review2-reviewed-r1-sql-20261022/REPORT.vi.md) | All 11 final failures lack required evidence in the top-30 pool: H04 VI→EN (1), H08 target VI (2), H11 (4), H14 (4). H04 correct chunk moves from dense rank 19 to fused rank 33. |
| Does the reranker help? | [Metrics CSV](../../artifacts/evaluation/heldout-review2-v1/runs/review2-reviewed-r1-sql-20261022/metrics.csv), [analysis](../../artifacts/evaluation/heldout-review2-v1/runs/review2-reviewed-r1-sql-20261022/analysis.json) | Dense 52→62 complete cases with BGE; translated hybrid 63→69, with six rescued cases and no full-evidence regressions against the raw hybrid arm. |
| How certain is the improvement? | [Analysis: `paired_intent_bootstrap`](../../artifacts/evaluation/heldout-review2-v1/runs/review2-reviewed-r1-sql-20261022/analysis.json), [final report](../../artifacts/evaluation/heldout-review2-v1/runs/review2-reviewed-r1-sql-20261022/REPORT.vi.md) | 10,000 bootstrap samples clustered by 20 intents: gain vs dense +21.25 pp, 95% CI [10,35]; vs dense+BGE +8.75 pp, CI [0,20]. This is not three repeated inference runs. |
| Can the recorded results be checked again? | [Verification record](../../artifacts/evaluation/heldout-review2-v1/runs/review2-reviewed-r1-sql-20261022/verification.json), [frozen manifest](../../artifacts/evaluation/heldout-review2-v1/manifest.json), [runner instructions](../../artifacts/evaluation/heldout-review2-v1/README.md) | Saved-output replay, hashes, pinned code/inputs, and the verification command below. |

## Latency and resource boundaries

Final warm retrieval mean / median / p95: **3,609 / 3,578 / 4,605 ms**. See the CSV's `mean_latency_ms`, `median_latency_ms`, and `p95_latency_ms` columns.

- Timing excludes model startup, live translation API, and generation. Translation preparation averaged approximately **0.560 s/query** separately; do not add stage averages and call the sum measured end-to-end latency.
- Query encoding was timed once per question text and shared between its two target-corpus cases. Raw hybrid timing is the pre-rerank stage of the hybrid pipeline.
- Recorded PyTorch peak allocated memory was **2.212 GiB with sequential model loading**. It is not total GPU memory or production memory with both models resident.
- One pass per case/method; no repeated-run mean ± standard deviation, concurrency, or cold-start measurements.
- Members used separate evaluation setups. Retrieval and generation share document material but use different question sets. Their results do not establish end-to-end quality, and cross-machine latency is not a controlled comparison.

## Historical experiments: supporting evidence only

| Experiment | Source | Correct interpretation |
|---|---|---|
| Earlier embedding comparison | [Comparison report](../../artifacts/evaluation/embedding-comparison-20261018/comparison.md) | E5 93.33% versus MiniLM 80.00% expected-source-file recall@10 on 20 VI questions. This is a different metric/dataset from the main 80-case evidence benchmark. |
| Four-direction financial-document pilot | [Comparison report](../../artifacts/evaluation/four-direction-20261018/comparison.md) | Page-based evidence coverage on different financial reports; not directly comparable to chunk/component evidence scores. |
| Earlier 48-case development set | [Development evidence](../../artifacts/evaluation/fresh-reviewed-v1/), [development metrics report](../../artifacts/evaluation/retrieval-metrics-20261022/REPORT.vi.md) | The older 100% complete-evidence result is development evidence, not the headline Review 2 result. |
| Production integration | [E5 rollout](../e5-production-rollout.md), [optional translated hybrid + BGE](../translated-hybrid-rerank.md) | Implementation/rollout evidence, not proof that every production request reproduces the controlled benchmark. |
| New PDF inputs | [Dataset navigation](../../artifacts/datasets/README.md) | Bảo An and translated VietStyle are separate policies and future experiment inputs. No new retrieval/generation result is supplied for them here. |

## Limitations to state during Q&A

- Known simulated corpus; 20 intent clusters. Labels were assistant-authored/source-checked, with user-approved revisions, not independently certified double annotations. See the [overlap audit](../../artifacts/evaluation/heldout-review2-v1/overlap-audit.json) and [review status](../../artifacts/evaluation/heldout-review2-v1/review-status.json).
- Six intents have identical VI/EN table evidence chunks. The complete 80-case set is not a pure cross-language generalization test.
- No original-query-only hybrid arm in this run: translation effects are not isolated from BM25/fusion effects.
- Frozen corpus metadata still contains old Qwen preparation labels. Actual vectors are verified E5 768-dimensional vectors; see [statistics and vector hash](retrieval-report-stats.json). Do not rewrite frozen inputs to hide this discrepancy.
- Use the default **SQL backend** to reproduce the recorded result. The optional offline adapter has BM25 tie-order differences; see [offline diagnostics](../../artifacts/evaluation/heldout-review2-v1/runs/review2-reviewed-r1-sql-20261022/offline-adapter-diagnostics.json).
- Huy's recorded checkpoint defaults to ordinary `hybrid`; the separately inspected main commit `1ffe05bbd5bcf477d2fe583d086db4f47b1f9497` defaults to `translated_hybrid_rerank`, with RAG top5 and a 24,000-character context cap. The benchmark uses top10; do not describe branch-specific settings as universal production behavior. HTTP/UI does not supply the verified document-language mapping used in this controlled experiment.
- This benchmark does not measure generated answers, citation faithfulness, refusal, RBAC, or OCR quality. Evidence in retrieval top 10 can still be lost during context packing.
- Two measured retrieval controls do not complete the separate Paper-vs-Group requirement. Deployment/CI and other members' metrics need their own evidence.

## Verify saved artifacts without new inference

Run from the repository root with the documented Python dependencies available:

```bash
.venv/bin/python artifacts/evaluation/heldout-review2-v1/run.py verify-run artifacts/evaluation/heldout-review2-v1/runs/review2-reviewed-r1-sql-20261022
```

This checks saved outputs; it is not a fresh latency/model benchmark. The standard command makes no new inference/API calls but rewrites the run's `verification.json`. For fresh inference requirements and commands, use the [benchmark README](../../artifacts/evaluation/heldout-review2-v1/README.md). Preserve frozen files and use a new run name.

See the [original Review 2 checklist](review2-task2-checklist.docx) and [group presentation plan](presentation-plan.md) for requirements and ownership. This guide creates no new experimental evidence.
