# Count workflow: implementation and measured coverage

Date: 2026-11-16 (Asia/Saigon). Local changes only; active application model remains
Groq `openai/gpt-oss-20b`. Previous Qwen is `qwen/qwen3.8-27b`.

## Delivered

The existing model call can return a bounded `count_query`. Python validates it and
compiles one single-source SQL query. There is no new planning model or dependency.
Supported count targets: source rows, non-NULL field occurrences, distinct non-NULL
field values. Each counter owns its own predicates; shared predicates restrict the
entire population. Flags equal to true/false do not match NULL. Distinct inventory
SKU counters count product_id, including conditional SKU counters, rather than
counting non-NULL flag values. The contract records the exact target and kind.

All latest-snapshot counters share MAX(snapshot_date), unaffected by count/population
predicates; an explicitly supplied period restricts the MAX to that requested window.
Unique source date fields are resolved deterministically from schema; ambiguous date
fields require a concrete choice. Snapshot/range
filters preserve requested dates; an inclusive end date becomes an exclusive next-day
boundary. Inventory ranges/history preserve exact snapshot groups. Empty filtered
populations at a known snapshot count as zero; an absent latest snapshot is unavailable,
not a claim that inventory is zero. Single-source compilation prevents join fanout;
rows intentionally retain source duplicates and distinct targets remove duplicates.
Monthly buckets and approved joins use the existing guarded SQL path, not this compiler.

Invalid generated interpretations get one repair. Malformed/mismatched plans become
generation failures; unsupported calculations become limitations with alternatives.
Genuinely missing snapshot scope still asks a concrete business question. Failed
interpretations no longer expose “Stored product values require product-level output”
as a clarification question. API tests cover both persistence of three KPIs/one dataset
and absence of clarification drafts for failed generated interpretations.

## Reproducible coverage

| Measurement | Passed / denominator | Rate | Meaning |
|---|---:|---:|---|
| Fixture arithmetic vs independent Python oracle | 32/32 | 100% | Enumerated count cases, with NULLs, duplicates, overlap and empty populations |
| Read-only live DB vs independently written CASE-based SQL | 32/32 | 100% | Same enumerated capabilities against current inventory/orders data |
| Unsafe/invalid contracts rejected | 18/18 | 100% | Joins, unknown source/fields, injection-shaped names, malformed targets, NULL misuse, dates and bounds |
| GPT-OSS 20B end-to-end | 3/4 | 75% | One trial per fixed English request; one bounded repair allowed |
| Qwen 3.8 27B end-to-end | 4/4 | 100% | Same four requests and independent reference contracts |

The model trials cover: three SKU counts; rows vs non-NULL vs distinct; independent
true/false predicates; and counts from orders as a different source. Both models passed
the user's exact three-SKU-count dashboard with three KPI tiles, one SQL query and one
model call. GPT-OSS failed the separate rows/non-NULL/distinct request: it omitted outputs
initially and returned malformed JSON during repair. The failure was reported without
asking the user to clarify. Reported success requires the correct count objects,
conditions, reference values and tile count, not merely dashboard status=complete.

This is finite capability coverage, not universal SQL coverage, test line coverage,
production reliability, or a statistically significant model comparison. The fixture
suite includes duplicate/NULL observations that current live snapshots do not contain.
The measured live latest snapshot is 2026-11-13, with 97 rows and 97 distinct product IDs.

Artifacts (private/ignored):
`artifacts/local/dashboard-single-dataset/count-coverage-live.json`,
`count-model-coverage.json`, and `count-model-progress.jsonl` in the original workspace.
Every case and per-model response is retained there. No evaluation dashboard was saved.

Reproduce from the clean local integration checkout:

```powershell
$env:PYTHONPATH='src;.'
uv run python -m unittest discover -s tests -p 'test_count*.py' -v
uv run python scripts/agents/evaluate_count_queries.py --output artifacts/local/count-coverage.json
uv run python scripts/agents/evaluate_count_models.py --env-file <local-env-file> --output artifacts/local/count-models.json
```

The live DB mode (`--live`) needs the existing read-only analytics configuration loaded.
The model command makes paid calls; fixture evaluation makes none.

## Clarification regression supplement

The screenshot continuation “latest inventory snapshot” → “Jan to Dec 2026” now keeps
latest mode with inclusive 2026 bounds. Compiler tests include a newer 2027 snapshot,
which must not be selected; tests also reject dropped/changed bounds and retain outer
and nested-query date checks. An API regression exercises both user turns and persists
three KPIs from one query. A live GPT-OSS trial with that clarification history completed
with three distinct-SKU KPIs and one model call. This supplement is not a rerun of the
four-request per-model comparison above and does not change its reported percentages.
Legacy count interpretations receive a count-only repair schema instead of competing
legacy and count schemas; a changed generated period is a repairable interpretation
error rather than a technical clarification question.
