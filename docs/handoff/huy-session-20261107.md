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

## Next steps
1. Check the overnight run: `tail -5 /opt/enterprise-knowledge-ai-agent/testv2-before.log`. If it stopped on rate limits, resume per arm with the same command plus `--resume --retry-errors`. The runner is not on main: `git show origin/Huy:scripts/agents/run_vietstyle_arm.py > /tmp/run_vietstyle_arm.py`.
2. scp the two `*-before.json` files to the laptop (`artifacts/local/vietstyle-runs/`).
3. Turn the 5 flags ON in the VPS `.env`, `docker compose up -d backend-api`, then run "after": test v2 (`B2-after`, `E2E-K-after`) and test v1 (`B2-after`, `E2E-K-after`, cases `/benchmarks/vietstyle-test-v1/questions.json`, rbac role `finance_analyst`).
4. Score with three judges (`scripts/agents/score_vietstyle_arm.py`: Judge A gpt-oss-120b on Groq, Judge B Codex via Orca, Judge C Claude subagent), majority vote, pooled McNemar on v1+v2 (~70 paired questions).
5. Report: fill the two remaining [pending] lines (VI.1.9, VII.1), add a before/after table, List of Tables (6.6–6.8+), export PDF.
6. Still pending from before: Knowledge and Auto modes on test v1 with the old configuration (optional now that "after" runs supersede it).
