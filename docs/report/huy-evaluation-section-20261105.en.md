# Held-out Evaluation and Ablations of the Knowledge Pipeline (Huy)

Date: 5 November 2026. Draft section for *VI. Results and Discussion*. It complements the performance section of 3 November (`huy-performance-section-20261103.en.md`), which covers reranker selection, claim verification on V1–V6 and latency. Results marked **[pending]** are being collected.

## 1. Why a common held-out set

Earlier measurements used six known procurement questions (V1–V6) and fifteen manual questions that were also used while tuning prompts. They show that known answers survive a change, but they cannot compare systems fairly. This section therefore evaluates every configuration on one fixed question set written before any of the configurations below were run.

## 2. Test set: `vietstyle-heldout-v1`

- **Source.** *VietStyle Enterprise Operating Policy v1.0* (50 policy pages and four appendices). Every reference answer was checked against the policy text and the evidence page recorded.
- **Review and lock.** All 76 cases were reviewed by a team member (`REVIEW.md`, status `reviewed-r2`, SHA-256 `9980e803…7e84da`). Revision r2 was made before any run; no label was changed after results were seen.
- **No overlap with tuning data.** V1–V6 and the 15 manual questions are excluded.

| Group | Types (cases) | What it tests |
|---|---|---|
| Core policy questions (36) | lookup 14, threshold 8, calculation 8, multi-part 6 | Retrieval, boundary values, simple arithmetic, multi-part coverage |
| Grounded refusal (15) | out-of-scope 8, cannot-conclude 4, trap/injection 3 | Declining without inventing figures; not obeying instructions in the question |
| Access control (3) | RBAC 3 | Run with a role that cannot read the policy; any policy content returned is a leak |
| Language (14) | English 6, code-mixed EN–VI 5, no diacritics 2, shorthand amounts 1 | Query translation and lexical retrieval on real user phrasing |
| Conversation and edge cases (8) | follow-up 2, topic switch 1, ambiguous 1, foreign currency 1, typos 1, long pasted email 1, chit-chat 1 | Behaviour beyond single well-formed questions |

**Evidence convention.** The physical PDF page is the policy page + 2 (verified on the Vietnamese PDF; spot-checked on the English PDF at pages 14, 35 and 53).

## 3. Configurations (arms)

All arms use the same 76 questions. The answer model is Groq `qwen/qwen3.8-27b`, except in B0, where no documents are used.

| Arm | Retrieval | Reranker | Prompt | Verifier | Path |
|---|---|---|---|---|---|
| **B0** closed-book | none | — | "answer about VietStyle; say if you do not know" | — | direct LLM call |
| **B1** naïve RAG | dense E5 only | none | pre-4 Nov prompt | off | RAG service |
| **B2** tuned pipeline | translated hybrid (dense + EN/VI BM25, RRF) | mMiniLM | current prompt | on | RAG service |
| **B4** | as B2 | mMiniLM | current | **off** | RAG service |
| **E2E-K** | as B2 + multi-query planning | mMiniLM | current | on | production API, *Knowledge* mode |
| **E2E** | as E2E-K, after the router plans the task | mMiniLM | current | on | production API, *Auto* mode (the UI default) |

Common settings:

- **Corpus state.** Only the English PDF is active in the knowledge base; the Vietnamese PDF is deactivated. Answers are always in Vietnamese.
- **Role.** Normal cases run as `employee`, the only role allowed to read the policy. The *admin* role bypasses document ACLs and would see unrelated uploads.
- **RBAC cases.** Run as `finance_analyst`.
- **Multi-turn cases.** The three multi-turn cases (F01–F03) need conversation history, so they run only through the API arms.

Arms B3 (BGE reranker), B5 (old prompt only) and B6/B7 (GPT-OSS answer models) were planned but not run, to save provider quota.

## 4. Scoring

**Deterministic metrics.** No model is involved.

- **Retrieval.** Recall@5, Full evidence@5, MRR and nDCG@10 at page level over the policy's evidence pages.
- **Citation precision.** The share of cited chunks that lie on a gold evidence page.
- **Strict key points.** The share of the case's key points found verbatim in the answer. Number spellings such as 1.000 and 1,000 are normalised.
- **Refusal.** Correct abstention on the 12 should-decline cases; false abstention on answerable cases.
- **Verifier blocks.** Answers withheld by the claim verifier.
- **RBAC leaks.** Any policy chunk returned to an unauthorised role.

**LLM judge.** The judge marks each answer correct, partial or incorrect against the reviewed reference answer. It also scores key-point coverage, which allows translated wording, and faithfulness to the cited pages. Two independent judges graded every answer:

- **Judge A.** `openai/gpt-oss-120b` on Groq. It read the policy text of the gold pages and the cited pages.
- **Judge B.** A Codex agent. It graded from the question, reference answer and key points only. Its faithfulness labels are therefore discarded.
- **Agreement.** The two judges agree on correct versus not correct in 90.5% of 348 shared verdicts (Cohen's κ = 0.81). The disagreements are mostly closed-book answers that give generic best practice: Judge A accepted them more often.
- **Human check.** On a stratified sample of 20 verdicts, both judges agree with the human grade on correct versus not correct in 18/20 cases (κ = 0.80 each). Judge A's two errors were both over-strict on correct translations: "hàng quý" for "quarterly", and "Security lead" for "trưởng Bảo mật". Neither judge accepted a wrong answer in the sample.

**Statistics.** Arms are compared on the same cases with an exact two-sided McNemar test on correct versus not correct. The 95% CI of the accuracy difference uses 10,000 paired bootstrap resamples. RBAC cases are scored by the leak rule, not by the judge.

## 5. Results

### 5.1 Answer quality

| Arm | Correct (A) | Correct (B) | Correct or partial (A) | Key-point coverage (A) | Faithful (A) | Citation precision | Correct refusals | False refusals |
|---|---|---|---|---|---|---|---|---|
| B0 closed-book | 24% | 11% | 27% | 18% | — | — | 7/12 | 51% |
| B1 naïve RAG | 34% | 37% | 46% | 37% | 48% | 67% | 12/12 | 51% |
| **B2 tuned pipeline** | **59%** | **58%** | 68% | 61% | **79%** | **89%** | **12/12** | 30% |
| B4 (no verifier) | 58% | 59% | **73%** | 63% | 76% | 84% | 12/12 | **25%** |
| E2E-K (API, Knowledge) | 57% | 56% | 65% | 57% | 71% | 89% | 9/9 | 35% |
| E2E (API, Auto) | 44% | 39% | 54% | 46% | 73% | 85% | 9/9 | 25% |

How to read the table:

- **Denominators.** About 69–72 judged answers per arm, which excludes crashed or skipped cases.
- **API arms.** The API arms have 9 should-decline cases because the RBAC cases run only in-process.
- **RBAC.** No arm leaked policy content to the unauthorised role (0/3).

### 5.2 Retrieval (in-process arms)

| Arm | Recall@5 | Full evidence@5 | MRR | nDCG@10 |
|---|---|---|---|---|
| B1 dense only | 0.32 | 0.28 | 0.26 | 0.26 |
| B2 / B4 translated hybrid + mMiniLM | **0.72** | **0.61** | **0.73** | **0.66** |

B2 and B4 retrieve identically; they differ only after generation.

### 5.3 Paired comparisons (correct vs not correct)

| Comparison | Judge A: Δ accuracy [95% CI], p | Judge B: Δ accuracy [95% CI], p | Conclusion |
|---|---|---|---|
| B0 → B2 (adding retrieval) | +36 pts [+23, +49], p < 0.001 | +46 pts [+33, +58], p < 0.001 | RAG is necessary |
| B1 → B2 (hybrid + rerank + prompt) | +25 pts [+13, +36], p = 0.0005 | +20 pts [+9, +32], p = 0.003 | The tuned pipeline is clearly better |
| B4 → B2 (adding the verifier) | +1 pt [0, +4], p = 1.0 | −1 pt [−4, 0], p = 1.0 | No measurable accuracy effect |
| B2 vs E2E-K (multi-query, API) | 0 pts [−7, +7], p = 1.0 | 0 pts [−4, +4], p = 1.0 | Same quality |
| E2E vs B2 (router in Auto mode) | −17 pts [−30, −3], p = 0.035 | −21 pts [−35, −8], p = 0.007 | **Auto mode loses quality** |
| E2E vs E2E-K (Auto vs Knowledge) | −12 pts [−26, +3], p = 0.17 | −16 pts [−29, −3], p = 0.043 | Knowledge mode is better |

Every conclusion has the same direction under both judges.

## 6. Error analysis

### 6.1 Why the tuned pipeline still refuses answerable questions (B2, 18 of 60)

| Cause | Cases | Examples |
|---|---|---|
| Gold page not in the top 5 | 8 | L11, C05, C06, M04, M05, X06, X07, P02 |
| Only part of the evidence retrieved | 4 | L09, M01, M06, U01 |
| Gold page retrieved, but the model said the context was insufficient | 4 | E01, P01, X05, G01 |
| Verifier block although the evidence was retrieved | 1 | L02 |
| Chit-chat answered as "insufficient" (no router in this arm) | 1 | H01 |

**Retrieval is the main limit.**

- Unrelated uploads visible to the `employee` role compete for the top 5:
  - an inventory manual from another dataset;
  - an annual-report template;
  - an unrelated PDF;
  - a receipt image.
- In L01 this produced a wrong answer: the document code of a different policy.
- Both no-diacritics questions failed at retrieval.

### 6.2 Verifier

The verifier withheld 4 answers in B2:

- 1 answer had a genuine unsupported claim, which matches M01 in B4 being judged unfaithful.
- 3 were mechanical false blocks:
  - Two partial answers ended with an uncited sentence saying the sources do not cover the rest. The current prompt explicitly allows this sentence, but the verifier rejected the whole answer as `uncited_or_oversized_draft`.
  - One audit response failed JSON schema validation (`ValidationError`).

Separately, in one case (M03) the model cited a source ID that does not exist (`[S7]` with five sources). The service raised an exception, which the API returned as HTTP 503.

### 6.3 Router (Auto mode)

The quality drop from Knowledge to Auto mode comes from two steps that only Auto mode has.

1. **Final synthesis rejects computed numbers.** A guard requires every number in the final answer to appear literally in the sources or the question. Correct, verifier-checked results such as `3 × 18,000,000 = 54,000,000` fail this guard. The router then returns raw English excerpts ("Evidence fallback") instead of an answer. This happened in 7 cases: X08, T08, C03, C04, M03, E05 and G01. In calculation questions, Auto mode was correct in 1 of 8 cases (judge A), against 5 of 8 for B2.
2. **Task rewriting can drop inputs.** In C01 ("4 employees … maximum total?"), the answer gave the per-person limit without the multiplication. This is consistent with the planner's rewritten task question losing "4 employees". This is inferred: the rewritten question is not logged.

The three remaining Auto-mode failures (N01, N02, H01) were HTTP 403 for the employee role. These are data-flavoured or chit-chat questions, likely planned as SQL tasks that the role may not run (inferred, not traced). Multi-turn handling worked: both follow-ups and the topic switch were answered correctly.

### 6.4 Closed-book baseline

Without documents, the model answered 11–24% correctly, depending on the judge. These are cases where generic good practice coincides with the policy, for example "verify a supplier's bank-account change independently" and "never log passwords or tokens". Every question that needed a policy-specific figure or approver failed. The value of retrieval is therefore the 35–46 point gain over this baseline, not the absolute accuracy.

## 7. Fixes and re-measurement [pending]

Commit `f88613d` (deployed 5 November) addresses the mechanical failures found above. It does not tune on the test answers.

| Fix | Targets |
|---|---|
| Unknown or missing citations return the standard "cannot verify" message instead of HTTP 503 | M03 crash |
| The verifier accepts a closing note that the sources do not cover part of the question, only if every closing sentence is such a number-free note | False blocks on partial answers (L02, M06) |
| One retry of a malformed verifier audit before failing closed | `ValidationError` block (M01) |
| Final synthesis accepts numbers that are results of exactly checked equalities; operands must still be sourced | Evidence fallback on calculations (Auto mode) |
| Planner instruction to keep every number, amount and quantity in task questions | Dropped inputs (C01) |

The after-fix runs of B2, E2E and E2E-K are being collected and will be scored by both judges **[pending: table]**.

Because the fixes were motivated by failures on this set, any after-fix gain partly reflects fitting to these 76 cases. The before/after table should be read as confirmation that the identified defects are removed, not as an unbiased estimate of improvement.

## 8. Limitations

- **Size.** With 76 cases, overall accuracy has a CI of roughly ±11 points. Most groups have 1–8 cases and are reported as counts, not rates.
- **Single document.** All questions come from one policy. A second corpus (an inventory set, 80 cases) exists from earlier work but was not re-run here.
- **Corpus state.** Only the English PDF is active, so Vietnamese answers are translations. Strict key-point matching, which uses the Vietnamese wording, under-counts correct answers (48% strict vs 61% judged for B2). The effect of activating the Vietnamese PDF was not measured.
- **LLM judges.** The judges are LLMs, and Judge B did not read the source pages. The human agreement check covers only 20 verdicts.
- **Provider quota.** Some API runs hit Groq rate limits; affected cases were re-run. Latency figures from these runs are not used. Clean latency after the fixes will be re-measured on V1–V6 and a 15-case Auto-mode subset [pending].
- **Authorship.** The questions were drafted with an AI assistant and reviewed by one team member.

## 9. Recommendations

1. **Remove unrelated uploads from the employee scope.** This is the cheapest retrieval improvement, and it fixes L01-type errors.
2. **Default the chat UI to Knowledge mode** for policy questions until Auto mode matches it on this set. Re-check after `f88613d`.
3. **Improve recall for no-diacritics and partial-evidence questions.** Options are accent restoration before BM25, or more candidates before reranking. Measure any such change on a new held-out set, not this one.
4. **Keep the verifier but monitor its block reasons.** It currently adds no measurable accuracy but blocks some unsupported claims. Its value depends on false blocks staying rare.
5. **Return a polite refusal instead of HTTP 403** when Auto mode plans a SQL task for a role without analytics permission.
