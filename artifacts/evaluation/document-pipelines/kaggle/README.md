# Kaggle workflow

## Dataset reuse rule

- The shared HTML benchmark uses `letrongnhan/vietnamese-enterprise-e2e-hard-scans` as its single Kaggle input dataset.
- Keep one stable Kaggle dataset ID for this benchmark and update that dataset when its inference inputs change.
- Do not create separate `v1`, `v2`, timestamped, or per-run Kaggle datasets.
- Before updating, verify the target owner/dataset ID and compare input file hashes to avoid updating the wrong dataset or re-uploading unchanged files.
- Store inference inputs in the Kaggle dataset; keep owner-reviewed references and scoring labels local, then evaluate returned predictions locally.
- `shared-html/manifest.jsonl` lists the current inference images without annotation labels.
