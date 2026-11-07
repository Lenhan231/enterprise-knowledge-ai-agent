# Plain reranking plus preceding source text: verified results

Reviewed 2026-10-20. Input: `reranker_parent_plain_results.zip`.

**Finding:** the predecessor-only input preserves the Q13/Q15 fixes without
the metadata-prefix Q01 regression. Vietnamese complete-evidence cases improve
17→18/19 and English same-language cases14→15/19. Q20 still regresses. This is
the strongest complete-case profile among the tested reranker input variants
for this E5 candidate pipeline, not proof of general superiority or production
readiness.

## Fixed experiment

Both arms ran on the same Colab Tesla T4, PyTorch2.11.0+cu130, float32, batch4.
Same pinned BGE-reranker-v2-m3 revision
`953dc6f6f85a1b2dbfca4c34a2796e7dde08d41e`, 80 cases/20 paired intents,1,063
passages, E5 top30 candidates, evidence v3 and final top10. No model/vector,
label, candidate pool, translation or generation changes.

- Control: exact plain original passages.
- Treatment: identical original anchor plus the same eligible preceding source
  passage used in experiment2, without added filename/section/table prefixes.
  Native headings in the original source text are preserved.
- The rule adds context to13 passages/69 candidate-query pairs. It uses fixed
  document/language/location/ACL/section checks, never questions or labels.
- Preceding text is used only for relevance scoring. Only original selected
  anchors earn evidence coverage, with unchanged exact character provenance.
- No total context-token cap. Recorded maximum686 tokens is below the1024
  per-pair input limit, with zero truncation reported by Colab preflight.

## Full required evidence within top10

Each direction has19 eligible intents. Q14 remains unresolved and excluded from
full-intent success;61 required ready components are evaluated per direction.

| Query → documents | Plain control | Plain + preceding text | Required components: control → treatment |
|---|---:|---:|---:|
| VI → VI | 17/19 | **18/19** | 59→60/61 |
| EN → EN | 14/19 | **15/19** | 55→56/61 |
| VI → EN | 12/19 | 12/19 | 46→47/61 |
| EN → VI | 12/19 | 12/19 | 49→49/61 |

Required component gains: Q13.audit_update VI→VI, Q15.history VI→VI and
Q13.freeze in VI→EN and EN→EN. Sole component loss: Q20.proposal_checks VI→VI.
This yields3 newly complete direction/intents and1 newly incomplete one, but
directions reuse paired intents and must not be treated as independent samples.

## The four questions requested for inspection

### Q01 VI → VI: stays complete

The original approval-status evidence remains available in the selected ten.
Neither component coverage nor full success regresses. This avoids the loss
seen when adding metadata prefixes. It is preservation of the plain baseline,
not a newly recovered fact in this same-runtime comparison.

### Q13 VI → VI: fixed

The explicit no-delete/no-direct-source-edit guard (SOP parser4) moves from
rank21 to5. Required coverage improves8/9→9/9; Q13.audit_update is now met.
The underlying original guard text, not merely the added neighbor, is selected.
Its raw relevance logit changes-4.594→-0.954.

### Q15 VI → VI: fixed

The same guard moves27→1, logit-5.027→1.754. Required coverage improves3/4→4/4;
Q15.history is now met. The form/transaction-ID alternative remains governed
by frozen v3 labels; no annotation was added to obtain this improvement.

### Q20 VI → VI: remains a regression

Workbook KPI Summary parser434 is promoted13→6 (logit-3.742→-0.972).
The manual's replenishment-policy parser5 falls10→11, despite its unchanged
logit-2.515. That passage supplies the explicit pre-PO checklist: available
stock, open PO, held stock, backorder, MOQ, budget and delivery schedule.
Its exclusion makes Q20.proposal_checks incomplete under the existing labels.

The scoring of contextualized candidates improved their ranks but the fixed
top-ten selection displaced an answer-bearing checklist. This is a concrete
selection trade-off to investigate. It is not justification for weakening the
labels or hardcoding Q20's document into retrieval.

## Across the three completed experiments

| Input variant | VI → VI | EN → EN | VI → EN | EN → VI |
|---|---:|---:|---:|---:|
| Plain reranker | 17/19 | 14/19 | 12/19 | 12/19 |
| Metadata prefixes | 16/19 | 14/19 | 12/19 | 12/19 |
| Metadata + preceding text | 17/19 | 15/19 | 12/19 | 12/19 |
| Plain + preceding text | **18/19** | **15/19** | 12/19 | 12/19 |

The new plain-control top-ten orders AND full evidence objects match all80
cases from the earlier plain FP32 Colab run. The primary causal comparison
remains the two conditions paired within this new run. Comparing separate
experiments alone would also involve GPU/runtime differences.

Remaining incomplete intents under the treatment:

- VI→VI: Q20.
- EN→EN: Q01,Q11,Q12,Q20.
- VI→EN: Q01,Q04,Q08,Q11,Q12,Q13,Q20.
- EN→VI: Q01,Q08,Q11,Q12,Q13,Q15,Q20.

Q13 EN→EN becomes complete because the preparation/count passage (English SOP
parser2) moves27→4 and supplies Q13.freeze. In VI→EN it moves28→7, improving
Q13 from2/9 to3/9 components but leaving other gaps. The canonical VI guard is
still absent from the top30 for Q13/Q15 EN→VI; reranking cannot select it from
outside its pool. This remains distinct from the VI→VI top10 selection issue.

## Verification and limits

Local replay passed all160 case/condition rankings and4800 saved score entries,
finite values, strict input/vector/label hashes, runner SHA256 against the
uploaded bundle, deterministic context rendering, unchanged-pair equality,
direction summaries and independent character coverage. It reads the matching
bundle's canonical inputs, so review is not tied to the checkout's current HEAD.
Original returned ZIP remains preserved; extracted artifacts and regenerated
verification are in `colab-results/`. Detailed changes are in `findings.json`.

There are2400 control pairs plus69 changed treatment pairs requiring actual
inference; the other treatment entries reuse identical control scores. Treatment
changes top-ten order in38/80 cases and membership in26/80. Recorded paired
inference time166.997seconds excludes download/load, preflight, verification,
dense retrieval and generation. It is not per-query added latency or an
end-to-end app measurement. No local model download/inference was performed.

This is a repeatedly inspected, assistant-annotated20-intent benchmark, not
independent held-out evaluation. Labels remain non-exhaustive. These results
measure required retrieved evidence rather than generated answer accuracy.

Reproduce review:

```powershell
.venv/Scripts/python.exe -X utf8 artifacts/evaluation/colab-reranker-context-20261020/analyze_results.py --parent-plain
```

## Decision

Retain plain+preceding-text as the most promising input variant from these
experiments. Do not globally deploy it yet: Q20 is a real loss and the held-out
evidence requirement remains unmet. The experiment supports surrounding source
text helping these particular short clauses; it does not establish that every
short passage should be expanded.

If further work is authorized, inspect Q20's final selection and whether context-
dependent scores should select/return a mapped source unit rather than only
the anchor. Any returned neighbor must have real source provenance and be
scored as actual returned evidence; ranking-only context must not silently earn
coverage. Evaluate the same frozen labels, all directions, and gains/losses,
then obtain fresh human-reviewed cases. Keep candidate retrieval and new model
comparisons as separate experiments. No production change was made here.
