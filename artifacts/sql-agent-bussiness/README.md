# SQL Agent Business Benchmark

This folder contains the frozen five-case SQL Agent pilot, deterministic scoring and run tooling, and the design-only 40-case expansion. The original historical evidence remains in [`../sql-agent-business-pilot5-2026-11-20/`](../sql-agent-business-pilot5-2026-11-20/) and must not be edited.

## Contents

- [`cases.json`](cases.json): five frozen questions, gold SQL, bound parameters, reference rows and semantic contracts.
- [`runs/pilot5-main-8e4abbd1-20261121/`](runs/pilot5-main-8e4abbd1-20261121/): preserved clean-commit baseline. Its original report remains unchanged; the protocol 1.1.2 / scorer 2.0.2 rescore recognizes the verified `DATE` year predicate but still fails P02 because `delivered` is absent (3/4 supported E2E).
- [`runs/pilot5-decider-flash-b0bec419-20261121T014720Z/experiment/`](runs/pilot5-decider-flash-b0bec419-20261121T014720Z/experiment/): five-case trial using the free Perplexity Decisions model for SQL schema selection, on the same frozen snapshot and references. Protocol 1.2.0 / scorer 2.1.0 reports 4/4 supported E2E, selector raw Recall@5 4/4, and 1/1 safe unsupported abstention. Selector succeeded in all three cases that needed it. P03 used the configured local Codex SQL fallback, so this remains end-to-end Agent evidence, not a single-SQL-LLM comparison. The 40-case cohort was not run.
- [`runs/pilot5-sqlfix-groq-b86b4d9-20261121T0047Z/experiment/`](runs/pilot5-sqlfix-groq-b86b4d9-20261121T0047Z/experiment/): fresh five-case run on the same fingerprint and reference, with the uncommitted fixes hashed. Scorer 2.0.2 reports 4/4 supported E2E, 4/4 SQL semantics, 4/4 business results, 2/4 strict exact, and 1/1 valid unsupported abstention. P02 generated and executed the delivered filter; P05 abstained before SQL generation/execution. JEV returned HTTP 402 three times, so recall@5 is not measurable. One P03 SQL generation used local Codex fallback; its model identity was not captured, so this is end-to-end SQL Agent evidence, not a single-model comparison. The initial scorer 2.0.0 output is retained under `initial-score-scorer-2.0.0/`; the corrected versioned rescore is linked from the experiment directory.
- [`runs/pilot5-origin-main-e6f3b909/`](runs/pilot5-origin-main-e6f3b909/): earlier dirty-worktree run, preserved separately; it scored 4/4 business end-to-end and 2/4 strict exact. Its source revision and provider fallback differ, so do not attribute the score difference to one code change.
- [`scorer.py`](scorer.py), [`runner.py`](runner.py), [`preflight.py`](preflight.py), [`reference_runner.py`](reference_runner.py): offline score, atomic execution, fail-closed read-only preflight and gold-reference generation.
- [`PROTOCOL.md`](PROTOCOL.md), [`failure_classes.json`](failure_classes.json): metric definitions, reproduction steps and failure taxonomy.
- [`benchmark_40_plan.json`](benchmark_40_plan.json): 30 execute and 10 abstain candidates. It remains design-only and unexecuted. It is not ready for gold preparation yet: B40-007 duplicates P02, B40-031 duplicates P01, B40-021 duplicates P04, and B40-036/B40-037 overlap P05's unsupported dimensions. Reviewers must resolve and version these overlaps, then adjudicate ambiguity and approve gold SQL/rows before any 40-case execution.
- [`THESIS_ALIGNMENT.md`](THESIS_ALIGNMENT.md): thesis-ready methods, historical observations, limitations and next evaluation steps.

This SQL-specific package stays separate from `evaluation/run_agent_benchmarks.py`, which runs a 75-prompt, three-agent RAGAS evaluation, and from `evaluation/agent_benchmarks/sql_analytics_agent_benchmark.json`, a distinct 25-question cohort whose recorded data ends in 2022. Those cohorts use different questions, snapshots and scoring contracts; do not pool their scores with this five-case pilot. This package adds frozen SQL semantics and result oracles, source/reference hashes, and a fail-closed preflight for either a dedicated non-production database or an explicitly acknowledged frozen analytics snapshot.

## Verify offline

```bash
PYTHONPATH=src uv run python -m unittest discover -s artifacts/sql-agent-bussiness/tests -v
PYTHONPATH=src uv run python artifacts/sql-agent-bussiness/scorer.py \
  --cases artifacts/sql-agent-bussiness/cases.json \
  --data artifacts/sql-agent-bussiness/data.json \
  --output /tmp/sql-agent-business-scores.json
```

The Decider Flash trial reconfirmed the frozen snapshot fingerprint `dbc14b99acc2920ffaeb4190ba45708982c971f0671b0b9e8114b595f2594028` and read-only role, with three successful schema selections. A later synthetic probe of the current Jev key returned `limit_source=openrouter_credits`; the earlier pilot's response body was not retained, so that run's exact provider diagnostic remains unknown. See [`PROTOCOL.md`](PROTOCOL.md) for model attribution, freeze acknowledgement and fallback interpretation.
