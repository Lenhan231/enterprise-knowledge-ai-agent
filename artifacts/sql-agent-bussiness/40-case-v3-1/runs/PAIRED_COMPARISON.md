# SQL Agent comparison with restored follow-up context

The original application at `37b5fed5` and the updated application at `8649a7eb` each attempted the same 40 frozen cases with all five prior turns supplied. They used the same database fingerprint, case set, reference answers, schema selector model, and v3.3 scorer.

The original agent used Groq `openai/gpt-oss-20b`. The updated agent used Cloudflare `@cf/openai/gpt-oss-20b`. Both completed with zero model fallbacks. They used different deployments of GPT-OSS 20B, so the comparison does not isolate the agent revision from provider effects. The original run resumed from its fifth completed case after an HTTP 429 and recorded nine further same-model backoffs. Elapsed times are not directly comparable.

| Metric | Original v3.3 | Updated v3.3 | Original offline v3.4 | Updated offline v3.4 |
|---|---:|---:|---:|---:|
| Business end-to-end | 9/30 (30.0%) | 14/30 (46.7%) | 15/30 (50.0%) | 19/30 (63.3%) |
| Business result among executed supported cases | 10/19 (52.6%) | 16/26 (61.5%) | 16/19 (84.2%) | 22/26 (84.6%) |
| SQL semantic accuracy | 15/30 (50.0%) | 22/30 (73.3%) | 15/30 (50.0%) | 22/30 (73.3%) |
| Valid clarification or abstention | 8/10 (80.0%) | 6/10 (60.0%) | 8/10 (80.0%) | 6/10 (60.0%) |
| Overall task success | 17/40 (42.5%) | 20/40 (50.0%) | 23/40 (57.5%) | 25/40 (62.5%) |
| Unsafe executions | 0 | 0 | 0 | 0 |

Offline v3.4 accepts exact UTC midnight month starts where the reference uses month-start dates. It accepts reviewed aliases only for the exact saved SQL and parameters with a passing linked semantic audit. The rescore takes no provider or database calls. The v3.3 source, scores, and saved observations remain intact.

## Post-fix regression results

- B40-031 asked for the comparison periods and made no SQL execution call.
- B40-028 aligned both years by month number and returned the difference. All 12 rows matched the reference after equating the output label `difference` with `difference_2024_minus_2023`.
- B40-013 grouped by the segment stored on the historical inventory row and matched the required result. The query still returned an extra snapshot date.
- B40-021 grouped by snapshot category and returned all four reference rows, including the zero-count category.
- B40-025 grouped by snapshot category and matched the average plus NULL and non-NULL counts in all four reference rows.

The five regression checks reused questions already seen during development. Their results are evidence for these fixes and do not change the 40-case scores above.

[Original-agent Groq report](context-fixed-original-37b5fed5-groq-oss20b/report.md) · [Updated-agent Cloudflare report](context-fixed-main-8649a7eb/report.md) · [Original offline scores](context-fixed-original-37b5fed5-groq-oss20b/scores-v3.4.json) · [Updated offline scores](context-fixed-main-8649a7eb/scores-v3.4.json)

The [earlier original-agent run](context-fixed-original-37b5fed5/report.md) mixed providers after Cloudflare rejected its requests. Its scores are excluded from the table.
