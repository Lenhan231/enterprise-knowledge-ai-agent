# Agent benchmark comparison

Dataset: 75 cases per model (25 knowledge, 25 SQL, 25 report). Each model uses the same saved questions and app routes. Qwen results were reused from the earlier run. GPT-OSS case outputs were saved incrementally; the 20B run resumed after a serialization fix.

| Model | Knowledge answered | SQL answered | SQL safety | SQL result checks | Abstention | Reports generated | Run errors |
|---|---:|---:|---:|---:|---:|---:|---:|
| `qwen/qwen3.8-27b` | 25/25 | 25/25 | 17/25 | 22/25 | 17/25 | 16/25 | 9 |
| `openai/gpt-oss-20b` | 25/25 | 25/25 | 17/25 | 21/25 | 17/25 | 14/25 | 11 |
| `openai/gpt-oss-120b` | 25/25 | 25/25 | 20/25 | 22/25 | 20/25 | 22/25 | 3 |

SQL result checks compare returned rows to the supplied expected-result assertions. SQL safety is the app validator's pass/fail field. Abstention checks are limited to cases with an observed abstention value. Knowledge and report correctness still need human review.

Mean agent latency in seconds (legacy Qwen knowledge timings were not isolated from scoring):

| Model | Knowledge | SQL | Report |
|---|---:|---:|---:|
| `qwen/qwen3.8-27b` | n/a | 8.21 | 69.35 |
| `openai/gpt-oss-20b` | 33.35 | 8.22 | 43.00 |
| `openai/gpt-oss-120b` | 33.89 | 7.64 | 42.52 |

## Ragas and manual scoring

Ragas was configured with `openai/gpt-oss-20b` and the `GROQ_API_KEY_RAGAS` credential. During the saved Qwen run, some metrics were scored, but judge calls also failed with Groq JSON validation errors and rate limits. Ragas could not provide a consistent score set across all three models. GPT-OSS-20B and GPT-OSS-120B generation outputs have no Ragas scores. Manual scoring is required for faithfulness, answer relevancy, context precision, and claim-level hallucination rate. Hallucination rate is not inferred from faithfulness.

Partial Qwen Ragas scores (not directly comparable because each metric has a different denominator):

| Metric | Mean | Scored answers |
|---|---:|---:|
| faithfulness | 0.9 | 12 |
| answer_relevancy | 0.7296 | 26 |
| context_precision | 0.9457 | 23 |

## Provider limitation

The configured Cloudflare Llama 3.1 8B endpoint returned HTTP 401 despite a token being configured. Its two attempted cases are retained in `results-cf-meta-llama-3.1-8b-instruct-fp8.json` and are excluded from the three-model comparison. GPT-OSS-120B was used as the third available Groq model; its ID is listed in Groq's [supported models](https://console.groq.com/docs/models).

## Case outputs

- `results-qwen-qwen3.8-27b.json` - `qwen/qwen3.8-27b`
- `results-openai-gpt-oss-20b.json` - `openai/gpt-oss-20b`
- `results-openai-gpt-oss-120b.json` - `openai/gpt-oss-120b`
