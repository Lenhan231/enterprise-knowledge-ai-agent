# Simulated Panel Review — FA26AI48 Capstone Report

Manuscript: *Enterprise Knowledge AI Agent using Retrieval-Augmented Generation for Intelligent Question Answering, Data Analytics and Business Decision Support* (Google Doc 1dmKUA7A…, read 11 Nov 2026, ≈10,400 words).
Review mode: `full` (academic-paper-reviewer v1.11.1). Venue: FPT University AIP491 capstone committee (Review 3, 2 Dec 2026). `criteria_binding_unavailable`: no formal committee rubric was supplied, so no venue-alignment claim is made.
Anchors below use the report's own section/table numbers.

## Review Panel Provenance (read first)

- **Role separation:** five personas (Journal-Fit/committee, R1 methodology, R2 domain, R3 practical, Devil's Advocate) from the accepted cards.
- **Invocation context:** all five seats ran **inline in one session, in sequence, sharing one context**. They were **not** context-isolated and could see each other's output. Treat agreement between seats as one reader's view from five angles, not as independent corroboration.
- **Model family / provider:** one family for all seats (same session model). No cross-model reviewer.
- **Accountable human:** none during the review; the author triages.
- **Checks run (11 Nov, after Python was set up):** suggested-reference check, reviewer claim check and acronym check. Results are in the attachments at the end. They are advisory and do not change the decision.
- **Checks not run:** the sprint-contract conformance checker, panel-synthesis checker and panel-provenance builder. They need the structured two-call reviewer outputs that this inline run did not produce, so the decision was made by the synthesizer's judgement, not recomputed mechanically.
- **Claim-check deviation:** the judge agent read the prompt file with one file-read instead of receiving it with no tools at all. Devil's Advocate findings were not in the check, because its report is not in the table format the script parses; its issues map to findings that were checked (B1–B3, SG-6).

---

## Decision

### Major Revision

For a capstone at Review 3 this means: the evaluated core (Chapter VI.1, VII) is strong and largely defensible, but the report as a whole does not yet support its own title and research questions, and three evaluation statements need correcting before the committee reads them.

## Blocking Issues (source order)

1. **B1 — Scope promised but not evidenced** (DA-C1, EIC-W1, EIC-W2). The title, Objective (4) and RQ1 promise document extraction quality, data analytics and business decision support, but the report contains no parsing/OCR results beyond a five-page layout pilot, and no SQL, dashboard or report results at all (VI.1.1 `[An TODO]`, VI intro "reported by their owners"). Either add those results or narrow the title, objectives and RQs to what is evaluated.
2. **B2 — Evaluation-protocol statements contradict the results chapter** (R1-W1, R1-W2, DA-M1). IV.4 says test set 1 "is used only once, to confirm the final configuration"; VI.1.10 runs it again before and after a second round of improvements and pools it into the headline 61% → 72%. IV.5 and VII.2 call the judges "two independent LLM judges", while VI.1.10 shows Judges B and C agreed on all 74 test-set-2 "before" verdicts. Reword the protocol to what was actually done and qualify the headline.
3. **B3 — Access-control claims are stronger than the evidence, and the policy is described inconsistently** (R3-W1, DA-M2). "Leaked nothing to unauthorised roles" (VI.2 RQ3, VII.1) rests on 3 development questions and 1 test question, with Appendix B "not yet certified". The empty-ACL/admin policy is stated three different ways (II.2.3 / IV.7 "needs an explicitly agreed policy"; V.4 "administrators bypass … by design, including empty lists"; Appendix B item 4 "deny access … resolve admin-bypass inconsistency").

## Reviewer Summary

| Seat | Recommendation | One-line view |
|---|---|---|
| Journal-Fit (committee) | Major Revision | Two of three members' work has no results; front matter and management chapter are placeholders. |
| R1 Methodology | Minor Revision for VI.1 alone; Major for the report | Unusually careful evaluation; protocol wording and judge-independence claims must be fixed. |
| R2 Domain | Major Revision | Honest about novelty; literature chapter and baselines are too thin to support RQ2's "best configuration". |
| R3 Practical | Major Revision | RBAC and data-protection claims need a threat model and coverage, not 4 questions. |
| Devil's Advocate | 1 CRITICAL, 4 MAJOR | Strongest case: the 72% measures fit to a self-authored benchmark, not enterprise utility. |

## Consensus Analysis

**Agreement (raised from ≥3 angles; same-session caveat applies):**
- The evaluation in VI.1 is the report's strongest part: locked sets, paired tests, judge–human agreement, failure analysis, reproducible artifacts (Appendix A).
- The report does not yet cover RQ1 or the analytics agents, so the title overreaches (B1).
- Claim strength around "independent judges", "used only once" and "leaked nothing" should be reduced to what the evidence shows (B2, B3).
- The literature chapter (III) is a framework, not a review.

**Disagreement:**
- *Severity of the statistics.* R1 treats p = .065 with a bootstrap CI of 1.6–20.3 as acceptable if explained; the Devil's Advocate treats any "improvement" headline from it as overstated. Resolution: keep the number, add one sentence explaining why the exact McNemar test (p = .065) and the bootstrap interval (excludes 0) can disagree at n = 64, and say "borderline" everywhere the 61% → 72% appears (slides included).
- *Whether project-process text belongs in the report.* The committee seat wants the test-suite paragraph (VI.2, "701 tests … about 65 fail") moved out of Discussion; R1 values its honesty. Resolution: move it to V.4 or an appendix as known maintenance debt, keep it.

## Required Revisions (Must Fix)

| ID | Item | Where | Owner |
|---|---|---|---|
| RQ-1 | Add parsing/OCR results that answer RQ1 (CER/WER or a reviewed-page accuracy, table extraction quality, provenance check) — or narrow RQ1 | IV.1, IV.5, VI.1.1, VII.1 | Nhân |
| RQ-2 | Add SQL / dashboard / report evaluation (An's frozen benchmarks of 10 Nov exist in the repo) with dataset, metric and denominator | IV.2, IV.5, VI.1 (new subsection), VII.1 | An |
| RQ-3 | If RQ-1/RQ-2 cannot be completed by 2 Dec, change the title and Objective 4 so they do not promise "data analytics and business decision support" results | Cover, I.3, IV.1 | Team |
| RQ-4 | Rewrite IV.4 "Data split" to match what happened: test set 1 was used for Section 1.9, then re-run in 1.10 after improvements whose design followed its results; state that only test set 2 was locked before the improvements; report the test-set-2-only result next to the pooled one | IV.4, VI.1.10, VII.1 | Huy |
| RQ-5 | Replace "two independent LLM judges" with an accurate description (Judge A plus two near-identical judges; human check on 20 development verdicts only, none on the test sets); ideally human-check a sample of test-set verdicts | IV.5, VI.1.9, VII.2 | Huy |
| RQ-6 | State one empty-ACL/admin policy and use it everywhere; update Appendix B item 4 to the implemented behaviour (admin exception, 30 Oct) | II.2.3, IV.7, V.4, App. B | Huy |
| RQ-7 | Qualify the leak claim: "none of the 4 role-restricted questions returned restricted content", and report the test-set case where another company's documents answered (VI.1.9) as evidence of the missing company scope | VI.2 RQ3, VII.1, slides | Huy |
| RQ-8 | Add an abstract; fill Acknowledgement and the lists of tables and figures | Front matter | Team |
| RQ-9 | Remove drafting and process residue from the formal text (examples below) | II.2.4, II.2.5, IV.2, IV.6, V.2, App. A | Team |

**Examples for RQ-9** (text that reads as internal notes, not as a report):
- "has been rented … according to the user" (II.2.4)
- "avoid merging the historical Huy implementation wholesale into current main" (II.2.5)
- "Huy's separate bilingual retrieval experiment" (IV.2) → "a separate bilingual retrieval experiment"
- "was not found in this audit" (IV.6, V.2)
- "RBAC completion is now assigned to Huy" (I.6)
- "The following material is in the project repository on branch Huy" (App. A): keep the path, drop the framing

## Suggested Revisions (Should Fix)

| ID | Item | Where |
|---|---|---|
| SG-1 | Expand Chapter III into a real review: multilingual / cross-lingual retrieval benchmarks, Vietnamese NLP resources, RAG evaluation frameworks, attribution / claim verification, LLM-judge bias. Each source should connect to a project decision. | III |
| SG-2 | Add or discuss missing baselines so RQ2's "best configuration" is supported: BM25 alone, and dense + BM25 fusion without translation (to separate the effect of translation from fusion). Note that the frozen comparison used BGE while the deployed reranker is MiniLM. | IV.4, VI.1.1 |
| SG-3 | Define metrics per experiment: chunk-level Recall@k (IV.5) vs page-level gold evidence (citation precision, Table 6.5); top-5 vs top-8 with neighbours; which "80" and which "76" (Table 6.2 vs Table 4.1). | IV.5, VI.1.2, VI.1.5 |
| SG-4 | Add a threat model for access control (who the adversary is, what must not leak, what is out of scope), and state that RBAC acceptance tests 1–8 are planned. | IV.7, V.4, App. B |
| SG-5 | Discuss data protection: documents and questions are sent to an external LLM provider (Groq); state the implications for enterprise use, data residency and consent, and what a production deployment would change. | IV.7 |
| SG-6 | Address corpus circularity: the questions were drafted with an AI assistant and reviewed by one member. **The report never says that VietStyle is a synthetic company policy** (the claim check found this; the slides do say it), so state it in IV.2 and name it in VII.3 next to "single document". Propose a second corpus or an external question writer. | IV.2, VII.3 |
| SG-7 | Turn the Project Management chapter from "proposed" into "what we did": actual schedule, meetings, milestones and the change process used. | II |
| SG-8 | Give RQ4 one consistent answer: same-session numbers only (10 Nov: 20.6 s off → 12.1 s with 2 threads), and present the 3 Nov 6.7 s as a different configuration (English policy only). | VI.2, VII.1 |
| SG-9 | Explain the McNemar / bootstrap disagreement in one sentence (see Consensus). | VI.1.10 |
| SG-10 | Move the test-suite paragraph from Discussion to V.4 or an appendix. | VI.2 |
| SG-11 | Check figures 5.1 and 6.1–6.3 are inserted with captions and are readable when printed. | V.2, VI.1 |

## Revision Roadmap (source order; triage is yours)

Each item carries its source. You decide `will_address`, `wont_address` or `not_on_point` for each; nothing is ranked beyond the Blocking / Required / Suggested split above.

| # | Source | Item | Owner | Suggested by 2 Dec? |
|---|---|---|---|---|
| 1 | EIC-W1, DA-C1 | RQ-1 parsing results | Nhân | yes |
| 2 | EIC-W1, DA-C1 | RQ-2 analytics results | An | yes |
| 3 | EIC-W1 | RQ-3 title/scope fallback | Team | only if 1–2 slip |
| 4 | R1-W1, DA-M1 | RQ-4 data-split wording + test-set-2 result | Huy | yes (text only) |
| 5 | R1-W2 | RQ-5 judge description (+ optional human check) | Huy | wording yes; human check optional |
| 6 | R3-W1 | RQ-6 one ACL policy | Huy | yes |
| 7 | R3-W1, DA-M2 | RQ-7 leak-claim wording | Huy | yes |
| 8 | EIC-W3 | RQ-8 abstract and front matter | Team | yes |
| 9 | EIC-W4 | RQ-9 drafting residue | Team | yes |
| 10 | R2-W1 | SG-1 literature | Team | partly |
| 11 | R2-W2 | SG-2 baselines | Huy | discuss if no time to run |
| 12 | R1-W3 | SG-3 metric definitions | Huy | yes |
| 13 | R3-W2 | SG-4 threat model | Huy | yes |
| 14 | R3-W3 | SG-5 data protection | Huy | yes |
| 15 | R2-W3, DA-M3 | SG-6 corpus circularity | Huy | yes (text) |
| 16 | EIC-W5 | SG-7 management chapter | Team | yes |
| 17 | R1-W4 | SG-8 RQ4 consistency | Huy | yes |
| 18 | R1-W5 | SG-9 statistics sentence | Huy | yes |
| 19 | EIC-W6 | SG-10 move test-suite text | Huy | yes |
| 20 | EIC-W7 | SG-11 figures | Team | yes |

---

## Appendix: Panel Reports

### Journal-Fit Reviewer (capstone committee member) — Major Revision, confidence 4

**Summary.** A committee member would read Chapter VI.1 as the work of a strong evaluator and the rest as a report still being written. The document cannot be graded as a three-member project yet.

**Strengths**
- S1. Honest scope statements: no new algorithm or fine-tuning is claimed (III.7), and incomplete work is labelled as such (I intro, II.2.3).
- S2. Results tied to code versions and retained artifacts (V intro, App. A), which makes the defense demonstrable.

**Weaknesses**
- W1 (Major). The parsing/OCR and SQL/dashboard/report components have no results; RQ1 is unanswered (IV.1 "[Nhân TODO: RQ1 evidence.]"; VI.1.1 "[An TODO] Insert … results"). The title promises analytics and decision support that are not evaluated. *Fix:* RQ-1 to RQ-3.
- W2 (Major). Imbalance: about 4,400 of 10,400 words are Chapter VI, almost all one member's work; Chapter VII.1 "Other components" is two sentences. *Fix:* each owner adds a results subsection and a conclusion paragraph.
- W3 (Major). No abstract; Acknowledgement and the lists of tables and figures are placeholders. *Fix:* RQ-8.
- W4 (Major). Internal-note language in formal text (see RQ-9 examples). A committee reads "according to the user" as an unedited AI draft.
- W5 (Minor). Project Management describes a "proposed" plan; there is no schedule, no milestones and no actual meetings (II.1.2, II.2.1). *Fix:* SG-7.
- W6 (Minor). The test-suite paragraph opens the Discussion (VI.2) and sets a negative frame before the research questions. *Fix:* SG-10.
- W7 (Minor). Figure captions exist (5.1, 6.1–6.3). Confirm the images are present and legible.

**Questions for the team:** Which RQ1 numbers can Nhân report by 2 Dec? Which of An's frozen benchmarks will be reported, and on what dataset?

### Peer Reviewer 1 (IR evaluation methodology) — Minor for VI.1, Major for the report, confidence 5

**Summary.** The answer-level evaluation is more rigorous than most capstone work: paired tests, bootstrap CIs, locked sets, judge–human agreement, failure analysis, explicit power limits (VII.3). The weaknesses are in how the protocol is described, not in the numbers.

**Strengths**
- S1. Paired design with an exact McNemar test and paired bootstrap (IV.5), reported with intervals and honest "borderline" wording (VI.1.10).
- S2. A development/test split introduced when the 76-question set started informing fixes (IV.4), and a second test set locked before code changes (VI.1.10).
- S3. Failure analysis separates refusals from confident errors (VI.1.6, Table 6.5), which is the right decomposition for a fail-closed system.

**Weaknesses**
- W1 (Major). Protocol contradiction: test set 1 is described as used "only once" (IV.4) but is re-run and pooled in VI.1.10. The pooled 61% → 72% therefore mixes a set whose earlier result was known before the improvements with one that was not. *Fix:* RQ-4; report test set 2 alone (56% → 69%, p not stated; give it) as the cleanest estimate.
- W2 (Major). Judge independence is overstated. Judges B and C agreed on 74/74 and 68/74 verdicts (VI.1.10 end), the human check covers 20 development verdicts only (IV.5), and the test-set majority is effectively two votes. *Fix:* RQ-5. Optional: a 20-verdict human check on test set 2.
- W3 (Major). Metric definitions shift between experiments without a table: chunk-level vs page-level gold evidence, top-5 vs top-8 with neighbour expansion, two different "80"-question benchmarks. *Fix:* SG-3, a one-table "experiment registry" (set, size, unit of relevance, k, corpus state, date).
- W4 (Minor). RQ4 has three different answers on different days and configurations (VI.1.4, VI.1.10, VI.2). *Fix:* SG-8.
- W5 (Minor). p = .065 alongside a bootstrap CI excluding 0 needs one explanatory sentence (SG-9). Many paired comparisons are reported without correction; say they are descriptive.

### Peer Reviewer 2 (multilingual retrieval and RAG) — Major Revision, confidence 4

**Strengths**
- S1. Translated hybrid retrieval is a sensible design for a bilingual corpus, and the Vietnamese-policy activation result (Table 6.7) is a useful, honestly hedged finding.
- S2. The reranker choice is justified by measured quality and latency on the target hardware (Table 6.2), including a negative result (INT8, 20 candidates).

**Weaknesses**
- W1 (Major). Chapter III cites five methods and is otherwise a framework with TODOs; there is no discussion of cross-lingual retrieval, Vietnamese NLP resources, RAG evaluation frameworks, attribution / claim verification or LLM-judge bias. *Fix:* SG-1. Candidate areas to search (unverified, check before citing): BEIR and MIRACL for multilingual retrieval evaluation; RAGAS and ARES for RAG evaluation; PhoBERT and Vietnamese legal-retrieval work for Vietnamese resources; work on judge position and verbosity bias beyond Zheng et al. (2023).
- W2 (Major). Baselines cannot isolate the contribution of translation: there is no BM25-only arm and no untranslated dense + BM25 fusion arm (Table 6.1). The frozen benchmark also used BGE, not the deployed MiniLM. *Fix:* SG-2: run the two arms if the frozen harness allows it, otherwise state the limitation in VI.2 RQ2.
- W3 (Major). Corpus circularity: one synthetic policy written for the project, with questions drafted by an AI assistant (IV.7, VII.3 item 2). Retrieval results may reflect how the questions were phrased against the document. *Fix:* SG-6.
- W4 (Minor). The cost of the translation step (an extra LLM call per query, its latency and its failure fallback) is not reported.

### Peer Reviewer 3 (enterprise security and governance) — Major Revision, confidence 4

**Strengths**
- S1. Filtering by role before ranking and before neighbour expansion is the correct design (IV.7, V.4), and the open gaps are listed candidly (V.4 "Open policy gaps").
- S2. The availability trade-off of a fail-closed verifier is discussed explicitly (VI.2 "Claim verifier").

**Weaknesses**
- W1 (Major). The evidence for "no leaks" is 4 questions; Appendix B's 8 acceptance checks are uncertified; the empty-ACL/admin policy is stated three different ways; and the VI.1.9 case (another company's documents answered a restricted role) shows the missing company scope in practice. *Fix:* RQ-6, RQ-7.
- W2 (Major). There is no threat model, so a reader cannot tell what "access control works" means. *Fix:* SG-4.
- W3 (Major). Data protection is absent: company documents and user questions are sent to an external LLM API on a free tier (VI.1.10 mentions the provider's limit). For an "enterprise" system this is the first question a client would ask. *Fix:* SG-5.
- W4 (Minor). "Business decision support" has no user or stakeholder evaluation; consider a short scenario walk-through or, after the defense, a small user study.

### Devil's Advocate — 1 CRITICAL, 4 MAJOR

**Strongest counter-argument.** The report's evidence of quality comes from one synthetic policy document written for the project, questions drafted with an AI assistant and checked by one team member, and answers graded mainly by LLM judges, two of which behave as one. The second round of improvements was designed after test-set-1 results were known, and that set is pooled into the headline. "72% on unseen questions" therefore measures how well the system fits a benchmark its authors built, not how it would serve an enterprise. Meanwhile, two of the three components named in the title have no results at all. A committee member could fairly say the project demonstrates a well-evaluated document QA prototype, not an enterprise knowledge, analytics and decision-support agent.

**Issues**
- **C1 (CRITICAL — Evidence Sufficiency).** The title, Objective 4 and RQ1 are not supported by any reported evidence (VI intro; VI.1.1 TODOs; VII.1 "Other components"). *Adjudication in the decision:* validated; this is B1. It is repairable either by adding the results or by narrowing the scope.
- **M1 (MAJOR).** Test-set reuse contradicts the stated protocol (IV.4 vs VI.1.10). → B2.
- **M2 (MAJOR).** "Leaked nothing" is generalised from 4 questions (VII.1). → B3.
- **M3 (MAJOR).** Self-authored corpus and AI-drafted questions (IV.7). → SG-6.
- **M4 (MAJOR).** Judge non-independence (VI.1.10 end vs IV.5 "independent"). → B2.

**Ignored alternatives.** Retrieval gains may partly reflect the Vietnamese policy being activated mid-study rather than the method alone (Table 6.7); the report separates this for the dev set but the frozen benchmark and VietStyle results are not on the same corpus state.

**Missing stakeholders.** Employees who would actually ask questions; IT/security owners who would approve sending documents to an external API.

**Observations (not defects).** The report's hedging is unusually careful for student work; that care is an asset in the defense and should extend to the remaining chapters.

---

## Revision coaching (Phase 2.5)

Because the decision is Major Revision, the skill offers a guided conversation to set your revision strategy and record your triage for each roadmap item. You can skip it and work from the tables above.

---

## Attachment: Suggested-Reference Check (advisory, #1001)

Suggested-reference check (script output, not a reviewer finding; #1001)
Seats read: R2, R3 (complete).

| Seat | # | Reference | Result |
|---|---|---|---|
| R2 | 1 | Thakur, N. et al. (2021) "BEIR: A Heterogeneous Benchmark for Zero-shot Evaluation of Information Retrieval Models" arXiv:2104.08663 | Found in an index |
| R2 | 2 | Zhang, X. et al. (2023) "MIRACL: A Multilingual Retrieval Dataset Covering 18 Diverse Languages" arXiv:2210.09984 | Found in an index |
| R2 | 3 | Es, S. et al. (2024) "RAGAS: Automated Evaluation of Retrieval Augmented Generation" arXiv:2309.15217 | Found in an index |
| R2 | 4 | Saad-Falcon, J. et al. (2024) "ARES: An Automated Evaluation Framework for Retrieval-Augmented Generation Systems" arXiv:2311.09476 | Found in an index |
| R2 | 5 | Nguyen, D. Q. et al. (2020) "PhoBERT: Pre-trained language models for Vietnamese" arXiv:2003.00744 | Found in an index |

"Found" means an index holds a record with this DOI or arXiv ID and title, or with this title. It does not show that the work supports the recommendation, or that the authors and year are right.

## Attachment: Reviewer Claim Check (advisory, #1002)

The judge answered 20 of 20 findings from 4 reviewers: it marked 0 as contradicted, and 2 cannot be checked from the manuscript alone.

The author decides what to do with each row. This check does not change the decision, the consensus counts, or the Revision Roadmap. The judge is the session model; as this judge, the #1002 contrast test passed Claude Opus 5.5 and Claude Fable 5.1 (gpt-6-astra and Gemini 4 Argon passed it in part one, through other transports); other models are untested.

Claims marked not checkable: (1) R2-W3 says the policy is synthetic, but the report never says so, which is now part of SG-6; (2) EIC-W2's word counts are approximate.

## Attachment: Acronym Check (advisory, #849)

Script output on the plain-text copy of the report. Most rows are false alarms: the plain-text copy lost the Definitions and Acronyms table, so ACL, AI, BM25, CER/WER, JWT, LLM, MRR, nDCG, OCR, RAG, RBAC, RRF and VPS show as undefined although the table defines them. TODO, TEAM, TABLE and the reference-list entries are not report text. **Real gaps** (used but defined nowhere): SQL, CPU, RAM/GB, WBS, API, HTTP, BGE, MiniLM, mMARCO, INT8, IoU, VND, and RQ1–RQ4 (spell out "research question" once). Add them to the acronym table or expand at first use.

```
### Acronym check (advisory; no reply needed)
Coverage: body (partial)
Not in this input: English abstract, Chinese abstract.
Not checked:
- Body, line 173: API (the initials before its parentheses do not spell it)

| Scope | Line | Rule | Acronym | Uses |
|---|---|---|---|---|
| Body | 3 | Not defined | TABLE | 29 |
| Body | 7 | Not defined | FPT | 1 |
| Body | 9 | Not defined | AI | 23 |
| Body | 22 | Not defined | TEAM | 17 |
| Body | 22 | Not defined | TODO | 43 |
| Body | 27 | Not defined | ACL | 5 |
| Body | 29 | Not defined | BM25 | 6 |
| Body | 30 | Not defined | CER | 2 |
| Body | 30 | Not defined | WER | 2 |
| Body | 32 | Not defined | JSON | 2 |
| Body | 32 | Not defined | JWT | 1 |
| Body | 33 | Not defined | LLM | 10 |
| Body | 34 | Not defined | MRR | 9 |
| Body | 35 | Not defined | nDCG | 1 |
| Body | 36 | Not defined | OCR | 14 |
| Body | 38 | Not defined | RAG | 32 |
| Body | 39 | Not defined | RBAC | 12 |
| Body | 40 | Not defined | RRF | 2 |
| Body | 41 | Not defined | VPS | 5 |
| Body | 56 | Not defined | SQL | 17 |
| Body | 89 | Not defined | WBS | 1 |
| Body | 93 | Not defined | CPU | 8 |
| Body | 99 | Not defined | GB | 3 |
| Body | 99 | Not defined | RAM | 4 |
| Body | 133 | Not defined | IV | 1 |
| Body | 139 | Not defined | RQ1 | 2 |
| Body | 140 | Not defined | RQ2 | 3 |
| Body | 141 | Not defined | RQ3 | 2 |
| Body | 142 | Not defined | RQ4 | 3 |
| Body | 160 | Not defined | BGE | 11 |
| Body | 160 | Not defined | MiniLM | 7 |
| Body | 160 | Not defined | mMARCO | 2 |
| Body | 211 | Not defined | LOCKED | 1 |
| Body | 211 | Not defined | SKIP | 1 |
| Body | 251 | Not defined | HTTP | 2 |
| Body | 273 | Not defined | IoU | 1 |
| Body | 273 | Not defined | PP | 1 |
| Body | 281 | Not defined | INT8 | 3 |
| Body | 346 | Not defined | VND | 3 |
| Body | 500 | Not defined | MARCO | 1 |
| Body | 500 | Not defined | MS | 1 |
| Body | 503 | Not defined | ACM | 2 |
| Body | 503 | Not defined | SIGIR | 1 |
| Body | 505 | Not defined | NLP | 1 |
| Body | 507 | Not defined | BERT | 1 |
| Body | 510 | Not defined | IJCNLP | 1 |
| Body | 511 | Not defined | MT | 1 |
| Body | 524 | Not defined | README | 2 |
| Body | 528 | Not defined | OWNER | 1 |
| Body | 539 | Not defined | ID | 1 |
```
