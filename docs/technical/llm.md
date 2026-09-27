# LLM provider and answer evaluation

`RAGService` uses `GroqProvider`. It sends an OpenAI-compatible Responses API
request to Groq, by default with `openai/gpt-oss-20b`, temperature `0`, low
reasoning effort and a 1,000-token output limit. `GROQ_MODEL` selects the model;
`GROQ_API_KEY` stays server-side. Qwen models use reasoning effort `none`.
Changing the model requires confirming provider support for the endpoint and
generation parameters.

`data/evaluation/vinamilk_qa_cases.json` and
`scripts/run_review1_grounded_qa.py --cases ... --company ...` exercise answers,
source-document citation, expected financial/product facts and an employee
access-denial control. The reports are
`artifacts/evaluation/vinamilk-qa-smoke.json` and
`artifacts/evaluation/vinamilk-qa-qwen3.8-smoke.json`. Both used the same case
hash, hybrid retrieval, top-10 contexts, prompt and output cap:

| Available model | Expected source/fact checks | Input/output tokens | Mean end-to-end latency |
| --- | ---: | ---: | ---: |
| Groq `openai/gpt-oss-20b` | 5/5 | 11,805 / 412 | 4.54 s |
| Groq `qwen/qwen3.8-27b` | 5/5 | 12,921 / 247 | 14.85 s |

Paired rerun on 2026-09-26 created
`artifacts/evaluation/vinamilk-qa-gpt-oss-20b-fingerprinted.json` and
`artifacts/evaluation/vinamilk-qa-qwen3.8-fingerprinted.json`. All five case
context hashes and final prompt hashes matched between models (case-file
SHA-256 `baf2f221b1902b831a3395e484fdd65bbf82a79966548b6455a780ea0ca2520b`; prompt-template file SHA-256
`d54c398374f294436fcafcc6bf5313b0614e77ef78e6042af9e884a039f09fdf`). Both
again passed expected-source/fact and role-denial checks 5/5. In this run,
mean end-to-end latency over the four answerable cases was 11.72 s for
GPT-OSS-20B and 15.38 s for Qwen3.8-27B; these include retrieval/model warmup
effects and differ from the earlier smoke run. Treat paired artifacts as the
current reproducible proxy comparison. They do not make Qwen3.8 an exact Qwen3
baseline or replace human semantic scoring.

These are smoke measurements on four answerable cases plus one employee
financial-denial control, not statistical quality scores. The runner records
expected-source accuracy, expected-fact coverage, context precision against
the manually labeled relevant-document IDs, citation-covered non-empty line
fraction, and whether an answer contains any valid source citation. These are
transparent proxies, not RAGAS context precision, bullet-level attribution or
semantic faithfulness. Faithfulness, answer relevancy and hallucination rate
still require human review. Correct abstentions are excluded from answer
citation averages. Re-score a saved report without model calls using
`uv run python scripts/score_qa_artifact.py <run.json> --output <scored.json>`.
New runs also include per-case hashes of the exact retrieved context and final
prompt, plus the prompt-template hash. Compare these hashes across model runs;
only cases with matching fingerprints had identical model inputs.

## Expanded paired proxy comparison

On 2026-09-27, the same five Vinamilk cases were run with Groq
`openai/gpt-oss-120b`. Its retrieved-context and final-prompt fingerprints
match the existing GPT-OSS-20B and Qwen3.8 runs on all five cases. The scoring
protocol accepts source-equivalent wording for the sustainability fact (for
example, “100% of factories and farms” or “all of its factories and all of its
farms”); the official report uses the former. The revised labels are stored
separately from the original generation-case hash in each `facts-v2` report.

| Available proxy model | Source/fact/RBAC smoke | Mean latency across four answerable cases | Mean labeled context precision | Mean cited-line coverage |
| --- | ---: | ---: | ---: | ---: |
| Groq `openai/gpt-oss-20b` | 5/5 | 11.72 s | 1.00 | 0.8125 |
| Groq `qwen/qwen3.8-27b` | 5/5 | 15.38 s | 1.00 | 1.0000 |
| Groq `openai/gpt-oss-120b` | 5/5 | 9.88 s | 1.00 | 0.8000 |

These are one-run measurements on five cases, with no semantic human ratings.
GPT-OSS-120B's 2024 finance answer adds an incorrect unit conversion while
also stating the expected headline figures; its 5/5 deterministic checks do
not establish faithfulness. Line-level citation coverage is a proxy, not
claim-level attribution. The three reports are
`artifacts/evaluation/vinamilk-qa-gpt-oss-20b-facts-v2.json`,
`artifacts/evaluation/vinamilk-qa-qwen3.8-facts-v2.json`, and
`artifacts/evaluation/vinamilk-qa-gpt-oss-120b-facts-v2.json`.

## Financial report-answer scope

The report agent puts explicitly labelled consolidated revenue/profit passages
first and asks for one cited bullet per requested metric. It must not add
differently labelled statement figures or invent an accounting basis or
reconciliation; if the same named metric and scope conflict, it must report the
conflict. This followed a live browser finding where an earlier prompt required
the model to include both overview and detailed-statement values even when the
retrieved passages did not explain their different labels. The updated prompt
was checked through the analyst dashboard: the 2024 question returned total
consolidated revenue of 61,824 billion VND and consolidated after-tax profit of
9,453 billion VND, both with a citation to the 2024 annual report, page 12.
Unverifiable citations still fail closed; the UI now distinguishes this from
retrieval finding no passages. The full authenticated route suite subsequently
passed 5/5 (`artifacts/evaluation/vinamilk-app-qa-suite.json`, mean 26.405 s).
This is a prompt regression fix and a small live QA check, not a semantic
faithfulness study.

The proposal's exact baselines remain unresolved: Qwen3-32B and Llama 3.1/3.3
were retired for Groq developer-tier accounts; Qwen3.8 is a later proxy, and
GPT-OSS is an open-weight GPT model, not a proprietary OpenAI GPT API model.
The local environment has no `OPENAI_API_KEY`. Confirm current account access
and select exact checkpoints before the final thesis comparison; see Groq's
[model deprecation history](https://console.groq.com/docs/deprecations).

For semantic review, use the blinded packet workflow below. Imported scores are
stored in `human_reviews` for each answer row. Score faithfulness, answer
relevancy and context precision from 1 (poor)
to 5 (fully meets), then count unsupported factual claims and total verifiable
claims. Exclude correct refusals from claim counts. Record an anonymous
reviewer ID and notes; score against cited source excerpts/pages while blind to
model identity. Re-run `score_qa_artifact.py` after annotations to compute means
and the pooled hallucinated-claim fraction. Missing or invalid reviews are
excluded; empty review fields are not zero scores. For a defensible model
comparison, have at least two reviewers independently score the same answers
and report reviewer-level results before resolving disagreements. Current
artifacts contain no completed semantic ratings, so no semantic model winner
can yet be claimed.

To run the blind comparison, prepare a shuffled packet and keep its mapping key
private from reviewers:

```bash
uv run python scripts/qa_human_review.py prepare \
  --runs artifacts/evaluation/vinamilk-qa-gpt-oss-20b-fingerprinted.json \
         artifacts/evaluation/vinamilk-qa-qwen3.8-fingerprinted.json \
  --output artifacts/evaluation/qa-review-packet.json \
  --key-output artifacts/evaluation/qa-review-private-key.json
```

Give each reviewer a separate copy of the packet. Once each has filled all
ratings and a distinct anonymous reviewer ID, import them together:

```bash
uv run python scripts/qa_human_review.py import \
  --packets artifacts/evaluation/qa-review-reviewer-1.json \
           artifacts/evaluation/qa-review-reviewer-2.json \
  --key artifacts/evaluation/qa-review-private-key.json \
  --output-dir artifacts/evaluation/human-reviewed
```

The preparer rejects runs with different case sets or retrieved-context hashes.
The packet omits model/run labels; the separate key maps randomized response
IDs back to each run. Import validates complete response coverage, reviewer
uniqueness, score ranges and claim counts before writing annotated run copies.
Keep the private key away from reviewers until scoring is complete.
The last successful live Groq model-list check (2026-09-26) returned 11 IDs,
including `qwen/qwen3.8-27b`, `openai/gpt-oss-20b`, and
`openai/gpt-oss-120b`; exact Qwen3, Llama 3, and proprietary GPT IDs were
absent. A later refresh from this runtime returned HTTP 403 at Cloudflare
before a provider response, so it did not revalidate account access. Groq's
current [deprecation history](https://console.groq.com/docs/deprecations)
states Qwen3-32B and Llama 3.1/3.3 were retired for developer-tier accounts in
2026; enterprise access may differ. The local `.env` has Groq credentials but
no direct OpenAI or Llama API credentials. Recheck from an allowed network if
the thesis requires those exact model families.

Keep separate reports for each model using identical cases, retrieved
contexts, prompt, and decoding settings. Human reviewers should score
faithfulness, answer relevancy, context precision and hallucinated claims
against the cited evidence before model comparisons are reported.
