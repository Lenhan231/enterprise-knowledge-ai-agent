# Isolated Knowledge / invoice evaluation, v1

Scope: merge current main into a branch from local QuocAn; freeze 30 Inventory
Management questions from approved VSC-OPS-POL-001 v1.0 (effective 2026-10-23),
and ten invoice questions with independent live read-only SQL oracles. The policy
has 25 supported questions and five explicitly unanswerable operational lookups.
References are authored before generations, source-linked and author-reviewed;
they are not externally certified gold or an unseen generalization benchmark.

Build order: integration/regression verification, fixture/oracle freeze, two-case
smoke in each group, then missing generations and metrics, then aggregate/report.
No production writes, invoice approvals, migrations or merge/push to main.

Knowledge uses the merged production KnowledgeAgent, role employee, pinned local
E5 and BGE reranker, the live approved VN policy document only, top-k 5. Source
scope is applied at the retrieval boundary. No gold passages are supplied to the
agent. Default optional multiquery and claim-verifier flags remain off; their
new runtime is integrated and tested, but this cohort is not their ablation.
RAGAS Faithfulness, Answer Relevancy and Context Precision use the existing
CodexCLIJudge and local embeddings. Full retrieved context, actual cited sources,
latency, abstentions, schema-valid citation rate and expected-page citation hits
are retained. Expected-page hits are a citation-location proxy, not proof of
claim entailment. Abstentions and failed generations remain in denominators;
faithfulness of a statement-free refusal is N/A, relevancy is scored, and context
precision remains reference-based. Provider failure is not a valid abstention.

Invoice execution and numerical metrics reuse existing deterministic comparison
helpers, including their strict output-column contract. No LLM judge is needed.
Schema/keys/privileges and source data hashes are captured before generation and
rechecked afterward. Live population size is disclosed; limited data cannot
establish arbitrary SQL equivalence, fanout safety or multi-currency behavior.

One immutable row per case/metric. Resume only missing work. Never replace failed
scores or successful generations. Provider failures are recorded and stop further
scheduling; a changed source/config/dataset requires a new cohort. Judge cache
keys include the exact prompt, schema and model config; cached successes can
resume interrupted metric calculations. No retry may relabel a recorded failure.
Smoke records are reused in the same frozen cohort only when source and config
hashes match. Old SQL/Report files and results remain byte-identical.

Comparisons describe integration and preserved historical metrics. A single new
cohort is not a paired improvement claim over historical, incompatible datasets.
No optional model sweep or rerunning old SQL/Report benchmarks is in scope.
