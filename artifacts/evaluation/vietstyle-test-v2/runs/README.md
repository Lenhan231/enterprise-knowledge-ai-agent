# Test set 2 runs: before and after the improvements

Raw evidence for report Section VI.1.10 (Table 6.9). Questions: `../questions.json` (40 cases, locked before any code change).

| File | Contents |
|---|---|
| `B2-before.json`, `B2-after.json` | Tuned RAG (pipeline called in-process), improvements off / on |
| `E2E-K-before.json`, `E2E-K-after.json` | Knowledge mode through the API, improvements off / on |
| `*.scored.json` | Scored with Judge A (gpt-oss-120b) plus deterministic metrics (`scripts/agents/score_vietstyle_arm.py score`) |
| `judge-verdicts-claude-testv2-*.jsonl` | Judge C (Claude subagent) verdicts |
| `judge-verdicts-codex-testv2-*-iso.jsonl` | Judge B (Codex) verdicts, graded in a separate workspace holding only the prompts |
| `flags-off-01.json`, `flags-on-01.json`, `flags-on-02.json` | V1–V6 latency on 10 Nov 2026, improvements off / on, same session (`scripts/operations/measure_pipeline_latency.py`) |
| `flags-on-threads2.json` | Same, with the reranker limited to two threads (`RERANKER_THREADS`, default 2) |

"Improvements" = `KNOWLEDGE_TOP_K=8`, `KNOWLEDGE_CONTEXT_RADIUS=1`, `QUERY_NORMALIZATION_ENABLED=1`, `KNOWLEDGE_COMPLETENESS_RULE=1`, `KNOWLEDGE_AUDIT_MAX_OUTPUT_TOKENS=1536`, `KNOWLEDGE_CONTEXT_MAX_CHARS=20000` (main commits e7fd295, 4e4bc02, 4b725d0). The judge prompts are not stored; regenerate them with `score_vietstyle_arm.py export`.
