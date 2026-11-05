# Huy's sections — paste-ready text for the group Google Doc

How to use this file:

- **Order.** Each block names a section of the Google Doc and an action: **REPLACE** (the paragraph starting with the quoted words) or **INSERT AFTER** (the quoted paragraph). Work top to bottom.
- **Pasting tables.** Open this file in a Markdown preview (for example VS Code `Ctrl+Shift+V`) and copy from the rendered view, so tables paste as Google Docs tables.
- **Pending values.** Text marked **[pending]** waits for data: the after-fix runs, the human judge check and clean latency.
- **Notes for you.** Lines starting with "Note:" are for you only. Do not paste them.

---

## Front matter, I. Project Introduction

**REPLACE** the paragraph starting "Working group draft, 30 October 2026. Implementation statements refer to main commit beac2f3…"

> Working group draft, November 2026. Unless a historical experiment is explicitly identified, implementation statements refer to main commit f88613d (5 November 2026). Pending owner contributions are marked; proposed work is not presented as a completed result.

**I.3 Project Objective: REPLACE** the sentence "Retrieval is assessed using Recall@10, MRR@10, and Full evidence@10."

> Retrieval is assessed with Recall, MRR and Full evidence at the depth that each experiment feeds forward. The frozen bilingual comparison uses top 10. The production pipeline passes the top 5 reranked chunks to the answer model, so the held-out evaluation uses @5. Knowledge AI answers are assessed for correctness against reviewed reference answers, citation precision, grounded refusal and access-control leakage.

---

## IV. Methodology

**IV.1: REPLACE** the paragraph starting "RQ1: How does document extraction…"

> RQ1: How well does document extraction preserve usable text, tables and provenance? RQ2: Which retrieval and reranking configuration retrieves the required evidence best on the project corpora, and what does it cost on the CPU-only deployment? RQ3: Does the integrated Knowledge AI answer policy questions correctly, cite the right evidence, refuse when the policy does not contain the answer and withhold content from unauthorised roles? RQ4: What latency does a user experience on the deployed system, and which stages dominate it? RQ2–RQ4 are answered quantitatively below. [Nhân TODO] RQ1 evidence. [An TODO] SQL, dashboard and report evaluation.

**IV.2: INSERT AFTER** the paragraph starting "The shared Review 2 corpus snapshot contained five Vietnamese documents…"

> For answer-level evaluation, a separate held-out set (vietstyle-heldout-v1) was written from VietStyle Enterprise Operating Policy v1.0 (50 policy pages and four appendices). It contains 76 cases.
>
> - **Core questions (36):** 14 lookup, 8 threshold, 8 calculation and 6 multi-part.
> - **Grounded refusal (15):** 8 out-of-scope, 4 cannot-conclude and 3 trap or prompt-injection cases.
> - **Access control (3):** RBAC cases.
> - **Language variants (14):** English, code-mixed English–Vietnamese, unaccented and shorthand-amount questions.
> - **Conversation and edge cases (8):** follow-ups, a topic switch, an ambiguous question, foreign currency, typos, a pasted e-mail and chit-chat.
>
> Every reference answer and evidence page was checked against the policy text and reviewed by a team member. The set was then locked (SHA-256 9980e803…7e84da) before any configuration was run. Questions used earlier for tuning (V1–V6 and fifteen manual questions) are excluded. The physical PDF page equals the policy page + 2; this was verified on the Vietnamese PDF and spot-checked on the English PDF.

**IV.3: REPLACE** the sentence "BGE reranking scores query–candidate pairs."

> A cross-encoder reranks the fused candidates. BGE-reranker-v2-m3 was used in the frozen comparison. Production uses mmarco-mMiniLMv2-L12-H384-v1, which matched BGE at the production depth (top 5) and is several times faster on the CPU server (Section VI.1.2).

**IV.4: REPLACE** the first paragraph starting "No task-specific fine-tuning was performed…" and keep the second paragraph about the frozen evaluation as it is.

> No task-specific fine-tuning was performed. All components are pretrained and used with frozen settings. Two controlled evaluations replace a train/validate cycle.
>
> 1. **Frozen retrieval comparison.** Four retrieval arms: Dense E5, Dense E5 + BGE, Translated Hybrid, and Translated Hybrid + BGE. Each arm used 30 candidates and retained the top 10 (RTX 2060, FP32, reranker batch size 4).
> 2. **Held-out ablation of the whole Knowledge pipeline.** The arms below were run on the same 76 questions with the same answer model (Groq qwen/qwen3.8-27b), except the closed-book arm.

> | Arm | Description |
> |---|---|
> | B0 | Closed-book: the model answers without documents |
> | B1 | Naïve RAG: dense E5 only, no reranker, earlier prompt, no verifier |
> | B2 | Tuned pipeline: translated hybrid retrieval, mMiniLM reranker, current prompt, claim verifier |
> | B4 | B2 without the claim verifier |
> | E2E-K | Production API, Knowledge mode: B2 plus multi-query search planning |
> | E2E | Production API, Auto mode (the UI default): the router plans the task, then Knowledge AI answers and a synthesis step composes the reply |

> Normal cases run as the employee role, the only role allowed to read the policy. The RBAC cases run as a role without access. Only the English policy PDF was active in the knowledge base during these runs.

**IV.5: INSERT AFTER** the paragraph starting "For query i with gold chunk set G_i…"

> Answer-level metrics (held-out set):
>
> - **Correctness.** Each answer is graded correct, partial or incorrect against the reviewed reference answer.
> - **Key-point coverage.** The share of required points that are conveyed.
> - **Citation precision.** The share of cited chunks that lie on a gold evidence page.
> - **Refusals.** Correct abstention on the 12 should-decline cases, and false abstention on answerable cases.
> - **Verifier blocks.** The number of answers the claim verifier withheld.
> - **RBAC leakage.** Whether any policy chunk was returned to an unauthorised role.
>
> Correctness and coverage were graded by two independent LLM judges: gpt-oss-120b, which read the gold and cited policy pages, and a Codex agent, which read the reference answer and key points only. The judges agree on correct versus not correct in 90.5% of 348 shared verdicts (Cohen's κ = 0.81). A 20-verdict human check is [pending]. RBAC cases are scored by rule, not by a judge.
>
> Arms are compared on the same questions with an exact two-sided McNemar test. A paired bootstrap (10,000 resamples) gives the 95% interval of the accuracy difference.

---

## V. System Design and Implementation

Note: you may also replace "Architecture snapshot: current main beac2f3" with "f88613d".

**V.2: REPLACE** the paragraph starting "Knowledge flow: authenticated request → …" (including the [Huy TODO] at its end)

> Knowledge flow:
>
> 1. Authenticated request, then a server-created identity and agent authorisation.
> 2. Query translation (Vietnamese↔English).
> 3. Role-filtered dense search on the original query and BM25 search on both language versions, run concurrently.
> 4. Reciprocal rank fusion, then top-30 cross-encoder reranking, keeping the top 5 as context.
> 5. Answer generation with inline [S#] citations.
> 6. Optional claim verification:
>    - literal equalities are checked exactly;
>    - each cited claim is audited against numbered evidence units;
>    - any failure withholds the answer.
>
> Knowledge mode adds a search-planning step that may split a question into two sub-queries. Auto mode first asks a planner to route the request to Knowledge and/or SQL tasks, rewrites the task question, and composes the final reply in a synthesis step. That step rejects any number not found in the sources.
>
> Identity currently carries document roles but no company or document-ID scope.

**V.3: REPLACE** the paragraph starting "Docker Compose defines backend API…" (keep it if another member owns deployment and has written this part).

> Docker Compose runs five services on a CPU-only Contabo VPS (12 GB RAM):
>
> - backend API;
> - embeddings (multilingual-e5-base);
> - reranker (mMiniLM by default; BGE can be selected with RERANKER_MODEL);
> - document processing;
> - chunking.
>
> An optional proxy fronts them. Supabase PostgreSQL/pgvector and the Groq language-model API are external.
>
> Deployment procedure:
>
> 1. Pull main on the VPS.
> 2. Rebuild only the changed service (for example `docker compose up -d --build --no-deps backend-api`).
> 3. Wait for the container health check.
>
> Model weights are cached in a named volume. One exception is the VietOCR recogniser weights, which are downloaded to the container's /tmp at start. A recreated document-processing container therefore re-downloads them, and an interrupted download leaves a corrupt file that blocks start-up until the container is recreated.

**V.4: REPLACE** "[Huy TODO] Validate asynchronous embedding, disabled-document filtering, ACL changes/revocation, and cross-agent evidence handling."

> Measured so far, all sequential and single-user:
>
> - **Latency.** Warm median latency for six fixed policy questions fell from 12.6 s to 6.7 s after two changes: the telemetry write was moved off the response path, and the dense and BM25 queries now run concurrently on pooled connections.
> - **Concurrency limits.** The reranker serves one request at a time (process-wide lock). Each backend process opens at most 10 database connections.
> - **Provider dependence.** The service depends on Groq quotas: when the daily token limit is reached, Knowledge requests fail (HTTP 503) and Auto mode reports that planning is unavailable.
>
> Concurrent throughput has not been measured. Asynchronous embedding, ACL revocation and cross-agent evidence handling still need acceptance tests.

**RBAC status paragraph: REPLACE** the paragraph starting "RBAC implementation status (Huy): JWT authentication and route permissions exist…"

> RBAC implementation status (Huy).
>
> Implemented:
>
> - JWT authentication and route permissions.
> - The server creates VerifiedIdentity; client-supplied roles are not trusted.
> - Knowledge AI rejects requests without document permission.
> - Candidate retrieval and parent-context expansion both filter by role, processing_status = 'ready' and knowledge_base_active.
> - Report document retrieval propagates roles.
>
> Outstanding:
>
> - Admin bypasses the document ACL by design, including documents with an empty ACL.
> - The access-update schema still requires at least one role, so "deny all" cannot be expressed.
> - Identity has no company or document-ID scope.
> - In Auto mode, a data-flavoured question from a role without analytics permission returns HTTP 403 instead of a polite refusal.
>
> In the held-out evaluation, none of the three RBAC cases leaked policy content to an unauthorised role. The full acceptance checklist in Appendix B is not yet certified.

---

## VI. Results and Discussion

**VI (intro line): REPLACE** "Results below separate Huy's frozen retrieval comparison from pending parser, agent, deployment, and RBAC acceptance results."

> Results are reported per experiment, because the experiments use different questions, corpora and hardware. Section 1.1 is the frozen bilingual retrieval comparison. Sections 1.2–1.4 cover the deployed Knowledge pipeline. Section 1.5 is the held-out answer-level evaluation. Parser and SQL/report results are reported by their owners.

**VI.1: INSERT** the heading "1.1 Frozen retrieval comparison" before "Frozen retrieval comparison (20 intent clusters…". Keep that table and the paragraph starting "The final retrieval arm completed 17 more cases…".

**VI.1: REPLACE** "[Huy TODO] Add measured RBAC acceptance results after implementation; no pass rate is available yet." with the following blocks (1.2–1.5).

> **1.2 Reranker selection for the CPU deployment.**
>
> On the frozen 80-case benchmark (same E5 top-30 candidates), mMiniLM FP32 reached the same Full evidence@5 as BGE (47/76 cases each) and 182 versus 183 evidence components. mMiniLM INT8 lost evidence (45/76), so it was rejected.
>
> On the VPS, BGE INT8 reranking took 19.8–26.6 s per call (median per pass), against 3.4–8.8 s for mMiniLM FP32. mMiniLM was therefore selected for production.
>
> Reducing reranking from 30 to 20 candidates gave no measurable speed-up and made one multi-part answer lose all citations, so it was reverted. The offline simulation that predicted no loss had ranked a different candidate order from production, which is why it was wrong.

> **1.3 Claim verification.**
>
> When enabled, the verifier checks literal arithmetic exactly and audits each cited claim against numbered evidence units. The check is fail-closed: if any step fails, the answer is withheld.
>
> On six known-correct live answers, it first blocked one answer, because an equality written inside parentheses could not be parsed. After that fix, all six answers were kept, with a median verification time of 0.65 s.
>
> Its effect on the held-out set is reported in 1.5.

> **1.4 Latency.**
>
> On six fixed policy questions (Knowledge mode, verifier on), the warm median HTTP latency fell from 12.6 s to 6.7 s (maximum 9.1 s).
>
> | Stage | Median time |
> |---|---|
> | Database wait | 2.7 s |
> | Reranking | 1.5 s |
> | Answer generation | 0.84 s |
> | Verification | 0.59 s |
> | Search planning | 0.41 s |
>
> The remaining database time is mostly network round trips to Supabase (about 0.4 s each). Latency after the 5 November fixes is [pending].

> **1.5 Held-out answer-level evaluation (76 cases).**
>
> | Arm | Correct, judge A | Correct, judge B | Correct or partial (A) | Citation precision | Correct refusals | False refusals |
> |---|---|---|---|---|---|---|
> | B0 closed-book | 24% | 11% | 27% | – | 7/12 | 51% |
> | B1 naïve RAG | 34% | 37% | 46% | 67% | 12/12 | 51% |
> | B2 tuned pipeline | 59% | 58% | 68% | 89% | 12/12 | 30% |
> | B4 without verifier | 58% | 59% | 73% | 84% | 12/12 | 25% |
> | E2E-K, API Knowledge | 57% | 56% | 65% | 89% | 9/9 | 35% |
> | E2E, API Auto | 44% | 39% | 54% | 85% | 9/9 | 25% |
>
> Judge A is gpt-oss-120b; judge B is the Codex agent. Each arm has 69–72 judged answers. The API arms have 9 should-decline cases because RBAC cases run only in-process. No arm leaked policy content to an unauthorised role.
>
> Retrieval in B2 reached Recall@5 0.72, Full evidence@5 0.61 and MRR 0.73, against 0.32, 0.28 and 0.26 for dense-only retrieval (B1).

> | Paired comparison (same questions) | Judge A: Δ accuracy [95% CI], p | Judge B: Δ accuracy [95% CI], p |
> |---|---|---|
> | Adding retrieval (B0 → B2) | +36 pts [+23, +49], p < 0.001 | +46 pts [+33, +58], p < 0.001 |
> | Tuned vs naïve RAG (B1 → B2) | +25 pts [+13, +36], p = 0.0005 | +20 pts [+9, +32], p = 0.003 |
> | Adding the verifier (B4 → B2) | +1 pt [0, +4], p = 1.0 | −1 pt [−4, 0], p = 1.0 |
> | Multi-query planning (B2 vs E2E-K) | 0 pts [−7, +7], p = 1.0 | 0 pts [−4, +4], p = 1.0 |
> | Auto vs B2 (E2E vs B2) | −17 pts [−30, −3], p = 0.035 | −21 pts [−35, −8], p = 0.007 |
> | Auto vs Knowledge mode (E2E vs E2E-K) | −12 pts [−26, +3], p = 0.17 | −16 pts [−29, −3], p = 0.043 |
>
> Both judges agree on the direction of every comparison. Results after the 5 November fixes are [pending].

**VI.2 Discussion: REPLACE** the sentence starting "Latest local selected checks reported 33 passes…" and **INSERT AFTER** that paragraph the following paragraphs.

> At commit f88613d, the full test suite has 701 tests, of which about 65 fail locally. The same failures occur before and after the November fixes, so none is caused by them.
>
> | Cause of failure | Tests |
> |---|---|
> | Optional module not installed locally (for example docling, OpenCV) | 19 |
> | Import of a helper that has since been removed | 7 |
> | Call to an old constructor signature | 4 |
> | Fixture or environment errors (mainly missing keys) | about 35 |
>
> These test failures are maintenance debt and should be cleaned up before the final submission.

> Retrieval is the main limit of the tuned pipeline. In B2, 18 of 60 answerable questions were refused or withheld.
>
> | Cause | Cases |
> |---|---|
> | Gold page missing from the top 5 | 8 |
> | Evidence only partly retrieved | 4 |
> | Model judged retrieved evidence insufficient | 4 |
> | Verifier block | 1 |
> | Chit-chat outside the router | 1 |
>
> Unrelated uploads visible to the employee role compete for the top 5. In one case they produced the document code of a different policy. Both unaccented questions failed at retrieval.

> The claim verifier did not change accuracy. It blocked one answer that the judge also found unfaithful. Three further blocks were mechanical:
>
> - two partial answers ending with an allowed "the sources do not cover the rest" sentence;
> - one malformed audit response.
>
> Separately, an answer that cited a non-existent source was returned as HTTP 503.

> Auto mode lost 17–21 points against the same pipeline called directly. The cause is two steps that only Auto mode has.
>
> 1. **The synthesis guard.** It rejects every number not found literally in the sources, including correct computed results such as 3 × 18,000,000 = 54,000,000. In 7 cases it replaced the answer with raw English excerpts. Auto mode answered 1 of 8 calculation questions correctly, against 5 of 8 for B2.
> 2. **Task rewriting.** The planner's rewritten task question appears to drop inputs: one answer omitted "4 employees". This is inferred, because the rewritten question is not logged.
>
> Multi-turn handling worked: both follow-ups and the topic switch were answered correctly.

> Without documents, the model answered 11–24% correctly, only where generic good practice coincides with the policy. Every question that needed a policy-specific figure or approver failed. The value of retrieval is therefore the 35–46-point gain over this baseline.

> Commit f88613d targets the mechanical failures:
>
> - unknown or missing citations now return the standard "cannot verify" message instead of HTTP 503;
> - the verifier accepts a closing "sources do not cover" note, and retries one malformed audit;
> - synthesis accepts results of exactly checked equalities whose operands are sourced;
> - the planner is instructed to keep every number in task questions.
>
> Because these fixes were motivated by failures on this set, the after-fix scores [pending] confirm the defects are removed. They are not an unbiased estimate of improvement.

**VI.3 Recommendations: REPLACE** the sentence "Profile representative CPU reranking before changing models or candidate counts." with:

> For Knowledge AI:
>
> 1. Remove unrelated uploads from the employee scope. This is the cheapest retrieval gain.
> 2. Default the chat UI to Knowledge mode for policy questions until Auto mode matches it on the held-out set.
> 3. Improve recall for unaccented and partial-evidence questions (accent restoration before BM25, or more candidates before reranking). Validate such changes on new held-out questions, not on this set.
> 4. Keep the verifier but monitor its block reasons.
> 5. Return a polite refusal instead of HTTP 403 when Auto mode plans a task the role may not run.
> 6. Run a 3–5-user concurrency test.
> 7. Co-locate the VPS and the database to cut network round trips.

---

## VII. Conclusion

**VII.1: REPLACE** the sentences about Huy's results ("Huy's retained retrieval benchmark shows 69/80…" up to "…requires policy alignment and acceptance testing.").

> On the frozen bilingual benchmark, translated hybrid retrieval with BGE reranking completed the required evidence in 69/80 cases, against 52/80 for dense E5. On the CPU deployment, an mMiniLM reranker kept the same top-5 evidence quality at a fraction of BGE's latency. Warm latency was 6.7 s (median, six questions).
>
> On a locked 76-question held-out set, the tuned Knowledge pipeline answered 58–59% of questions correctly, against 34–37% for naïve dense RAG and 11–24% without documents. It refused every out-of-scope and injection question, and leaked nothing to unauthorised roles.
>
> The claim verifier did not change accuracy. Auto mode was 17–21 points worse than calling the pipeline directly, because of its synthesis and task-rewriting steps, which were then fixed [after-fix result pending].
>
> A parsed-document chunking worker is on main. RBAC has a working foundation with known policy gaps.

**VII.3: INSERT AFTER** the paragraph starting "Limitations include a small clustered retrieval set…"

> For Knowledge AI, the held-out set has 76 questions from a single policy document, so overall accuracy carries roughly ±11 points of uncertainty, and subgroups are reported as counts. The questions were drafted with an AI assistant and reviewed by one team member. Answers were graded by LLM judges, with a small human check. Only the English policy PDF was active, so answers to Vietnamese questions were translated. Some API runs hit provider rate limits and the affected cases were re-run.
>
> Future work: a second held-out corpus; clean latency and concurrency measurements after the fixes; and an Auto-mode router that preserves the user's inputs and accepts verified calculations.

---

## VIII. References

**INSERT** under "[Huy TODO] E5, BGE reranking, BM25, RRF, and access-control references." and delete that TODO line. Verify each entry against the original and apply the required citation style before submission.

> - Wang, L., Yang, N., Huang, X., Yang, L., Majumder, R., & Wei, F. (2024). Multilingual E5 text embeddings: A technical report. arXiv:2402.05672.
> - Chen, J., Xiao, S., Zhang, P., Luo, K., Lian, D., & Liu, Z. (2024). BGE M3-Embedding: Multi-lingual, multi-functionality, multi-granularity text embeddings through self-knowledge distillation. arXiv:2402.03216.
> - Bonifacio, L., Jeronymo, V., Abonizio, H. Q., Campiotti, I., Fadaee, M., Lotufo, R., & Nogueira, R. (2021). mMARCO: A multilingual version of the MS MARCO passage ranking dataset. arXiv:2108.13897.
> - Wang, W., Bao, H., Huang, S., Dong, L., & Wei, F. (2021). MiniLMv2: Multi-head self-attention relation distillation for compressing pretrained transformers. Findings of ACL-IJCNLP 2021.
> - Nogueira, R., & Cho, K. (2019). Passage re-ranking with BERT. arXiv:1901.04085.
> - Robertson, S., & Zaragoza, H. (2009). The probabilistic relevance framework: BM25 and beyond. Foundations and Trends in Information Retrieval, 3(4), 333–389.
> - Cormack, G. V., Clarke, C. L. A., & Büttcher, S. (2009). Reciprocal rank fusion outperforms Condorcet and individual rank learning methods. Proceedings of SIGIR 2009, 758–759.
> - Lewis, P., et al. (2020). Retrieval-augmented generation for knowledge-intensive NLP tasks. Advances in Neural Information Processing Systems 33.
> - Zheng, L., et al. (2023). Judging LLM-as-a-judge with MT-Bench and Chatbot Arena. Advances in Neural Information Processing Systems 36 (Datasets and Benchmarks Track).
> - McNemar, Q. (1947). Note on the sampling error of the difference between correlated proportions or percentages. Psychometrika, 12(2), 153–157.
> - Cohen, J. (1960). A coefficient of agreement for nominal scales. Educational and Psychological Measurement, 20(1), 37–46.
> - Efron, B., & Tibshirani, R. J. (1993). An introduction to the bootstrap. Chapman & Hall.
> - Model cards: intfloat/multilingual-e5-base; BAAI/bge-reranker-v2-m3; cross-encoder/mmarco-mMiniLMv2-L12-H384-v1; Qwen/Qwen3.8-27B (served via the Groq API).

**Project evidence: INSERT AFTER** [E5].

> - [E6] Held-out set and review record: artifacts/evaluation/vietstyle-heldout-v1/ (questions.json, REVIEW.md), branch Huy.
> - [E7] Runner and scorer: scripts/agents/run_vietstyle_arm.py, scripts/agents/score_vietstyle_arm.py.
> - [E8] Performance and evaluation notes: docs/report/huy-performance-section-20261103.en.md, docs/report/huy-evaluation-section-20261105.en.md.
> - [E9] Fix commit f88613d (main).

Note: the run outputs, scored files and judge verdicts are still in artifacts/local/, which git ignores. They must be committed (for example to artifacts/evaluation/vietstyle-heldout-v1/runs/) before E6 can be cited as full evidence.

---

## IX. Appendices

**Appendix A: INSERT AFTER** the line starting "RBAC code to review in E1:"

> Knowledge AI evaluation: E6 contains the 76 reviewed cases. E7 runs one arm per file and scores it deterministically and with an optional LLM judge; it also exports judge prompts and imports external verdicts. Paired comparisons use the scorer's compare command (McNemar and bootstrap).

**Appendix B:** keep the checklist as "planned, not yet certified". Optionally add after item 8:

> Held-out evidence so far: 0/3 RBAC cases leaked policy content (role without access).
