# Fine-tuned Qwen3-0.6B · prompt rerun v3

50 invoices; same saved OCR revision and Modal adapter as the earlier runs. The only intended variable is the prompt text.

| Metric | Original | Prompt v2 | Prompt v3 |
|---|---:|---:|---:|
| Whole-invoice exact | 10% | 14% | 8% |
| `invoice_no` exact | 22% | 22% | 20% |
| `seller` exact | 96% | 96% | 92% |
| `subtotal` exact | 70% | 68% | 54% |
| `tax_amount` exact | 98% | 96% | 96% |
| `total_amount` exact | 98% | 98% | 98% |
| Exact item-row rate | 96.1% | 94.4% | 96.1% |
| Mean latency | 22.3s | 27.6s | 27.9s |

## Result

All 50/50 calls returned schema-valid JSON. Prompt v3 scored 8% (4/50), down from prompt v2’s 14% (7/50) and the original 10% (5/50). `invoice_no` fell to 20% (10/50); subtotal fell to 54% (27/50). Item-row exact returned to 96.1%.

Paired with v2, invoice-number errors did not improve: zero fixes and one regression. Subtotal had two fixes and nine regressions. This longer instruction set is not an improvement on this 50-invoice set.

Examples from the new run:

- `invoice_0079.pdf`: the model returns the seller name as `invoice_no`, despite OCR containing `Số: DEMO26-0079`.
- `invoice_0090.pdf`: OCR lists `22.448.800 Thuế GTGT` and `303.058.800 Tổng tiền thanh toán`; model assigns `303.058.800` to tax and invents `583.678.800` as total.
- `invoice_0043.pdf`: model assigns the payable total to `subtotal`.

Interpretation: more prompt rules do not reliably make this 0.6B adapter bind labels to values. The failure includes semantic field substitution and, in some records, incorrect number generation. Prompt-only tuning is not resolving it.

Artifacts: `finetuned_prompt_v3_results.json` has full outputs and raw responses; `finetuned-prompt-v3-review.html` provides interactive per-invoice review.
