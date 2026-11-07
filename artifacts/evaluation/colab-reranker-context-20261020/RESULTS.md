# Colab source-context experiment: findings

Reviewed 2026-10-20. Returned input: `reranker_context_results.zip`.

**Conclusion: do not adopt this metadata-prefix rule.** It changed rankings
but did not fix the targeted missing evidence and introduced one complete-intent
regression. This is a small post-hoc diagnostic, not a held-out production test.

## What was run

- Same pinned BGE-reranker-v2-m3 revision
  `953dc6f6f85a1b2dbfca4c34a2796e7dde08d41e` for both conditions.
- Colab reports NVIDIA A100-SXM4-40GB, PyTorch 2.11.0+cu130, float32, batch 4.
- Same 80 cases from 20 paired intents, unchanged E5 top-30 candidate pools,
  1,063 shared passages, top-ten output, evidence v3 labels.
- Control: plain passage. Treatment: filename and available section/table title
  for passages at most 800 Unicode characters; missing sections may inherit
  preceding same-document/language/location/role section metadata.
- 1,055/2,400 pairs changed. Unchanged-pair logits are reused exactly.
  3,455 pairs required actual inference; two 80×30 score matrices were saved.
- Added headers affect ranking only. Coverage is checked against unchanged
  original passages and character provenance, so prefixes cannot earn evidence.
- No total context-token cap. Recorded per-pair maximum 507 under the configured
  1,024 limit, zero truncated pairs. Tokenizer preflight was performed by the
  Colab run; local review did not load a tokenizer or model again.

## Complete-evidence results

Each direction has 19 fully eligible intents; Q14 is unresolved and excluded.
The component denominator is 61 required ready components per direction.

| Query → documents | Plain complete | Prefix complete | Plain components | Prefix components |
|---|---:|---:|---:|---:|
| VI → VI | 17/19 | **16/19** | 59/61 | **58/61** |
| EN → EN | 14/19 | 14/19 | 55/61 | 55/61 |
| VI → EN | 12/19 | 12/19 | 46/61 | 46/61 |
| EN → VI | 12/19 | 12/19 | 49/61 | 49/61 |

Across all 80 cases, no required ready component changed from missed to met.
The only component change was Q01.approval in VI→VI, met→missed. This statement
is about the fixed annotation rubric, not a claim that every unlabelled alternative
or generated answer was exhaustively evaluated.

## Targeted questions

| VI → VI question | Plain coverage | Prefix coverage | Explicit history-guard rank |
|---|---:|---:|---|
| Q13: count/adjustment process | 8/9 | 8/9 | 21 → 21 |
| Q15: adjustment transaction fields | 3/4 | 3/4 | 27 → 21 |

The same short SOP parser chunk 4 contains the explicit no-delete/no-direct-
source-edit instruction. For Q15 its logit improved from -5.027 to -3.695,
but rank 21 is still outside the returned ten; Q15.history remains missing.
Q13.audit_update also remains incomplete. No label was relaxed to hide either.

The standalone Q15 form table (SOP parser 8) improves from rank 11 to 6.
That is a real ranking improvement, but its transaction-ID component was already
covered by a prose alternative at baseline under evidence v3. Thus this
promotion adds no new required coverage. A higher rank for one useful passage
does not necessarily improve completeness of the selected set.

For English queries targeting Vietnamese documents, the canonical VI guard is
absent from the top-30 pool for Q13 and Q15. This reranker cannot recover that
specific passage from outside its candidate pool. That is a separate limitation
from the VI→VI selection failure.

## Regression: Q01 VI → VI

The training-deck cover (parser 0), which supplies accepted approval-status
evidence, falls from rank 10 to 14; its logit changes from 0.935 to 0.546.
Registry parsers 4 and 11 enter the top ten (12→7 and 14→10); registry parser 0
also leaves (9→12). Q01.approval becomes unsupported under the fixed v3 labels,
so a previously complete answer-evidence set becomes incomplete.

The prefix changes individual relevance scores, but selection still simply
sorts query–passage scores. It does not ensure collective coverage of every
required detail. This explains the selection mechanism, not a claim that the
model has learned a particular causal preference.

## Verification and timing

- Local replay passed **all 160 condition/case rankings** and **4,800 saved
  score entries**, hashes, unchanged-pair equality, exact rendering and direction
  summaries. Evidence coverage also passed the independent character check.
- Returned runner SHA256 matches the code included in the input ZIP. Corpus,
  case, model revision and v3 label hashes match the fixed experiment.
- Original returned ZIP is preserved. Extracted results are in `colab-results/`;
  verification is regenerated there. No model/API/GPU call was used locally.
- Treatment changes top-ten order for 64/80 cases and top-ten membership for
  33/80, yet yields no required-component gain under these labels.
- Plain float32 top-ten order differs from the old GPU float16 run in two
  cases (Q11 EN→VI and Q13 EN→EN); aggregate complete/component counts match
  the documented historical v3 baseline. The paired comparison uses the new
  same-runtime control, not those historical logits.
- Recorded paired inference time is 51.51 seconds for all 80 cases. It excludes
  model download/load, preflight, evidence verification and generation, and
  combines plain inference with modified-input inference. It is neither added
  reranker latency nor end-to-end application response time.

Reproduce the local review (existing NumPy environment, no model needed):

```powershell
.venv/Scripts/python.exe -X utf8 artifacts/evaluation/colab-reranker-context-20261020/analyze_results.py
```

Machine-readable findings and diagnostic passage texts: `findings.json`.

## Decision and next possible experiment

Keep this prefix rule experimental; do not enable it in production or change
the embedding model based on it. The experiment only tested metadata prefixes
on short inputs. It does not establish whether actual parent/sentence context,
better source segmentation, or another selection method would help.

If further work is requested, a controlled parent-context experiment is a more
direct next test: give the reranker nearby source text for a short clause using
uniform, provenance-preserving rules, keep candidates and v3 labels fixed,
evaluate every direction and report regressions. If that context is also
returned to the answer model, score its actual mapped text separately rather
than silently crediting ranking-only additions. Keep no total context-token cap
as requested. Broader candidate retrieval is a separate factor and should not
be changed simultaneously. Fresh human-reviewed/held-out cases are still needed
before selecting a production configuration.

No production retrieval/index, database, labels or historical results were changed.
