# Huy's additions, 8 Nov 2026: retrieval and prompt improvements (paste-ready)

Adds Section VI.1.10 and Table 6.9, and replaces the two remaining [pending] lines. Same conventions as `huy-gdoc-paste-20261105.en.md` (APA, table captions above, English).

---

▶ Where: VI.1.9 Locked test set. Replace "Results for Knowledge mode and Auto mode on the test set are [pending]."

Knowledge mode was run on the test set only with the improved configuration of Section 1.10, where it answered 76% of the questions correctly. Auto mode was not run on the test set; its development-set results are given in Table 6.6.

— end of block —

▶ Where: after Section VI.1.9, before "VI.2 Discussion". Insert this section.

**1.10 Retrieval and prompt improvements on a second locked test set**

The failure analysis (Table 6.5) showed that most remaining errors came from retrieval: the evidence page was missing from the top five passages, only part of the evidence was retrieved, or an unaccented question retrieved the wrong pages. Five changes were made to address these causes:

- **More passages.** The answer model receives the eight best reranked passages instead of five.
- **Neighbouring context.** Each passage is extended with the adjacent passage on either side from the same page, and passages already covered by a higher-ranked one are dropped. Access rights are checked again for the added text.
- **Accent restoration.** The existing translation call also rewrites an unaccented or misspelled Vietnamese question in standard Vietnamese; this form is used for the Vietnamese keyword search and for reranking.
- **Completeness rule.** The answer prompt asks the model to answer every part of a multi-part question, with its conditions, deadlines and responsible parties.
- **Verifier budget.** The claim verifier may produce longer audits (1,536 instead of 768 output tokens), so audits of long answers are no longer cut off.

Each change is controlled by a configuration setting, so the previous configuration remained available for comparison. Because eight extended passages can exceed the answer model's per-request input limit of 7,000 tokens on the provider's free tier, the context is capped at 20,000 characters when these settings are enabled.

To measure the changes without reusing questions that had informed them, a second test set of 40 questions (vietstyle-test-v2) was written and locked before any code was changed. It follows the type mix of the first test set, with more multi-part, unaccented and misspelled questions, and none of its questions repeats a fact from the development set, the first test set or the tuning questions. Each reference answer was checked against the policy text, cross-reviewed by an independent agent and checked by a team member. Both test sets were then run with the previous and the improved configuration and graded by the same three judges. Judges B and C graded each run in a separate workspace that contained only the grading prompts.

**Table 6.9.** Answers judged correct before and after the improvements (majority of three judges).

| Test set and configuration | Before | After |
|---|---|---|
| Test set 1, Tuned RAG | 19/28 (68%) | 21/28 (75%) |
| Test set 1, Knowledge mode | – | 22/29 (76%) |
| Test set 2, Tuned RAG | 20/36 (56%) | 25/36 (69%) |
| Test set 2, Knowledge mode | 22/38 (58%) | 27/38 (71%) |
| Both test sets, Tuned RAG (paired) | 39/64 (61%) | 46/64 (72%) |

*Note.* The first test set's "before" run is the final configuration of Section 1.9. Knowledge mode had no complete "before" run on the first test set because the provider's daily quota ran out. Questions skipped by a configuration (follow-up questions in-process, access-control questions over the API) are excluded. In the Knowledge mode "after" runs, each search returned five passages rather than eight, because the search planner applied its per-branch limit even when it did not split the question; this was corrected after the runs, so the Knowledge mode results understate the improved configuration slightly.

Across both test sets, Tuned RAG answered 9 more questions correctly and 2 fewer, a gain of 10.9 percentage points (95% bootstrap CI 1.6 to 20.3). The exact McNemar test on the 64 paired questions gave p = .065, so the improvement is consistent but only borderline significant at this sample size. Knowledge mode improved by 13 points on the second test set (5 gained, none lost; p = .062). On the second test set, Recall@5 rose from 0.81 to 0.87 and MRR from 0.75 to 0.79; on the first, MRR rose from 0.81 to 0.85 and key-point coverage from 66% to 74%. Answers also stayed closer to their sources: Judge A, the only judge that reads the cited pages, rated 83% (Tuned RAG) and 88% (Knowledge mode) of the cited answers on the second test set as faithful, up from 73% and 78%, and 92% in both configurations on the first test set.

The changed questions match the intended causes. The unaccented question about emergency purchases was answered from the wrong policy page before and correctly after accent restoration. Four multi-part questions moved from partially to fully correct, and one question whose audit had failed was verified after the larger verifier budget. The two losses were longer answers that the verifier withheld, and citation precision on the second test set fell from 87% to 82%, because more passages give the model more nearby but non-evidential text to cite. Every remaining incorrect answer was a refusal or a withheld answer rather than a confidently wrong one. The verifier's handling of long answers is therefore the next limit to address, and it should be tuned on the development set, not on these test sets.

Judges B and C agreed very closely (all 74 verdicts on the second test set before the change, 68 of 74 after it). The majority verdict therefore reflects two strong judges with Judge A as a check, rather than three fully independent votes.

— end of block —

▶ Where: VII.1 Summary of Findings. Replace the sentence that says Knowledge and Auto mode results on the test set are [pending].

A second set of improvements targeted the remaining retrieval failures. On 64 paired questions from two locked test sets, they raised Tuned RAG accuracy from 61% to 72% (95% CI for the difference 1.6 to 20.3 points; McNemar p = .065), and Knowledge mode reached 71–76% on the two test sets. All remaining errors were refusals rather than confidently wrong answers.

— end of block —

▶ Where: VII.3 Future Work (or Limitations). Add.

**Multi-part questions.** Questions whose parts are answered in different policy sections remain the main retrieval failure. Splitting such a question into up to three searches was tried on the development set: it retrieved slightly more evidence pages (0.76 to 0.80 of the evidence pages) but did not fix the target questions and increased refusals, so it was not adopted. A lasting fix likely needs chunking that keeps related clauses together, or retrieval that follows cross-references between sections.

**Verifier on long answers.** The two answers lost after the improvements were long answers that the claim verifier withheld. Verifying long answers in parts, tuned on the development set, is the next step.

**Citation precision.** With more passages in the prompt, the model sometimes cites nearby passages that do not contain the evidence (citation precision 87% to 82% on the second test set). A stricter citation instruction could address this.

— end of block —

▶ Where: List of Tables. Add Table 6.9 "Answers judged correct before and after the improvements (majority of three judges)", together with Tables 6.6–6.8 if they are not yet listed.

▶ Where: Appendix A, evidence paths. Add: test set 2 questions and review files in `artifacts/evaluation/vietstyle-test-v2/`; before/after run outputs and judge verdicts for both test sets (to be committed under `artifacts/evaluation/vietstyle-test-v2/runs/` and `artifacts/evaluation/vietstyle-test-v1/runs/`).
