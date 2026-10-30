# Agent benchmark comparison

- **Dataset:** commerce-agent-benchmarks-v1
- **Models:** qwen/qwen3.8-27b (Qwen) and openai/gpt-oss-120b (GPT-OSS 120B)
- **Judge:** Luna 5.6 Medium (Codex CLI)
- **Evaluation configuration:** `{"cases_per_agent": 25, "agents": ["knowledge", "sql", "report"], "metrics": ["faithfulness", "answer_relevancy", "context_precision"], "retry_policy": "one retry for transient failures; two attempts maximum"}`
- **Run date:** Qwen 2026-10-24; GPT-OSS 2026-10-24
- **Source:** The two JSON files linked below only.

## Run completion

| Model | Cases | Completed | Run errors |
|---|---:|---:|---:|
| Qwen 3.8 27B | 75 | 74 | 1 |
| GPT-OSS 120B | 75 | 74 | 1 |

## Overall RAGAS metrics

Means use successfully scored eligible cases; denominators are shown as scored / eligible.

| Model | Metric | Mean | Scored / eligible | Coverage | Score errors |
|---|---|---:|---:|---:|---:|
| Qwen 3.8 27B | faithfulness | 0.5176 | 63 / 63 | 1.0 | 0 |
| Qwen 3.8 27B | answer_relevancy | 0.778 | 74 / 74 | 1.0 | 0 |
| Qwen 3.8 27B | context_precision | 0.4788 | 63 / 63 | 1.0 | 0 |
| GPT-OSS 120B | faithfulness | 0.422 | 66 / 66 | 1.0 | 0 |
| GPT-OSS 120B | answer_relevancy | 0.7632 | 74 / 74 | 1.0 | 0 |
| GPT-OSS 120B | context_precision | 0.492 | 66 / 66 | 1.0 | 0 |

## Per-agent RAGAS metrics

| Agent | Model | Metric | Mean | Scored / eligible | Coverage |
|---|---|---|---:|---:|---:|
| knowledge | Qwen 3.8 27B | faithfulness | 0.9909 | 22 / 22 | 1.0 |
| knowledge | Qwen 3.8 27B | answer_relevancy | 0.8408 | 25 / 25 | 1.0 |
| knowledge | Qwen 3.8 27B | context_precision | 1 | 22 / 22 | 1.0 |
| report | Qwen 3.8 27B | faithfulness | 0.2698 | 16 / 16 | 1.0 |
| report | Qwen 3.8 27B | answer_relevancy | 0.6683 | 24 / 24 | 1.0 |
| report | Qwen 3.8 27B | context_precision | 0.3698 | 16 / 16 | 1.0 |
| sql | Qwen 3.8 27B | faithfulness | 0.2596 | 25 / 25 | 1.0 |
| sql | Qwen 3.8 27B | answer_relevancy | 0.8204 | 25 / 25 | 1.0 |
| sql | Qwen 3.8 27B | context_precision | 0.09 | 25 / 25 | 1.0 |
| knowledge | GPT-OSS 120B | faithfulness | 0.8525 | 21 / 21 | 1.0 |
| knowledge | GPT-OSS 120B | answer_relevancy | 0.8414 | 24 / 24 | 1.0 |
| knowledge | GPT-OSS 120B | context_precision | 0.9946 | 21 / 21 | 1.0 |
| report | GPT-OSS 120B | faithfulness | 0.2298 | 20 / 20 | 1.0 |
| report | GPT-OSS 120B | answer_relevancy | 0.6794 | 25 / 25 | 1.0 |
| report | GPT-OSS 120B | context_precision | 0.35 | 20 / 20 | 1.0 |
| sql | GPT-OSS 120B | faithfulness | 0.2141 | 25 / 25 | 1.0 |
| sql | GPT-OSS 120B | answer_relevancy | 0.772 | 25 / 25 | 1.0 |
| sql | GPT-OSS 120B | context_precision | 0.1833 | 25 / 25 | 1.0 |

## Case completion and SQL metrics

| Model | Agent | Cases | Completed | Run errors | SQL safety | SQL semantic correctness | Abstention accuracy |
|---|---|---:|---:|---:|---:|---:|---:|
| Qwen 3.8 27B | knowledge | 25 | 25 | 0 | n/a | n/a | n/a |
| Qwen 3.8 27B | report | 25 | 24 | 1 | n/a | n/a | n/a |
| Qwen 3.8 27B | sql | 25 | 25 | 0 | 0.6800 (17/25) | 0.8800 (22/25) | 0.6800 (17/25) |
| GPT-OSS 120B | knowledge | 25 | 24 | 1 | n/a | n/a | n/a |
| GPT-OSS 120B | report | 25 | 25 | 0 | n/a | n/a | n/a |
| GPT-OSS 120B | sql | 25 | 25 | 0 | 0.8400 (21/25) | 0.8800 (22/25) | 0.8400 (21/25) |

## Run errors

| Model | Case | Error recorded in JSON |
|---|---|---|
| Qwen 3.8 27B | R25 | `RateLimitError: Error code: 429 - {'error': {'message': 'Rate limit reached for model `qwen/qwen3.8-27b` in organization `org_01m4jcwnjke9nsdhr5x4b27ggz` service tier `on_demand` on tokens per day (TPD): Limit 200000, Used 198740, Requested 2597. Please try again in 9m37.584s. Need more tokens? Upgrade to Dev Tier today at https://console.groq.com/settings/billing', 'type': 'tokens', 'code': 'rate_limit_exceeded'}}` |
| GPT-OSS 120B | K06 | `ValueError: Generated answer contains no source citations. Answer: Công thức tính **Reorder Point (ROP)** được định nghĩa là:   ;  ; \[ ; \text{ROP} = \text{Nhu cầu mỗi ngày} \times (\text{Lead time} + \text{Safety days}) ; \]   ;  ; Trong tài liệu mô phỏng, các tham số mặc định được thiết lập như sau:   ;  ; - **Lead time**: 14 ngày   ; - **Safety stock (Safety days)**: 7 ngày   ; - **Review period**: 7 ngày   ;  ; (Tham khảo S1, S2) ; Targeted rerun blocked before answer generation: RateLimitError: Error code: 429 - {'error': {'message': 'Rate limit reached for model `openai/gpt-oss-120b` in organization `org_01m4jcwnjke9nsdhr5x4b27ggz` service tier `on_demand` on tokens per day (TPD): Limit 200000, Used 197929, Requested 2705. Please try again in 4m33.888s. Need more tokens? Upgrade to Dev Tier today at https://console.groq.com/settings/billing', 'type': 'tokens', 'code': 'rate_limit_exceeded'}}` |

## Retry outcomes

| Model | First-attempt successes | Operations retried | Final failures |
|---|---:|---:|---:|
| Qwen 3.8 27B | 274 / 275 | 0 | 1 |
| GPT-OSS 120B | 280 / 282 | 0 | 2 |

## Limitations

Hallucination rate is not calculated in these artifacts; it requires manual claim-level review. Run errors remain represented separately and are excluded from scoring where required inputs are absent.

## Source files

- [results-rerun-2026-10-23-qwen-qwen3.8-27b.json](results-rerun-2026-10-23-qwen-qwen3.8-27b.json)
- [results-rerun-2026-10-24-openai-gpt-oss-120b.json](results-rerun-2026-10-24-openai-gpt-oss-120b.json)
