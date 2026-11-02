# Inventory agent benchmark — 2026-11-02

The attached 90-case JSONL is archived unchanged in `source-dataset.jsonl`; its SHA-256 is in `manifest.json`. Each agent has its own directory and question file. **Knowledge's 30 cases are deferred.** SQL and Report each run all 30 original questions, without rewriting prompts or supplying a template.

The application baseline was committed and pushed to `QuocAn` before evaluation (`f8996f6`). Generation uses the configured Groq model at temperature 0. The existing provider automatically switches to numbered `.env` keys on rate/quota errors, preserving the model. No keys are written to artifacts. Judge: the existing `CodexCLIJudge`, `gpt-5.6-luna`, reasoning `medium`, with the same evaluator preamble.

## Files and reproduction

Each evaluated agent directory contains `questions.jsonl`, independent `references.json`, append-only `generations.jsonl`, append-only per-metric `scores.jsonl`, and `summary.json`. Report downloads are also saved as `Rxx.md`. Generation records retain actual evidence, result metadata, status, latency and failures. Scores retain judge reasons/traces and evaluator errors. Knowledge contains questions only.

```powershell
uv run python -m evaluation.run_inventory_agents_benchmark --stage references
uv run python -m evaluation.run_inventory_agents_benchmark --stage generate
uv run python -m evaluation.run_inventory_agents_benchmark --stage score
uv run python -m evaluation.run_inventory_agents_benchmark --stage summary
uv run python -m unittest discover -s tests -p test_inventory_benchmark.py
```

Stages resume missing work. They never regenerate successful responses or overwrite frozen references. One explicit infrastructure retry is allowed for previously recorded rate-limit failures; all original attempts are retained. Validation and answer failures are not retried. Agent execution is serial, with bounded waits/retries for Groq cooldowns (which consume the normal report deadline); judging runs at most two cases concurrently. Report's normal internal two-operation concurrency and 180-second deadline remain in effect. Decisions requiring user confirmation are recorded as the first response; the evaluator does not implicitly authorize restricted scope.

## Metrics

All reported scores are 0–1. Definitions and denominators matter more than a blended average; no cross-agent aggregate is computed.

| Agent | Metric | Method |
|---|---|---|
| SQL | Execution Accuracy | Custom Ragas metric: result multiset equality against independent read-only reference SQL, numeric tolerance 1e-6 absolute/relative. Judge aligns column aliases only; values are compared in code. Extra descriptive response columns are ignored; reference columns must match. |
| SQL | SQL Semantic Equivalence | Ragas `SQLSemanticEquivalence` with the shared schema; generated parameters are bound before comparison. |
| SQL | Numerical Accuracy | Reference numeric-cell accuracy at matching dimensions/entities; excludes dates and IDs, penalizes missing/extra rows. Uses the same alias alignment and decimal tolerance. |
| Report | Faithfulness | Ragas `Faithfulness` against actual retrieved evidence and runtime validated facts, never the independent oracle or report text itself. |
| Report | Factual Correctness | Ragas `FactualCorrectness`, F1 mode, against the independently frozen case reference. |
| Report | Numerical Accuracy | Custom Ragas metric enumerates quantitative claims with judge alignment of metric/entity/date/unit, then compares normalized decimal values in code. Stores every evaluated claim and reason. No quantitative claims yields N/A. |
| Report | Report Completeness | Ragas `RubricsScoreWithReference`, query-specific requirements plus applicable report components; five-point rubric normalized as `(score-1)/4`. Correct unsupported-request explanations can be complete without a fabricated report. |

SQL execution failures for supported requests score zero, not N/A. Unsupported S29/S30 have no valid SQL or numeric gold, so those metrics are N/A and their actual refusal responses remain inspectable. Report faithfulness is N/A when no evidence was retrieved. Evaluator errors are null with an error reason, never zero or a fabricated score. Summaries show scored/N/A/error/pending counts separately; means cover scored cases only. Inspect these counts before comparing agents.

## Reference scope and limitations

The supplied dataset has behavioral rubrics but **no gold SQL or factual/numeric answers**. References are separately authored fixed SQL queries, executed in a single read-only repeatable-read transaction before generation. They are not generated from agent outputs. Their hashes are frozen. These are author-reviewed evaluator references, not independently certified gold.

The bounded detail interpretation is 200 rows with explicit oracle ordering; top-N ties use product ID. Consequently an equally defensible alternative detail ordering/default limit can lose execution accuracy: inspect semantic-equivalence and SQL before interpreting a zero. Aggregates always cover the full requested scope before detail limits. S28 means duplicate rows in excess of the first row per key. S23's independently aggregated calendar-year unit ratio is distinct from canonical order-based return rate.

Historical evidence cannot establish current 2026 quantities, supplier receipt compliance or whether returns were restocked. Catalog COGS supports only explicitly labelled cost proxies, not approved accounting valuation. Source ratios, missing observations, overlapping flags, currency uncertainty and approval restrictions remain explicit in references.

The dataset names a policy identifier/page but does not include policy passages. No invented policy text is used as gold; report factual correctness therefore has incomplete policy-reference coverage. Reference detail samples are capped at 200 and are not exhaustive truth for every possible report claim. Numerical claim enumeration and semantic scope alignment are model judgments, not formal proof. Large responses may exceed the judge's timeout; these remain visible evaluator errors. No manual scores are substituted for failed Ragas calls.
