# Inventory Knowledge evaluation: reproducibility

Branch: `eval/knowledge-invoice-20261110`. Integration merge: `f0d5d25`.
The merge parents are local QuocAn `43f4446` (ahead of remote `2423126`) and main
`cae083c`. Measured application/evaluator: **`6bf2f73f2eb32940571dcfb424f20a6d336b56f2`**.
No changes were merged or pushed to main, and no production data was modified.

The complete metric comparison is in `COMPARISON.md`. This folder's Knowledge
run and the invoice v2 run are separate cohorts; their records are never mixed.

## Inputs and environment

`knowledge/dataset.json` contains the 30 frozen questions, independent reference
answers and exact policy-page passages. The source is approved
VSC-OPS-POL-001 v1.0, effective 2026-10-23, Inventory Management pages 25–35.
There are 25 supported policy questions and five unsupported operational lookups.
References are author-reviewed, not externally certified or an unseen held-out set.

The production KnowledgeAgent uses only the live indexed VN policy document,
an employee role, top-k 5, translated hybrid retrieval, E5 base at `d128750...`
and BGE reranker v2-m3 at `953dc6f...`, CPU int8 reranking. Answer model:
`qwen/qwen3.8-27b`, temperature 0. Optional multiquery and claim-verification
flags remain off, matching their default setting. Their runtime is integrated,
but this run is not a live ablation of those options.

RAGAS uses the existing Codex CLI adapter with `gpt-5.6-luna`, medium reasoning.
The installed RAGAS is the existing fork at
`https://github.com/GoldSharon/ragas.git`, commit
`735726d5c29e072b5e4e877759d254f78e0f7c73`, version
`0.1.dev1148+g735726d5c`; it is not an unspecified latest PyPI release.
`runtime-environment.json` records package versions and hashes of its modules.
Authenticated Codex CLI 0.167.0, the recorded Python environment, read-only
Supabase access and cached pinned HF models are prerequisites. Credentials are
loaded from the original workspace's `.env`; none are saved in the artifacts.

HF's default E5 revision was verified to equal the pinned revision and its
`config.json` lookup cached before offline RAGAS loading. If preparing a clean
cache, verify that equality first; otherwise use the exact pinned local model.
The first RAGAS initialization failed on that missing cache lookup before any
score was written; its diagnostic log is retained, and no metric record was
replaced when initialization resumed.
Preserve checkout line endings: source byte guards include them. On a fresh
pinned reproduction worktree, `restore_checkout_bytes.py --checkout PATH` reports
newline differences; add `--write` to restore only LF/CRLF forms whose hashes
match the frozen manifest and whose contents come from the pinned Git commit.
It refuses any other difference and never disables a source guard. Temperature 0
does not guarantee bitwise deterministic model answers or judge results.

## Commands

Run from a checkout/worktree of the measured revision with this frozen cohort
folder available. Use the recorded virtual environment, not an unpinned upgrade.
`python` below denotes that environment's executable.

```powershell
python -m unittest discover -s tests -p test_knowledge_invoice_benchmark.py -v
python -m evaluation.run_knowledge_invoice_benchmark --stage verify --output artifacts/evaluation/knowledge-invoice-2026-11-10-v3
```

For a **new** experiment, use a new output directory and the authenticated env
file; freeze before generating anything. First generate and score K01/K26 as
smoke cases, then generate the missing questions. Never use failed-score retries
to replace a saved metric.

```powershell
python -m evaluation.run_knowledge_invoice_benchmark --stage freeze --output artifacts/evaluation/knowledge-reproduction --env-file PATH_TO_ENV
python -m evaluation.run_knowledge_invoice_benchmark --stage generate --group knowledge --ids K01 K26 --output artifacts/evaluation/knowledge-reproduction --env-file PATH_TO_ENV
python -m evaluation.run_knowledge_invoice_benchmark --stage score --group knowledge --ids K01 K26 --output artifacts/evaluation/knowledge-reproduction --env-file PATH_TO_ENV
python -m evaluation.run_knowledge_invoice_benchmark --stage generate --group knowledge --output artifacts/evaluation/knowledge-reproduction --env-file PATH_TO_ENV
python -m evaluation.run_knowledge_invoice_benchmark --stage score --group knowledge --output artifacts/evaluation/knowledge-reproduction --env-file PATH_TO_ENV
python -m evaluation.run_knowledge_invoice_benchmark --stage postflight --output artifacts/evaluation/knowledge-reproduction --env-file PATH_TO_ENV
python -m evaluation.run_knowledge_invoice_benchmark --stage summarize --output artifacts/evaluation/knowledge-reproduction
```

The delivered cohort used `score_partitions.py` to score the remaining K02–K15
and K16–K30 except K26 in two disjoint partitions. `prepare-a`, `score-a`,
`prepare-b`, `score-b`, `merge` retain each worker's raw records and check exact
parent manifest and generation hashes. Merge refuses missing, overlapping or
changed score records. This is parallel scoring of one cohort, not a combination
of incompatible runs. Per-judgment caches include prompt, schema and model
configuration; interruptions reuse cached judgments and completed records.

The invoice reproduction uses its v2 source revision and the same commands with
`--group invoice`, a new folder and smoke IDs I01/I08. Do not run the v3 evaluator
against v2's existing source-byte manifest.

## Limits and preservation

Startup is logged separately in `model-startups.jsonl`; per-question request
latencies exclude model loading, judge time and between-request pacing. The
failed cold-start smoke remains in v2. Metrics include all applicable frozen
cases; abstentions remain visible. Faithfulness of statement-free refusals is
N/A; relevancy still scores them, and Context Precision uses the independent
reference. Citation ID validity and expected-page matches are structural/location
proxies, not claim-level citation entailment certification.

Schema/data/corpus hashes match before and after generation. All **754** existing
agent evaluation files checked in the preservation manifest remain byte-identical;
no old SQL/Report baseline or improved score was replaced. The original dirty
QuocAn worktree was left intact. Production Knowledge/SQL/Report source matches
the integrated main revision. Focused Report/invoice/integrity tests: 87 pass.
Knowledge runtime tests: 85 run, three failures already present on main. Broad
discovery also retains historical QuocAn experiment expectations that differ
from main; no green full-suite or production-readiness claim is made.
