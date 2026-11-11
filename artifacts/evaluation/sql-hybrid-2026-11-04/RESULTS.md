# Isolated hybrid SQL experiment — 2026-11-04

Recommendation: **keep production unchanged; retain this as a narrow evaluation variant.** Reject the previous single-pass replacement. This hybrid preserves canonical inventory mapping and deterministic compilation and improves the separately frozen field fixtures, but six explicit requests cannot establish non-inferiority for general natural-language retrieval.

## What changed

`evaluation/sql_hybrid.patch` adds one direct-field branch to the existing agent in an isolated worktree. `evaluation/hybrid_field_contract.py` recognizes complete literal field requests and validates the generated AST against every requested projection, source, filter/date, ordering and row bound. Inventory measures retain canonical mapping/compilation. Raw product price/cogs remain source fields, without inferred currency or company-level metric approval.

The original two-attempt SQL loop remains: one generation plus one repair. Both prompts retain the contract. Existing RBAC, SQLGlot, metric validation, approved-join checks and read-only execution remain in place. Production `src`, metric definitions, permissions, dependencies, original frozen inputs, scoring modules and judge configuration are unchanged; see `integrity-review.json`.

## Fresh paired field evaluation

Six new questions and independently authored references were frozen before generation, separately from the original benchmark. Both variants used the existing Ragas library and scoring implementation, the same `CodexCLIJudge` (`gpt-5.6-luna`, medium), and the same agent provider configuration. Zero provider failures or failed attempts occurred across 12 generations; all 36 metric records completed without evaluator errors. Existing three-key Groq fallback was configured but not exercised by a quota failure.

| Category | Execution accuracy, production → hybrid | Semantic equivalence | Numerical accuracy | LLM calls |
|---|---:|---:|---:|---:|
| Inventory metadata (2) | 1/2 → 2/2 | 1/2 → 2/2 | Not applicable to metadata* | 5 → 2 |
| Product numeric fields (3) | 2/3 → 3/3 | 2/3 → 3/3 | 2/3 → 3/3 | 4 → 3 |
| Product attributes (1) | 1/1 → 1/1 | 1/1 → 1/1 | N/A | 1 → 1 |
| Total (6) | **4/6 → 6/6** | **4/6 → 6/6** | **2/4 → 3/3*** | **10 → 6** |

*The unchanged scorer assigns a failed supported request zero before checking numerical applicability. Thus the failed metadata case F01 contributes a baseline numerical zero. The comparable numeric-field subset is 2/3 → 3/3; the official aggregate is preserved, not adjusted. The baseline unnecessarily clarified F01 and F05; the hybrid completed both. No unsupported fixtures are in this six-case cohort, so a new valid-refusal rate is unavailable.

Fresh request completion was 4/6 → 6/6. Observed p50/p95 latency was **1.918/4.080 s → 1.834/3.472 s** (inclusive percentiles). This small sequential sample includes baseline clarifications and is not a reliable overall speed estimate. The 40% call reduction applies only to these six requests.

Fresh generations/scores measure root experiment revision `0dc92a3` and hybrid application revision `cb9bfdc11a282585091cace9b70b7f8299ea3fa2`. A later numeric-magnitude guard (`1c17bd0`, application `60c9a91b9c5bfde9fefc0bd170563c1a8d10c35f`) passed focused tests and **6/6 exact response replays through the real database**. No fresh model scores or end-to-end latency are claimed for that later revision.

## Original frozen categories: exact replay, not fresh scoring

None of the original 30 questions qualifies for the direct-field grammar. Existing production model responses were replayed through the hybrid and real read-only repository. All 30 matched SQL, parameters, result multisets, statuses, answers and consumed response counts. Therefore the original scores below are **inherited baseline measurements verified by replay**, not new Ragas judgments or new provider timings.

| Category | Cases replayed identically | Execution accuracy, both | Semantic equivalence, both | Numerical accuracy, both |
|---|---:|---:|---:|---:|
| Canonical inventory | 13/13 | 9/13 | 0/13 | 9/13 |
| Inventory diagnostics | 4/4 | 4/4 | 3/4 | 2/2 |
| Commerce analytics | 8/8 | 8/8 | 5/8 | 7/7 |
| Cross-domain | 3/3 | 3/3 | 0/3 | 2/2 |
| Unsupported | 2/2 | N/A | N/A | N/A |

Original overall execution accuracy remains **24/28**, semantic equivalence **8/28**, numerical accuracy **20/24**, and executed request completion **26/30**. The two unsupported requests S29/S30 remain valid refusals (**2/2**, source-policy review with identical replay). Original logical model calls remain **35**, with **zero new model API calls** for replay and no provider failures. Replay runtime is not used as fresh request latency. Original semantic weaknesses, including snapshot/grain/delta ambiguities and cross-domain equivalence disagreements, remain unresolved by this scoped experiment.

## Safety and regression evidence

Five contract tests and seven isolated-agent tests pass. Adversarial mutations cover missing/wrong fields, values and dates, extra/dropped filters, reversed ranking, wrong limits, calculations, unsupported source/write attempts, and oversized generated numbers. They also prove authorization precedes provider/repository use, canonical mapping remains active, the previous blue-stock filter regression is blocked, and invalid direct SQL receives at most one repair without unsafe execution. Recognized requests with ambiguous/unsupported tails fail clarification instead of partial parsing. These are finite adversarial checks, not a proof of universal semantic or security correctness.

Full-suite results: **715 tests, 11 failures, 51 errors, 19 skips**, versus the recorded pre-experiment **703 tests, 11 failures, 51 errors, 15 skips**. There are no new failure/error identities; see `full-tests-latest.json` and `regression-comparison.json`. Isolated-only tests are skipped in production-mode discovery and pass in the focused patched-worktree run. The repository already has failing/import-error tests; this experiment does not claim a green full suite. Production source and Report integration code remain unchanged; no new provider-intensive Report benchmark was run.

## Reproduce and limitations

Use `PROTOCOL.md` and `evaluation/run_sql_hybrid_evaluation.py`. The public patch applies to `ac0d8a2`; copy the helper from the matching root experiment revision into the isolated checkout. Fresh generation/scoring uses root `0dc92a3` plus the measured patch/helper, existing credentials and database. Latest root `1c17bd0` adds replay verification and numeric hardening. Manifests contain application/evaluation hashes and reject changed-code resumption into an existing score directory. Do not overwrite frozen fixture/reference files or old cohort scores; use a separate output folder for a new run. To run focused integration tests, set `SQL_HYBRID_ROOT` to the patched worktree and discover `test_hybrid_field_contract.py` and `test_sql_hybrid_variant.py` separately.

Direct eligibility currently requires explicit English field names and SQL-style literal clauses in a stateless request. General English/Vietnamese, conversational references, aggregates and inventory measures retain production behavior; joins, OR and unsupported expressions cannot enter the direct path. This sacrifices coverage for an independently checkable contract. It does not fix existing production intent weaknesses outside that grammar. The grammar already constructs the full request AST, so the extra model SQL generation may be redundant; measure a deterministic field rendering option before calling this a broad architectural simplification. Modify and extend independent natural-language/paraphrase and NULL/tie fixtures before considering adoption.
