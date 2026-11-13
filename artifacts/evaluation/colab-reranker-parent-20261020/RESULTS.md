# Preceding source context: verified findings

Reviewed 2026-10-20. Returned ZIP: `reranker_parent_context_results.zip`.

**Finding:** actual preceding text fixes the targeted Vietnamese Q13/Q15
omissions, but introduces a Q20 regression. It improves over metadata-only
prefixes. Against the original plain reranker, Vietnamese complete-case count
is unchanged, with different failed questions. This is promising diagnostic
evidence, not a production rollout result.

## Controlled comparison

Both new conditions ran on the same Tesla T4, PyTorch 2.11.0+cu130, float32,
batch four, with the same pinned BGE-reranker-v2-m3 revision
`953dc6f6f85a1b2dbfca4c34a2796e7dde08d41e`.
The 80 cases, 1,063 passages, E5 top-30 candidate lists, evidence-v3 labels
and final ten anchor passages are unchanged. Q14 remains unresolved and is
excluded from full-intent scoring (19 eligible intents/direction;61 ready
required components/direction).

Control: metadata prefixes on short candidates. Treatment: those same prefixes
plus the immediately preceding eligible source passage. The uniform rule uses
same document/language/location/roles and nonconflicting section metadata;
no question, answer labels or score-based context selection. It changes13
passages and69/2400 query-candidate pairs. The unchanged pair scores are reused
exactly; 2469 pairs required actual inference and4800 matrix entries were saved.

Only the original selected anchors earn evidence. Preceding text is ranking-only;
an answer present solely in an added neighbor cannot inflate character coverage.
No total context-token cap. Recorded maximum718 tokens is below the1024
per-pair model limit, with zero truncated pairs.

## Results: full evidence in top ten

| Query → documents | Original plain reranker¹ | Metadata-only control | Preceding-text treatment |
|---|---:|---:|---:|
| VI → VI | 17/19 | 16/19 | **17/19** |
| EN → EN | 14/19 | 14/19 | **15/19** |
| VI → EN | 12/19 | 12/19 | 12/19 |
| EN → VI | 12/19 | 12/19 | 12/19 |

¹ Original plain result is historical, from the previous Colab experiment.
The primary causal comparison is the new same-runtime metadata vs parent
comparison. The rerun metadata-control top-ten orders and full evidence objects
match all80 cases from the previous metadata run exactly, despite T4 vs A100.

| Query → documents | Metadata components | Preceding-text components |
|---|---:|---:|
| VI → VI | 58/61 | **59/61** |
| EN → EN | 55/61 | **56/61** |
| VI → EN | 46/61 | **47/61** |
| EN → VI | 49/61 | 49/61 |

## Q13 and Q15: targeted omissions fixed

| VI → VI | Metadata guard rank | Parent guard rank | Component coverage |
|---|---:|---:|---|
| Q13: complete count/adjustment process | 21 | **5** | 8/9 → **9/9** |
| Q15: minimum adjustment transaction records | 21 | **1** | 3/4 → **4/4** |

The short SOP parser4 guard explicitly prohibits deleting old transactions or
directly editing source files. It now receives SOP parser3 as preceding context,
which discusses the update workflow and required adjustment fields. The guard's
own unchanged text enters the final ten, satisfying Q13.audit_update and
Q15.history under frozen v3 labels. This is a selection improvement, not a label
change or credit awarded for the neighbor.

For Q13 EN→EN the preparation/count passage (English SOP parser2) moves23→4;
Q13.freeze becomes covered, improving8/9→9/9. For Q13 VI→EN the same passage
moves23→10, improving2/9→3/9, but the intent still lacks other required details.

The canonical VI guard remains absent from the top30 for Q13/Q15 EN→VI. This
experiment cannot select that absent candidate; broader retrieval is separate.

## Regression: Q20 VI → VI

Workbook parser434 (KPI Summary with PO/inventory-position notes) moves13→6.
The manual's replenishment-policy parser5 is consequently pushed10→11 despite
its unchanged logit. That manual passage lists available stock, open PO, held
stock, backorder, MOQ, budget and delivery-schedule checks before issuing a PO.
Its exclusion causes Q20.proposal_checks to go from met to missed.

This shows the fixed-top10 selection trade-off: context can make a related
summary score higher and displace a passage containing a necessary checklist.
Independent query-passage relevance sorting does not guarantee complete coverage
of all answer requirements.

Relative to metadata control: complete gains Q13 VI→VI, Q15 VI→VI and Q13 EN→EN;
complete loss Q20 VI→VI. Additional partial gain Q13.freeze VI→EN.
Those are the only changed required-ready components across all80 cases.

Relative to original plain reranking, VI→VI now fails **Q01 and Q20** instead
of **Q13 and Q15**. Q01's approval-status regression from the earlier metadata
prefix experiment remains unresolved. Do not describe17/19 as an improvement
over the original plain17/19 or claim that the original regression was cured.

## Verification

- Local replay passed all160 case/condition rankings,4800 matrix entries,
  finite score checks, exact input rendering, unchanged-pair equality, original
  input/vector/label hashes, independent stable sorting and character coverage.
- Returned runner SHA256 matches the supplied parent-input ZIP. Config explicitly
  records `context_mode=parent` and `control_mode=metadata`. The legacy JSON
  `plain_*` keys mean metadata control in this run.
- Treatment changes top-ten order in42/80 cases and membership in29/80.
- Original returned ZIP is preserved; extracted files and regenerated audit are
  in `colab-results/`. `findings.json` contains per-component changes, all Q13/Q15
  directions and diagnostic source texts/ranks/logits.
- Paired inference time168.57seconds excludes download/load, preflight,
  verification and generation. It combines both arms and is not added reranker
  latency or end-to-end response time. Do not compare with the earlier A100's
  runtime as a controlled context-overhead comparison.
- No model download, GPU inference, API call or database access was needed for
  this local results review. No production retrieval, labels or index changed.

Reproduce the saved-result review:

```powershell
.venv/Scripts/python.exe -X utf8 artifacts/evaluation/colab-reranker-context-20261020/analyze_results.py --parent-context
```

## Decision

Keep this experiment and the demonstrated Q13/Q15 fixes. Do not enable the
combined prefix/parent rule globally yet. The controlled evidence supports the
claim that this predecessor rule helps these short clauses; it does not prove
all short chunks need context or that labels/answers are independently correct.
This is a repeatedly inspected, assistant-annotated20-intent set, not held-out
validation or generated-answer evaluation.

A useful next step, if requested, is to isolate **parent text without metadata
prefixes** against the original plain reranker, keeping the same predecessor
mapping, pools and v3 labels. That tests whether the useful Q13/Q15 effect can
survive without the metadata behavior that lost Q01. Q20 remains a genuine
selection regression to inspect, not a label to weaken automatically. Evaluate
gains AND losses across all directions and seek held-out human-reviewed evidence
before adopting a production policy.
