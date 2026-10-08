# LLM providers

## Application configuration

`GroqProvider` is the primary generator. It reads `GROQ_API_KEY` and
`GROQ_MODEL` (default `openai/gpt-oss-20b`), uses temperature 0, a 1,000-token
output limit, a 30-second timeout, and no SDK retries. The application owns
fallback decisions so provider retries do not hold a request before fallback.

Knowledge Q&A, ReportAgent, and SQLAnalyticsAgent can use the Hugging Face
Inference Provider after a retryable Groq error. Set `HUGGINGFACE_LLM_FALLBACK=true` and
`HUGGINGFACE_API_KEY`; `HUGGINGFACE_LLM_MODEL` defaults to
`openai/gpt-oss-20b:cheapest`. That suffix selects a low-price provider; it does
not mean the request is free. A 402 response disables fallback for the current
process; restart after credits or billing change. Retryable Groq failures log
available retry and token-limit headers without logging prompt text. OCR image
captioning and financial-page extraction use separate provider paths.

Knowledge RAG limits formatted retrieved context to 5,000 characters as a
bounded prompt-size safeguard. Characters are not Groq tokens, so this is not a
provider rate-limit guarantee. On 2026-10-08, a live Commerce request received
HTTP 429 with `retry-after=64`, `remaining_tokens=8000`, and a 1 ms token reset;
those headers do not show that the token bucket was exhausted. The fallback
logger now records request/day and token quota headers; they help distinguish
an exhausted daily-request or token bucket from another 429 cause. A Groq HTTP 429 is surfaced as
`provider_rate_limited`, while other temporary failures remain
`provider_unavailable`. Hugging Face returning HTTP 402 means that fallback
needs provider credits; it is not a missing API key.

API keys stay server-side. Provider-backed embeddings and generation transmit
the submitted text to the selected provider; use local embeddings when that
transfer is not acceptable. Do not add secrets or private source text to
tracked evaluation artifacts.

## Evaluation

The current Commerce question set and latest API checks are tracked in
[`commerce-decision-support.md`](../commerce-decision-support.md). The nine
SQL-plus-RAG cases are an application smoke set, not a model-quality score.
The latest full replay was limited by provider quotas; deterministic fallback
checks do not verify model-written SQL or semantic recommendation quality.
Human review remains necessary before reporting answer-quality results.

Run one case against a configured local app with:

```bash
PYTHONPATH=src uv run python tools/agents/evaluate_commerce_decision_support.py \
  --case-id INV-01
```

The script checks response structure, sources, and mechanical expectations.
Review the saved answer against the case's gold evidence before treating it as
correct. See [agent evaluation](agents-and-evaluation.md) for the broader
proposal coverage and remaining model comparisons.
