# Proposed SQL cleanup — awaiting user review

No files have been deleted. Preserve the production baseline through the existing baseline evaluation/revision, and preserve the integrated inventory hybrid at `9642d32`. These are the proposed obsolete experiment files to remove together:

1. `evaluation/run_sql_single_pass_benchmark.py`
2. `evaluation/sql_single_pass_contract.py`
3. `evaluation/sql_single_pass.patch`
4. `evaluation/replay_single_pass_report.py`
5. `evaluation/run_sql_hybrid_evaluation.py`
6. `evaluation/sql_hybrid.patch`
7. `evaluation/sql_hybrid_deterministic.patch`
8. `evaluation/sql_cross_domain_fidelity.patch`

The first four belong to the rejected single-pass experiment. The next three belong to earlier hybrid construction/replay experiments; the current inventory hybrid is implemented in production modules and has a separate replay runner. The last is a cross-domain experiment outside the approved inventory demo scope.

Conditional follow-up file removals, only after retaining their useful security/semantic assertions in current inventory tests:

- `tests/test_sql_single_pass_variant.py` imports the retired experiment contract; migrate relevant adversarial checks before deleting it.
- `tests/test_sql_hybrid_variant.py` uses the historical `SQL_HYBRID_ROOT` variant harness; retain RBAC/filter/NULL/ranking coverage before retiring that wrapper.

Keep `src/core/agents/sql_analytics_agent.py`, `src/core/analytics/field_retrieval.py`, metric mapping/validation, SQLGlot and repository modules, `evaluation/hybrid_field_contract.py`, inventory benchmark/replay runners, semantic ablation helpers used by the baseline comparison, existing security tests, all frozen questions/references/scores/generations and existing Report/Knowledge code. Do not remove unrelated failing tests as cleanup.

Tradeoff: deleting historical experiment patch/runners retires their reproduction from the current checkout. Their original Git revisions and all frozen evidence remain. Retain those tools if current-checkout reproducibility of rejected variants is still required. Local historical worktrees and Docker volumes are excluded from this deletion proposal.
