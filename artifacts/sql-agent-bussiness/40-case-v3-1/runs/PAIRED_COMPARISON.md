# SQL Agent comparison with restored follow-up context

The original application at `37b5fed5` and the updated application at `8649a7eb` each attempted the same 40 frozen cases. Both runners supplied the five frozen prior turns. The database fingerprint, case set, reference answers, selected provider chain, case pacing, and v3.3 scorer matched.

Cloudflare failed on 39 recorded submissions in the original-agent rerun. Its telemetry recorded 31 Groq fallback submissions and eight local Codex fallback calls. The updated-agent run recorded zero SQL-provider and local Codex fallback calls. A subsequent Cloudflare probe returned HTTP 429. The observed score difference is therefore confounded by provider availability.

| Metric | Original v3.3 | Updated v3.3 | Original offline v3.4 | Updated offline v3.4 |
|---|---:|---:|---:|---:|
| Business end-to-end | 7/30 (23.3%) | 14/30 (46.7%) | 11/30 (36.7%) | 19/30 (63.3%) |
| Business result among executed supported cases | 9/15 (60.0%) | 16/26 (61.5%) | 13/15 (86.7%) | 22/26 (84.6%) |
| SQL semantic accuracy | 11/30 (36.7%) | 22/30 (73.3%) | 11/30 (36.7%) | 22/30 (73.3%) |
| Valid clarification or abstention | 9/10 (90.0%) | 6/10 (60.0%) | 9/10 (90.0%) | 6/10 (60.0%) |
| Overall task success | 16/40 (40.0%) | 20/40 (50.0%) | 20/40 (50.0%) | 25/40 (62.5%) |
| Unsafe executions | 0 | 0 | 0 | 0 |

Offline v3.4 accepts exact UTC midnight month starts where the reference uses month-start dates. It accepts reviewed aliases only for the exact saved SQL and parameters with a passing linked semantic audit. The rescore takes no provider or database calls. The v3.3 source, scores, and saved observations remain intact.

## Post-fix regression results

- B40-031 asked for the comparison periods and made no SQL execution call.
- B40-028 aligned both years by month number and returned the difference. All 12 rows matched the reference after equating the output label `difference` with `difference_2024_minus_2023`.
- B40-013 grouped by the segment stored on the historical inventory row and matched the required result. The query still returned an extra snapshot date.
- B40-021 grouped by snapshot category and returned all four reference rows, including the zero-count category.
- B40-025 grouped by snapshot category and matched the average plus NULL and non-NULL counts in all four reference rows.

The five regression checks reused questions already seen during development. Their results are evidence for these fixes and do not change the 40-case scores above.

[Original-agent report](context-fixed-original-37b5fed5/report.md) · [Updated-agent report](context-fixed-main-8649a7eb/report.md) · [Original offline scores](context-fixed-original-37b5fed5/scores-v3.4.json) · [Updated offline scores](context-fixed-main-8649a7eb/scores-v3.4.json)
