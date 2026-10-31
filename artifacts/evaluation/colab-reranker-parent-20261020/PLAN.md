# Preceding source context: controlled follow-up

Status: prepared for user-run Colab inference. No new reranker results yet.
Date: 2026-10-20. Previous metadata-only experiment remains preserved in
`../colab-reranker-context-20261020/`.

## Hypothesis and fixed conditions

The short history guard may need actual surrounding source text for the
cross-encoder to recognize its connection to the question. Metadata prefixes
alone failed to fix this. This follow-up isolates the added source-body context:

- Control: the previous metadata-only rendering.
- Treatment: identical rendering plus one immediately preceding source passage
  for candidate passages of at most 800 Unicode characters.
- Same model revision, GPU/dtype, original E5 top-30 pools, 80 cases, evidence v3,
  and top-ten output in both conditions. Plain baseline from previous runs is
  historical context only; rerun this control on the same new GPU runtime.
- Selection rule uses document ID, language, consecutive retrieval AND parser
  indexes, matching page/sheet/slide and identical role lists. Conflicting
  nonempty section titles exclude a neighbor. If all location fields are
  missing, a shared nonempty section is required. No query/label/score-based
  neighbor selection and no cross-document context.
- If no valid predecessor exists, treatment equals control. Both arms reuse
  identical scores for identical input pairs. No total context-token cap.
- Preflight all question/passage pairs with the pinned BGE tokenizer; reject
  input above the 1,024-token per-pair model limit. This is an architecture
  input bound, not a cap on the total context returned by retrieval.
- Neighboring text is ranking-only. Scoring and final selected passage text
  retain the original character provenance. Adding an answer in a neighbor
  cannot itself earn evidence coverage for the anchor.

## Before / after code

`scripts/retrieval/evaluate_reranker_source_context.py`: previously compared
plain input with metadata prefixes. Optional `--context-mode parent` now compares
metadata prefixes with the deterministic predecessor rendering. The existing
default metadata mode is preserved. Config records `context_mode=parent` and
`control_mode=metadata`. The JSON's legacy `plain_*` fields refer to the
metadata-only control in this mode; `source_context_*` refers to parent context.

`../colab-reranker-context-20261020/build_bundle.py --parent-context`: builds a
separate notebook/input bundle and separate Colab result paths, preserving the
first notebook, bundle and returned results. Strict input hashes and saved
candidate/evidence replay are reused. No production source/index changes.

`preflight.py`: validates the frozen data, deterministic history-guard predecessor
and both sets of tokenizer input lengths using the already-cached tokenizer.
It never loads reranker weights or downloads anything. See `preflight.json` for
counts/maxima. The portable input loader and notebook Python syntax are checked
by the bundle builder without running a model.

## Run in Colab

1. Upload `reranker_parent_context_colab.ipynb` at https://colab.research.google.com/.
2. Choose a free GPU runtime. Do not purchase compute units; availability varies.
3. Run cells in order. At the upload picker choose
   `reranker_parent_colab_inputs.zip` (about 22 MB).
4. Inference and model download happen on Colab. No local model download or API
   key is required. Both experimental arms run together on the assigned GPU.
5. Run the saved-score verification and download cells. Return
   `reranker_parent_context_results.zip` for analysis.

Report full-intent and component coverage in all four directions, Q13/Q15 guard
ranks, gains and regressions (including Q01). Check predecessor rendering,
unchanged-pair scores, every saved ranking and independent character coverage.
This is a post-hoc diagnostic on 20 paired intents, not held-out validation or
answer-generation accuracy. No model migration or production integration is
authorized by this experiment.
