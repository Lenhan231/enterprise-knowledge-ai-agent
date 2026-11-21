# Rotated SQL Agent model pilot

**Status: exploratory repeated development pilot; no model winner established.**

This report adds a second five-case pass and reverses model run order to reduce order-related bias. It does not run the 40-case cohort.

## Design

- Round 1 ran GPT-OSS 20B then 120B; round 2 ran 120B then 20B. Each model saw P01–P05 in the same order with 60 seconds between cases.
- Round 2 used application revision `72e60fa3311c6d310c2b453df156860a7c2cb3ee` and runner hash `0719c1976a7584d2a1cd2222dadabe85a8447c78877b71620f1da14987b25843` for both models; only `SQL_GROQ_MODEL` differed.
- Case-set SHA-256: `ddade2d597b30a6bb4c74fc7b997dfe9a617e6c5348cd8b64bf7016463d100c4`; database fingerprint: `dbc14b99acc2920ffaeb4190ba45708982c971f0671b0b9e8114b595f2594028` (frozen snapshot, read-only role); reference SHA-256: `295c53652e5fe3a7fc8c3c35cffb9ecf4f6bc23e44b6db861955e369d0932a17`.
- SQL source fingerprint was `5feb222132233fa2bd8ee010eac42b804a64bb0d0f13ad80b7252c3b0728a57d` across all four runs. Local Codex and Hugging Face fallback were disabled in round 2; no secondary SQL provider submissions occurred.
- Groq account billing tier was not checked, so this report makes no claim that the requests were free.
- The round 1 runs used the same SQL source fingerprint but different app/benchmark-runner revisions. Treat round 2 as the controlled, order-reversed pair; round 1 is a repeat baseline.

## Per-run results

| Round and order | Model | Business E2E | SQL semantic | Execution success | Strict exact | Valid unsupported abstention | SQL generation calls | Status |
|---|---|---:|---:|---:|---:|---:|---:|---|
| 1: 20B then 120B | gpt-oss-20b | 4/4 (100%) | 4/4 (100%) | 4/4 (100%) | 2/4 (50%) | 1/1 (100%) | 2 | `completed` |
| 1: 20B then 120B | gpt-oss-120b | 3/4 (75%) | 4/4 (100%) | 3/4 (75%) | 2/4 (50%) | 1/1 (100%) | 3 | `completed_with_failures` |
| 2: 120B then 20B | gpt-oss-120b | 2/4 (50%) | 3/4 (75%) | 2/4 (50%) | 2/4 (50%) | 1/1 (100%) | 3 | `completed_with_failures` |
| 2: 120B then 20B | gpt-oss-20b | 4/4 (100%) | 4/4 (100%) | 4/4 (100%) | 2/4 (50%) | 1/1 (100%) | 2 | `completed` |

## Case outcomes

| Case | 20B round 1 | 20B round 2 | 120B round 1 | 120B round 2 |
|---|---|---|---|---|
| P01 | executed | executed | executed | executed |
| P02 | executed | executed | executed | executed |
| P03 | executed | executed | failed (provider_failure) | failed (provider_failure) |
| P04 | executed | executed | executed | clarification_required (supported_request_not_executed) |
| P05 | unsupported | unsupported | unsupported | unsupported |

- P03 failed with `RateLimitError` on 120B in both rounds; the SQL output was not executed and is not business-result evidence.
- P04 executed on 120B in round 1 but returned `clarification_required` in round 2 after changing the requested historical period; validation blocked execution.
- P05 was safely abstained in all four model runs. No unsafe repository execution was recorded.

## Descriptive two-round totals

These totals summarize eight repeated supported-case attempts per model; repeated questions are not independent observations.

| Metric | GPT-OSS 20B | GPT-OSS 120B |
|---|---:|---:|
| Business end-to-end accuracy | 8/8 (100%) | 5/8 (62.5%) |
| SQL semantic accuracy | 8/8 (100%) | 7/8 (87.5%) |
| Execution success | 8/8 (100%) | 5/8 (62.5%) |
| Strict result exact match | 4/8 (50%) | 4/8 (50%) |
| Supported noncompletion | 0/8 (0%) | 3/8 (37.5%) |
| Valid unsupported abstention | 2/2 (100%) | 2/2 (100%) |

## Interpretation

GPT-OSS 20B completed all supported pilot cases in both runs (8/8 descriptive attempts). GPT-OSS 120B completed 5/8; one failure was a provider rate limit on P03 in both rounds, and one was an incorrect clarification on P04 in the rotated run. The signal favors 20B for end-to-end completion under this exact setup, but does not isolate general SQL reasoning or establish a statistically reliable winner. Most pilot cases use deterministic paths; only two need general SQL generation.

For a real model choice, use the independently reviewed 40-case cohort after gold SQL/results and case hashes are frozen. This report does not execute or tune on those 40 cases.

## Reproduction artifacts

- [`comparison.json`](comparison.json): full hashes, run manifests, metrics and per-case outcomes.
- [`gpt-oss-20b/`](gpt-oss-20b/) and [`gpt-oss-120b/`](gpt-oss-120b/): round 2 raw observations, scores and runner reports.
- Prior round 1: [`../model-ab-groq-oss20b-vs-oss120b-20261121-final/comparison.md`](../model-ab-groq-oss20b-vs-oss120b-20261121-final/comparison.md).
- Benchmark protocol: [`../../PROTOCOL.md`](../../PROTOCOL.md).
