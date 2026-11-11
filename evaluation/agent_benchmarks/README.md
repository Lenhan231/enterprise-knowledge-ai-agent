# Agent benchmarks

This directory contains 75 labeled prompts: 25 each for the Knowledge, SQL Analytics and Report agents.

## Files

- `knowledge_agent_benchmark.json`: question labels, expected facts, evidence source names and abstention/RBAC tests.
- `sql_analytics_agent_benchmark.json`: 25 SQL questions, 23 gold query formulations and 2 expected-abstention cases.
- `report_agent_benchmark.json`: 25 report requests, required sections, source requirements and prohibited behaviors.
- `report_template_fixtures.json`: logical templates to test preservation of heading order, KPI tables and limitations.
- `dashboard_static_outlines.json`: fixed dashboard component contracts; the agent fills data into these outlines rather than inventing layouts.
- `MODEL_AND_EVALUATION_PLAN.md`: research findings, model comparison protocol, metrics, GraphRAG recommendation and sprint plan.

## Scoring

Use the proposal metrics on every generated answer: `faithfulness`, `answer_relevancy`, `context_precision`, and claim-level `hallucination_rate`. Use the existing Ragas/human-review evaluation code. SQL-specific supplementary metrics are SQL safety/validation pass rate, execution accuracy, abstention accuracy and latency.

A gold SQL query is a semantic reference. Compare returned values/meaning, not exact SQL strings. Execute all benchmark SQL in the existing read-only, allowlisted repository path; never run arbitrary model SQL directly.

## Grounding caveats

- Commerce data coverage ends on 2022-12-31; don't claim current 2026 inventory or 2025 revenue.
- The inventory documents are simulated Datathon drafts; policy targets require business-owner approval.
- Currency is not confirmed by the dataset.
- The database does not fully supply open PO, supplier lead-time, backorder or warehouse-location facts.
