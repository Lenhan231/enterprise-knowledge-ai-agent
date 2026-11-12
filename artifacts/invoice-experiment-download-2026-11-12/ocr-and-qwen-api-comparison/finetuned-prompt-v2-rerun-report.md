# Fine-tuned Qwen3-0.6B prompt rerun

50 invoices, same saved OCR (`lenhanm1/enterprise-printed-ocr-vietocr-tesseract` revision `6deb1cb10ecbf240aead77525e80aa4c58adfb23`), same Modal model/adapter. Only the current generalized extraction prompt changed; OCR was not rerun.

| Metric | Previous prompt | Revised prompt | Change |
|---|---:|---:|---:|
| Whole-invoice exact | 10.0% | 14.0% | +4.0 pp |
| Successful/schema-valid | 50/50 | 50/50 | — |
| Exact item-row rate | 96.1% | 94.4% | -1.7 pp |
| Description CER | 0.0032 | 0.0032 | unchanged |
| Description WER | 0.0046 | 0.0046 | unchanged |
| Mean end-to-end latency | 22.3s | 27.6s | +5.3s |

## Header exact match

| Field | Previous | Revised | Change |
|---|---:|---:|---:|
| `invoice_no` | 22.0% | 22.0% | +0.0 pp |
| `date` | 100.0% | 100.0% | +0.0 pp |
| `seller` | 96.0% | 96.0% | +0.0 pp |
| `buyer` | 98.0% | 100.0% | +2.0 pp |
| `subtotal` | 70.0% | 68.0% | -2.0 pp |
| `tax_amount` | 98.0% | 96.0% | -2.0 pp |
| `total_amount` | 98.0% | 98.0% | +0.0 pp |

## Reading the result

The prompt change produced only a small whole-invoice gain: 5/50 to 7/50. `invoice_no` stayed at 11/50 (22%), the dominant bottleneck. In failed examples the model still selected the invoice title, seller/buyer name, or a monetary value even though OCR contains `Số: DEMO26-…`. This shows the 0.6B LoRA model is not reliably following the generalized field-association instructions; prompt wording alone did not fix it.

Subtotal exact match moved from 35/50 (70%) to 34/50 (68%). Five invoices were corrected and six regressed. Item-row exact decreased from 96.1% to 94.4%, while description CER/WER stayed unchanged. Therefore the new prompt is not a clear overall improvement and should not be treated as a validated accuracy win.

Artifacts: `finetuned_prompt_v2_results.json` contains all outputs and per-invoice checkpointed results; `rerun_finetuned_prompt_v2.py` reproduces this run against the saved OCR. The shared prompt source is `src/document_processing/invoice_text_processor.py`.
