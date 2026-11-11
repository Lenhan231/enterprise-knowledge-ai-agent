# Handoff — Huy's evaluation work, state on 7 Nov 2026

For a new Claude/Codex session: read this first, then `docs/report/huy-gdoc-paste-20261105.en.md` (report text) if needed.

## Working rules (from Huy)
- Reply in English; Vietnamese only when asked. The report is English.
- Huy runs every VPS command (`root@147.93.171.214`, repo `/opt/enterprise-knowledge-ai-agent`); give exact commands, he pastes output.
- Never print or send keys, DSN or `.env` contents. Do not change VPS env unless asked.
- Git flow: commit on `Huy` → push → cherry-pick only the needed `src`/`tests` commits onto `main` → push. No artifacts on main, no Co-Authored-By lines, no history rewrites. Run the full test suite and diff failures against a baseline worktree before pushing (≈63 failures pre-exist).
- Benchmarks: save Groq quota (TPD 200k per org); never overwrite run outputs, use new file names; stop on daily rate limits.
- Locked datasets are never edited after a run. The Google Doc report is shared: edit only Huy's parts.

## What happened this session
1. **Test set v2 locked**: `artifacts/evaluation/vietstyle-test-v2/questions.json`, 40 questions, reviewed-r2, sha256 `82299af40be4875672309e96d14348a5b3929552f45ca16118f4004196843f61` (Codex cross-review + Huy check). Written before the code changes below.
2. **Knowledge improvements on main** (`e7fd295`, `4e4bc02`), all behind env flags, default OFF:
   - `KNOWLEDGE_TOP_K=8` (default 5)
   - `KNOWLEDGE_CONTEXT_RADIUS=1` — same-page neighbour chunks after rerank, ACL rechecked, duplicates dropped
   - `QUERY_NORMALIZATION_ENABLED=1` — translator restores Vietnamese accents; used for VN BM25 and reranking
   - `KNOWLEDGE_COMPLETENESS_RULE=1` — prompt rule 11 (answer every part)
   - `KNOWLEDGE_AUDIT_MAX_OUTPUT_TOKENS=1536` (default 768)
   - Always on: Auto-mode synthesis number guard accepts "18 triệu"/"4tr5" and units between operands.
3. **Smoke test on VPS with all flags on** (dev X06, M04, L04): flags work; X06 unaccented question now retrieves the right page. M04 withheld (`uncited_or_oversized_draft`) — known retrieval miss (approval matrix p.19 / quotes p.18 not retrieved), not a regression.
4. **Flags removed again on VPS**; the **test v2 "before" run** was started overnight (B2 then E2E-K) → `artifacts/local/knowledge-latency/vietstyle-test-v2/runs/{B2,E2E-K}-before.json`, log `testv2-before.log` on the VPS.
5. Notion "Issues" page updated by Codex (16 entries). Slides: https://claude.ai/artifact/GWyieuFzmd1NLZhDsfk5Vv (24 + 2 backup, FA26AI48 branding; private until shared).

## Progress on 7 Nov (afternoon)
- Test v2 **before** (flags off) and **after** (5 flags on) runs done for B2 and E2E-K; all 40 rows clean. Local copies: `artifacts/local/vietstyle-runs/testv2/` (raw runs, Judge A `*.scored.json`, Judge B `judge-verdicts-codex-testv2-{before,after}-iso.jsonl`, Judge C `judge-verdicts-claude-testv2-{before,after}.jsonl`). Judges B and C ran in isolated scratch folders (only the prompts) after the first Codex before-run matched Claude 74/74; the isolated rerun matched too, so the agreement is genuine. The first non-isolated Codex file (`judge-verdicts-codex-testv2-before.jsonl`) is not used.
- **Result (majority of 3 judges, correct):** B2 20/36 (56%) → 25/36 (69%), 7 gained / 2 lost, McNemar p = 0.18. E2E-K 22/38 (58%) → 27/38 (71%), 5 gained / 0 lost, p = 0.06. B2 Recall@5 0.81 → 0.87, MRR 0.75 → 0.79, key points 61 → 64%, citation precision 87 → 82%, false abstention 22 → 25%.
- Gains: Q35 unaccented (accent restoration), Q09/Q15/Q19/Q36 partial → correct (completeness + context), Q24 (audit budget, was ValueError), Q26 (top-k/context). Losses (B2): Q14 withheld `uncited_or_oversized_draft` (longer answers trip the verifier), Q10 verifier `insufficient`. All remaining wrong answers are declines, none confidently wrong → the verifier is now the main limit.
- Test v1 **after** runs done on the VPS (`/benchmarks/vietstyle-test-v1/runs/{B2,E2E-K}-after.json`). B2 **Q12 fails twice with APIStatusError** (looks deterministic) — print the row's `error` text: if 400 (context length / generation failure) it is a real bug from the larger context; if 429/503 just retry. E2E-K had no "before" on test v1, so report it unpaired.
- Latency in these runs is not usable (benchmark shares the CPU reranker); measure separately on an idle server, flags on vs off, with `scripts/operations/measure_pipeline_latency.py`.
- VPS `.env` currently has the 5 flags ON.

## Progress on 8 Nov — results complete
- Groq's on-demand tier rejects one request over 7,000 input tokens; with the flags on, test v1 Q12 hit 413. Fix on main `4b725d0`: `KNOWLEDGE_CONTEXT_MAX_CHARS` (default 24000); VPS `.env` now has `KNOWLEDGE_CONTEXT_MAX_CHARS=20000` plus the 5 flags. Only test v1 B2 Q12 was rerun under the 20000 budget.
- Test v1 after runs scored by 3 judges (local: `artifacts/local/vietstyle-runs/testv1/`; B/C isolated verdicts copied there).
- **Final results (majority of 3 judges, correct):**
  | | Before | After |
  |---|---|---|
  | Test v1 B2 | 19/28 (68%) | 21/28 (75%) |
  | Test v1 Knowledge | no complete run | 22/29 (76%) |
  | Test v2 B2 | 20/36 (56%) | 25/36 (69%) |
  | Test v2 Knowledge | 22/38 (58%) | 27/38 (71%) |
  - **Pooled B2, 64 paired questions:** 9 gained / 2 lost, McNemar p = .065, difference +10.9 points (95% bootstrap CI +1.6 to +20.3).
  - Test v1 B2 MRR 0.81 → 0.85, key points 66 → 74%, citation precision 92% unchanged.
  - Report wording: consistent ~11-point improvement, borderline significant.
- Caveats for the report: v1 "before" = production config of 6 Nov (b616744); Judges B and C agree very closely (treat as two strong judges plus A as check).
- Next: draft report section VI.1.10 + before/after table, fill [pending] lines, slide 21, Notion; decide keeping flags on in production (recommended, with 20000 budget); optional idle-server latency on vs off.

## Progress on 8–9 Nov — multi-part retrieval attempt (dev set only)
- Report text for VI.1.10 / Table 6.9 drafted: `docs/report/huy-gdoc-paste-20261108.en.md` (not yet pasted into the Google Doc). Add a note there: Knowledge mode "after" runs used 5 passages per search (multiquery capped unsplit searches at 5; fixed in `5a178f1`).
- `RAGResult.withheld_draft` added (diagnosis only). Dev analysis: most withheld drafts lacked the evidence page, so the main limit is retrieval of multi-part questions, not the verifier.
- Tried on dev (`B2-MQ` arm, decompose=True, `KNOWLEDGE_MULTIQUERY_MAX=3` + accent prompt "hủy PO" fix): page recall 0.758 → 0.797, full evidence 38 → 39/60, withheld 7 → 8, declined 2 → 4. X07 fixed (accent fix). M01–M04 still unsolved, M06 worse.
- **Decision proposed:** keep the accent prompt fix; do NOT adopt the 3-way split. Huy to remove `KNOWLEDGE_MULTIQUERY_MAX=3` from VPS `.env` and `docker compose up -d backend-api`. Multi-part questions → Future Work. Stop tuning; spend remaining time on report, slides, demo.
- VPS `.env` now: 6 flags ON (`KNOWLEDGE_TOP_K=8`, `KNOWLEDGE_CONTEXT_RADIUS=1`, `QUERY_NORMALIZATION_ENABLED=1`, `KNOWLEDGE_COMPLETENESS_RULE=1`, `KNOWLEDGE_AUDIT_MAX_OUTPUT_TOKENS=1536`, `KNOWLEDGE_CONTEXT_MAX_CHARS=20000`) + `KNOWLEDGE_MULTIQUERY_MAX=3` (to remove).
- Remaining: paste report section, List of Tables 6.6–6.9, PDF export; slides (Nhân/An results, supervisor name, demo questions + fallback video, share link); Notion final results.

## Next steps (older, mostly done)
1. Check the overnight run: `tail -5 /opt/enterprise-knowledge-ai-agent/testv2-before.log`. If it stopped on rate limits, resume per arm with the same command plus `--resume --retry-errors`. The runner is not on main: `git show origin/Huy:scripts/agents/run_vietstyle_arm.py > /tmp/run_vietstyle_arm.py`.
2. scp the two `*-before.json` files to the laptop (`artifacts/local/vietstyle-runs/`).
3. Turn the 5 flags ON in the VPS `.env`, `docker compose up -d backend-api`, then run "after": test v2 (`B2-after`, `E2E-K-after`) and test v1 (`B2-after`, `E2E-K-after`, cases `/benchmarks/vietstyle-test-v1/questions.json`, rbac role `finance_analyst`).
4. Score with three judges (`scripts/agents/score_vietstyle_arm.py`: Judge A gpt-oss-120b on Groq, Judge B Codex via Orca, Judge C Claude subagent), majority vote, pooled McNemar on v1+v2 (~70 paired questions).
5. Report: fill the two remaining [pending] lines (VI.1.9, VII.1), add a before/after table, List of Tables (6.6–6.8+), export PDF.
6. Still pending from before: Knowledge and Auto modes on test v1 with the old configuration (optional now that "after" runs supersede it).

## Progress on 10 Nov — report, slides, latency
- VPS: multiquery flag removed; 6 flags ON; reranker capped at 2 threads (`OMP_NUM_THREADS: ${RERANKER_THREADS:-2}` in compose, main 0304598); UI Relevance badge removed (main 1bd46ca). All deployed.
- Latency (same session, warm medians): flags off 20.6 s, on 17.0 / 13.4 s, on + 2 reranker threads 12.1 s. Reranking dominates; thread test in the container showed 1–2 threads faster than 6 (shared vCPUs). Not the Vietnamese PDF (ruled out with older runs).
- Google Doc: Huy's sections pasted (VI.1.9, VI.1.10 + Table 6.9, VII.1, VII.3, Appendix A) and fixed after a Codex + subagent review (Q39 answered wrongly, overclaims softened, outdated latency/guard/top-5 sentences). Repo copy: docs/report/huy-gdoc-paste-20261108.en.md.
- Run outputs committed on Huy (47e65a6): artifacts/evaluation/vietstyle-test-{v1,v2}/runs/.
- Slides updated (artifact GWyieuFzmd1NLZhDsfk5Vv): supervisors Nguyễn Xuân Huy, Nguyễn Trọng Tài; latency, test set, closing (72%, ≈12 s), demo notes with 3 live-checked questions.
- Open: Nhân/An slide results; List of Tables; Appendix B [Huy TODO]; demo restricted-role + Auto question + fallback video; short wording "5 triệu và 5.000.001 ... về phê duyệt?" is withheld (dev-set tuning backlog, check verifier reason); Notion final results.

## Progress on 11 Nov (laptop) — panel review, report fixes, mentor checklist, streaming plan
- **Simulated panel review** of the Google Doc (academic-paper-reviewer, full mode): **Major Revision**. Full text: `docs/report/panel-review-20261111.md` (roadmap with owners, check attachments). Caveat: all five seats ran in one session; the sprint-contract checkers did not run.
- **Blocking issues:** B1 (title/RQ1 promise parsing + analytics results that are missing) → Nhân/An add results; **cut-off 25 Nov**, else narrow the title, Objective 4 and RQ1. B2 (test-set "used only once", "independent judges") and B3 (access-control claims, three different ACL descriptions) → **fixed in the Google Doc on 11 Nov** (20 replacements + new Table 4.3, revision-locked, verified by re-read). Exact text: `docs/report/huy-gdoc-paste-20261111.en.md`.
- **Also applied:** SG-3 Table 4.3 (experiment registry), SG-4 threat model, SG-5 Groq data paragraph, SG-6 VietStyle is fictional (policy generated by Huy), SG-8 one RQ4 answer (12.1 s).
- **Placeholders left in the Doc:** IV.2 "[Huy: confirm]" (policy generated with an AI assistant?), Table 4.3 reranker row "[Huy: check document version(s)]", IV.7 "[Nhân/An TODO]" invoice path. Optional, not added: VII.3 least-privilege sentence.
- **Human check on test set 2:** blind, stratified, 20 verdicts (`artifacts/evaluation/vietstyle-test-v2/judge-review-20261111.md` + `.key.json`, seed 20261111; scripts `scripts/evaluation/make_human_check_sheet.py`, `score_human_check_sheet.py <folder>`). Majority agreed in 17/20, κ = 0.77; all 3 disagreements = judges stricter (partial vs human correct). Item 5 recorded as đúng (refusal of an out-of-scope question).
- **Slides:** academic-structure deck (new, https://claude.ai/artifact/NAAhHJUGmKzmkCzrKcZ5Gn) now says "0 / 4 role-restricted questions" and "borderline, p = .065"; original deck (GWyieuFzmd1NLZhDsfk5Vv) unchanged. Mentor rule: no text under 18 pt — both decks use 24–28 px (= 12–14 pt), so all text sizes need raising to ≥ 36 px.
- **Mentor's Review 3 checklist** (`kiem-tra-khoi-luong-task-3-truoc-review-lan-3.docx`, 18-item self-assessment with evidence links). Status from the repo: done — Docker Compose (7); partial — UI (1), optimisation (3), latency benchmark but **no memory footprint** (4), citations/guardrails (5), **CI exists but the last 60 runs on main all failed, no CD** (6), tests 701 / ~65 failing (9), thesis ~10.4k words in FPT I–IX layout vs mentor's 6 chapters (12), slides 28 vs 20–25 (14), repo (16), checkpoints (17); not done — **streaming (2), monitoring (8), load test (10), UAT/SUS (11), plagiarism check (13), demo video (18)**. Open question for the mentor: FPT template or 6 chapters?
- **Streaming (Huy's task), decided option C:** stream pipeline stages (retrieving → reranking → writing → verifying) over SSE, then release the answer only after the claim verifier passes, typed out on screen. Reason: generation is ~1 s of ~12 s, and streaming raw tokens would show text the verifier may withhold. Plan: new `POST /api/chat/stream` (FastAPI StreamingResponse, text/event-stream), `app.js` reads the stream with fetch + ReadableStream, Nginx `proxy_buffering off`, fallback to `/api/chat` on a dropped stream, report time-to-first-update vs full answer.
- **Before coding streaming on Huy:** Huy is 157 behind / 119 ahead of main; 90 code files differ (main.py, app.js, agents). Merge origin/main into Huy first — a trial merge showed only one conflict, `artifacts/datasets/vietstyle-operations-vi-v1/VietStyle_Enterprise_Operating_Policy_v1.0_VN.md` (add/add). Then run the suite for a failure baseline, build streaming, cherry-pick src/tests to main.
- Laptop note: `python` was the Windows Store stub; fixed with `uv python install 3.12 --default` + App execution aliases off.
