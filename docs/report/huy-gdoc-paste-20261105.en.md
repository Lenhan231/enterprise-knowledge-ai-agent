# Huy's sections: paste-ready academic text for the group report

Template: AIP491 Capstone Project Students' Guide. Citation style: APA 7, in-text (Author, year), reference list in alphabetical order.

## How to use this file

1. **Open the preview.** Open this file in a Markdown preview (for example VS Code `Ctrl+Shift+V`) and copy from the rendered view, so tables paste as Google Docs tables.
2. **Find the target.** Each block starts with **▶ Where** (the section and paragraph to replace or insert after). It ends with a line `— end of block —`. Copy only the text between the two.
3. **Captions.** Table and figure numbers follow the chapter, for example Table 4.1 or Figure 6.3. Put table captions above tables and figure captions below figures. In Google Docs, add the List of Tables and List of Figures from these captions at the end.
4. **Figures.** The images are in `docs/report/figures/`. Insert each one where its block says.
5. **Pending text.** Text marked **[pending]** waits for data. Lines starting with *Note:* are for you only; do not paste them.

---

## Definition and Acronyms (add rows)

▶ Where: the acronym table. Add these rows.

| Acronym | Definition |
|---|---|
| RAG | Retrieval-Augmented Generation |
| BM25 | Best Matching 25, a lexical ranking function |
| RRF | Reciprocal Rank Fusion |
| MRR | Mean Reciprocal Rank |
| nDCG | normalised Discounted Cumulative Gain |
| RBAC | Role-Based Access Control |
| LLM | Large Language Model |
| CI | Confidence Interval |
| VPS | Virtual Private Server |

— end of block —

---

## I. Project Introduction

▶ Where: replace the paragraph starting "Working group draft, 30 October 2026. Implementation statements refer to main commit beac2f3…"

This document reports the state of the project in November 2026. Experiments are described with the system version they measured. Incomplete work is identified as such and is not presented as a completed result.

— end of block —

▶ Where: I.3 Project Objective. Replace the sentence "Retrieval is assessed using Recall@10, MRR@10, and Full evidence@10."

Retrieval is assessed with Recall, Mean Reciprocal Rank and Full evidence at the depth that each experiment passes forward. The frozen bilingual comparison uses the top 10. The deployed pipeline passes the top 5 reranked passages to the answer model, so answer-level evaluation uses the top 5. Answers are assessed for correctness against reviewed reference answers, citation precision, grounded refusal and access-control leakage.

— end of block —

---

## IV. Methodology

▶ Where: IV.1. Replace the paragraph starting "RQ1: How does document extraction…"

The project addresses four research questions:

- **RQ1.** How well does document extraction preserve usable text, tables and provenance?
- **RQ2.** Which retrieval and reranking configuration best retrieves the required evidence, and what does it cost on a CPU-only deployment?
- **RQ3.** Does the integrated Knowledge AI answer policy questions correctly, cite the correct evidence, decline when the policy does not contain the answer, and withhold content from unauthorised roles?
- **RQ4.** What latency does a user experience on the deployed system, and which processing stages dominate it?

RQ2–RQ4 are answered quantitatively in Chapter VI. [Nhân TODO: RQ1 evidence.] [An TODO: SQL, dashboard and report evaluation.]

— end of block —

▶ Where: IV.2. Insert after the paragraph starting "The shared Review 2 corpus snapshot contained five Vietnamese documents…"

For answer-level evaluation, a separate question set was written from the VietStyle Enterprise Operating Policy v1.0, which has 50 policy pages and four appendices. The set has 76 questions; its composition is given in Table 4.1.

Every reference answer and evidence page was checked against the policy text and reviewed by a team member. The set was then locked with a cryptographic hash before any configuration was run. Questions previously used to tune prompts (six latency questions and fifteen manual questions) were excluded.

**Table 4.1.** Composition of the 76-question evaluation set.

| Group | Question types (count) | Purpose |
|---|---|---|
| Core policy questions (36) | lookup 14, threshold 8, calculation 8, multi-part 6 | Retrieval, boundary values, simple arithmetic and multi-part coverage |
| Grounded refusal (15) | out-of-scope 8, cannot-conclude 4, trap or prompt injection 3 | Declining without inventing figures, and not following instructions embedded in a question |
| Access control (3) | role-based access 3 | Run under a role that may not read the policy; any returned policy content is a leak |
| Language variants (14) | English 6, code-mixed 5, unaccented 2, shorthand amounts 1 | Query translation and lexical matching on realistic phrasing |
| Conversation and edge cases (8) | follow-up 2, topic switch 1, ambiguous 1, foreign currency 1, typing errors 1, pasted e-mail 1, chit-chat 1 | Behaviour beyond single well-formed questions |

— end of block —

▶ Where: IV.3. Replace the sentence "BGE reranking scores query–candidate pairs."

A cross-encoder reranks the fused candidates (Nogueira & Cho, 2019). The frozen comparison used BGE-reranker-v2-m3 (Chen et al., 2024). The deployed system uses an mMARCO-trained multilingual MiniLM cross-encoder (Bonifacio et al., 2021; Wang et al., 2021). It matched BGE at the deployed depth of five passages and was several times faster on the CPU server (Section VI.1.2).

— end of block —

▶ Where: IV.4. Replace the first paragraph starting "No task-specific fine-tuning was performed…". Keep the second paragraph about the frozen evaluation.

No task-specific fine-tuning was performed: all components are pretrained and used with fixed settings. In place of a train/validate cycle, the project uses two controlled evaluations and an explicit data split.

The first evaluation is a frozen retrieval comparison of four configurations: dense E5 (Wang et al., 2024), dense E5 with BGE reranking, translated hybrid retrieval, and translated hybrid retrieval with BGE reranking. Each configuration retrieved 30 candidates and retained the top 10.

The second evaluation is an ablation of the complete Knowledge pipeline on the 76-question set. Six configurations, listed in Table 4.2, were run on the same questions with the same answer model, Qwen3.8-27B served through the Groq API. The only exception is the closed-book configuration, which is given no documents.

**Table 4.2.** Configurations compared in the ablation.

| Configuration | Description |
|---|---|
| Closed-book | The answer model receives no documents |
| Naive RAG | Dense retrieval only, no reranker, earlier prompt, no claim verification |
| Tuned RAG | Translated hybrid retrieval, multilingual MiniLM reranker, current prompt, claim verification |
| Tuned RAG without verifier | As Tuned RAG, with claim verification disabled |
| Knowledge mode (API) | The deployed service in Knowledge mode: Tuned RAG plus optional splitting of a question into two search queries |
| Auto mode (API) | The deployed service in its default mode: a planner routes and rewrites the task, Knowledge AI answers, and a synthesis step composes the reply |

Normal questions were run under the employee role, the only role permitted to read the policy. Access-control questions were run under a role without that permission. Only the English version of the policy was active in the knowledge base during these runs.

**Data split.** The 76-question set served as the held-out set for the ablation, which was run before any change to the system. Its failures were then analysed to design corrective fixes, so from that point it served as a development set.

A second set of 30 new questions (vietstyle-test-v1) was written afterwards with the same type mix. None of its questions repeats a fact asked in the development set. It is locked before any further measurement and is used only once, to confirm the final configuration. Accuracy is therefore reported only on sets that had not been used for tuning when they were run.

— end of block —

▶ Where: IV.5. Insert after the paragraph starting "For query i with gold chunk set G_i…"

Answer-level metrics are computed per question and averaged over the relevant subset:

- **Correctness:** correct, partial or incorrect against the reviewed reference answer.
- **Key-point coverage:** the share of required points conveyed.
- **Citation precision:** the share of cited passages that lie on a gold evidence page.
- **Correct abstention:** the share of should-decline questions that the system declined.
- **False abstention:** the share of answerable questions that the system declined.
- **Verifier blocks:** the number of answers withheld by the claim verifier.
- **Leakage:** whether any policy passage reached an unauthorised role.

Correctness and coverage were graded by two independent LLM judges, following the LLM-as-a-judge approach (Zheng et al., 2023). Judge A (gpt-oss-120b) read the policy text of the gold and cited pages. Judge B (a Codex agent) read only the reference answer and key points, so its faithfulness labels were not used. Access-control questions were scored by rule rather than by a judge.

Agreement between the judges, and between each judge and a human grader on a stratified sample of 20 verdicts, is measured with Cohen's kappa (Cohen, 1960).

Configurations are compared on the same questions with an exact two-sided McNemar test (McNemar, 1947). A 95% confidence interval of the accuracy difference is obtained from 10,000 paired bootstrap resamples (Efron & Tibshirani, 1993).

— end of block —

▶ Where: IV.7 Ethical Considerations. Insert at the end of the section.

The evaluation itself was designed to limit three further risks.

- **Unsafe test content.** Test questions contain no personal data. Access-control questions verify that policy content is not disclosed to roles without permission.
- **Exposed credentials.** API keys are kept in server-side configuration and are never placed in prompts, logs or evaluation files.
- **Bias from AI-assisted work.** The question sets were drafted with an AI assistant and reviewed by a team member, and the answers were graded by LLM judges. Both introduce possible bias. To reduce it, two judges of different origin were used and their verdicts were compared with a human grader.

— end of block —

---

## V. System Design and Implementation

▶ Where: V.2. Replace the paragraph starting "Knowledge flow: authenticated request → …" (including the [Huy TODO] at its end). Insert Figure 5.1 after the first paragraph.

Figure 5.1 shows the Knowledge AI flow.

1. After authentication, the server creates the user's verified identity and authorises the request.
2. The question is translated between Vietnamese and English.
3. Dense retrieval on the original question and BM25 retrieval (Robertson & Zaragoza, 2009) on both language versions run concurrently, and are fused with reciprocal rank fusion (Cormack et al., 2009).
4. A cross-encoder reranks the top 30 candidates, and the top five become the context for the answer model.
5. The answer model writes an answer with inline citations.
6. When claim verification is enabled, literal equalities are checked exactly and each cited claim is audited against numbered evidence units. Any failure withholds the answer.

[Insert Figure 5.1: `docs/report/figures/fig5-1-knowledge-flow.png`]

**Figure 5.1.** Knowledge AI processing flow. Solid boxes form the shared pipeline; dashed boxes are steps specific to Knowledge mode or Auto mode.

The two user-facing modes differ before and after the shared pipeline.

- **Knowledge mode** may split a question into two search queries.
- **Auto mode** first asks a planner to route the request to Knowledge and/or SQL tasks, and rewrites the task question. It then composes the final reply in a synthesis step that rejects any number not found in the sources.

The verified identity currently carries document roles but no company or document-level scope.

— end of block —

▶ Where: V.3. Replace the paragraph starting "Docker Compose defines backend API…" (skip this block if another member owns deployment).

The system is deployed with Docker Compose on a CPU-only virtual private server with 12 GB of RAM. It runs five services:

- the backend API;
- an embedding service (multilingual E5-base);
- a reranker service;
- document processing;
- chunking.

An optional reverse proxy fronts these services. The database (PostgreSQL with pgvector, hosted on Supabase) and the language-model API (Groq) are external.

To deploy a change, the operator updates the main branch on the server, rebuilds only the affected service, and waits for its health check. Model weights are cached in a persistent volume, with one exception: the OCR recogniser downloads its weights into the container at start-up. A recreated document-processing container therefore downloads them again, and an interrupted download prevents the service from starting until the container is recreated.

— end of block —

▶ Where: V.4. Replace "[Huy TODO] Validate asynchronous embedding, disabled-document filtering, ACL changes/revocation, and cross-agent evidence handling."

The measured behaviour is sequential and single-user.

- **Latency.** Moving telemetry off the response path and running database queries concurrently reduced the median warm latency from 12.6 s to 6.7 s (Section VI.1.4).
- **Concurrency limits.** The reranker serves one request at a time, and each backend process opens at most ten database connections.
- **Provider quotas.** The service depends on the language-model provider's quotas. When a daily token limit is reached, Knowledge requests fail, and Auto mode reports that planning is unavailable.

Concurrent throughput has not been measured. Asynchronous embedding, permission revocation and cross-agent evidence handling still require acceptance tests.

— end of block —

▶ Where: replace the paragraph starting "RBAC implementation status (Huy): JWT authentication and route permissions exist…"

**Implemented access control.**

- **Authentication.** Users authenticate with JSON Web Tokens, and route permissions are enforced.
- **Server-side identity.** The server constructs a verified identity; roles supplied by the client are not trusted.
- **Knowledge requests.** Requests without document permission are rejected.
- **Retrieval filters.** Candidate retrieval and parent-context expansion both filter by role, processing status and the document's knowledge-base flag.
- **Reports.** Report document retrieval propagates the user's roles.

**Open policy gaps.**

- Administrators bypass document access lists by design, including empty lists.
- The access-update schema requires at least one role, so "deny all" cannot be expressed.
- The identity has no company or document scope.
- In Auto mode, a data-related question from a role without analytics permission returns an HTTP 403 error instead of a polite refusal.

In the evaluation, none of the three access-control questions leaked policy content to an unauthorised role. The full acceptance checklist in Appendix B has not yet been certified.

— end of block —

---

## VI. Results and Discussion

▶ Where: replace the intro line "Results below separate Huy's frozen retrieval comparison from pending parser, agent, deployment, and RBAC acceptance results."

Results are reported per experiment, because the experiments use different questions, corpora and hardware:

- Section 1.1 reports the frozen bilingual retrieval comparison.
- Sections 1.2–1.4 report reranker selection, claim verification and latency for the deployed pipeline.
- Sections 1.5–1.7 report the answer-level evaluation.

Parser and SQL/report results are reported by their owners.

— end of block —

▶ Where: before "Frozen retrieval comparison (20 intent clusters…". Insert this heading and caption, then keep that table and the paragraph after it.

**1.1 Frozen retrieval comparison**

**Table 6.1.** Retrieval quality on the frozen bilingual benchmark (20 intent clusters, 80 directional questions, top 10).

— end of block —

▶ Where: replace "[Huy TODO] Add measured RBAC acceptance results after implementation; no pass rate is available yet." with the following text (Sections 1.2–1.7).

**1.2 Reranker selection for the CPU deployment**

Table 6.2 compares reranker candidates on a second frozen benchmark of 80 VietStyle questions. Each candidate scored the same 30 dense candidates per question.

**Table 6.2.** Reranker comparison: evidence retrieved in the top 5 (76 scored question variants) and per-call reranking time on the deployment server.

| Reranker | Full evidence@5 | Evidence components@5 (of 244) | Reranking time on the VPS |
|---|---|---|---|
| BGE-reranker-v2-m3, INT8 | 47 | 183 | 19.8–26.6 s |
| Multilingual MiniLM, FP32 | 47 | 182 | 3.4–8.8 s |
| Multilingual MiniLM, INT8 | 45 | 175 | not deployed |

*Note: the BGE FP32 row in your 3 Nov notes has 47 / 183 at about 29 s per call; add it if space allows.*

The multilingual MiniLM model retrieved the same top-5 evidence as BGE at a fraction of its latency, so it was selected for deployment. Its INT8 version lost evidence and was rejected.

A further attempt to rerank 20 instead of 30 candidates gave no measurable speed-up and removed all citations from one multi-part answer, so it was reverted. An offline simulation had predicted no loss, but it ranked a different candidate order from the deployed pipeline. This shows that offline replays must reproduce the production order to be informative.

**1.3 Claim verification**

On six known-correct live answers, the verifier initially withheld one answer because an equality written inside parentheses could not be parsed. After correcting the parser, all six answers were retained, with a median verification time of 0.65 s. The verifier's effect on answer accuracy is reported in Section 1.5.

**1.4 Latency**

On six fixed policy questions, run in Knowledge mode with verification enabled, the median warm latency fell from 12.6 s to 6.7 s (maximum 9.1 s). Two changes caused the reduction: the telemetry write was moved off the response path, and the dense and BM25 queries were run concurrently on pooled connections.

Figure 6.1 shows the remaining time per stage. Database access dominates, mostly because of network round trips of about 0.4 s each to the hosted database. After the November fixes, the warm median was 7.1 s (database wait 1.9 s, reranking 3.3 s). The fixes did not change retrieval, and reranking time varied from 1.7 s to 5.3 s between requests, so the difference from 6.7 s lies within run-to-run variation on the shared server.

[Insert Figure 6.1: `docs/report/figures/fig6-1-latency-stages.png`]

**Figure 6.1.** Median warm time per processing stage on six fixed questions. Stage times overlap partly and are not additive.

**1.5 Answer-level evaluation**

Table 6.3 and Figure 6.2 report answer quality for the six configurations on the 76-question set.

**Table 6.3.** Answer quality by configuration (76 questions; 69–72 judged answers per configuration).

| Configuration | Correct (judge A) | Correct (judge B) | Correct or partial (A) | Citation precision | Correct abstentions | False abstentions |
|---|---|---|---|---|---|---|
| Closed-book | 24% | 11% | 27% | – | 7/12 | 51% |
| Naive RAG | 34% | 37% | 46% | 67% | 12/12 | 51% |
| Tuned RAG | 59% | 58% | 68% | 89% | 12/12 | 30% |
| Tuned RAG without verifier | 58% | 59% | 73% | 84% | 12/12 | 25% |
| Knowledge mode (API) | 57% | 56% | 65% | 89% | 9/9 | 35% |
| Auto mode (API) | 44% | 39% | 54% | 85% | 9/9 | 25% |

How to read Table 6.3:

- **Abstention denominators.** The API configurations have nine should-decline questions, because the access-control questions were run only in-process.
- **Access control.** No configuration leaked policy content to the unauthorised role.
- **Auto mode.** In the Auto-mode run, three questions failed because of a provider rate limit inside the planned task. They are counted as incorrect, so Auto-mode accuracy may be understated by up to four points.

[Insert Figure 6.2: `docs/report/figures/fig6-2-accuracy-by-configuration.png`]

**Figure 6.2.** Share of answers judged correct by each configuration under both judges. Confidence intervals for the differences between configurations are given in Table 6.4.

Retrieval quality differed sharply between the naive and the tuned configuration. Tuned RAG reached a Recall@5 of 0.72, Full evidence@5 of 0.61 and MRR of 0.73, against 0.32, 0.28 and 0.26 for dense-only retrieval.

**Table 6.4.** Paired comparisons on the same questions (correct versus not correct).

| Comparison | Judge A: difference [95% CI], p | Judge B: difference [95% CI], p |
|---|---|---|
| Adding retrieval (closed-book → Tuned RAG) | +36 points [+23, +49], p < .001 | +46 points [+33, +58], p < .001 |
| Tuned versus naive RAG | +25 points [+13, +36], p < .001 | +20 points [+9, +32], p = .003 |
| Adding the verifier | +1 point [0, +4], p = 1.00 | −1 point [−4, 0], p = 1.00 |
| Knowledge mode versus Tuned RAG | 0 points [−7, +7], p = 1.00 | 0 points [−4, +4], p = 1.00 |
| Auto mode versus Tuned RAG | −17 points [−30, −3], p = .035 | −21 points [−35, −8], p = .007 |
| Auto mode versus Knowledge mode | −12 points [−26, +3], p = .17 | −16 points [−29, −3], p = .043 |

Both judges agree on the direction of every comparison. The two judges agreed with each other on 90.5% of 348 shared verdicts (κ = 0.81). On a stratified sample of 20 verdicts, each judge agreed with the human grader in 18 cases (κ = 0.80). Judge A's two disagreements were over-strict gradings of correct translations, and neither judge accepted an incorrect answer in the sample.

**1.6 Failure modes**

Overall accuracy combines two different failures: declining an answerable question, and answering it wrongly. Figure 6.3 separates them.

- **Tuned RAG** answered 42 of 60 answerable questions. Of those, 32 were correct (76%) and 38 correct or partially correct (90%). Only four answerable questions received a confidently wrong answer.
- **Knowledge mode** behaved the same way: 78–79% of its answers were correct, and about 5% of answerable questions were answered wrongly.

These rates rest on about 40 answered questions, so they carry roughly ±13 points of uncertainty.

[Insert Figure 6.3: `docs/report/figures/fig6-3-failure-modes.png`]

**Figure 6.3.** Outcomes for answerable questions in Tuned RAG and Knowledge mode (judge A). Most errors are refusals rather than wrong answers.

**1.7 Effect of corrective fixes (development set)**

Fixes were then made to failure handling and number checking (Section 2). After these fixes, Tuned RAG scored 57% under both judges, against 58–59% before. On the 69 paired questions, judge A changed its grade for one question and judge B for none (p = 1.00 under both).

The fixes did remove the defects they targeted:

- **Server error eliminated.** One request had previously failed with a server error; it no longer does.
- **Fewer mechanical blocks.** Verifier blocks with a mechanical cause fell from three to one.

The affected answers had not been correct before the fixes, so accuracy was not expected to change.

The two service modes were then re-run after the fixes, and their results are given in Table 6.6. Neither mode changed significantly. After the fixes, Auto mode remained about 12 points below Knowledge mode under both judges (p = .12–.15). It also remained 15–17 points below Tuned RAG (p = .019–.064).

**Table 6.6.** Accuracy of the service modes before and after the corrective fixes (paired questions).

| Mode | Judge A: before → after, p | Judge B: before → after, p |
|---|---|---|
| Knowledge mode | 57% → 56%, p = 1.00 | 56% → 54%, p = 1.00 |
| Auto mode | 45% → 42%, p = .77 | 39% → 41%, p = 1.00 |

Two kinds of answers were still rejected by the synthesis guard: amounts written in shorthand in the question (for example "18 triệu" for 18,000,000), and equalities with a currency unit between the operands (for example "4.000.000 VND + 1.500.000 VND = 5.500.000 VND").

**1.8 Knowledge-base configuration (development set)**

Two configuration changes were then tested on the development set (Table 6.7). They change the knowledge base, not the code or the prompts:

1. **Clean-up.** Four unrelated test uploads (a receipt image, a report template and two unrelated documents) were deactivated.
2. **Vietnamese policy.** The Vietnamese version of the policy was activated alongside the English one.

**Table 6.7.** Effect of the knowledge-base configuration on Tuned RAG (development set, after the corrective fixes).

| Configuration | Recall@5 | MRR | Citation precision | Strict key points | False abstentions | Correct (A / B) |
|---|---|---|---|---|---|---|
| Original knowledge base | 0.71 | 0.73 | 87% | 46% | 36% | 57% / 57% |
| Unrelated uploads deactivated | 0.72 | 0.71 | 88% | 45% | 34% | 59% / 57% |
| … and Vietnamese policy active | 0.81 | 0.82 | 95% | 61% | 30% | 61% / 60% |

**Clean-up.** Deactivating the unrelated uploads removed them from every result list but did not change accuracy (p = 1.00 under both judges). The question answered from the other company's policy remained wrong, because that policy is legitimate content and stays in the knowledge base.

**Vietnamese policy.** Activating the Vietnamese policy improved every retrieval measure: Recall@5 rose from 0.72 to 0.81, MRR from 0.71 to 0.82, and citation precision from 88% to 95%. Answers also used the policy's own Vietnamese terms more often, with strict key-point matches rising from 45% to 61%, and false abstentions fell. Accuracy rose by about three points, but this gain is not significant on 70 paired questions (p = .69–.79).

The final configuration therefore keeps the unrelated uploads deactivated and the Vietnamese policy active.

**1.9 Locked test set**

The final configuration was run once on the locked 30-question test set [pending: results, three judges and majority vote].

— end of block —

▶ Where: VI.2 Discussion. Replace the sentence starting "Latest local selected checks reported 33 passes…". Insert the paragraphs below after that paragraph.

The full automated test suite has 701 tests, of which about 65 fail locally both before and after the November fixes. The failures are caused by:

- optional modules that are not installed locally (19 tests);
- imports of helpers that have since been removed (7 tests);
- outdated constructor calls (4 tests);
- fixture or environment errors (about 35 tests).

None of these failures was introduced by the fixes. They are maintenance debt to be cleared before submission.

**Research questions.** The results answer three of the research questions as follows.

- **RQ2: retrieval and reranking.** Translated hybrid retrieval with cross-encoder reranking was the best configuration on both corpora. On the frozen benchmark it completed the required evidence in 69 of 80 questions, against 52 for dense retrieval. On the VietStyle set it more than doubled Recall@5 over dense-only retrieval. On CPU, the multilingual MiniLM reranker preserved top-5 evidence quality at several times lower latency than BGE.
- **RQ3: answer quality and safety.** Retrieval raised correctness from 11–24% to 58–59%. The system declined every out-of-scope and injection question, and leaked no content to unauthorised roles. When it answered, 76–79% of its answers were correct.
- **RQ4: latency.** Median warm latency is 6.7 s, dominated by database round trips to the hosted database.

**Relation to prior work.** These findings are consistent with prior work. Fusing lexical and dense rankings improves over either alone (Cormack et al., 2009), and cross-encoder reranking improves the ordering of a fixed candidate pool (Nogueira & Cho, 2019). Retrieval augmentation also grounds answers in documents that the model has not memorised (Lewis et al., 2020). The level of agreement observed here between the LLM judges and the human grader is similar to that reported for strong LLM judges (Zheng et al., 2023).

**Main limitation: retrieval.** In Tuned RAG, 18 of 60 answerable questions were declined or withheld. The causes are listed in Table 6.5. The knowledge base also holds another company's inventory policy (the frozen benchmark corpus), and one generic question about the document code, version and effective date was answered from that policy instead of VietStyle's. Both unaccented questions failed at retrieval.

**Table 6.5.** Causes of declined or withheld answers in Tuned RAG.

| Cause | Questions |
|---|---|
| Gold evidence page not in the top five | 8 |
| Evidence only partly retrieved | 4 |
| Evidence retrieved, but judged insufficient by the model | 4 |
| Withheld by the verifier | 1 |
| Chit-chat, which has no handler outside Auto mode | 1 |

**Claim verifier.** The verifier did not change accuracy. It withheld one answer that the judge also found unsupported by its sources, and it made answers slightly more faithful (79% against 76%). However, three of its four blocks were mechanical:

- two partial answers ended with a sentence, explicitly allowed by the prompt, stating that the sources do not cover the rest;
- one audit response was malformed.

Separately, an answer citing a non-existent source caused a server error.

The verifier also affects availability. It makes a further model call after the answer is written, and it fails closed. When the provider's rate limit was reached during one run, eight otherwise complete answers were withheld with the "cannot verify" message; these cases were re-run for the results reported here. Enabling the verifier therefore trades some availability under load for a lower risk of unsupported answers.

**Auto mode.** Auto mode lost 17–21 points against the same pipeline called directly, because of two steps that only Auto mode performs.

1. **Synthesis number guard.** The guard rejects every number not found literally in the sources, including correct computed results such as 3 × 18,000,000 = 54,000,000. In seven questions, it replaced the answer with raw source excerpts. Auto mode answered one of eight calculation questions correctly, against five of eight for Tuned RAG.
2. **Task rewriting.** The planner's rewritten task question appears to drop inputs: one answer omitted "four employees". This explanation is inferred, because the rewritten question is not logged.

Multi-turn handling worked: both follow-up questions and the topic switch were answered correctly.

**Corrective fixes.** The corrective fixes addressed these mechanical failures:

- invalid citations now produce the standard "cannot verify" message instead of a server error;
- the verifier accepts the closing note about uncovered parts and retries one malformed audit;
- the synthesis step accepts results of exactly checked equalities whose operands are sourced;
- the planner is instructed to keep every number in the task question.

Because these fixes were designed from failures on the development set, results on that set only confirm that the defects were removed. An unbiased estimate requires the locked test set.

**Closed-book baseline.** Without documents, the model answered correctly only where generic good practice coincides with the policy. It failed every question that required a policy-specific figure or approver.

— end of block —

▶ Where: VI.3 Recommendations. Replace the sentence "Profile representative CPU reranking before changing models or candidate counts."

For Knowledge AI, the results support seven recommendations:

1. Keep both language versions of each policy active, since this improved every retrieval measure, and add company- or document-level scoping so that a question about one company is not answered from another company's policy.
2. Default the chat interface to Knowledge mode for policy questions until Auto mode matches it on the evaluation set; to close the gap, the Auto-mode synthesis guard should accept shorthand amounts from the question and equalities with units between operands.
3. Improve recall for unaccented and partially retrieved questions, for example by restoring diacritics before lexical search or passing more candidates to the reranker, and validate such changes only on the locked test set.
4. Keep the claim verifier, but monitor the reasons for its blocks.
5. Return a polite refusal instead of an HTTP 403 error when Auto mode plans a task the user's role may not run.
6. Run a concurrency test with three to five simultaneous users.
7. Place the server and the database in the same region to reduce network round trips.

— end of block —

---

## VII. Conclusion

▶ Where: VII.1. Replace the sentences about Huy's results ("Huy's retained retrieval benchmark shows 69/80…" up to "…requires policy alignment and acceptance testing.").

**Retrieval.** Translated hybrid retrieval with cross-encoder reranking completed the required evidence in 69 of 80 questions on the frozen bilingual benchmark, against 52 for dense retrieval. On the CPU deployment, a multilingual MiniLM reranker kept the same top-5 evidence quality at a fraction of BGE's latency, and the median warm latency was 6.7 s.

**Answer quality.** On a locked 76-question evaluation set, the tuned Knowledge pipeline answered 58–59% of questions correctly, against 34–37% for naive dense retrieval and 11–24% without documents. When it answered, 76–79% of its answers were correct, and only about one answerable question in twenty received a confidently wrong answer. Most failures were refusals caused by retrieval misses. The system declined every out-of-scope and injection question and leaked nothing to unauthorised roles.

**Verifier and Auto mode.** The claim verifier did not change accuracy. Auto mode was 17–21 points less accurate than the pipeline called directly, because of its synthesis and task-rewriting steps. Corrective fixes removed the server error and most mechanical blocks without changing accuracy in either the direct pipeline or the two service modes. Auto mode remained about 12 points below Knowledge mode, because its synthesis guard still rejects shorthand amounts and equalities with units between operands. Results for the locked test set are [pending].

**Other components.** A parsed-document chunking worker is in place. Access control has a working foundation with known policy gaps.

— end of block —

▶ Where: VII.3. Insert after the paragraph starting "Limitations include a small clustered retrieval set…"

The answer-level evaluation has six limitations:

1. **Size.** It uses 76 questions from a single policy document, so overall accuracy carries about ±11 points of uncertainty, and subgroups are reported as counts.
2. **Authorship.** The questions were drafted with an AI assistant and reviewed by one team member.
3. **Grading.** Answers were graded by LLM judges, checked against human grades on only 20 verdicts.
4. **Corpus state.** Only the English policy was active, so answers to Vietnamese questions were translated.
5. **Rate limits.** Some service runs hit provider rate limits, and the affected questions were re-run. In Auto mode, a rate-limited verifier is not visible in the response, so a small number of affected answers may remain undetected.
6. **Test-set power.** The 30-question test set can detect only large differences.

Future work should add a second evaluation corpus, measure latency and throughput under concurrent load after the fixes, and redesign the Auto-mode synthesis so that it preserves the user's inputs and accepts verified calculations.

— end of block —

---

## VIII. References

▶ Where: replace "[Huy TODO] E5, BGE reranking, BM25, RRF, and access-control references." with these entries. Then merge them with the other members' entries into one alphabetical list. Verify each entry against the original before submission.

Bonifacio, L., Jeronymo, V., Abonizio, H. Q., Campiotti, I., Fadaee, M., Lotufo, R., & Nogueira, R. (2021). *mMARCO: A multilingual version of the MS MARCO passage ranking dataset* (arXiv:2108.13897). arXiv. https://doi.org/10.48550/arXiv.2108.13897

Chen, J., Xiao, S., Zhang, P., Luo, K., Lian, D., & Liu, Z. (2024). *BGE M3-Embedding: Multi-lingual, multi-functionality, multi-granularity text embeddings through self-knowledge distillation* (arXiv:2402.03216). arXiv. https://doi.org/10.48550/arXiv.2402.03216

Cohen, J. (1960). A coefficient of agreement for nominal scales. *Educational and Psychological Measurement, 20*(1), 37–46.

Cormack, G. V., Clarke, C. L. A., & Büttcher, S. (2009). Reciprocal rank fusion outperforms Condorcet and individual rank learning methods. In *Proceedings of the 32nd International ACM SIGIR Conference on Research and Development in Information Retrieval* (pp. 758–759). ACM.

Efron, B., & Tibshirani, R. J. (1993). *An introduction to the bootstrap*. Chapman & Hall.

Lewis, P., Perez, E., Piktus, A., Petroni, F., Karpukhin, V., Goyal, N., Küttler, H., Lewis, M., Yih, W., Rocktäschel, T., Riedel, S., & Kiela, D. (2020). Retrieval-augmented generation for knowledge-intensive NLP tasks. In *Advances in Neural Information Processing Systems 33* (pp. 9459–9474).

McNemar, Q. (1947). Note on the sampling error of the difference between correlated proportions or percentages. *Psychometrika, 12*(2), 153–157.

Nogueira, R., & Cho, K. (2019). *Passage re-ranking with BERT* (arXiv:1901.04085). arXiv. https://doi.org/10.48550/arXiv.1901.04085

Robertson, S., & Zaragoza, H. (2009). The probabilistic relevance framework: BM25 and beyond. *Foundations and Trends in Information Retrieval, 3*(4), 333–389.

Wang, L., Yang, N., Huang, X., Yang, L., Majumder, R., & Wei, F. (2024). *Multilingual E5 text embeddings: A technical report* (arXiv:2402.05672). arXiv. https://doi.org/10.48550/arXiv.2402.05672

Wang, W., Bao, H., Huang, S., Dong, L., & Wei, F. (2021). MiniLMv2: Multi-head self-attention relation distillation for compressing pretrained transformers. In *Findings of the Association for Computational Linguistics: ACL-IJCNLP 2021* (pp. 2140–2151).

Zheng, L., Chiang, W.-L., Sheng, Y., Zhuang, S., Wu, Z., Zhuang, Y., Lin, Z., Li, Z., Li, D., Xing, E. P., Zhang, H., Gonzalez, J. E., & Stoica, I. (2023). Judging LLM-as-a-judge with MT-Bench and Chatbot Arena. In *Advances in Neural Information Processing Systems 36: Datasets and Benchmarks Track*.

— end of block —

*Note: the page ranges for Lewis et al. (2020) and Wang et al. (2021) are from memory; check them. Model cards (intfloat/multilingual-e5-base, BAAI/bge-reranker-v2-m3, cross-encoder/mmarco-mMiniLMv2-L12-H384-v1, Qwen/Qwen3.8-27B) can be cited as web sources, for example: Hugging Face. (n.d.). Title. Retrieved Month Day, Year, from URL.*

---

## IX. Appendices

▶ Where: Appendix A. Insert after the line starting "RBAC code to review in E1:"

**Knowledge AI evaluation evidence.** The following material is in the project repository on branch Huy.

- **Question sets and review records:** artifacts/evaluation/vietstyle-heldout-v1/ and artifacts/evaluation/vietstyle-test-v1/.
- **Scripts:** scripts/agents/run_vietstyle_arm.py runs one configuration per output file. scripts/agents/score_vietstyle_arm.py scores it deterministically and with an LLM judge, imports external judge verdicts, and runs the paired McNemar and bootstrap comparisons. scripts/agents/report_figures.py draws Figures 5.1 and 6.1–6.3.
- **Code version:** the corrective fixes are in commit f88613d on the main branch.
- **Human check:** the 20-verdict human grades are in artifacts/evaluation/vietstyle-heldout-v1/judge-review-20261105.md and its .human.json file.

[pending: path of the committed run outputs, scored files and judge verdicts]

— end of block —

▶ Where: Appendix B. Keep the checklist marked "planned, not yet certified". Optionally add after item 8:

Evaluation evidence so far: 0 of 3 access-control questions leaked policy content to a role without permission.

— end of block —
