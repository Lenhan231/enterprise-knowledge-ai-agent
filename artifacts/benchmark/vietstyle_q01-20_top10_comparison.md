# VietStyle benchmark comparison

| Run | Retrieval request k | Final top_k | Mean source recall@10 |
|---|---:|---:|---:|
| Previous (vietstyle_q01-20_translated_hybrid.json) | 100 | 10 | 0.8167 |
| New (vietstyle_q01-20_translated_hybrid_top10.json) | 10 | 10 | 0.8583 |

Both runs cover the same 20 questions, the same five document IDs, the same three models, and use top_k=10. The new run caps dense and lexical retrieval requests at 10 before fusion; the prior run requested 100 candidates and retained 10 fused contexts.

| Model | Previous generated | New generated | Change |
|---|---:|---:|---:|
| gpt_oss_20b | 15/20 | 18/20 | +3 |
| cloudflare_llama_3_1_8b | 17/20 | 15/20 | -2 |
| qwen3 | 17/20 | 20/20 | +3 |

## Questions with changed source recall@10

| Question | Previous | New | Change |
|---|---:|---:|---:|
| Q08 | 0.67 | 0.33 | -0.33 |
| Q12 | 0.67 | 1.00 | +0.33 |
| Q17 | 0.50 | 1.00 | +0.50 |
| Q20 | 0.67 | 1.00 | +0.33 |

Comparison uses the saved reports. Generation completion can vary with API availability; source recall is the retrieval comparison.
