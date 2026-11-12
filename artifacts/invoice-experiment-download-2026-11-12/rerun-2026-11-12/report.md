# Invoice extraction rerun — 2026-11-12

## Scope

All models use the same 50 held-out invoices, labels, and the exact `holdout-ocr.json` downloaded from Kaggle dataset `ltrngnhn/invoice-50-holdout-ocr-cache` (SHA-256 in `results/metrics.json`). OCR was produced by Docling 2.129.0 with fine-tuned VietOCR. The Qwen LoRA adapter was reused; training was not repeated. Qwen used Kaggle GPU inference; Groq and Gemini used local `.env` keys after Kaggle secret access failed before provider requests.

## Results

| Model | Successful | Whole invoice exact | Item row exact (macro) | Mean latency / invoice |
|---|---:|---:|---:|---:|
| qwen3-0.6b-base | 50/50 | 0.0% | 0.0% | 9.24s |
| qwen3-0.6b-lora | 50/50 | 0.0% | 91.4% | 45.28s |
| qwen3-1.7b-base | 50/50 | 0.0% | 87.6% | 29.58s |
| groq | 6/50 | — | — | — |
| gemini | 50/50 | 50.0% | 91.1% | 9.17s |

Whole-invoice exact requires matching all normalized header fields, totals, item count and every item row. The scoring function treats digits-only fields numerically and ignores a leading Vietnamese `Ngày` label for dates.

## Interpretation

The base Qwen3-0.6B did not recover line items. Fine-tuning raised item-row exact accuracy substantially, with slower inference. Qwen3-1.7B base was faster than the fine-tuned 0.6B and retained strong item-row accuracy. Neither Qwen model achieved a fully exact invoice under the strict all-fields metric. Gemini completed 50/50. Groq is incomplete: 6/50 succeeded, 39 requests were rejected with HTTP 429, and 5 invoices were not reached. The provider reported its 200,000-token daily limit was at 199,731. Accuracy metrics are withheld for Groq because coverage is partial.

## Reproduction and artifacts

- Kaggle notebook: [Invoice Qwen 50 Rerun 2026 11 12](https://www.kaggle.com/code/ltrngnhn/invoice-qwen-50-rerun-2026-11-12). Qwen was version 1; API-only code was Quick Saved as version 2 and attempted as version 3, which stopped before requests because Kaggle secret access raised `ConnectionError`.
- Rerun source commit: `535932f912949f860ef735df690c3bc60714f8cf`.
- Per-invoice predictions, scored rows, metrics and execution log are in [`results/`](results/).
- Exact OCR input used by all five models: [`inputs/holdout-ocr.json`](inputs/holdout-ocr.json). The initial local API outputs from an older OCR serialization were discarded and rerun against this verified Kaggle cache.
- API runner: [`run_api_benchmark.py`](run_api_benchmark.py). It reads provider keys from the local `.env` without writing them to outputs.
