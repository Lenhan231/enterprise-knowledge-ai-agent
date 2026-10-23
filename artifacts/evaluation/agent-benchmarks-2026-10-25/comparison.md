# Qwen3.8-27B vs GPT-OSS-120B benchmark comparison

**Dataset:** `commerce-agent-benchmarks-v1`  
**Models:** `qwen/qwen3.8-27b` and `openai/gpt-oss-120b`  
**Judge:** Luna 5.6 Medium (Codex CLI), as recorded in both JSON files; first nine case scores were manually scored  
**Evaluation configuration:** 75 cases per model (25 knowledge, 25 SQL, 25 report); RAGAS metrics `faithfulness`, `answer_relevancy`, and `context_precision`; manual scores are retained for the first nine cases. Exact RAGAS package version and embedding model are not recorded in these JSON files.  
**Run date:** Not recorded in the JSON. Artifact directory date label: `2026-10-25` (inferred from its path).

## Schema consistency

The files use the same top-level keys, dataset label, 75 case IDs in the same order, and the same core per-case field names. The per-case key union differs only because Qwen has an optional `latency_note` field. Other omissions are concentrated in failed or partially scored cases. GPT-OSS also uses a `generated` status for some records, while Qwen uses `scored`/`score_partial`; these status values do not consistently describe runtime completion across files.

For this comparison, fields absent from a record are treated as null/empty; runtime outcome is normalized to **answered** or **run error** based on the answer/error fields. A numeric metric score remains scored even if a diagnostic is also present in `score_errors`.

| Canonical field | Normalized type | Source fields / rule |
|---|---|---|
| `case_id`, `agent`, `model`, `question` | string | Same names and types in both files |
| `answer` | string or null | Blank/missing answer becomes null; determines answered status |
| `contexts`, `evidence_sources` | list | Missing values become empty lists |
| `reference` | string or null | Stored as a JSON-encoded list string in both files; preserve source representation |
| `scores.<metric>` | finite number or null | Read per case; ignore missing, null, Boolean, or non-finite values |
| `score_errors.<metric>` | string diagnostic or absent | Normalize absent to empty; keep distinct from execution `error` |
| `error` | string diagnostic or null | Execution failure text; missing becomes null |
| `latency_seconds`, `total_case_seconds` | number or null | Missing/null values stay null; do not compare missing latency as zero |
| `sql_safety_pass`, `sql_semantic_correctness`, `abstention_expected`, `abstention_observed` | Boolean or null | Missing/non-Boolean values are not counted |
| `status` | `answered` / `run_error` | Derived consistently from answer presence and execution error; raw status retained only as a source diagnostic |

The stored GPT-OSS `summary.ragas_partial` counts are eight cases lower per metric than the numeric per-case counts, because the summary excludes the available manual scores in the first nine cases. The report therefore recomputes means and denominators from per-case records for both models rather than mixing stored summary conventions.

## Results

### Case outcomes

| Agent | Qwen answered / cases | Qwen run errors | GPT-OSS answered / cases | GPT-OSS run errors |
|---|---:|---:|---:|---:|
| Knowledge | 25/25 | 0 | 25/25 | 0 |
| SQL | 25/25 | 0 | 25/25 | 0 |
| Report | 16/25 | 9 | 22/25 | 3 |

### SQL checks

| Check | Qwen3.8-27B | GPT-OSS-120B | Denominator |
|---|---:|---:|---|
| SQL safety | 17/25 | 20/25 | SQL cases with Boolean result (25 each) |
| SQL result correctness | 22/25 | 22/25 | SQL cases with Boolean result (25 each) |
| Expected abstention matched | 17/25 | 20/25 | SQL cases with observed Boolean abstention (25 each) |

### RAGAS metrics

A metric denominator includes only answered records with the inputs required by that metric: answer for answer relevancy; answer plus retrieved contexts for faithfulness; answer, contexts, and reference for context precision. Means use only finite numeric per-case scores. First-nine manual scores are included in the per-case totals.

| Metric | Qwen mean (scored / eligible) | GPT-OSS mean (scored / eligible) | Eligible cases without numeric score (Qwen / GPT-OSS) |
|---|---:|---:|---:|
| `faithfulness` | 0.4762 (55/57) | 0.4217 (65/66) | 2 / 1 |
| `answer_relevancy` | 0.7721 (66/66) | 0.8073 (71/72) | 0 / 1 |
| `context_precision` | 0.462 (57/57) | 0.4981 (65/66) | 0 / 1 |

The stored GPT-OSS summary reports 57/63/57 scored cases for faithfulness/answer relevancy/context precision, while its per-case data contains 65/71/65 numeric scores. Those eight extra numeric scores per metric are in the first nine manually scored cases. Qwen's stored counts match its per-case numeric counts. This comparison uses the per-case counts and reports eligible-case denominators for both models.

### Mean latency (seconds)

| Agent | Qwen mean (records with latency) | GPT-OSS mean (records with latency) |
|---|---:|---:|
| Knowledge | n/a (0 records) | 33.89 (25 records) |
| SQL | 8.21 (5 records) | 7.64 (25 records) |
| Report | 69.35 (16 records) | 42.52 (25 records) |

Qwen has no per-case knowledge latency and only five SQL latencies, so its available latency values are incomplete and should not be read as directly comparable for those agents. GPT-OSS has latency values for all 25 records per agent.

## Error and missing-data representation

| Source diagnostic | Qwen3.8-27B | GPT-OSS-120B |
|---|---:|---:|
| Execution failures in knowledge | 0 | 0 |
| Execution failures in SQL | 0 | 0 |
| Execution failures in report | 9 | 3 |
| Eligible `faithfulness` cases with no numeric score | 2 | 1 |
| Eligible `answer_relevancy` cases with no numeric score | 0 | 1 |
| Eligible `context_precision` cases with no numeric score | 0 | 1 |

Execution failures are represented by a per-case `error` string and an error status; metric/judge diagnostics are strings in the metric-keyed `score_errors` object. GPT-OSS K07 has numeric manual scores alongside deferred-score diagnostics for all three metrics; the comparison counts its numeric scores and retains the diagnostics as history. A metric counts as scored only when its per-case value is numeric.

## Limits in the source data

- `hallucination_rate` is null throughout these files, so no hallucination-rate comparison is available.
- Reference and RAGAS configuration details beyond the metric names and judge label are not present in the JSON; do not infer an embedding model or exact RAGAS package version.
- The report uses only the two result JSON files; it does not incorporate other benchmark runs or external documentation.
