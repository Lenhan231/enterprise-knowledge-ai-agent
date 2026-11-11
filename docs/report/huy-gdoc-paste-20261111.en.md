# Report paste — 11 Nov 2026 (review fixes B2, B3)

Rewrites approved after the simulated panel review of 11 Nov (Major Revision; blocking issues B2 and B3 are Huy's).
Apply in the Google Doc only after Nhân and An have finished editing their sections.
Each block names its location and the text it replaces.

Evidence for the new human-check numbers: `artifacts/evaluation/vietstyle-test-v2/judge-review-20261111.md` (blind sheet, graded by Huy) and `judge-review-20261111.key.json` (judge verdicts; seed 20261111, 5 verdicts per run, stratified by majority grade).

---

## B2, part 1 — test-set use

▶ Where: IV.4 Model Training and Validation. Replace the paragraph that starts "A second set of 30 new questions (vietstyle-test-v1)…" (and the "Data split." paragraph before it) with:

**Data split.** The 76-question set served as the held-out set for the ablation, which was run before any change to the system. Its failures were then analysed to design corrective fixes, so from that point it served as a development set. A second set of 30 new questions (vietstyle-test-v1) was written afterwards with the same type mix; none of its questions repeats a fact asked in the development set. It was locked and first used to measure the configuration of Section VI.1.9. A further round of improvements (Section VI.1.10) was then designed from development-set failures only. Because the result on the first test set was already known at that point, a third set of 40 questions (vietstyle-test-v2) was written and locked before any code was changed. Both test sets were then used to compare the configurations before and after these improvements. The second test set is the only one whose result was unknown when any design decision was made, so it gives the cleanest estimate; the first test set and the pooled result are reported alongside it.

▶ Where: VI.1.10, directly after the sentence that ends "…only borderline significant at this sample size." Add:

On the second test set alone, Tuned RAG improved from 20/36 (56%) to 25/36 (69%), with 7 questions gained and 2 lost (exact McNemar p = .18).

---

## B2, part 2 — judges

▶ Where: IV.5 Evaluation Metrics. Replace "Correctness and coverage were graded by two independent LLM judges, following the LLM-as-a-judge approach (Zheng et al., 2023). Judge A … so its faithfulness labels were not used." with:

Correctness and coverage were graded by LLM judges, following the LLM-as-a-judge approach (Zheng et al., 2023). Judge A (gpt-oss-120b) read the policy text of the gold and cited pages. Judge B (a Codex agent) read only the reference answer and key points, so its faithfulness labels were not used. On the test sets a third judge (Judge C, a Claude subagent) was added, and the majority verdict is reported. The judges are different models, but their errors were not shown to be independent: Judges B and C agreed on almost every test-set verdict (Section VI.1.10), so the majority mainly reflects their shared judgement, with Judge A as a check.

▶ Where: IV.5. Replace "Agreement between the judges, and between each judge and a human grader on a stratified sample of 20 verdicts, is measured with Cohen's kappa (Cohen, 1960)." with:

Agreement between the judges, and between each judge and a human grader (a team member), is measured with Cohen's kappa (Cohen, 1960) on two stratified samples of 20 verdicts: one from the development set, and one from the second test set, graded blind to the judges' verdicts and to the configuration.

▶ Where: VI.1.10, after the last paragraph ("Judges B and C agreed very closely … rather than three fully independent votes."). Add:

On the blind test-set sample, the human grader agreed with the majority verdict in 17 of 20 cases (κ = 0.77; 85% for each judge). In all three disagreements the judges rated as partial an answer the grader rated correct, and the grader rejected no answer that the judges had accepted, so the judges were, if anything, slightly stricter than the human grader.

▶ Where: VII.2 Contributions and Reflections. Replace "two independent LLM judges checked against human grades" with:

LLM judges of different origin, checked against a human grader on 20 development-set and 20 test-set verdicts

▶ Also check: VI.1.9 ("To strengthen the final measurement, a third judge …") needs no change; VII.3 item 3 ("checked against human grades on only 20 verdicts") → "checked against human grades on 40 verdicts (20 per evaluation stage)".

---

## B3 — access control

▶ Where: IV.7 Ethical Considerations. Replace "Current main enforces role, processing-status and knowledge-base filters before ranking; the empty-ACL/admin behaviour still needs an explicitly agreed policy." with:

Current main enforces role, processing-status and knowledge-base filters before ranking. Documents with an empty access list are hidden from every role except administrators. Administrators may read every active, ready document, because they are the ones who assign roles to documents and must be able to check a document before and after assigning them, including when testing access settings.

▶ Where: V.4, list "Implemented access control." Add as a new item:

**Administrator scope.** Administrators may read every active, ready document, including documents with no assigned roles, because they assign document roles and test access settings. Other roles need a matching role, so a document with an empty list is hidden from them.

▶ Where: V.4, list "Open policy gaps." Delete "Administrators bypass document access lists by design, including empty lists." (moved above). Keep the other three items.

▶ Where: Appendix B, item 4. Replace with:

4. Empty allowed_roles: hidden from every non-admin role; administrators may read any active, ready document (policy decided 30 October 2026).

▶ Where: VI.2 (RQ3 paragraph) and VII.1 (Answer quality paragraph). Replace "leaked no content to unauthorised roles" / "leaked nothing to unauthorised roles" with:

none of the four role-restricted questions (three development, one test) returned restricted policy content

▶ Where: VI.1.9. Replace "This reflects a weakness in the choice of that question, not a failure of access control, and the question was not changed after the run." with:

This was not a leak: the role was permitted to read those documents. It does show the missing company scope in practice, since a question about one company can be answered from another company's documents (Section V.4). The question was not changed after the run.

▶ Optional (not yet confirmed): VII.3 Limitations and Future Work, add:

In production, the right to assign document roles should be separated from the right to read every document, or administrator reads should at least be logged.

---

## SG-6 — say that VietStyle is fictional

▶ Where: IV.2, after "…a separate question set was written from the VietStyle Enterprise Operating Policy v1.0, which has 50 policy pages and four appendices." Add:

VietStyle is a fictional company: its policy was generated for this project by a team member with the help of an AI assistant [confirm], so that every answer can be checked against a known text, and it was translated into Vietnamese on 23 October 2026.

▶ Where: VII.3, answer-level limitation 1. Replace "It uses 76 questions from a single policy document" with:

It uses 76 questions from a single fictional policy written for the project

▶ Where: VII.3, answer-level limitation 2. Replace with:

2. Authorship. The policy and the questions were both drafted with an AI assistant, and the questions were reviewed by one team member. Questions written this way may match the policy's wording more closely than real employees' questions would.

---

## SG-5 — data sent to an external provider

▶ Where: IV.7 Ethical Considerations, after "Exposed credentials. …". Add:

External language-model provider. Answer generation, query translation, search planning and claim verification call a hosted language model (Qwen3.8-27B through the Groq API). Each call sends the user's question to the provider, and answer generation and verification also send the retrieved policy passages; embeddings and reranking run on the project's own server. The evaluation used only a fictional policy and no personal data. A deployment on real company documents would need either a data-processing agreement with the provider that covers retention and use of the submitted text, or a self-hosted model; neither was evaluated.

[Nhân/An: add the invoice path here if it sends documents to Gemini or a Modal endpoint.]

---

## SG-4 — threat model for access control

▶ Where: IV.7, after the first paragraph ("Only server-verified identity …"). Add:

Threat model. The access-control design assumes an authenticated user who tries to obtain content from documents their role may not read: by asking for it directly or indirectly, by embedding instructions in a question, or by sending role or permission values from the client. It does not cover a compromised server, administrator account or database; inferring that a document exists from response timing; or exposure at the language-model provider (see "External language-model provider" below). Within this model, the filters in Section V.4 keep restricted passages out of retrieval, context expansion, prompts and citations. The acceptance checklist in Appendix B is the planned test of this design.

---

## SG-3 — one table of all experiments

▶ Where: end of IV.4 Model Training and Validation. Add the table and its caption, and refer to it from the start of Chapter VI ("Results are reported per experiment …, see Table 4.3"):

Table 4.3. Experiments reported in Chapter VI.

| Experiment (section) | Questions | Corpus state | Relevance unit | Passages to the model | Version / date |
|---|---|---|---|---|---|
| Frozen bilingual retrieval (VI.1.1) | 80 directional, 20 intent clusters | 10 document versions, 1,063 chunks | Annotated gold chunks, with alternative-evidence rules | 30 candidates → top 10 (BGE reranker) | Run of 22 Oct 2026 |
| Reranker selection (VI.1.2) | 80 VietStyle questions, 76 scored variants, 244 evidence components | VietStyle [check: which document version(s)] | Evidence components | Same 30 dense candidates → top 5 | Selected 3 Nov 2026 (a8c1031, 0330a12) |
| Ablation and fixes, development set (VI.1.5–1.8) | 76 (69–72 judged) | VietStyle, English only; Vietnamese added in VI.1.8 | Gold evidence pages | Top 5 | Runs of 4–6 Nov 2026; fixes in f88613d |
| Locked test set 1 (VI.1.9) | 30 (28 judged) | VietStyle EN + VN, unrelated uploads deactivated | Gold evidence pages | Top 5 | main b616744 |
| Improvements, test sets 1 and 2 (VI.1.10) | 30 and 40 (28–29 and 36–38 judged) | As VI.1.9 | Gold evidence pages | Top 8, each with its neighbours, capped at 20,000 characters | e7fd295, 4e4bc02, 4b725d0; 7–10 Nov 2026 |
| Latency (VI.1.4, VI.1.10) | 6 fixed questions (V1–V6), warm medians | 3 Nov: English only; 10 Nov: as VI.1.9 | – | As the configuration measured | 3 Nov and 10 Nov 2026 |

---

## SG-8 — one answer for RQ4

▶ Where: VI.2, research-question answers. Replace the "RQ4: latency." paragraph with:

RQ4: latency. For the final configuration, measured in one session on 10 November 2026 on six fixed questions, the warm median response time was 12.1 s (slowest 20 s), and reranking on the shared CPU server was the largest stage. In the same session it was 20.6 s with the improvements off, and 13.4–17.0 s with them on before the reranker was limited to two threads. The 6.7 s measured on 3 November, when database round trips dominated, used the English policy only and is not directly comparable.

▶ Where: VII.1, "Retrieval." paragraph. Replace "and the median warm latency was 6.7 s on 3 November (12.1 s on 10 November after limiting the reranker to two threads, on a more contended shared server; Section VI.1.10)" with:

and the final configuration answered in a median of 12.1 s on a shared CPU server (six fixed questions, 10 November 2026; Section VI.1.10)

---

## Slides to update to match

- "0 leaks" / "0 access leaks" → "0 of 4 role-restricted questions" (rbac, ablation, closing slides).
- 61% → 72%: add "borderline, p = .065" where it appears without it, and optionally the test-set-2 result 56% → 69%.
