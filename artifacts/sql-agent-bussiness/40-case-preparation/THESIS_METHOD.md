# SQL Agent benchmark method (draft)

## Scope

Evaluate SQL Agent business correctness and safe completion on a frozen, independently reviewed 40-case cohort. The benchmark excludes Knowledge retrieval, Auto routing, response-prose quality and user-facing synthesis. Record route/invocation only as diagnostic metadata; do not count it as SQL correctness.

## Freeze before evaluation

Freeze the case wording and hash, two-reviewer decisions/adjudication, author-reviewed gold SQL and parameters, reference results, per-case comparison tolerances, approved schema/JOIN contract, read-only database fingerprint and benchmark/scorer version. Keep all five pilot cases as development examples outside the held-out set. Do not revise the cohort after inspecting Agent outputs.

## Execution protocol

For each supported case, submit exactly the frozen question (and explicitly specified context for follow-up cases) to the SQL Agent against the same frozen read-only snapshot. Capture initial and repaired SQL, bound parameters, generated-SQL and repair call counts, schema/JEV selection calls, provider/model attribution, validation outcomes, read-only execution events, final rows/status, latency and errors. Do not turn an unsupported query into an unverified execution. For unsupported cases, capture clarification/abstention behavior without executing business SQL.

Follow-up cases B40-026–030 require a versioned adapter that injects the frozen typed semantic context but no assistant answer or result rows. Until that adapter is implemented and independently tested, those cases are not evidence of live multi-turn behavior.

## Primary measures

- **Business end-to-end accuracy:** supported cases with correct final business rows and unsupported cases with valid safe clarification/abstention, over all executed cohort cases; publish separate supported and unsupported numerators/denominators.
- **Supported SQL semantic accuracy:** supported questions whose final SQL preserves all required tables, filters/population, time, grouping, ranking/tie-break, limit and output contract. Exact SQL string match is secondary only.
- **Business result accuracy:** supported cases that execute and match reference rows under frozen per-case tolerance. Report exact numerator/denominator and row comparison details.
- **Valid unsupported abstention rate / false clarification rate:** supported cases incorrectly clarified/refused versus unsupported cases safely clarified/abstained. Invalid schema clarifications do not count as valid abstention.
- **Supported noncompletion and validation-blocked rates:** report failed, validation-blocked, repair-exhausted and provider/network cases separately; do not relabel them as successful refusal.
- **Unsafe execution count:** any query that violates read-only, approved-source, schema/JOIN or authorization rules and reaches DB execution. Target is zero.
- **Repair recovery:** semantically invalid initial SQL corrected within the existing bounded repair budget, reported over eligible repair attempts.
- **Latency and invocation cost:** median/p95 latency and counts by provider, generation, repair and schema selection. Distinguish JEV unavailable/fallback from successful JEV selection.

All metrics must show numerator, denominator, exclusions and NOT RUN cases. Missing provider/database access is NOT RUN, never a synthetic pass.

## SQL LLM comparison (future protocol only)

To compare two SQL LLMs, change only the SQL generation model. Freeze prompt and schema, SQL Agent code, JEV policy, validator/repair budget, fallback provider, database snapshot, temperature/settings and request limits. Prefer single-provider attribution; if fallback is enabled, freeze it and report every fallback submission. Run paired cases in counterbalanced model order, randomize order within each pair, and keep one output per model/case unless a repeated-run protocol is predeclared. Score blind to model identity with the frozen deterministic scorer and independent adjudication. Report paired accuracy deltas with confidence intervals and paired error categories; do not use exact-match as the sole quality measure. This protocol is documentation only; no new model comparison is run here.

## Readiness boundary

This folder contains a draft cohort and provisional reference preparation only. It is not frozen and is not ready for 40-case Agent execution until independent review, adjudication, gold validation and the context adapter requirement are complete.
