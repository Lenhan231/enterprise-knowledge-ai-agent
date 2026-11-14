# Cloudflare Llama 8B dashboard coverage

Tested on 2026-11-14 against the live read-only analytics source using the latest dashboard reconciliation changes.

| Model / case | Observed outcome |
|---|---|
| `@cf/meta/llama-3.1-8b-instruct` | Cloudflare returned HTTP 410, model deprecated. |
| `@cf/meta/llama-3.1-8b-instruct-fp8-fast`, English monthly revenue trend + summary, Jan–Dec 2026 | Two final repeated checks completed with a chart and summary. All 11 observed monthly values matched Groq Qwen and Cloudflare GPT-OSS-20B exactly. |
| Same FP8-fast model, Vietnamese monthly revenue + summary, July–September 2026 | The final check failed strict dashboard-plan validation. Other exploratory attempts produced extra fields, unrelated tiles or daily rather than monthly grouping. Bilingual reliability is not established. |

Cloudflare documents the retired model in its [May 2026 deprecation notice](https://developers.cloudflare.com/changelog/post/2026-05-08-planned-model-deprecations/). The working variant was selected explicitly; no provider or deployment environment was silently switched.

Two compatibility fixes came from these checks:

- Extract the model's first JSON object with the existing SQL JSON parser, then validate it against the unchanged strict dashboard schema. Llama emitted a valid plan followed by a schema echo and SQL example. Trailing content is discarded; trailing SQL is never executed or forwarded to the SQL agent.
- Bind a temporal alias to the single observed date output projected through a CTE, even when grouping occurs inside the CTE. Unknown metrics and ambiguous date dimensions still fail safely.

Regression checks cover schema echoes with hostile trailing SQL, forbidden model-supplied metric/currency authority, and CTE monthly field binding. All 38 focused dashboard checks pass. Full-suite fail-fast still encounters the unchanged document-processing metadata assertion. Raw outputs and database observations remain under ignored `artifacts/local`; no credentials or benchmark snapshots are published.

For the tested Cloudflare variant, configure the backend explicitly:

```dotenv
SQL_LLM_PROVIDER=cloudflare
SQL_CLOUDFLARE_MODEL=@cf/meta/llama-3.1-8b-instruct-fp8-fast
```

These are narrow smoke checks, not a 50-question benchmark or a guarantee for arbitrary prompts. Keep metric validation enabled. The Vietnamese planning failures need further work before calling this model interchangeable with the larger tested models.
