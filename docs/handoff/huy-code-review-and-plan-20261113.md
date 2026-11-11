# Code changes on 12 Nov (streaming, typing, run details) and the plan for 13 Nov

See all code changes in one diff:

```bash
git diff b737541 578de96 -- src tests          # on branch Huy
git log --oneline b737541..578de96             # the five commits
```

On main the same changes are commits ca080bf, 84ada9a, 80b4e4a, 959bbe2, e3416d9.

## 1. Streaming stage progress (c6e7e10)

**Problem.** The UI showed one fixed message for 10–20 s. The mentor's checklist (1.2) asks for a streaming response.

**Design.** The answer is not streamed token by token, because the claim verifier may withhold it. The server streams *which stage is running*, then sends the answer once, after verification.

| File | Change |
|---|---|
| `src/core/latency.py` | New `stage_listener` ContextVar. `measure(stage)` calls the listener with `(stage, "started")` and `(stage, "completed"/"failed")`. When no listener is set, behaviour is unchanged. |
| `src/app/agents.py` | New route `POST /api/agents/chat/stream`. It runs the existing `agent_chat()` unchanged in a task, with a listener that pushes events into an `asyncio.Queue`. Stages run on worker threads (`asyncio.to_thread` copies the context, so the listener comes along), so events go back to the loop with `loop.call_soon_threadsafe`. The response is `text/event-stream`: `event: stage` lines, then one `event: result` (the same JSON as `/chat`) or `event: error`. `X-Accel-Buffering: no` stops Nginx from buffering. If the client disconnects, the task is cancelled. |
| `src/app/static/app.js` | `askAgentStream()` reads the stream with `fetch` and `ReadableStream`, parses the SSE blocks and updates the status line (`STAGE_STATUS` maps stage → message). If the stream fails before the answer arrives, the UI falls back to `POST /api/agents/chat`. |
| `tests/test_chat_stream.py` | Event order, including a stage that runs in a worker thread; error path returns 503 as an `error` event. |

Mentor questions (backend/frontend streaming; dropped connection; buffer overflow):
- **Dropped connection:** the UI re-asks via `/chat`, which costs one extra run.
- **Buffer:** the queue holds only small stage events, about 12 per request, plus one result.
- **Proxy buffering:** disabled by the header.

## 2. Typing effect (eb8dae6, 43b752d, f095cfa)

`typeOutText(element, revealAfter)` in `app.js`:
- The answer is rendered in full first. Then only its **text nodes** are blanked and refilled with `requestAnimationFrame`, so bold, lists and `[S1]` links stay intact.
- Speed is about 60 characters a second, 3–10 s in total.
- The source cards (`.citations`, then each `.citation`) stay hidden and fade in one by one afterwards. The CSS rule is at the end of `styles.css`.
- It is skipped when the OS "reduce motion" setting is on.
- It runs only once per new answer (`turn.typeOut`).
- Copy still copies the full answer.

## 3. Run details (578de96)

| File | Change |
|---|---|
| `src/core/agents/knowledge_agent.py` | `metadata["search"]` = lexical queries (VN/EN), reranker candidate count, passages given to the model, reranker model, context radius. It is taken from the first context, so it is present even when nothing is cited (withheld answers). |
| `src/app/static/app.js` | `renderRunDetails(data)` shows: route and task trace; "Searched as" VN/EN; passages (candidates → given → cited); claim check in plain words (`VERIFICATION_REASONS`); time per stage from `metadata.latency`. |
| `tests/test_knowledge_outcomes.py` | `metadata["search"]` is kept when nothing is cited. |

Tests: the full suite has 810 passed, with the same 39 failures and 25 errors as main. Run it as `PYTHONPATH=src uv run --with pytest pytest tests`.

## 4. Mentor's Review 3 checklist: status

| Item | Status | Evidence / gap |
|---|---|---|
| 1.1 UI input (text, PDF/DOCX upload) | done | image/video/voice input not supported: say it is out of scope |
| 1.2 Streaming | done 12 Nov | stage streaming + typed answer; explain why not raw tokens |
| 1.3 Source highlight, history, **thumbs up/down** | partial | source cards and run details done; **no feedback buttons** |
| 1.4 Optimisation (INT8/ONNX…) | partial | reranker INT8 vs FP32 measured, thread cap; no LLM-side (Groq hosted) |
| 1.5 Before/after benchmark: latency, **memory**, accuracy | partial | latency + accuracy done; **memory footprint missing** (`docker stats`) |
| 1.6 Citations, context window, guardrails | partial | citations + claim verifier + injection questions; context budget `KNOWLEDGE_CONTEXT_MAX_CHARS`; conversation memory? |
| 2.1 CI/CD with history | weak | `.github/workflows/ci.yml` exists; recent runs on main fail; no CD |
| 2.2 docker-compose | done | |
| 2.3 Monitoring | partial | admin agent-monitoring page (runs, latency, p95); no Prometheus/Grafana |
| 3.1 Unit/integration tests | partial | 810 pass, 64 fail/error (stale tests) |
| 3.2 Load test (Locust/k6) | **missing** | `scripts/operations/evaluate_api_load.py` exists; no report |
| 3.3 UAT (SUS/CSAT) | **missing** | |
| 4 Thesis 6 chapters, 60–100 pages, plagiarism check | open | FPT I–IX layout vs 6 chapters: ask the mentor |
| 5 Slides 20–25, 18 pt minimum | open | 26 slides; font sizes must be ≥ 36 px |

## 5. Plan for 13 Nov (Huy), in order

1. **Deploy and check (15 min).** On the VPS: `git pull && docker compose up -d --build backend-api`. Test streaming, typing and run details in the browser. Run the curl stream check from the chat log.
2. **Thumbs up/down (1.3, ~1 h).** Two buttons per answer, `POST /api/agents/feedback`, stored in the existing agent-run table or a small new table, shown on the monitoring page. Small and visible in the demo.
3. **Memory footprint (1.5, 15 min, no quota).** `docker stats --no-stream` with the reranker FP32 vs INT8 and the embeddings container → one table row each for the report and slides.
4. **Load test (3.2, ~1.5 h, uses Groq quota).** Use `evaluate_api_load.py`, or Locust with 1/3/5 concurrent users on 2–3 known questions. Report concurrent users, RPS, average/p95 time, failure rate. Run when quota is fresh; 5 users × a few minutes ≈ 100–200 Groq calls.
5. **CI green (2.1, ~1 h).** Make `ci.yml` run only the tests that pass (or mark stale tests skip with a reason), so the history shows green runs; optional CD step that builds images.
6. **UAT/SUS (3.3).** Prepare a 10-question SUS form (Google Form) and ask 5–10 classmates to try the demo. Needs people, so start early.
7. **Ask the mentor:** FPT I–IX template or 6 chapters? This decides how much the report needs restructuring.
8. Slides: raise fonts to ≥ 36 px and trim to ≤ 25 slides (after Nhân/An add results).

Not urgent / skip if short on time: Prometheus/Grafana (the monitoring page covers the basics), voice/image input.
