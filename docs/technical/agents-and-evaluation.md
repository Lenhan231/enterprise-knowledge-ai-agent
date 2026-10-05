# Commerce agents and evaluation

## Two question paths

- **Policy/document Q&A:** `AgentRouter` sends document-only questions to `KnowledgeAgent`. Commerce retrieval first filters active sources by role and resolved domain, then applies the same source-scope ranking used for report evidence before generating an answer from those exact ranked passages. Explicit policy questions additionally filter to `company_policy_reference`, so an inventory-policy question does not retrieve promotion or logistics policies. External operating examples remain attributed to their publisher and scope; unmentioned platform rules are excluded.
- **Unseen Commerce questions:** after dashboard, explicit policy, and decision-support routing, `AgentRouter` uses the shared intent classifier to distinguish document-only questions from SQL/report requests. Method-only questions retain a narrow wording fallback when the classifier is unavailable; the detected domain is passed into KnowledgeAgent retrieval and reflected as auto-detected in the answer UI. Explicit Decision Support form submissions always stay on ReportAgent.
- **Decision support:** Questions asking what changed, what ranks highest, or what action to take go to `ReportAgent`. It obtains a bounded, read-only SQL result from the selected Commerce domain and retrieves relevant operating references. The answer separates observations, policy/method, decision limits, and missing data. Policy PDFs are shared with Q&A; no duplicate corpus is maintained.
- **Dashboard:** `/api/commerce/dashboard` returns curated aggregates from the private `commerce` schema. It does not depend on hard-coded KPI values or the document metric-review tables.
- Explicit chart requests for a recognized Commerce domain route to `DashboardAgent` before decision-report synthesis. It uses the same curated SQL aggregates as the dashboard page, returns the chart series with a `[C#]` observation citation, and honors any year range named in the question. Inventory fill rate is graphed separately from stockout/overstock counts because the units differ.

Question-specific SQL is generated within a domain table/column allowlist, parsed and checked with SQLGlot, executed read-only with a timeout and row limit, and returned with the query and dataset-provenance citation. It cannot query arbitrary schemas or mutate data. Commerce source data and the three policy PDFs are synthetic demo material; external cookbooks/practices are references, not Commerce Demo policy. The agent must not invent thresholds or infer missing warehouse, campaign-cost, carrier, route, forecast or SLA facts.

## Evaluation

The nine SQL-plus-RAG decision cases are in `data/evaluation/commerce_decision_benchmark.json`; they record gold observations, expected behavior, missing data and whether an operating reference is required. The twelve retrieval cases, including three method-only cases, are in `data/evaluation/commerce_retrieval_cases.json`.

With the local app configuration and an Admin demo login in `.env`, replay all nine through the authenticated API:

```bash
PYTHONPATH=src uv run python scripts/agents/evaluate_commerce_decision_support.py
```

Run one case while debugging with `--case-id INV-01`, or choose an output file with `--output`. The evaluator checks HTTP success, citation integrity, domain SQL provenance, synthetic-dataset disclosure, document source locations, required operating-reference presence, numeric fact coverage, and whether cited structured SQL rows contain the expected dimension/value groups. The row check recognizes SQL aliases and verifies grouping; it does not prove that the final answer associates those rows correctly or that its qualitative reasoning or recommendation is sound. Review each answer against its case's `gold_observations` and `expected_behavior` before reporting semantic scores. Provider rate limits stop the replay and leave the remaining case IDs in the output artifact.

Run the relevant regression suites with:

```bash
PYTHONPATH=src uv run python -m unittest tests.test_agents tests.test_rag tests.test_app_request_models -q
PYTHONPATH=src uv run python -m unittest tests.test_commerce_decision_evaluation tests.test_commerce_knowledge_manifest -q
```

OCR/upload quality is evaluated separately in `data/evaluation/ocr/README.md`; synthetic scan fixtures are not business evidence and stay isolated from the RAG corpus. Model/retrieval evaluation commands and limitations are listed in `scripts/README.md`.
