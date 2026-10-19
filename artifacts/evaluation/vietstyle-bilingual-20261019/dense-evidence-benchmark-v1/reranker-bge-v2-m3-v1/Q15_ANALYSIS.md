# Q15: reported reranker regression versus actual context

## Main finding

The official evidence-v2 score drops from4/4 to2/4 components, but one of the two reported losses is an annotation gap. The transaction ID is still explicitly present in reranked chunk4. The more substantive omission is the explicit instruction not to delete old transactions or directly edit source files, whose canonical chunk drops from dense7 to reranker27.

This corrects the earlier summary that both pieces of information disappeared from the final context. The accepted source positions disappeared, but the transaction-ID fact survives in a duplicated parser representation. No labels, vectors, rankings or published scores were changed by this review. Complete-intent failure would remain even if the transaction-ID alternative were accepted, because the explicit history guard is still absent.

## Question and expected content

Original question: “Những trường thông tin tối thiểu nào phải lưu cho một giao dịch điều chỉnh tồn kho?”

English meaning: “What minimum information fields must be retained for an inventory adjustment transaction?”

The reference includes ticket/policy/SKU/before-after/reason/evidence/entry person/approver, timestamp/counter, adjustment transaction ID, and the no-deletion/direct-source-edit control. Evidence-v2 divides these into4 required components.

| Component | Dense rank of accepted source | Reranked rank | What the final context actually contains |
|---|---:|---:|---|
| Q15.core_fields | 1 | 1 | Complete core field list retained |
| Q15.timestamp_counter | 3 | 4 | Timestamp and counter retained |
| Q15.transaction_id | 9 | 11 | Canonical table excluded, but identical transaction-ID meaning remains in another chunk at rank4 |
| Q15.history | 7 | 27 | Explicit no-delete/no-direct-source-edit instruction excluded; related no-overwrite wording remains at rank9 |

## Transaction ID: confirmed annotation gap

The accepted label only points to SOP parser index8, the separately extracted form table:

> Field: Adjustment Transaction ID | Nội dung: Mã giao dịch điều chỉnh sau duyệt

This source moves from dense9 to reranker11 (raw relevance logit -2.76171875), just outside top10.

However SOP parser index5 is reranker4 and includes this exact text:

> Adjustment Transaction ID Mã giao dịch điều chỉnh sau duyệt

It is the same form content duplicated in the PDF prose extraction, not a guess by the answer model. In the frozen parser text, the alternative is at Unicode interval[888,947), SHA2560d5cac2f0b776b6f06967e82a2394d69068a5fca6178a7d9c1ec1b029897e609. The containing chunk also discusses records retention, transaction IDs and synchronization timestamps.

The scorer correctly follows its registered alternatives, but evidence-v2 has not registered this equivalent source span for Q15.transaction_id. Therefore “the final context lost the transaction ID” is too strong; “the accepted table occurrence fell outside top10” is accurate. A future label revision should review this duplicate occurrence consistently in both languages and for every candidate model. Do not change old scores silently.

## History control: a real explicit-detail omission

SOP parser index4 contains:

> Không xóa giao dịch cũ hoặc sửa trực tiếp file nguồn; dùng giao dịch điều chỉnh có thể truy vết.

It is dense7 but reranker27 (raw logit -5.02734375). The model assigns much lower relevance than to general workflow or policy material. This is a142-character chunk including its existing section heading, so it is neither lost from the corpus nor truncated at inference.

There is related text at reranker9 in INV-POL-001:

> Lưu người thao tác, thời điểm, giá trị trước/sau và lý do; không ghi đè lịch sử

That provides useful history/audit context, but it does not explicitly cover both prohibitions in the current reference: deleting old transactions and directly editing source files. Do not automatically declare this component complete from partial overlap. The independent reranker score is not itself a proof that a mandatory instruction is unnecessary.

The question's surface wording asks for fields; the source/reference additionally include a history-preservation control. That distinction may contribute to low query-passage relevance. Whether this control should be mandatory in the evaluation is a semantic rubric decision, not something to relax merely because this model ranks it poorly. The current review retains it.

## What replaced the excluded chunks?

The reranker promotes these formerly lower-ranked candidates into top10:

- SOP index0: cover and overall procedure outline, dense28→reranker3.
- CSV index11: AI authorization/citation rules, dense14→reranker5.
- Manual index2: overall principles and auditability, dense15→reranker7.
- Deck index7: data cleanliness and automation guidance, dense26→reranker10.

Some promoted chunks contain useful related material; others are less direct than the minimal adjustment form. For example, the clean-data slide gets logit -2.681640625 at rank10, narrowly above the form at -2.76171875 at rank11. These are raw scores, not calibrated probabilities; the gap is not an8% confidence statement.

The CrossEncoder assigns query–chunk relevance independently. The current selection simply sorts those scores; it has no rule requiring the selected10 to collectively cover all mandatory fields/controls, and it does not use evidence labels during selection. More generally related chunks can occupy slots while a short but necessary clause is omitted.

## Chunk/context observation and limits

The standalone form table begins with “Columns: Field | Nội dung” and has no section_title metadata. The joint reranker input is only question+chunk text; it does not prepend document filename or inherit the parent form caption. The prose version contains “Biểu mẫu tối thiểu” and more surrounding context and ranks4.

That is consistent with insufficient context contributing to the standalone table's ranking, but we have not run a controlled context-prefix ablation, so it is not a proven cause. The guard chunk already has a section heading, so a title-prefix fix alone is not established for that case either.

## Recommended next action

1. Record the transaction-ID duplicate as a candidate label alternative; review the corresponding English source and all models before any new version/rescore.
2. Keep the history-control omission visible. Inspect how source/section context and selected parent context affect these short chunks in an isolated experiment; do not hardcode Q15 or add gold-answer text to inputs.
3. Evaluate every question and retain baseline-versus-reranked regression reporting before enabling the reranker. Compare another model only after distinguishing actual omission from incomplete alternative labels.

This analysis used the saved80-case report,2,400 logits and frozen corpus/evidence-v2. No GPU/model rerun, production or database change was needed. This small set has already informed label reviews and should not be treated as an independent held-out production decision.
