# Approved SQL experiment cleanup

Applied after user approval on 2026-11-05. Production application source, metric formulas, baseline helpers and frozen benchmark inputs/results are unchanged. The newest inventory hybrid remains in the existing SQL Agent and analytics modules. Historical SQL baselines remain available through their frozen results and original Git revisions.

Removed the eight approved experiment files:

- `evaluation/run_sql_single_pass_benchmark.py`
- `evaluation/sql_single_pass_contract.py`
- `evaluation/sql_single_pass.patch`
- `evaluation/replay_single_pass_report.py`
- `evaluation/run_sql_hybrid_evaluation.py`
- `evaluation/sql_hybrid.patch`
- `evaluation/sql_hybrid_deterministic.patch`
- `evaluation/sql_cross_domain_fidelity.patch`

Retired `tests/test_sql_single_pass_variant.py` and `tests/test_sql_hybrid_variant.py` after moving their current-production agent assertions into `tests/test_inventory_adversarial.py`. The retained ten tests cover RBAC before provider/repository calls, canonical compilation, unsafe SQL rejection, wrong dates/ranking/formulas, lost filters with synthetic rows, ordinary product/inventory retrieval, and mocked Markdown/DOCX SQL-evidence compatibility. Variant switches and observation-recording scaffolding are removed. Report checks are unit tests with fake providers, not Report benchmarking.

The deleted evaluation-only contract tests do not become another production validation module. Current checks remain in `test_sql_semantic_authority.py` (NULL populations, safety ceilings, ranking and source population), `test_hybrid_field_contract.py` (exact fields, filters, dates, limits, arithmetic and NULL expressions), `test_metric_mapping.py` (mapping and compiled SQL), and the migrated adversarial tests. Earlier LLM-direct-field repair tests were specific to the retired variant: fully parsed retrieval now renders deterministically, and its field contract tests reject mutated SQL independently. Existing general SQL repair tests remain in place.

Verification: 258 focused tests run, 255 passed, 3 existing skips, zero failures/errors. This includes inventory, SQL generation/join/metric/follow-up checks, Report interface tests, field contracts, semantic authority, baseline ablation and frozen benchmark contract checks. A code-reference search found no remaining imports/callers of the deleted experiment tools. No application source or frozen evidence changed, so the prior 60/60 replay is not reported as a new benchmark run. Existing full-suite CI blockers remain; deleting obsolete experiments does not establish a green merge gate.

Historical provenance documents still refer to the original experiment files. Reproduce retired variants by checking out their original revisions; the removed runners are intentionally no longer runnable from the current checkout. Local worktrees, Docker volumes, Report/Knowledge functionality and unrelated tests were not deleted.
