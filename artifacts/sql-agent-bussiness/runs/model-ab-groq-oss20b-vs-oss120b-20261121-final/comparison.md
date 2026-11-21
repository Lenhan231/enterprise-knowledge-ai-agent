# SQL Agent model A/B pilot

## Scope

This is a five-case development pilot, not the held-out 40-case benchmark. Both runs use the same SQL Agent source fingerprint, case set, frozen reference, read-only database snapshot, Groq provider, selector model, and 60-second case spacing. `SQL_GROQ_MODEL` is the only application setting that changed. The benchmark runner revisions differ: the 120B run includes a counter correction for disabled Codex fallback; the SQL Agent source hashes are identical. The models were run sequentially, 20B first and 120B second; there was one run per model.

- Case-set SHA-256: `ddade2d597b30a6bb4c74fc7b997dfe9a617e6c5348cd8b64bf7016463d100c4`
- Gold-reference SHA-256: `295c53652e5fe3a7fc8c3c35cffb9ecf4f6bc23e44b6db861955e369d0932a17`
- Frozen database fingerprint: `dbc14b99acc2920ffaeb4190ba45708982c971f0671b0b9e8114b595f2594028` (read-only role verified)
- SQL source fingerprint: `5feb222132233fa2bd8ee010eac42b804a64bb0d0f13ad80b7252c3b0728a57d` (identical in both runs)
- Schema selector held constant: `perplexity/pplx-decider-flash-v1.3:free`
- SQL-generation fallback, local Codex fallback, and Hugging Face fallback: disabled; no secondary SQL-provider submissions occurred.
- Groq account billing tier was not verified; API access alone does not prove the calls were no-charge.

Run revisions: 20B `2f00c5b199ebdb8671ad76d641c0d9fc46054c49`; 120B `a5a2169727d6397b96e6bfc21ea7a8e70165f9a5`. The per-run manifests include benchmark-code hashes and provider-call counts.

## Results

| Metric | GPT-OSS 20B | GPT-OSS 120B |
|---|---:|---:|
| Business end-to-end accuracy | 4/4 (100%) | 3/4 (75%) |
| Business result accuracy (executed cases) | 4/4 (100%) | 3/3 (100%) |
| SQL semantic accuracy | 4/4 (100%) | 4/4 (100%) |
| Execution success | 4/4 (100%) | 3/4 (75%) |
| Strict exact match | 2/4 (50%) | 2/4 (50%) |
| Supported noncompletion | 0/4 (0%) | 1/4 (25%) |
| Valid unsupported abstention | 1/1 (100%) | 1/1 (100%) |
| Repair recovery | 0/0 (N/A) | 0/1 (0%) |
| Unsafe executions | 0 | 0 |
| SQL generation submissions | 2 | 3 |
| SQL repairs | 0 | 1 |
| Repository executions | 4 | 3 |
| SQL latency p50 / p95 (ms) | 9233.107 / 10341.271 | 9260.064 / 11334.504 |

## Per-case results

| Case | 20B status | 20B SQL semantic | 120B status | 120B SQL semantic | 120B failure |
|---|---|---:|---|---:|---|
| P01 | executed | True | executed | True | — |
| P02 | executed | True | executed | True | — |
| P03 | executed | True | failed | True | provider_failure |
| P04 | executed | True | executed | True | — |
| P05 | unsupported | None | unsupported | None | — |

## Interpretation

On this run, GPT-OSS 20B completed all four supported cases and the unsupported P05 case abstained correctly. GPT-OSS 120B also passed the semantic scorer on all four supported cases, but P03 did not reach execution: the model entered one bounded repair and the Groq endpoint returned `RateLimitError`. Thus its 3/4 end-to-end result is an operational noncompletion, not evidence that the SQL was semantically wrong; the SQL for P03 is unexecuted and must not be treated as verified business output.

The pilot favors 20B for end-to-end reliability under this endpoint configuration (4/4 versus 3/4), but does not establish general model superiority. The cohort is small, contains only two general SQL-generation questions, and is not held out. No 40-case questions were executed.

## Run artifacts

- [GPT-OSS 20B run](gpt-oss-20b/report.md), [raw observations](gpt-oss-20b/data.json), [scores](gpt-oss-20b/scores.json).
- [GPT-OSS 120B run](gpt-oss-120b/report.md), [raw observations](gpt-oss-120b/data.json), [scores](gpt-oss-120b/scores.json).
- Benchmark protocol: [`../../PROTOCOL.md`](../../PROTOCOL.md).
