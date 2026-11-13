# Assistant review of fresh questions

Reviewed 2026-10-21 against Huy commit 279be53. Status: assistant-reviewed, awaiting human decisions. No model inference, retrieval rankings, or new benchmark scores were used for this review. The corpus and all four draft file hashes match the manifest only after reconstructing CRLF bytes: the laptop hashed Windows line endings, whereas Git stores LF. Direct byte verification on WSL fails. Record canonical LF hashes in a NEW reviewed manifest before benchmarking; do not alter frozen chunk content or historical hashes. All 24 labelled quotes match their content hashes, offsets and language; all 48 cases link to the proper target-language evidence. This checks the frozen parsed corpus, not a new visual audit of original PDFs/Office files.

## Overall assessment

All 12 bilingual intents have answer support in the frozen corpus; no question/translation pair reverses the intended meaning. That does not make the draft ready to score. Missing equivalent passages, overly broad evidence spans, unresolved source-role differences and question overlap need attention. English counterparts are simulated translations, not independently authored validation data.

The original cases, labels, manifest and human review.csv are unchanged. This folder contains proposals only. evidence-proposals.json is deliberately NOT a replacement evaluator input: it uses indexed-chunk offsets, needs component decomposition, human confirmation, a new manifest and the planned adapter. Never pass it straight to evidence-v3 scoring.

## Per-intent findings

| Intent | Recommendation | Original-set relationship | Required answer / finding |
|---|---|---|---|
| F01 | Keep | No direct original equivalent | Record before confirming receipt; require photos AND an incident report. Receiving exceptions differ from Q04/Q16 customer returns. |
| F02 | Add alternative | Related Q06, different post-campaign task | Manual and Training Deck 6 both support the answer. Require sell-through, remaining stock, and return rate. Accept supported extra return reasons/forecast-error details. |
| F03 | Keep | Related Q20 PO governance; different record fields | Require reason, service impact, and approver. Do not turn this into a question about permission to issue a PO. |
| F04 | Clarify age wording | Related Q07, new 240-day threshold | Use days of supply explicitly, rather than implying physical SKU age. Require Inventory Manager AND Finance; assessment of write-down/disposal, not automatic disposal. |
| F05 | Add alternative | Related Q08/Q19 limitations; new demand rule | Accept Workbook README 0 as well as Manual appendix. Require up to three MOST RECENT AVAILABLE snapshots PER SKU; months need not be consecutive. |
| F06 | Narrow evidence; confirm audience | No direct original equivalent | Keep only the second sentence. Require policy_id, owner, trigger, action, SLA, approval. SOP metadata list is DIFFERENT and is not equivalent. This is a system-builder question; decide whether representative of intended users. |
| F07 | Narrow evidence; overlap flag | Strong subtask overlap Q13 | Only the Warehouse Supervisor/blind-count sentence is needed. Require supervisor assignment AND no access to system quantities during blind count. Deck blind-count mention alone is incomplete. |
| F08 | Narrow evidence; overlap flag | Strong subtask overlap Q13 | Only the count-by-variant sentence is needed. Require SKU, size, color, location AND no merging similar variants. The draft EN excerpt ends mid-next sentence, but the required answer sentence is complete. |
| F09 | Qualify source before use | Strong overlap Q14; unresolved source-role variation | Explicitly ask according to the Manual approval table. That row says Warehouse Supervisor, within one business day, with counter/data-entry separation. SOP uses Inventory Controller / Supervisor. Do not silently treat either role as universally correct. |
| F10 | Keep; preserve authority limitation | Related Q16 disposal; new approval chain | Require QA AND Inventory Manager AND Finance, subject to financial authority. Do not invent a monetary threshold or delegated authority absent from the documents. |
| F11 | Keep as overlap extension | Strong overlap Q03 plus new investigation SLA | Require next approximately 15% of annual consumption value, monthly counts, investigation within two business days. Deck/registry alone lack the investigation SLA; they are only partial evidence. |
| F12 | Add duplicate-table alternative; overlap flag | Strong overlap Q13/Q14 | Already scoped to SOP. Require hold related transactions, investigate root cause, Inventory Manager AND Finance. Accept SOP text chunk3 OR extracted table VI7/EN6. Manual approval row differs and is not equivalent. |

## Concrete corrections proposed

1. F02: add Training Deck chunk6 in each language as an alternative to the Manual. It contains the same three outcomes plus forecast error/corrective action. Extra supported detail should not cause a failure.
2. F05: add Workbook README chunk0 in each language. The question refers to the workbook, yet the draft labels only the Manual; excluding the workbook would penalize a correct retrieval.
3. F06/F07/F08: narrow the label to the actual answer sentence. F07 currently labels about a full page, including unrelated scope, triggers and preparation. F08 includes unrelated freeze/recount text and an incomplete subsequent EN sentence. No answer information needs adding, only a more precise evidence definition.
4. F09: qualify BOTH languages as a manual-table question. Suggested VI: "Theo bảng phê duyệt trong Inventory Management Policy Manual, ai duyệt điều chỉnh tồn nhỏ có đủ bằng chứng và thời hạn xử lý là bao lâu?" Suggested EN: "According to the Inventory Management Policy Manual approval table, who approves a small inventory adjustment with sufficient evidence, and what is the processing deadline?" Use Supervisor and one business day for that explicitly scoped question. If kept corpus-wide, approval-role reconciliation is still unresolved; exclude it from full success until humans settle it.
5. F12: add VI SOP chunk7 / EN SOP chunk6 as alternatives to PDF body chunk3. These are two extractions of the same table, not two required sources. Preserve the line breaks in exact offsets; do not invent parser coordinates.
6. F04: clarify VI to "Với SKU có days of supply trên 240 ngày, ai cần đánh giá và xem xét những phương án nào theo quy định kế toán?" and EN to "For a SKU with more than 240 days of supply, who assesses it and which accounting actions are considered?" This avoids confusing stock coverage with physical age. Confirm this intended interpretation in the source section.
7. Define component labels from each question before scoring. F01 needs timing + photos + report, F03 three recorded fields, F07 assignment + blindness, F08 identifiers + no merging, F11 share + frequency + SLA. A single large excerpt is not an adequate component specification. Keep alternative evidence as OR bundles, required details as AND. Record partial equivalents (e.g. deck ABC schedule without SLA) only for components they support.

## Human decisions needed

- Accept the explicit Manual scope for F09, and confirm F04 refers to days of supply. No business approval-role policy is being changed.
- Keep F07/F08/F09/F11/F12 as focused regression/extension tests, or replace some with independently authored questions for a stronger novelty claim. F11 extends Q03 with SLA; counting and approvals are already covered broadly by Q13/Q14. Remaining seven have distinct requested details but still come from familiar topics and documents.
- Keep F06 if developer-facing RAG questions are in scope; otherwise replace it with an operational inventory question.
- Confirm the proposed source alternatives and required details. Team-authored additional questions should be labelled before any scores are inspected.

## Limits and next action

Eight narrative, three structured-table and one mixed-PDF intent remain the draft categories. These categories do not isolate the actual input rule: F05 also has a workbook-table alternative, and F12 has both PDF-body and structured-table extractions. F09 and F10 share one approval-table anchor. Report category results descriptively; they are small and correlated. There is still no workbook numeric/data-row question; F05's README alternative is not a numeric workbook test.

This is a fresh assistant-authored extension on familiar documents, not an independent held-out evaluation. Do not claim 48 independent questions: there are 12 paired intents, 24 texts and 48 language-direction cases. Only after human decisions should we freeze revised questions/components/alternatives and build a compatible evaluator, embed new queries and freeze E5 top30 pools. Then compare plain, parent-plain and narrative-parent with the same pinned reranker on the same GPU. Old-question logits cannot be reused. Report candidate-pool availability separately from final10 selection and generation correctness separately from retrieval.

Files: assistant-review.csv (24 assistant checklists, no human sign-off), evidence-proposals.json (24 primary + 6 alternative exact spans), verification.json (mechanical checks). Corpus-wide lexical inspection was followed by source-context review; alternative discovery is not guaranteed exhaustive.
