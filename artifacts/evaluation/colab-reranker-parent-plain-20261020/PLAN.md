# Plain passages vs preceding source text, without added metadata

Status: Colab inference completed and returned; local replay passed.
Read `RESULTS.md`, `findings.json` and `colab-results/verification.json`.
The protocol below was recorded before the run and remains unchanged.

## Why this experiment

The previous parent experiment fixed Q13/Q15 compared with metadata-only
reranking, but Q01 remained regressed and Q20 lost a checklist. Vietnamese
complete-intent count remained17/19 versus the original plain reranker. This
test asks whether the predecessor text can retain the useful effect without
adding filename/section/table prefixes. It is a post-hoc diagnostic on the same
20 paired intents, not a held-out test or production decision.

## Fixed comparison

- Control: exact original plain passages.
- Treatment: same13 eligible predecessor/anchor pairs as the prior experiment,
  with the preceding source text and original anchor, without added metadata
  prefixes. Native headings already present in original source text remain.
- Unchanged source corpus, evidence-v3 labels, E5 vectors/top30 candidates,
  all80 cases, pinned BGE reranker, float32, batch4 and top10 output.
- Rerun both arms on the same assigned Colab GPU. Historical A100/T4 runs are
  context only, not substitutes for the new paired control.
- Same <=800-character anchor rule, immediate predecessor, document/language,
  exact page/sheet/slide/role checks, nonconflicting section rule. No answer,
  question or label-based context selection. No broader candidates or new labels.
- Additional context is ranking-only. Evidence coverage uses only the original
  selected anchor text/character provenance.
- No total context-token cap; reject overlength model pairs before inference.
  `preflight.json` records exact local tokenizer maxima under the1024 pair limit.

## Code changes and checks

`evaluate_reranker_source_context.py::render_parent` now accepts an optional
`include_metadata` flag. Existing parent behavior defaults to True and is
preserved. New `render_parent_plain` uses False. CLI `--context-mode parent-plain`
sets plain control and predecessor-text treatment; config records both modes.
No production code changes or local model download.

Existing builder/analyzer scripts gain `--parent-plain`, producing separate
paths. Existing experiment ZIPs, notebooks and results are preserved. The
preflight helper gains `--plain-control` and checks that the selected anchors
and preceding text are identical to experiment2; only added metadata is removed.
It uses only the already-cached pinned tokenizer, never model weights/network.

The bundle builder checks all strict frozen hashes/source mappings/original
dense rankings for1063 passages and80 cases, ZIP integrity, absence of `.env`
and weights, and notebook Python syntax. Saved-score verification will check
all160 rankings/4800 entries and independent evidence character coverage after
the new results are returned. Full application tests are not run for this
experiment-only change.

## Run on Colab

1. Upload `reranker_parent_plain_colab.ipynb` to https://colab.research.google.com/.
2. Select a free GPU runtime and run cells in order.
3. At the file picker upload `reranker_parent_plain_colab_inputs.zip` (~22MB).
4. The model downloads and runs on Colab, not on this laptop. No API key is used.
5. Run verification and download `reranker_parent_plain_results.zip`. Put it in
   this folder and tell Codex it is ready.

Then inspect it with:

```powershell
.venv/Scripts/python.exe -X utf8 artifacts/evaluation/colab-reranker-context-20261020/analyze_results.py --parent-plain
```

Report all four directions, full-intent/component gains AND losses, and the
Q01 approval, Q13/Q15 guard and Q20 proposal-check positions. Check whether
the Q13/Q15 fixes survive, whether Q01 recovers and whether Q20 still regresses.
Do not add labels or alter selection rules after seeing these results.
