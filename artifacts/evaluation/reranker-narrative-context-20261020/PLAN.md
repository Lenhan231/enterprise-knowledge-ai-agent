# Table-aware preceding-context experiment

Recorded before scoring the new policy, 2026-10-20.

## Hypothesis and fixed policy

Q20's observed regression occurs when preceding context raises the score of
an XLSX KPI row group, displacing an unchanged manual checklist from10→11.
The preceding-context experiment helped short narrative instructions in Q13
and Q15. Test whether preserving the original inputs for structured tables
retains the narrative gains and avoids that table promotion.

One fixed rule: if metadata declares element_type=table, layout_type=table,
chunking_method=table_row_groups or a non-null table_index, use the plain
original passage. Otherwise use the existing plain+predecessor renderer, with
its unchanged size, document, language, location, role and section checks.
No question IDs, document-name exceptions, labels, score thresholds or new
fusion weights participate in this rule. No parameter sweep is planned.

Keep v3 labels, all80 cases, same E5 top30, final10, reranker revision and saved
same-runtime float32 scores. No total context-token cap. The treatment chooses
between two exact inputs already scored by the last Colab experiment; reuse
those raw logits instead of doing another model/API/GPU run. Every reused
input must match deterministic rendering. Evaluate full-intent and required
component coverage for all four directions and report all regressions.

This is a post-hoc selection-policy test on the repeatedly inspected20-intent
dataset, not independent held-out evaluation. Do not alter labels to fix Q20
and do not enable a production policy based only on this result.
