# PVFCCo / Long Hậu 2008 benchmark

`long_hau_2008_cases.json` contains the latest 24 questions and their gold chunk/page labels. Q01–Q12 target the PVFCCo annual report; Q13–Q22 target Long Hậu's audited separate financial statements; Q23–Q24 require both. The latter PDF is misleadingly named `HPT - To trinh thong qua danh sach Cong ty Kiem toan signed1.pdf` in the index, but its content is Long Hậu's statements. The benchmark checks document content, not filename.

Run retrieval and all three models from `src/core/llm/models.py`:

```powershell
.venv\Scripts\python.exe evaluation\run_generation_benchmark.py
```

`gpt_oss_20b` uses `GROQ_API_KEY`, `qwen3` uses `GROQ_API_KEY_2`, and `gemini_flash` uses `GEMINI_API_KEY`. The two Groq keys must differ; separate keys may still share an organization quota. The script defaults to the two verified Supabase document IDs; override with `--annual-report-id` and `--long-hau-fs-id` if the documents are reindexed. Use `--question-id Q01 Q02` for selected questions or `--inspect-only` for retrieval without generation.

Outputs are `artifacts/benchmark/long_hau_2008.json` and the adjacent `.md` file. They include complete gold and retrieved chunk contents, ranks, scores, pages, answers, citations, and per-question metrics. These files are Git-ignored because they contain document text. Retrieval uses the embedding model recorded on indexed chunks.

Recall@K, Precision@K, MRR and nDCG use the supplied exact chunk labels, not just document identity. A missed gold chunk counts as a retrieval miss even if another chunk from the same PDF appears. Other passages might also legitimately answer a question; the scores are relative to the supplied labels, so inspect the full contexts when interpreting them.

Faithfulness, answer relevancy, context precision and hallucination rate need human review. Add a review to each answer's `human_reviews` array:

```json
{"reviewer":"R1","faithfulness":4,"answer_relevancy":5,"context_precision":3,"factual_claim_count":4,"hallucinated_claim_count":1}
```

Use integer scores from 1 (poor) to 5 (fully meets). Count a hallucinated claim only when a factual claim is unsupported or contradicted by the evidence. Then aggregate without model calls:

```powershell
.venv\Scripts\python.exe evaluation\run_generation_benchmark.py --score-only artifacts\benchmark\long_hau_2008.json
```

The sequential run also reports response time, retrieval latency and observed requests/second. It is not a load test, so GPU utilization and scalability remain unavailable.
