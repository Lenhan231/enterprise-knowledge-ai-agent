# Docling 5-Page Pipeline Pilot

Private, inference-only smoke-test input set with exactly five owner-reviewed page images, one page from each of five source documents.

- `shared-html-reviewed-pages.jsonl`: five page IDs, root-relative image paths, and SHA-256 hashes; no answer labels.
- `<reference_id>.png`: one page image per selected source document.

Use this only to verify a changed Docling configuration completes end to end on Kaggle before running the full benchmark. Do not tune thresholds, compare model quality, or report benchmark metrics from this pilot.
