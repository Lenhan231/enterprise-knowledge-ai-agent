# Code map: what changed on 12–13 Nov (branch Huy; the same code is on main)

All changes since the merge of main into Huy:

```bash
git diff b737541 HEAD -- src tests supabase
```

## A. Streaming and UI

| What | File:line |
|---|---|
| Stage listener hook (announces start and end of each stage) | `src/core/latency.py:10`, used in `measure()` at `:26` |
| SSE route `POST /api/agents/chat/stream` | `src/app/agents.py:224` |
| Frontend reads the stream, with fallback to `/chat` | `src/app/static/app.js:1428` `askAgentStream()`; stage messages `:1412` `STAGE_STATUS` |
| Stage text fades between stages | `app.js:1300` `swapStageText()`; called from `showStage` `:1941` |
| Stage text pulses | `src/app/static/styles.css:663` `stagePulse` |
| Typing effect, then source cards fade in | `app.js:1378` `typeOutText()`; triggered by `turn.typeOut = true` `:1958`; card fade `styles.css:662` |
| Run details panel | `app.js:1335` `renderRunDetails()`; labels `:1317` |
| Search details attached to Knowledge results | `src/core/agents/knowledge_agent.py:84` `metadata["search"]` |

## B. Thumbs up/down feedback

| What | File:line |
|---|---|
| Table (run once in the Supabase SQL editor) | `supabase/migrations/20261113090000_answer_feedback.sql` |
| Repository | `src/core/database/answer_feedback_repository.py:13` |
| `POST /api/agents/feedback` | `src/app/agents.py:184` (request model), `:206` (route) |
| `GET /api/admin/answer-feedback` | `src/app/main.py:1301` |
| Buttons on each answer | `app.js:1258` `attachFeedback()` |
| Monitoring page list | `app.js:1293` `renderAnswerFeedback()`, loaded at `:1223`; markup `index.html:451` |
| Static cache version | `index.html:458` (`?v=feedback-20261113b`) |

## C. Auto mode

| What | File:line |
|---|---|
| A single Knowledge task's answer passes through unchanged (verified, withheld or no match) | `src/core/agents/response.py:64` |
| Number guard ignores list numbering | `response.py:47` `_LIST_MARKERS` |
| A documents-only plan split into several Knowledge tasks is merged into one | `src/core/agents/router.py:166` |
| A lone Knowledge task gets the user's own words (unless it is a follow-up) | `router.py:172` |
| Planner flag `uses_context` | `src/core/models/agent_plan.py:30`; prompt `src/core/prompts/agents.py:7` |
| Prompt rules: one task for a documents-only question; resolve follow-ups against the most recent turn | `prompts/agents.py:20`, `:22` |

## D. Knowledge answer and retrieval

| What | File:line |
|---|---|
| Strict citation rule text (flag `KNOWLEDGE_STRICT_CITATION_RULE=1`) | `src/core/prompts/Knowledge.py:47` |
| Rule applied | `src/core/rag/rag_service.py:256` |
| Answer model and verifier get the accent-restored question | `rag_service.py:260` |
| Second dense search on the restored text | `src/core/retrieval/methods/translated_hybrid.py:23` (`embed` parameter), `:43` (4 workers), `:67` (start it), `:99` (fuse with the raw dense list) |
| Embedder passed in | `src/core/retrieval/retrieval_service.py:110` |

## Tests

| Covers | File |
|---|---|
| Streaming | `tests/test_chat_stream.py` |
| Feedback | `tests/test_answer_feedback.py` |
| Auto mode (pass-through, list numbers, own question, follow-ups, merge into one task) | `tests/test_orchestration_contracts.py` |
| Strict rule, restored question | `tests/test_knowledge_flags.py` |
| Search details | `tests/test_knowledge_outcomes.py` |
| Restored dense search | `tests/test_translated_hybrid.py` |

Run the tests with:

```bash
PYTHONPATH=src uv run --with pytest pytest tests
```

The expected baseline is 39 failures and 25 errors, all of which also occur without these changes.

## Not yet done

- Apply the feedback migration in Supabase.
- Set `KNOWLEDGE_STRICT_CITATION_RULE=1` in the VPS `.env` if you want the strict rule.
- A documents-only question that the router merges into one task uses the planner's objective when there is conversation history. Use the user's exact words when the question stands alone.
- Evaluate all of these on the dev set. The report is frozen, so all of this is future work.
