# Handoff: 12–13 Nov 2026 session (desktop → laptop)

The report is still **frozen as of 12 Nov**. Everything below is post-freeze work and was not evaluated.

## 1. Start here on the laptop

```bash
git fetch origin
git switch Huy && git pull
git merge origin/main          # Huy does not have the UI redesign yet; main does
PYTHONPATH=src uv run --with pytest pytest tests -q --continue-on-collection-errors
```

The known pre-existing failures are the baseline: 39 failed and 25 errors. Three failures in `test_retrieval_service` appear only when a local `.env` with Groq keys exists. Run only `tests/`, because `artifacts/.../test_bundle.py` shadows `core`.

## 2. What is live in production (main)

The web UI was redesigned and pushed to main. Vercel serves it.

| Commit | What |
|---|---|
| `4f0a739` | Ink & jade redesign. Every colour in `styles.css` is now a token (dark mode is a token swap). Be Vietnam Pro font. Icon theme toggle with a circular reveal. Inline `S1` chips that jump to their source. Green "Every claim checked" seal. Latency in seconds. |
| `b0e10f6` | Sidebar collapses without jumps. Copy and 👍/👎 icon row. Inline feedback card (reason chips and a note) replaces `window.prompt`. Padded access matrix. Full-height file picker. |
| `d3adad5` | Knowledge Q&A is question-first (layout B). The report agent folds under the answer. Sidebar footer rows match the nav. Monitoring sub-tabs (By agent / Recent runs / Answer ratings). Icons replace the rating emoji. Motion only on user actions. |
| `2f917a0` | Liquid glass on the control layer (sidebar, composers, monitoring tabs, phone bar) over soft jade/amber fields. Solid fallback for reduced transparency. |
| `9a5d157` | Feedback buttons light up instantly. The save runs in the background and is undone, with a message, if it fails. |

Files touched: `src/app/static/{index.html,styles.css,redesign.css,app.js}` only. No backend change.

**Rollback (old design):** branch `backup/ui-before-redesign-20261112` = `ed2f81c`, the exact production state before the redesign.
1. Fastest: Vercel dashboard → Deployments → the deployment before `2f917a0` → Instant Rollback.
2. UI files only: `git checkout backup/ui-before-redesign-20261112 -- src/app/static && git commit -m "ui: restore pre-redesign design" && git push origin HEAD:main`.
3. Full revert: `git revert --no-edit ed2f81c..9a5d157 && git push origin HEAD:main`.

**Design rules used** (keep them for further UI work):
- Jade = verified, amber = gap or partial, red = errors only.
- One font family.
- Glass only on navigation and controls; content stays solid.
- No all-caps labels and no fake numbering.
- Motion only in answer to a click, plus the answer's own reveal.

## 3. Things to tell or check

- **Teammate:** General Chat (their tab) now has the new styling. Only CSS changed; its markup and logic are unchanged.
- **Inventory:** the "Open inventory view" card was removed along with the agent cards. It was already broken, because it set agent mode `dashboard`, which is not an option in the picker, so it sent an empty mode. Ask whether an Inventory route should be added to "Route to".
- **Not screenshotted:** the Upload, Invoice Review, Processing and Upload Test tabs. They get the new tokens automatically, but look at them in both themes.
- **No true refraction:** liquid glass is frosted blur plus highlights. Real refraction needs a Chromium-only SVG filter.
- **Feedback save is slow on the server:** each rating opens a new Supabase connection (`_record_feedback` → `AnswerFeedbackRepository`), about 1 s. The UI hides it now. A proper fix is connection reuse (backend).
- **`answer_feedback` migration** (`supabase/migrations/20261113090000_answer_feedback.sql`): ratings were clicked in production, so it is probably applied. Confirm in Supabase that rows exist.

## 4. Open issues (backend, from earlier in the session)

- When Auto collapses a documents-only plan and history exists, it uses `plan.objective`, which can drop a part. Idea: use the user's exact words when the question stands alone (`src/core/agents/router.py` `_plan`).
- A stray `[S1]. [S2].` after the full stop in some answers (cosmetic).
- Run details shows only the last attempt; per-attempt reasons would help.
- Occasional ~30 s latency under server load (reranker threads already capped at 2).

**Follow-up test** (Auto, one conversation, no "New conversation" in between):
1. "Đi công tác thì hạn mức tiền khách sạn mỗi đêm là bao nhiêu?" → 1.800.000 / 2.500.000 VND (p.12)
2. "Khoản mua sắm 80 triệu cần ai duyệt?" → stands alone; Trưởng bộ phận + Mua sắm + Tài chính
3. "Còn 3 triệu thì sao?" → must resolve to a 3 million purchase → quản lý trực tiếp (≤ 5.000.000)

## 5. Plan for the next days (mentor checklist)

- Memory footprint (`docker stats` on the VPS).
- Load test.
- CI green.
- UAT / SUS.
- Ask the mentor about the 6-chapter template.
- Slides: fonts ≥ 36 px, ≤ 25 slides.
- Add the newer post-freeze items to the future-work note in `huy-code-review-and-plan-20261113.md` §3b:
  - strict citation rule;
  - restored question to the model;
  - restored dense search;
  - documents-only collapse;
  - most-recent-turn follow-up rule;
  - the UI redesign.

## 6. Local UI demo (try UI changes before pushing)

`scripts/ui-demo/` serves any copy of `src/app/static` with a fake API: signed in as admin, a canned Vietnamese handover answer, monitoring data and an access matrix. No backend or keys needed.

```bash
python3 scripts/ui-demo/demo_server.py src/app/static 8766          # open http://localhost:8766/
DEMO_STAGE_SECONDS=0 python3 scripts/ui-demo/demo_server.py src/app/static 8766   # instant stream, for screenshots
DEMO_FEEDBACK=slow|fail ...                                          # test the feedback save paths
# to compare with production: git worktree add ../ekai-main origin/main, then serve ../ekai-main/src/app/static on 8765
```

- **Screenshots:** `scripts/ui-demo/shots.sh <port> <prefix>` drives **Windows Edge** headless (the WSL Chromium lacks system libraries).
- **Phone width:** use `/phone.html`. Edge will not make a window narrower than ~477 px, so phone width is shown in a 390 px iframe.
- **URL options:** `?shot=answer|chat|chat-empty|feedback|monitor|ratings|access|report|collapsed|home` and `&theme=light|dark`. On the laptop, change the Edge path and the `C:\Users\Admin\...` temp path in `shots.sh` if they differ.
