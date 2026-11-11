# SQL metric definitions

Implement the approved first priority on QuocAn: reuse the existing Commerce metric ontology in planning and enforce recognized metric definitions before query execution.

- Planning includes source, formula, grain, dimensions, required filters, units and limitations from the existing ontology.
- Recognized metrics must use their canonical formula and sources. Wrong formulas, missing required filters and incompatible dimensions fail validation and enter the existing one-repair path; they never execute.
- Return the enforced definitions in response metadata and pass them to the answer summarizer. Unknown currency stays unknown; ratio formulas are not silently rescaled.
- Existing non-metric read-only queries retain their current behavior. No database migration, new dependency, general join fanout protection or benchmark/model run is included.
- Validation is deliberately conservative: supported formulas and transparent CTE aliases are checked structurally, not with a general SQL equivalence prover. Existing SQL safety limits remain in place.

Verify with offline unit tests using fake providers/repositories, canonical examples for every ontology metric, adversarial formulas and filters, and the existing focused SQL tests. Record any existing broader-suite failures separately.

Implementation notes:

- Named-metric checks verify source-column lineage and canonical expressions, including transparent CTE aliases. Supplemental measures that do not redefine a recognized metric retain their existing read-only behavior.
- DATE and NUMERIC casts are explicitly allowed so the existing canonical ratio definitions can pass the SQL safety validator; other cast targets remain blocked.
- Existing SQL-test assertions expecting public SQL diagnostics were corrected to the established response contract, which omits SQL and bound parameters. No production diagnostic exposure was added.

Validation:

- All 56 focused tests pass, including canonical examples for all 17 metrics, repair-before-execution, required filters, snapshot constraints, and a SQLite revenue fixture.
- Full discovery: 358 tests, 13 failures and 48 errors. Compared with HEAD under the same project environment, there are no new failing test IDs; three stale SQL response assertions now pass. The remaining failures are outside this change.
- Python compilation and whitespace checks pass. No live LLM, Supabase or Docker validation was performed.
