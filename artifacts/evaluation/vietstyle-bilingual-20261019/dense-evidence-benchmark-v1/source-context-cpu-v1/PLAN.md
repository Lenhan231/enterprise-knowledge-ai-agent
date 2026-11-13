# Source/section context for short reranker inputs

## Current execution status

Inference has not run. User requested an API option instead of local CPU and
configured a Hugging Face token locally. Availability metadata lists the same
BGE model under hf-inference/text-classification; no dedicated endpoints exist
in the account. A synthetic query–passage probe returned HTTP 402: no remaining
Inference Providers credits. Query-pair support is therefore not yet confirmed.
No benchmark text was sent, no endpoint was deployed, and local downloads are
paused with resumable parts retained. Continue after the user supplies credits
or another authorized execution option. Never treat the plan as a result.

Plan recorded before inference on 2026-10-20. Diagnostic extension of the
previously reviewed Q13/Q15 failures; this is not a held-out evaluation.

## Fixed experiment

- Frozen E5 vectors, original top-30 candidate lists, all 80 cases and 1,063
  bilingual passages from Huy `5733f22`. Evidence v3 SHA256:
  `cf022622eafcde551eac6ba26e3bd4f8aac7fc4239533dd951e5dbac1cb648e3`.
- Pinned BGE-reranker-v2-m3 revision
  `953dc6f6f85a1b2dbfca4c34a2796e7dde08d41e`, CPU float32, four threads,
  batch four. Recompute the raw-passage control on this same runtime.
- Treatment: for every original passage of at most 800 Unicode characters,
  prepend filename, existing section title and table title when available.
  If section is absent, use the closest preceding nonempty section metadata
  from the same document, language, page/sheet/slide and identical role list.
  All longer passages remain identical. Rule is independent of question,
  evidence labels, reference answers and model scores.
- This modifies 1,055/2,400 question–candidate pairs. Plain scores for unchanged
  inputs are reused exactly, so 3,455 pairs require actual inference.
- Select top ten by raw logits, stable dense-order ties. No total context-token
  cap; 1,024 is only the per-pair model input limit. Preflight every raw and
  contextual pair with the pinned tokenizer and reject truncation.
- Context is ranking-only: evidence scoring and final selected texts use the
  original passages/provenance. Additional heading text cannot earn coverage.
- Report all four directions, complete intents and required components,
  gains/regressions, Q13/Q15 history-guard ranks, and CPU control drift from
  historical GPU float16. Keep Q14 unresolved and excluded from full-intent
  denominator (19 eligible per direction; 61 ready required components).

## Code: before / after / verification

Before: `evaluate_vietstyle_reranker.py` uses question + plain chunk on GPU and
frozen v2 labels. After: new experiment-only
`scripts/retrieval/evaluate_reranker_source_context.py` reuses its loader,
candidate selection, model, pair preflight and evidence checks, then loads
unchanged v3 labels and compares two paired CPU conditions. Production code
and historical runners/results are unchanged.

The experiment creates an ignored `.venv/source-context-inputs/` Git archive
with `core.autocrlf=false`, so strict original hash checks work on Windows.
No historical file is edited or hashes relaxed. Model files are downloaded
once into ignored `.venv/benchmark-model-cache`; inference is offline/local.

After inference `--verify-only` checks saved input/score hashes, rendered
metadata, unchanged-pair score equality, all 160 rankings, direction summaries
and evidence coverage with the existing independent character check. No model
is loaded during verification.

Run from repository root with the existing Python environment:

```powershell
$env:OMP_NUM_THREADS='4'
$env:MKL_NUM_THREADS='4'
$env:HF_HUB_OFFLINE='1'
.venv/Scripts/python.exe -X utf8 scripts/retrieval/evaluate_reranker_source_context.py
.venv/Scripts/python.exe -X utf8 scripts/retrieval/evaluate_reranker_source_context.py --verify-only
```

No new embedding model, vector migration, database access, translation,
generation or production reranker integration is part of this experiment.
