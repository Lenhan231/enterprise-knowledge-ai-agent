# Single-pass SQL comparison

**Recommendation: modify; do not adopt this variant. Production remains unchanged.** Direct schema-grounded SQL handles ordinary inventory fields more flexibly, but this candidate did not demonstrate non-inferior correctness or preservation of the existing intent boundary.

Both full cohorts use the identical 30 frozen questions/references, same Groq model/temperature, unchanged Ragas metrics/scorers, and the same `gpt-5.6-luna` / medium judge. All 28 supported reference results were verified against the read-only database. Production is `624fc8c` with `src/` identical to `f48bec5`; the isolated full candidate is `fd44615`. This is a sequential paired experiment, not randomized performance testing.

| Measure | Production | Single-pass full candidate |
|---|---:|---:|
| Execution accuracy | 24/28 (85.7%) | 15/28 (53.6%) |
| SQL semantic equivalence | 8/28 (28.6%) | 5/28 (17.9%) |
| Numerical accuracy, inherited applicability | 20/24 (83.3%) | 12/25 (48.0%) |
| Numerical accuracy, common applicable cases | 20/24 (83.3%) | 12/24 (50.0%) |
| SQL executed, including empty results | 26/30 | 18/30 |
| Valid refusals, manual unsupported-case review | 2/2 | 2/2 |
| Final-attempt latency p50 / p95 | 2.194s / 3.492s | 2.021s / 4.576s |
| LLM calls, final attempts | 35 | 27 |
| LLM calls, all attempts | 35 | 28 |
| Latest provider failures / evaluator errors / pending scores | 0 / 0 / 0 | 0 / 0 / 0 |
| Historical provider-failed attempts | 0/30 | 1/31 |

Single-pass median latency was about 8% lower, while p95 was higher. Many faster responses were refusals/rejections, so this is not a demonstrated speedup for successful equivalent answers. The candidate's S26 first attempt hit Groq HTTP 503 capacity after 30.352s; only that provider-failed request was retried, successfully. Final-attempt latency excludes that superseded failure and between-request pacing. Provider failure records and stale scores remain in append-only files; current scores select the latest generation attempt.

The candidate removes the inventory mapping/compilation stage **and** the SQL repair pass. Consequently, this experiment does not isolate the effect of removing metric mapping alone. Production inventory answers already often use one LLM call followed by deterministic compilation; skipping mapping does not inherently eliminate a model call.

## What passed and what failed

The evaluation patch reuses production RBAC, SQLGlot allowlists, join/grain checks, metric formulas/approval checks, source-availability preflight, repository revalidation, read-only transactions and result interface. No production file, route, database permission, schema, metric formula or scoring implementation was edited. The single-pass prompt retains schema and business definitions; ordinary field retrieval does not require an LLM MetricMapping response. The experiment is stateless and is not registered in production routing.

The paired fixture tests show a real tradeoff:

- Seven injected invalid SQL cases were blocked by both paths: formula/date/filter/rank mutation, writes, private sources and a multiplying fact join. RBAC tests verify denial before provider/repository calls. Another 46 existing AST/metric/join/repository safety tests pass in the isolated checkout.
- For the additional free-text filter fixture, the supplied correct production mapping requires blue products. Mutating SQL to drop that predicate is rejected by production. The single-pass path accepts it and returns a red product with stock 100 before the blue product with stock 5. This is a new semantic population regression: **production blocks 8/8 of these negative fixtures; single-pass blocks 7/8**. The test measures a lost enforcement boundary, not a claim that production's LLM always interprets color correctly. No adversarial query was executed remotely.
- An ordinary approved `snapshot_date, product_id, year, month` inventory query executes through single-pass in one generation; production's mandatory interpretation rejects it after three fixture-provider calls. An ordinary product ID/name/category query works in both. This is fixture-based capability evidence, not an added frozen benchmark score.
- Single-pass rejections include missing bindings/LIMITs, unavailable canonical interpretations, and validated multi-fact/population constraints. Some are model SQL errors that production repairs; some are adapter limitations. They must not be attributed solely to the abstract architecture.

All full candidate failures and measured regressions are inspectable in raw generations, scores and [single-pass-v2/paired-summary.json](single-pass-v2/paired-summary.json). The preliminary `single-pass/` run contains adapter defects and is excluded from the accuracy table.

## Separate correction and evaluator limitations

The full candidate falsely rejects valid S08 SQL because of SQLGlot's alternate IS NOT NULL AST representation. The subsequent `1ec5007` correction has unit coverage for both forms. One separate fresh S08 request scored **execution 1.0, numerical 1.0, semantic 0.0**, with one generation call and no provider/evaluator error. Semantic disagreement concerns dynamic latest versus the frozen fixed date and extra snapshot provenance. This one-case result is in `null-fix/` and is **not substituted into the full candidate table**. No full-cohort accuracy is claimed for that later revision.

S11's raw runtime rows match the frozen rows on all identically named reference columns, but the inherited scorer reports execution/numerical zero. Its scoring pipeline uses an LLM for column alignment; an alignment inconsistency is a possible cause, but the mapping itself was not logged. [scorer-diagnostics.json](scorer-diagnostics.json) records the deterministic row check. Official scores remain unchanged. Strict semantic judging also penalizes provenance/schema and month-versus-closing-snapshot differences. These limitations qualify the numbers; they do not erase the demonstrated filter regression.

## Report compatibility and tests

Markdown and DOCX both complete through Report Agent's actual shared-SQL evidence path. The integration replay uses captured S09 SQL, the latest isolated variant and fresh read-only database rows: two rows included, eight facts, no new model API calls. A deterministic writer references validated facts. DOCX tables parse successfully in memory. This verifies interface/fact/table compatibility, not narrative quality, visual layout or period-comparison behavior. Shared-SQL facts retain date scope in SQL/field provenance; their report coverage snapshot list is empty. See [report-compatibility.json](report-compatibility.json).

The experiment's focused tests pass (10 initial paired fixture tests, 14 corrected-candidate tests, 15 final NULL-form tests). Some tests intentionally assert that a measured semantic regression exists; a green unit suite is **not** a non-inferiority pass. The full production-workspace suite runs **703 tests with 11 failures, 51 errors, 15 skips**, with no new failure/error names versus the recorded baseline. Production source is byte-for-byte untouched in the working tree and textually identical to `f48bec5` in Git.

Keep the existing pipeline for business metrics and unconstrained natural-language requests. Before considering adoption, constrain direct field requests with independently verifiable intent, preserve a validated population/filter contract, and reassess the loss of bounded SQL repair. Re-run a comparable cohort and adversarial fixtures after a targeted change; do not trade correctness for fewer calls.

## Reproduce

Use the recorded code revisions, same database snapshot and authenticated environment. The experiment runner loads the existing root `.env` without copying/logging keys. Create a detached checkout of `f48bec5`, apply `evaluation/sql_single_pass.patch`, copy the **matching revision** of `evaluation/sql_single_pass_contract.py` into its evaluation folder, and commit the isolated changes. Production stays on QuocAn. The worktree names expected by the runner are `artifacts/local/sql-single-pass-variant` for the preliminary run and `artifacts/local/sql-single-pass-candidate` for the corrected candidate/follow-up.

Use new output directories for a genuinely new experiment. Existing manifests reject changed source/helper/harness hashes; do not overwrite hashes to resume a different revision. Windows checkout line endings may alter byte hashes; preserve the recorded input bytes or start a clearly separate reproduction with the same frozen question records and verified reference hash. Use **absolute paths** for `--output` because the runner enters the isolated checkout before parsing stage arguments.

```powershell
# At 624fc8c: fresh production generation/scoring; production src equals f48bec5.
uv run python evaluation/run_sql_single_pass_benchmark.py production --stage verify
uv run python evaluation/run_sql_single_pass_benchmark.py production --stage generate
uv run python evaluation/run_sql_single_pass_benchmark.py production --stage score

# At fc16535 with detached candidate fd44615: full corrected single-pass run.
uv run python evaluation/run_sql_single_pass_benchmark.py single-pass-v2 --stage generate
uv run python evaluation/run_sql_single_pass_benchmark.py single-pass-v2 --stage score

uv run python -m evaluation.summarize_sql_semantic_pair --before artifacts/evaluation/sql-single-pass-2026-11-04/production --after artifacts/evaluation/sql-single-pass-2026-11-04/single-pass-v2
```

For the final NULL-form correction, use the helper at `c5e879b`, detached candidate `1ec5007`, `--ids S08`, and a separate absolute output directory. Then run `uv run python evaluation/replay_single_pass_report.py` for the read-only Report replay. Raw cohorts remain separate by revision. Knowledge and full Report quality benchmarking are excluded.
