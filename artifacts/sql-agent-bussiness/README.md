# SQL Agent Business Benchmark

This folder contains the frozen five-case SQL Agent pilot, deterministic scoring and run tooling, and the design-only 40-case expansion. The original historical evidence remains in [`../sql-agent-business-pilot5-2026-11-20/`](../sql-agent-business-pilot5-2026-11-20/) and must not be edited.

## Contents

- [`cases.json`](cases.json): five frozen questions, gold SQL, bound parameters, reference rows and semantic contracts.
- [`data.json`](data.json), [`scores.json`](scores.json) and [`report.md`](report.md): fresh five-case rerun evidence and deterministic scores; currently `NOT RUN` because no confirmed non-production database is configured.
- [`scorer.py`](scorer.py), [`runner.py`](runner.py), [`preflight.py`](preflight.py), [`reference_runner.py`](reference_runner.py): offline score, atomic execution, fail-closed read-only preflight and gold-reference generation.
- [`PROTOCOL.md`](PROTOCOL.md), [`failure_classes.json`](failure_classes.json): metric definitions, reproduction steps and failure taxonomy.
- [`benchmark_40_plan.json`](benchmark_40_plan.json): 30 answerable and 10 clarify/abstain candidates. It has not been run, and its gold rows are not prepared.
- [`THESIS_ALIGNMENT.md`](THESIS_ALIGNMENT.md): thesis-ready methods, historical observations, limitations and next evaluation steps.

This SQL-specific package stays separate from `evaluation/run_agent_benchmarks.py`, which runs a 75-prompt, three-agent RAGAS evaluation, and from `evaluation/agent_benchmarks/sql_analytics_agent_benchmark.json`, a distinct 25-question cohort whose recorded data ends in 2022. Those cohorts use different questions, snapshots and scoring contracts; do not pool their scores with this five-case pilot. This package adds frozen SQL semantics and result oracles, source/reference hashes, and a dedicated non-production database preflight.

## Verify offline

```bash
PYTHONPATH=src uv run python -m unittest discover -s artifacts/sql-agent-bussiness/tests -v
PYTHONPATH=src uv run python artifacts/sql-agent-bussiness/scorer.py \
  --cases artifacts/sql-agent-bussiness/cases.json \
  --data artifacts/sql-agent-bussiness/data.json \
  --output /tmp/sql-agent-business-scores.json
```

Live reference generation and SQL Agent runs require a dedicated endpoint explicitly classified as non-production, an allowlisted database host, the repository's least-privilege analytics role, and authorized provider configuration. See [`PROTOCOL.md`](PROTOCOL.md). Never point the benchmark at production.
