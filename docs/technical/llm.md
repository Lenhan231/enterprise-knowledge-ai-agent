# LLM provider and answer evaluation

`RAGService` uses `GroqProvider`. It sends an OpenAI-compatible Responses API
request to Groq, by default with `openai/gpt-oss-20b`, temperature `0`, low
reasoning effort and a 1,000-token output limit. `GROQ_MODEL` selects the model;
`GROQ_API_KEY` stays server-side. Qwen models use reasoning effort `none`.
Changing the model requires confirming provider support for the endpoint and
generation parameters.

Agent teardown closes the shared provider's HTTP client. PDF financial uploads
extract parser candidates first, then request LLM candidates only for selected
financial pages. If provider initialization or generation fails, the upload
keeps the parser candidates, records the document as ready after indexing, and
still requires admin review before any KPI is published. The upload closes the
provider on both success and provider-error paths; regressions are in
`tests/test_upload_processing_flow.py` and `tests/test_llm_provider.py`.

`data/evaluation/vinamilk_qa_cases.json` and
`scripts/agents/run_review1_grounded_qa.py --cases ... --company ...` exercise answers,
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
`uv run python scripts/agents/score_qa_artifact.py <run.json> --output <scored.json>`.
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

These are historical one-run measurements on five cases, with no semantic
human ratings. The initial finance anchors checked numbers without requiring
their magnitude units, so the 5/5 deterministic scores overstated correctness.
Line-level citation coverage is a proxy, not claim-level attribution. The
historical reports are
`artifacts/evaluation/vinamilk-qa-gpt-oss-20b-facts-v2.json`,
`artifacts/evaluation/vinamilk-qa-qwen3.8-facts-v2.json`, and
`artifacts/evaluation/vinamilk-qa-gpt-oss-120b-facts-v2.json`.

The legacy facts-v2 reports store source text only in `content_preview`, capped
at 500 characters. A missing expected fact inside that preview is not evidence
that the retrieved/cited chunk omitted it. The v3 rescore marks such checks as
unverifiable and reports evidence coverage (7/9, 8/9, and 7/9 expected fact
groups for GPT-OSS-20B, Qwen3.8-27B, and GPT-OSS-120B). New QA runs can retain
the full cited chunk with `--include-full-evidence`; use this only with public
or explicitly approved evaluation data because it writes document text to the
artifact. The blind-review packet includes source document, page, official URL
and complete evidence excerpt when available. Literal matching still cannot
establish semantic entailment. See the
[legacy diagnostic artifacts](../../artifacts/evaluation/).

## Unit-aware paired rerun

The QA labels now include amount-plus-unit expectations for the 2020 and 2024
financial answers. A new one-run comparison was made with full cited chunks
retained in the outputs. Retrieved-context and prompt hashes match across all
three models for each of the same five cases. The expected-label file was
updated after the GPT-OSS-20B generation, but labels do not enter the prompt;
the saved per-case prompt/context hashes confirm identical model inputs.

| Groq model | Expected source accuracy | Expected fact-case accuracy | Literal fact support in cited evidence | Cases |
| --- | ---: | ---: | ---: | ---: |
| `openai/gpt-oss-20b` | 1.00 | 0.75 (3/4) | 0.875 | 4 answerable + 1 correct denial |
| `qwen/qwen3.8-27b` | 1.00 | 1.00 (4/4) | 1.000 | 4 answerable + 1 correct denial |
| `openai/gpt-oss-120b` | 1.00 | 0.75 (3/4) | 0.875 | 4 answerable + 1 correct denial |

Both GPT-OSS variants failed the 2024 finance case: 20B called 61,824 billion
VND “61,824 million VND”; 120B answered approximately 61.8 billion VND. Qwen
gave the expected 61,824 and 9,453 billion VND figures. These are five-case,
single-run proxy results and literal checks, not human faithfulness scores or
general model rankings. Full scored outputs:
[20B](../../artifacts/evaluation/vinamilk-qa-gpt-oss-20b-full-evidence-scored.json),
[Qwen3.8](../../artifacts/evaluation/vinamilk-qa-qwen3.8-full-evidence-scored.json),
[120B](../../artifacts/evaluation/vinamilk-qa-gpt-oss-120b-full-evidence-scored.json).
A shuffled, model-blinded packet with source excerpts is ready at
`artifacts/evaluation/qa-review-packet-full-evidence.json`; its private mapping
key is ignored by Git. Two independent reviewers still need to complete and
return ratings.

The report prompt now explicitly forbids unit conversion, rounding and
currency changes. `ReportAgent` also withholds financial summaries if their
numeric values, magnitude scales or cited currency are absent from the cited
evidence. Unit tests cover the million/billion error and rounded values. A
post-change live GPT-OSS-20B check hit Groq's token-per-day 429 before reaching
the 2024 case; its partial output is retained as
`vinamilk-qa-gpt-oss-20b-unit-guard-rate-limited-attempt.json` and is not a
scored result. The guard's behavior is unit-tested, but its end-to-end provider
effect remains unverified until the quota resets.

An authenticated five-case post-guard `/api/ask` rerun on 2026-09-28 is saved as
[`vinamilk-app-qa-post-unit-guard-20260928.json`](../../artifacts/evaluation/vinamilk-app-qa-post-unit-guard-20260928.json).
The FY2020 finance case passed route, source, citation, amount and unit checks.
Groq returned HTTP 429 during the FY2024 case; the runner stopped as designed,
leaving 1/2 attempted cases and three explicit unrun IDs. This is partial
evidence only and does not verify the corrected FY2024 response. The runner now
accepts `--output` and `--cases` so future attempts can preserve prior runs.

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

## Requested-record scope

The grounded QA prompt preserves document identity as well as claim scope. If
someone asks for a particular record (for example, an invoice or contract) but
retrieval supplies a report disclosure, the answer should name the actual
report, qualify the disclosure, and say the requested record was not present in
the retrieved sources. It should not turn that observation into terms of the
missing record or assert that the record does not exist elsewhere. The invoice
business-case scorer enforces the Vinamilk 2020 related-party payment-term
example and requires an explicit invoice-absence qualification; no authenticated
post-prompt live model run is recorded yet.

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
and report reviewer-level results before resolving disagreements. The scorer
also calculates exact agreement and quadratic-weighted Cohen's kappa for each
1–5 rating dimension, pairing only responses both reviewers scored. With this
small packet these agreement statistics are descriptive, not a reliability
claim; kappa is `null` when chance-expected disagreement is zero or paired
ratings are unavailable. Current
artifacts contain no completed semantic ratings, so no semantic model winner
can yet be claimed.

To run the blind comparison, prepare a shuffled packet and keep its mapping key
private from reviewers:

```bash
uv run python scripts/agents/qa_human_review.py prepare \
  --runs artifacts/evaluation/vinamilk-qa-gpt-oss-20b-full-evidence.json \
         artifacts/evaluation/vinamilk-qa-qwen3.8-full-evidence.json \
         artifacts/evaluation/vinamilk-qa-gpt-oss-120b-full-evidence.json \
  --output artifacts/evaluation/qa-review-packet-full-evidence.json \
  --key-output artifacts/evaluation/qa-review-private-key-full-evidence.json
```

Give each reviewer an independent copy of the packet, named
`qa-review-reviewer-1-full-evidence.json` and
`qa-review-reviewer-2-full-evidence.json`. Once each has filled all ratings and
a distinct anonymous reviewer ID, import them together:

```bash
uv run python scripts/agents/qa_human_review.py import \
  --packets artifacts/evaluation/qa-review-reviewer-1-full-evidence.json \
           artifacts/evaluation/qa-review-reviewer-2-full-evidence.json \
  --key artifacts/evaluation/qa-review-private-key-full-evidence.json \
  --output-dir artifacts/evaluation/human-reviewed-full-evidence
```

The preparer rejects runs with different case sets or retrieved-context hashes.
The packet omits model/run labels and replaces source case IDs with random
blind IDs; the separate key maps randomized response IDs and blind case IDs
back to each run. Import validates complete response coverage, reviewer
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
