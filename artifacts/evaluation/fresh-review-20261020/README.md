# Fresh question draft for reranker validation

## Prepared

24 question texts (12 bilingual paired intents), expanded into 48 directional cases. Categories per intent: eight narrative, three structured-table, one mixed-PDF. Both languages use the existing frozen 1,063-chunk corpus. No original questions, labels, chunks, or model settings were changed. No retrieval outputs were consulted to author these new questions.

This is a source-grounded assistant draft, not an independently held-out benchmark. The assistant already inspected the documents and previous experiments. Some intents overlap broader original questions (especially counting and approvals); a reviewer must check novelty and add independently authored intents. Twelve paired intents are not 24 independent intents.

## Review first

1. Read REVIEW.md for each question and its exact supporting excerpt.
2. In review.csv, confirm support, translation, all required details, alternative valid source passages, and distinction from the original questions. Record reviewer and corrections; approve only after these checks.
3. Add team-authored questions where possible. Do not inspect new reranker scores while labeling. Include workbook-specific table questions in a later expansion; this draft's structured tables are in the manual, not the workbook.
4. Evidence currently identifies one supporting excerpt, not an exhaustive list of valid alternatives. Add equivalents before scoring to avoid penalizing another correct section. Mixed PDF text may duplicate separately extracted tables.
5. Freeze reviewed questions and labels as a new version with fresh hashes. Keep this draft and the original benchmark intact.

## Comparison protocol

- Embed the reviewed questions with exactly the existing E5 model/revision and preprocessing. Reuse saved document vectors after checking corpus/vector alignment; do not rechunk or re-embed documents unnecessarily.
- Freeze one top30 candidate pool for each case using the same target-language and access filters.
- Score all three variants with the pinned BGE reranker on the same Colab GPU, float32: plain, parent-plain, narrative-parent. No metadata-prefix variant in this comparison.
- Save logits, rendered inputs, model/software versions, hashes, pair lengths, truncation checks and timings. Never select labels or candidate pools using reranker results.
- Evaluate the final ten original anchor chunks. Extra preceding context cannot earn evidence coverage. Report candidate30 evidence recall separately: a missing candidate cannot be repaired by reranking.
- Report full evidence and required-component coverage per direction and category, paired gains/losses, ranks of required passages, and review every regression. Do not claim significance from twelve paired intents.
- Review generated answers/citations and latency separately before production integration. Do not change the rule while reporting this set as held-out; any tuning makes it a development set.

## Files and current execution state

- cases.json: questions and four-direction cases.
- evidence-draft.json: exact Unicode offsets within indexed chunk content, content hashes and review status. These offsets are NOT source-parser offsets; this file cannot be passed directly to the existing evidence-v3 evaluator.
- REVIEW.md: readable question/evidence packet.
- review.csv: editable review checklist, UTF-8 with BOM for Excel.
- manifest.json: initial draft/source hashes. Human review edits intentionally require a new reviewed manifest.
- scripts/retrieval/prepare_fresh_review_set.py: source-grounded builder; refuses to overwrite existing review work.

No new inference or model download was run. Previous saved scores belong to different questions and cannot be reused for these cases. After review, the remaining work is adapting the existing Colab runner to these cases and chunk-offset labels, preparing/fixing candidate pools, then obtaining a user-run GPU result. Do not interpret this draft as completed validation.
