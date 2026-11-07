# Narrative context policy: Q20 recovery

Completed 2026-10-20. This is an offline replay of saved model scores, not new inference or a production rollout.

## Diagnosis and change

Preceding context raised the Q20 Vietnamese KPI table fragment (workbook parser chunk434) from rank13 to6. This pushed the manual's required pre-purchase-order checklist (parser chunk5) from rank10 to11, outside the final ten passages.

The new general policy keeps structured table candidates as their original text and adds preceding source context only to non-table candidates. Table detection uses element_type, layout_type, chunking_method, or table_index metadata. It contains no question IDs, filename exceptions, label checks, or score adjustments. Existing adjacency, location, section, and access-role checks still apply to narrative context.

## Results

Full required evidence in the final ten original chunks:

| Query -> document | Original plain | Previous parent plain | Narrative policy | Required components |
|---|---:|---:|---:|---:|
| Vietnamese -> Vietnamese | 17/19 | 18/19 | **19/19** | **61/61** |
| English -> English | 14/19 | 15/19 | 15/19 | 56/61 |
| Vietnamese -> English | 12/19 | 12/19 | 12/19 | 47/61 |
| English -> Vietnamese | 12/19 | 12/19 | 12/19 | 49/61 |

Q20 Vietnamese proposal_checks is recovered; all five required Q20 components are present. Q13 retains its audit-update clause at rank5 (9/9 components), and Q15 retains its history clause at rank1 (4/4). No required component regresses across the 80 cases relative to the preceding-context variant. See changes-vs-parent.json for the complete component delta.

Q14 remains unresolved and excluded from the full-success denominator; its ready components still participate in component coverage.

## Verification and provenance

- Same frozen 1,063 passages, 80 cases, evidence v3 labels, E5 top30 candidate pools, and final10 selection.
- Same pinned BAAI/bge-reranker-v2-m3 revision 953dc6f6f85a1b2dbfca4c34a2796e7dde08d41e; saved float32 scores from the paired Colab T4 experiment.
- Every chosen input matches an already scored original or predecessor input exactly. Each chosen logit is checked against its matching source input. 51 table-context pairs fall back to plain; 18 narrative pairs retain context.
- Matching input bundle and runner hash verified. All 160 control/policy rankings and 4,800 saved score entries verified, including independent character-level evidence checks and rendering/input hashes. These counts are verification work, not fresh model predictions.
- No model download, API call, new embeddings, changed labels, or GPU run. No total context-token cap; source pair bound1024, source preflight maximum686 tokens, no truncation.
- score-lineage.json records original and derived hashes; verification.json records replay checks. Reproduction script: scripts/retrieval/evaluate_narrative_context.py. Shared rendering mode: narrative-parent.

## Limits and next work

This rule was selected after inspecting this small benchmark. The result is diagnostic and needs fresh human-reviewed held-out cases before generalizing. Evidence coverage is not generated-answer accuracy. The experiment renderer is implemented; production retrieval has not been integrated or deployed. Changes remain local and uncommitted.
