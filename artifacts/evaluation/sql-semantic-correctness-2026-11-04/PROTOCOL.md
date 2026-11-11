# SQL semantic correctness follow-up

The paired baseline is the completed 30-case cohort at `../sql-semantic-contracts-2026-11-03/final/`, application `153e5d5`. The after cohort is one new live run of S01-S30 at `paired/`, application `f53c56f`. This is a comparison with archived baseline attempts, not two simultaneous reruns. Provider errors may be retried, with original attempts retained. Successful generations and semantic failures are not silently retried.

The baseline predates some fixes already committed on QuocAn; the comparison measures cumulative branch improvements, not exclusively code added on November 4. A separate S27-only live follow-up at `a287d53` verifies an actionable population-filter repair after the full run. Its result is not substituted into the full-run aggregate. The same small follow-up also corrects the interpretation of “most recent” as time rather than ranking; that wording has unit-test coverage, not a new scored frozen question.

The inherited Ragas library, SQLSemanticEquivalence metric, execution/numerical scorers, `CodexCLIJudge`, `gpt-5.6-luna` model and medium reasoning setting are unchanged. The agent uses `qwen/qwen3.8-27b`, temperature 0 and the existing generation budgets. Three configured Groq keys are available in the established primary, backup, RAGAS-key order. No key values are published. Knowledge and Report live benchmarks are excluded.

Frozen questions, SQL references, result rows and identity fixtures remain byte-for-byte unchanged. The manifest records input hashes, application source hashes, revision and package versions. Before generation, all 28 supported SQL reference results were rechecked against the read-only database; all matched. Questions S29/S30 lack valid gold SQL and remain excluded from SQL accuracy denominators.

All 22 baseline SQLSemanticEquivalence failures were reviewed in `failure-audit.json`. Classification counts: six genuine mismatches, one valid equivalent SQL, ten reference/evaluator ambiguities, five execution/data/capability limitations. Ambiguity is not a claim of strict output-schema equivalence. S03/S04/S06/S07/S09 add a constant provenance column. S10/S11/S26/S27 would differ on multiple observations in a month. S20 is equivalent only under the approved NOT NULL discount constraint. Neither frozen references nor approved formulas were edited to resolve these disagreements.

## Changes and validation boundaries

The existing Pydantic `MetricMapping`, `MetricFilter`, `MetricTime` and `MetricRanking` remain the inventory semantic plan. Validated catalog IDs determine source fields, scalar versus aggregate representation, formula, units, denominator and missing-value policy. The compiler builds from that plan; AST checks independently enforce its population, exact filters, date scope, output grain, metric projections and ranking. Known metrics cannot silently become unrelated metrics. A requested non-NULL population has an explicit filter. Unrequested self/outer joins and extra join restrictions are rejected.

`MetricRanking.limit=null` means no user-specified TOP-N; execution still has the independent 200-row safety ceiling. Explicit row counts remain bounded. Unambiguous ranking direction cannot be dropped or reversed. The shared Report evidence collector was updated to treat a null TOP-N as a safety ceiling and disclose unknown completeness at 200 returned rows.

The existing narrow multi-fact validators, not a new generic planning architecture, enforce independently aggregated product operands, complete join keys, matching source periods, no inner LIMIT, no hidden filters/HAVING, inspectable numerator/denominator, NULLIF at zero denominators, no zero replacement of missing operands, and stable ratio ranking. Category comparisons retain FULL JOIN category labels and preserve absent measures as NULL. Raw fact joins remain forbidden. Explicit cancelled-order exclusions cover both spellings case-insensitively, and unit rankings require stable product IDs on ties.

Safe syntax normalization qualifies a column only when exactly one local approved source owns it. It adds a safety LIMIT only to a provably scalar aggregate. Ambiguous names and unbounded detail still fail the existing SQL validator. The MAX-snapshot diagnostic for explicitly dated current-stock requests runs only after RBAC and metric policy checks and explains unavailable current data from actual source availability.

RBAC, source allowlists, approved base joins, SQLGlot validation, repository revalidation, read-only transactions and database timeout enforcement remain in place. No database changes, new dependencies, catalog formula changes or scoring changes were made.

Tests include synthetic duplicate keys (group count versus excess versus participating rows), unequal raw fact multiplicities, zero denominators, NULL populations, tied ranks, complete/incomplete grouped keys, one-sided category coverage, hidden filters, wrong dates/formulas and the approved non-NULL discount boundary. These tests are correctness evidence, not benchmark accuracy scores.

## Reporting rules

Report every metric with its scored denominator and evaluator/provider failure counts. The inherited numerical scorer has variable applicability across runs; its means must not be presented as a fixed-denominator paired improvement. Also show paired per-case changes and any judge score change when the bound SQL is identical. Such changes are evidence of evaluator variability, not a demonstrated implementation improvement.

Latency is descriptive, measured per final attempt, includes request-local retries and excludes pacing between cases. The full suite ran concurrently during part of generation, so latency is not a controlled speed experiment. Existing full-suite failures must be reported separately from focused regression tests.

Remaining boundaries include scalar empty-count provenance (S05), monthly/annual movement rollups that exceed approved snapshot semantics (S12/S16), two-snapshot intersection changes (S13), ambiguous unspecified metric sets (S15), and incomplete natural-language intent verification. These limitations are not addressed by changing formulas or weakening SQL safety.
