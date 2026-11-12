# Corrected historical Knowledge baseline

This experiment restores the Knowledge pipeline published at `fed9824` and
evaluates the same 30 frozen questions/reference passages as integrated v3 at
`6bf2f73`. All 20 historical files and all questions are hash-checked (19 files
are byte-identical; one has the schema compatibility edit described below);
the indexed policy corpus also matches v3 (747 chunks).

The earlier 2026-11-11 comparison was invalid: a helper imported from the enclosing
workspace changed `sys.path`, so on-disk historical hashes did not prove which
modules executed. Its three experiment folders were removed from the repository
to temporary quarantine after permanent deletion was blocked by automatic review.
None of their generations, judgments or comparisons are reused here.

The corrected evaluator prioritizes its isolated project root as well as its
`src`, rejects imported `core`/`evaluation` modules outside that root, and records
loaded module paths and byte hashes in `runtime-imports.jsonl`. A self-check
confirmed that the guard rejects a foreign module. `source-provenance.json`
identifies the historical files; `frozen_runner.py` preserves the evaluator.
The manifest's application revision identifies the enclosing checkout; the
restored runtime revision is `config.historical_source_revision`.

The agent, RAG, retrieval, embedding, repository, answer provider and Knowledge
prompt come from `fed9824`. One SQL storage reference in retrieval's shared
`eligible_cte` changes `d.fiscal_year` to `c.metadata->>'fiscal_year'`, because
the old document column no longer exists. Parameter order, filtering and ranking
logic stay the same. The failed schema smoke remains in ignored local scratch,
not in this cohort. Surrounding models and judge support come from
`6bf2f73`. Evaluation adapters enforce employee/document scope at retrieval and
read refusal status from the historical RAGResult, which the old agent does not
propagate. Historical answer generation and validation are preserved.

Both pipelines use Qwen3.8-27B at temperature zero, top-k 5, translated hybrid
retrieval, pinned E5 base/BGE models and the existing RAGAS/Codex CLI
`gpt-5.6-luna` medium judge. Optional multiquery and claim verification remain off.
The historical reranker actually runs float32; v3 uses int8. The historical
provider retains its 1,000-output-token limit. This measures pipeline revisions,
not a single-feature ablation. Hosted model aliases and judgments can vary even
at temperature zero. No statistical-significance claim follows from one run.

The reused harness also freezes invoice references; no invoice generation or
scoring is requested. Credentials remain in the workspace `.env`. Live database
connections are read-only. The current application files are not reverted.
Judge caches are ignored by Git. Request timings exclude model startup and judge
time; concurrent scoring and differing precision limit latency comparisons.

The comparison can be checked offline from a normal checkout of main, without
the ignored runtime or API calls:

```powershell
python artifacts/evaluation/knowledge-baseline-30-2026-11-12/compare.py
```

It reads the published sibling v3 cohort, verifies all generation/score hashes,
checks dataset/corpus equality and validates recorded runtime-import hashes.
The local-worktree fallback exists only for the original QuocAn checkout.
No judge caches, transient logs or invalid earlier cohorts are published.

For runtime verification or a new live experiment, reconstruct the isolated
runtime from the pinned Git commits first. Run these commands from the repository
root; they do not switch or revert the current application. Use a fresh runtime
directory, not one containing unrelated work:

```powershell
$cohort='artifacts/evaluation/knowledge-baseline-30-2026-11-12'
$runtime='artifacts/local/knowledge-baseline-20261111/runtime'
New-Item -ItemType Directory -Force artifacts/local/knowledge-baseline-20261111 | Out-Null
git archive --format=zip --output=artifacts/local/knowledge-baseline-20261111/current.zip 6bf2f73f2eb32940571dcfb424f20a6d336b56f2 src evaluation data/semantic artifacts/datasets/vietstyle-operations-vi-v1
Expand-Archive -LiteralPath artifacts/local/knowledge-baseline-20261111/current.zip -DestinationPath $runtime
$historicalPaths=(Get-Content "$cohort/source-provenance.json" -Raw | ConvertFrom-Json).historical_files.PSObject.Properties.Name
git archive --format=zip --output=artifacts/local/knowledge-baseline-20261111/baseline.zip fed98243b2f87e47623d52161b2ade92e70b640f $historicalPaths
Expand-Archive -LiteralPath artifacts/local/knowledge-baseline-20261111/baseline.zip -DestinationPath $runtime -Force
Copy-Item -LiteralPath "$cohort/frozen_runner.py" -Destination "$runtime/evaluation/run_knowledge_invoice_benchmark.py"
$common=Join-Path $runtime 'src/core/retrieval/methods/common.py'
$adapted=[System.IO.File]::ReadAllText((Resolve-Path $common)).Replace('d.fiscal_year = %s',"c.metadata->>'fiscal_year' = %s")
[System.IO.File]::WriteAllText((Resolve-Path $common),$adapted,[System.Text.UTF8Encoding]::new($false))
```

With the recorded Python dependencies installed, verify the reconstructed source
and the import guard before making any live requests:

```powershell
$env:PYTHONPATH=(Resolve-Path artifacts/local/knowledge-baseline-20261111/runtime).Path
.venv/Scripts/python.exe -m evaluation.run_knowledge_invoice_benchmark --stage verify --output artifacts/evaluation/knowledge-baseline-30-2026-11-12
.venv/Scripts/python.exe artifacts/evaluation/knowledge-baseline-30-2026-11-12/check_isolation.py
```

The existing cohort is complete and append-only. For a new live run, choose a new
output directory, freeze it with `--stage freeze --env-file .env`, then use the
same output with stages `generate --group knowledge`, `score --group knowledge`
and `postflight`. Keep credentials local. The recorded package versions are in
`manifest.json`; do not upgrade the environment during a cohort.
