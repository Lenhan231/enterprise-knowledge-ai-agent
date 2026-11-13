# VietStyle bilingual evidence labels v1

Created 2026-10-19. Evaluation-only annotations for the existing 20 VietStyle intents in Vietnamese and English. No retrieval/model/generation run, production change, or database access. Questions, reference answers, source corpora, and historical benchmark results were not edited.

## What is included

- 20 paired intents / 40 language versions.
- 65 answer components shared across the two languages: 62 required and ready, 2 required but pending policy clarification, 1 optional context component.
- 184 exact source spans: 92 Vietnamese and 92 English. Alternative evidence can come from the manual, SOP, policy CSV, workbook README sheet, or slides.
- 19 fully labelled, unambiguous intents; Q14 has usable separation-of-duties evidence but 2 approval-role components pending clarification.
- Frozen source/question/provenance hashes, source document IDs, parser indexes, source text hashes, Unicode character offsets, exact quotations and source location metadata. These are source anchors, not final retrieval chunk IDs.

Files:

- `evidence.json`: machine-readable labels and complete alternatives.
- `REVIEW.md`: each question and answer component, with canonical Vietnamese/English quotations and conflicting role lists.
- `validation.json`: mechanical checks and coverage counts.

Annotations were curated by the assistant from the source text and checked mechanically. This is not independent human semantic certification; known alternatives are not guaranteed exhaustive. New valid evidence should trigger review and a new label version, not be automatically declared a retrieval error.

## How these labels differ from the old benchmarks

A matching file/page is no longer enough. A requirement is supported only by its answer-bearing content and needed context. For example, Q02 needs the role and responsibilities in the Inventory Manager row, not the title of the manual. Q05 separates six KPIs, including PO adherence (explicit in the policy registry). Q06 distinguishes campaign timing, forecast dimensions, logistics, campaign conditions and approval.

The intended scoring contract is AND across required ready components, OR across alternative bundles, and AND across all spans in an `all_of` bundle. A bundle may need context from multiple retrieved chunks. Optional context is not required for success. This task does not implement the retrieval-to-span mapper or scorer; those are the next benchmark preparation step.

Report ready-component coverage separately from complete-intent success. Do not silently count pending components as passed or failed. A complete-intent score can use the 19 resolved intents, with Q14 and the exclusion explicitly reported; Q14's unambiguous separation-of-duties component can still be assessed separately. The 62 ready required components include that Q14 component.

Old expected-file labels, including missing README.txt, are unchanged in the historical datasets. For this different fact-coverage metric, an unavailable file is not required when another available source supplies the necessary evidence. The workbook's README worksheet is a real source; it is not the missing standalone README.txt.

## Two special case types

**Calculations, Q09/Q10:** scenario numbers such as demand 10 or on-hand 120/open PO 40/backorder 25 are supplied by the question. Retrieve the formulas and, for Q09, the default assumptions 14/7/7. Results 210, 280 and 135 are derived and checked arithmetically; they do not have to occur in a source passage. A coincidental matching number elsewhere is not evidence.

**Unavailable data, Q18:** the workbook's default zeros are placeholders, not confirmed PO/backorder quantities for hypothetical SKU X. The evidence explicitly states the inputs are unavailable and must be entered. This is an abstention/data-availability question, not a zero-valued inventory lookup.

## Q14: do not force inconsistent approval roles into one answer

- SOP small-adjustment text: Inventory Controller / Supervisor. Manual row 3: Warehouse Supervisor. These role lists overlap but are not identical; no unique approver should be imposed without clarifying the intended policy.
- SOP large/recurring-adjustment text: Inventory Manager + Finance. Manual row 4: Inventory Controller + Finance / Operations.
- Both languages inherit the same variation; this is not a new English translation error.
- Exact excerpts from both documents are retained. The two affected components are marked `needs_policy_resolution`. The clear rule that counter, data-entry person and approver must be separate remains ready.

## Validation performed

The validator checks exact source/question/provenance SHA256 hashes; every quote and Unicode character range; source document identity and page/slide/sheet metadata; both-language evidence for every component; unique intent/component/span IDs and complete references; readiness/optional/conflict status; and the calculation examples. Its self-check confirms that a tampered quotation and a wrong-language source are rejected.

```bash
.venv/bin/python scripts/retrieval/validate_vietstyle_evidence.py --self-check
```

Only Python's standard library is required. The command regenerates REVIEW.md and validation.json, not evidence.json or the corpora. Exact frozen-byte hashes are intentional; a Windows checkout with automatic CRLF conversion needs LF-preserving checkout handling rather than silently weakening hashes.

## Next use

Before a model run, build or verify a mapping from bounded retrieval chunks back to these source spans (including split/overlapping fragments). Preserve source identity and required row/actor/formula context; do not reuse historical final chunk IDs after rechunking. Then score all four language directions against the target-language evidence, using the same question intents. The Vietnamese-only direction remains the team's main objective; cross-language results are a separate local experiment.

NEVER index evidence.json, this review, question files or reference answers as retrieval documents. Encoders receive passage text and the question only, not the gold labels. Do not use the gold evidence to choose document scope, rank candidates, or construct query translations.

## Per-intent readiness

| Intent | Ready required components | Pending | Optional | Fully ready |
| --- | ---: | ---: | ---: | --- |
| Q01 | 2 | 0 | 0 | yes |
| Q02 | 1 | 0 | 0 | yes |
| Q03 | 4 | 0 | 0 | yes |
| Q04 | 2 | 0 | 0 | yes |
| Q05 | 6 | 0 | 0 | yes |
| Q06 | 4 | 0 | 0 | yes |
| Q07 | 2 | 0 | 0 | yes |
| Q08 | 2 | 0 | 0 | yes |
| Q09 | 3 | 0 | 0 | yes |
| Q10 | 1 | 0 | 0 | yes |
| Q11 | 3 | 0 | 0 | yes |
| Q12 | 3 | 0 | 0 | yes |
| Q13 | 9 | 0 | 0 | yes |
| Q14 | 1 | 2 | 0 | no |
| Q15 | 4 | 0 | 0 | yes |
| Q16 | 4 | 0 | 0 | yes |
| Q17 | 3 | 0 | 0 | yes |
| Q18 | 2 | 0 | 0 | yes |
| Q19 | 1 | 0 | 1 | yes |
| Q20 | 5 | 0 | 0 | yes |
