# Document pipeline benchmark

Compare PP-StructureV3, MinerU Basic, and Docling using the same inputs. The complete benchmark and tuning decision are in [`results/benchmark-report.md`](results/benchmark-report.md); [`plan.md`](plan.md) records scope, data locations, and protocol.

Proposal preprocessing areas not yet covered by parser-pipeline metrics are
tracked in [`follow-up-metrics.md`](follow-up-metrics.md).

## Use these data folders

| Track | Candidate/review data | Official benchmark input |
|---|---|---|
| OCR | [`ocr/candidate-review/`](ocr/candidate-review/) — 520 candidate regions, IDs `OCR-CAND-*` | [`ocr/reference/`](ocr/reference/) — 500 adjudicated crops, issuer split, image-only PDFs |
| Tables | [`tables/candidate-review/`](tables/candidate-review/) — 220 regions | [`tables/reference/`](tables/reference/) — 150 accepted tables and grids |
| Layout | [`layout/exploratory/`](layout/exploratory/) — old prose-heavy run | [`layout/inputs/`](layout/inputs/) — official table-stratified 200 pages |
| Reading order | [`vn-enterprise-reading-order-reference.json`](../../../data/evaluation/layout/vn-enterprise-reading-order-reference.json) — 100 assistant-adjudicated development pages | [`results/reading-order/`](results/reading-order/) — per-engine development diagnostics; not a locked-test result |

Only the **reference/input** folder is used for official scores. For layout, `layout/inputs/` is the dataset root: its nested `inputs/` holds the 200 PDFs, `page-images/` holds rendered previews, and `manifest.json` maps them to source pages and splits. `kaggle-dataset/inputs/` is the upload copy. `exploratory/` is the older v1 input set; `exploratory-review/` contains v1 detector proposals and review aids, not labels. Review folders are for candidate labels and provenance. OCR candidate IDs and scoring IDs are different; do not join them by numeric suffix.

## Score the available tracks

```bash
uv run --extra evaluation python tools/processing/evaluate_document_pipeline_ocr.py
uv run --extra evaluation python tools/processing/evaluate_document_pipeline_tables.py
```

Score the 100-page reading-order development diagnostic against saved layout runs:

```bash
for engine in pp-structurev3 mineru docling; do
  python tools/processing/evaluate_document_pipeline_reading_order.py \
    --engine "$engine" \
    --raw-root "artifacts/evaluation/document-pipelines/results/layout-200-pages-v2/$engine/layout-200-pages-v2" \
    --output "artifacts/evaluation/document-pipelines/results/reading-order/$engine.json"
done
```

Reports go under `results/`. Folder names there retain run identifiers used by Kaggle; they are outputs, not alternate datasets.
