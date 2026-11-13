# Invoice extraction experiments bundle

Collected 2026-11-12 from the local project workspace. This archive includes historical benchmark summaries and raw predictions, OCR evidence, scoring/reproduction code, the fine-tuning notebook, synthetic training data (split into GitHub-compatible chunks), the final Qwen3-0.6B LoRA adapter, and a consolidated rerun of five models (Groq is partial because its daily token quota was exhausted).

## Included

- `reports/`: historical score summaries, original model outputs, and reproducibility notebooks.
- `groq-gpt-oss-120b/` and `groq-gpt-oss-20b/`: historical predictions, runner/scoring artifacts, and comparison notes.
- `ocr-and-qwen-api-comparison/`: shared 50-invoice OCR output, evaluated predictions, and summaries for Qwen/API prompt runs.
- `qwen3-0.6b-finetune/`: synthetic 1,000-invoice dataset archive, labels/manifest, Kaggle notebook, adapter, and version 9 evaluation outputs.
- `rerun-2026-11-12/`: same-cache results for Qwen3-0.6B base, fine-tuned Qwen3-0.6B, Qwen3-1.7B base, Groq GPT-OSS-120B (partial), and Gemini 3.1 Flash-Lite. Includes per-invoice predictions, metrics, the report, Kaggle notebook, exact OCR input, and local API reproduction script.

## Reproducibility notes

The rerun report is `rerun-2026-11-12/report.md`; all model runs use the same 50 held-out invoice files, labels, and Kaggle OCR cache. Qwen inference ran on Kaggle; Groq and Gemini API calls ran locally because Kaggle's secret service returned `ConnectionError`. Groq completed 6/50 before its 200,000-token daily quota was exhausted. The fine-tuning notebook documents the Qwen3-0.6B LoRA training path and Kaggle setup. Provider credentials are expected to be configured separately. **No `.env`, API keys, or other secrets are included.**

To reconstruct the synthetic dataset ZIP, concatenate all `qwen3-0.6b-finetune/invoice-synthetic-1000-sft.zip.part*` files in numeric order. For example: `cat qwen3-0.6b-finetune/invoice-synthetic-1000-sft.zip.part* > qwen3-0.6b-finetune/invoice-synthetic-1000-sft.zip`. The model download cache and intermediate optimizer/checkpoint snapshots are omitted; they are re-downloadable or superseded by the final adapter and result artifacts.
