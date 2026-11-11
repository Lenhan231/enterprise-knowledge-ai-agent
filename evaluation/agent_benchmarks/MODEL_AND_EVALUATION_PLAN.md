# Agent benchmark and model-evaluation plan

**Prepared:** 2026-10-21  
**Target deadline:** Monday 2026-10-26  
**Branch baseline:** `QuocAn` at `dd8ab9bef297ec9e7d7977502b2f2dbd809e8041`

## Current-state findings

- The `QuocAn` branch already implements LangGraph orchestration in `src/core/agents/router.py`.
- Text-to-SQL is already model-assisted, not a separately trained in-house model. `GroqProvider` defaults to `qwen/qwen3.8-27b`; `SQLAnalyticsAgent` asks for a JSON query plan, retries once after a validation error, and routes queries through `CommerceRepository`.
- SQL safety currently includes a finite approved-column schema, approved join keys/functions, one SELECT statement, explicit aliases, exact parameter binding, a result cap of 200 rows, a read-only transaction, a 5-second statement timeout, server-verified `analytics:read` authorization, and a dedicated `ANALYTICS_DATABASE_URL`.
- The database's `commerce` tables cover through **2022-12-31**. The current snapshot is not 2026 inventory. Policy docs also explicitly say currency, inbound POs, supplier lead times, backorders and warehouse locations are not fully provided.
- `report` routing exists as an optional graph node, but `src/core/agents/report_agent.py` was not found in `QuocAn`; the dashboard path in `src/app/main.py` currently uses an unsupported-route fallback. Treat report/template ingestion and dashboard outline rendering as implementation work, not completed features.
- `pyproject.toml` already includes both `langgraph` and `ragas`. The repo has `evaluation/run_ragas_24q.py` and `evaluation/run_generation_benchmark.py`, so this sprint does not need a new evaluation framework.

## 2024 Text-to-SQL literature and candidate

### Main candidate: CodeS-7B

Haoyang Li et al., **“CodeS: Towards Building Open-source Language Models for Text-to-SQL”**, arXiv:2402.16347 (published 2024-02-26): https://arxiv.org/abs/2402.16347

- CodeS is a family of SQL-specialized open checkpoints at 1B, 3B, 7B and 15B scale.
- The authors use incremental SQL-centric pretraining, schema-linking prompts and bi-directional data augmentation, and report strong results across Spider, BIRD and robustness benchmarks.
- Checkpoint: https://huggingface.co/seeklhy/codes-7b (Apache-2.0 license).
- Constraint: Hugging Face currently shows no hosted Inference Provider for this checkpoint; it must be run locally/on a GPU endpoint (e.g. Transformers/vLLM). Do not assume it is available through Groq.
- This is a candidate, not a winner. The repository's current Qwen-on-Groq path is the incumbent.

### Secondary paper: DTS-SQL (not the quick drop-in option)

Mohammadreza Pourreza and Davood Rafiei, **“DTS-SQL: Decomposed Text-to-SQL with Small Large Language Models”**, Findings of EMNLP 2024: https://aclanthology.org/2024.findings-emnlp.481/

The paper proposes two-stage fine-tuning and reports a 3–7 percentage-point execution-accuracy gain, reaching 60.31% on BIRD hold-out for a 7B model. This is a training method, not simply a hosted replacement checkpoint. With the Monday deadline, do not attempt to reproduce the fine-tuning pipeline.

### Fair model comparison

Run the same 25 `Sxx` questions through the current Groq model and CodeS-7B (only if inference can be stood up without derailing the delivery). Keep prompt, schema description, temperature, SQL safety validator, database, result limit and retries constant. Do **not** bypass validation for either model.

Primary selection metric: **executed semantic correctness** (gold result equality or a manually verified equivalent result, not string-exact SQL matching). Secondary metrics:
1. SQL validation pass rate / safe-query rate.
2. Execution accuracy on supported questions.
3. Correct abstention on unsupported/out-of-coverage questions.
4. Faithfulness and answer relevancy of the natural-language explanation.
5. Median/p95 latency and token/cost usage.

If CodeS cannot be run reproducibly by the deadline, keep the current Groq/Qwen model as the system default and record CodeS as a planned comparative experiment. Do not claim a paper's Spider/BIRD score predicts performance on our `commerce` schema.

## LangGraph versus Ragas

They are **not alternatives**:
- **LangGraph** orchestrates the application flow: classify, route, invoke SQL/knowledge/report agents, and combine outputs. It is already used in the router.
- **Ragas** evaluates generated answers using metrics such as faithfulness, answer relevancy and context precision. It is already declared in project dependencies and used by `evaluation/run_ragas_24q.py`.

Recommendation: keep LangGraph for orchestration. Reuse the existing generation evaluation workflow; do not rebuild it. If judge-model access is unreliable before Monday, use the repo's human-review workflow instead of blocking the demo on Ragas runs.

## Required proposal-aligned generation metrics

Score **every returned answer/report** using the proposal metrics:
- **Faithfulness**: factual claims are supported by retrieved passages or validated SQL rows.
- **Answer relevancy**: the response addresses the question and requested reporting period.
- **Context precision**: evidence shown/used is relevant to the answer, not irrelevant retrieved context or unrelated rows.
- **Hallucination rate**: number of unsupported/contradicted factual claims divided by total factual claims; audit at claim level. Do not silently substitute `1 - faithfulness` for hallucination rate.

The current benchmark README/script uses 1–5 human review scores for faithfulness, answer relevancy and context precision, plus factual-claim and hallucinated-claim counts. Use that existing rubric so results remain comparable.

For SQL only, also collect task-specific correctness/safety metrics: query validation rate, execution accuracy, unsupported-query abstention accuracy, and latency. These complement, not replace, the proposal metrics.

## Dashboard: static outlines first

Use `dashboard_static_outlines.json` as the approved layout contract:
1. Executive Overview
2. Sales Performance
3. Inventory Control & Exceptions
4. Digital Traffic
5. Returns & Fulfillment

The dashboard agent should choose an outline, fill predefined KPI/chart/table slots using validated analytics results, and return data plus short evidence-backed insights. Do not generate arbitrary HTML or new layout structures in this sprint. Display source period/limitations; especially note the dataset cutoff and missing currency unit.

## Report agent: user template controls the structure

Expected minimum flow:
1. Require a user-uploaded template (DOCX first; Markdown fallback for demo).
2. Extract heading order, tables/columns, placeholders and formatting metadata.
3. Build a report plan that maps each section to supported knowledge evidence and/or validated SQL outputs.
4. Populate the template without reordering headings; use explicit “unavailable in source data” placeholders where appropriate.
5. Add report period, citations/source list, assumptions and limitations.
6. Validate that all output numbers are grounded and no database write was requested.

Keep templates as the formatting source of truth; an uploaded template is not itself evidence for business facts.

## Graph-based RAG decision

**Do not implement GraphRAG before Monday.** The current knowledge corpus available to this benchmark is a small set of inventory policy/SOP/registry/training documents and the project already has hybrid retrieval plus citations. Graph indexing adds entity/relationship extraction, persistence, evaluation and ongoing synchronization. Microsoft's GraphRAG repository explicitly warns that indexing can be expensive: https://github.com/microsoft/graphrag.

Revisit only after benchmark results show a real gap on multi-hop questions that conventional hybrid retrieval cannot answer. If needed, test on 10–20 cross-document relationship questions as a separate experiment and compare answer metrics/latency/cost against the current retriever.

## Suggested plan to Monday 2026-10-26

- **Wed 21 Oct:** Freeze dataset/schema; commit the three benchmark sets, template fixtures and dashboard outline contract.
- **Thu 22 Oct:** Implement/repair the report template ingestion path and replace dashboard unsupported fallback with one static outline end-to-end.
- **Fri 23 Oct:** Run the 25 SQL cases through current Groq model; add a CodeS run only if inference environment is already available.
- **Sat 24 Oct:** Run knowledge and report cases; score proposal metrics with Ragas or human review; fix only top reproducible failures.
- **Sun 25 Oct:** Run all 75 cases from a clean session; produce scorecard and capture limitations.
- **Mon 26 Oct:** Demo/readout. Do not add GraphRAG or attempt fine-tuning this late.

## Dataset and interpretation notes

- `knowledge_agent_benchmark.json` is grounded in the indexed policy/SOP/registry/deck sources inspected in Supabase. The documents label thresholds as simulated drafts; answers must carry that caveat.
- `sql_analytics_agent_benchmark.json` includes 23 supported reference queries and 2 deliberate abstention cases. Gold SQL is a semantic reference, not a string-exact target. Supported queries use the existing schema and approved relationships.
- `report_agent_benchmark.json` evaluates template adherence, factual grounding, source notes, limitations and evidence-backed synthesis.
- `dashboard_static_outlines.json` is a fixed contract, not a generated UI implementation.

Some factual records and benchmark answers must be refreshed if the dataset is reloaded or its approved date coverage changes.
