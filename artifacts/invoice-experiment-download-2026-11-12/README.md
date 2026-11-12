# Invoice extraction experiments bundle

Collected 2026-11-12 from the local project workspace. This archive includes benchmark reports, raw predictions, OCR evidence, inspectable HTML reviews, scoring/reproduction code, fine-tuning notebook, synthetic training data (split into GitHub-compatible chunks), and the final Qwen3-0.6B LoRA adapter.

## Included

- `reports/`: consolidated report, score summaries, original model outputs, and reproducibility notebooks.
- `groq-gpt-oss-120b/` and `groq-gpt-oss-20b/`: benchmark predictions, runner/scoring artifacts, and HTML review pages.
- `ocr-and-qwen-api-comparison/`: shared 50-invoice OCR output, evaluated predictions, summaries, and HTML inspection views for Qwen/API prompt runs.
- `qwen3-0.6b-finetune/`: synthetic 1,000-invoice dataset archive, labels/manifest, Kaggle notebook, adapter, and version 9 evaluation outputs.
- `interrupted-rerun-2026-11-12/`: partial artifacts from a newly started five-model rerun. This run was interrupted and is **not a completed benchmark**; its partial API output must not be treated as a score.

## Reproducibility notes

The main comparison recorded in the report uses a 50-invoice cohort. OCR was shared across model comparisons where the saved artifacts indicate. The fine-tuning notebook documents the Qwen3-0.6B LoRA training path and Kaggle setup. Provider credentials are expected to be configured separately as environment variables/Kaggle Secrets. **No `.env`, API keys, or other secrets are included.**

To reconstruct the synthetic dataset ZIP, concatenate all `qwen3-0.6b-finetune/invoice-synthetic-1000-sft.zip.part*` files in numeric order. For example: `cat qwen3-0.6b-finetune/invoice-synthetic-1000-sft.zip.part* > qwen3-0.6b-finetune/invoice-synthetic-1000-sft.zip`. The model download cache and intermediate optimizer/checkpoint snapshots are omitted; they are re-downloadable or superseded by the final adapter and result artifacts.
