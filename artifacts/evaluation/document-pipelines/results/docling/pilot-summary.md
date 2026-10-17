# Docling pilot run

**Status:** completed exploratory run; not a model-selection result.

## Run setup

- 20 identical one-page PDF inputs from `pilot-v1/manifest.json`.
- Docling 2.129.0; RapidOCR 3.9.2, ONNX Runtime backend, Vietnamese OCR; CUDA accelerator selected.
- Kaggle reported Tesla T4 GPUs. The process reported peak RSS of 6,270 MiB.
- 20/20 pages returned `ConversionStatus.SUCCESS`.
- Raw Docling JSON and Markdown are retained under `document-pipeline-pilot/raw_pages/`.

## Exploratory OCR check

Two pages have single-reviewer full-page transcripts. CER/WER below use NFC,
case folding, collapsed whitespace, and a Markdown-to-text cleanup; punctuation
and Vietnamese diacritics are retained. These two pages are from one scanned
Long Hau report, so the scores only check that the scorer and output adapter
work.

| Page | CER | WER |
|---|---:|---:|
| Long Hau cover, page 1 | 19.11% | 47.22% |
| Long Hau board report, page 3 | 22.47% | 57.11% |

The output contains visible Vietnamese OCR errors, including dropped or
misrecognized diacritics. Use the unified scorer in
[`pilot-comparison.json`](../pilot-comparison.json) for the cross-pipeline
figures. These two single-reviewer scores are only a pilot check, not evidence
to select Docling.

## Structure and resource observations

- The parser emitted 16 table objects across 9 pages. This is a count of
  predictions only; the pilot does not yet have complete cell-grid references
  for these tables, so no TEDS or cell-accuracy score is available.
- On the separately labeled Long Hau balance-sheet page, Docling contained all
  four selected row anchors. This is 4/4 exact anchor rows on one page, not a
  table-structure score.
- No human-reviewed reading-order labels are available. The current 13 layout
  annotations are AI-assisted and remain review-required, so no layout score is
  reported.
- Total run time was 342.10 s. The median per-page conversion was 15.60 s and
  interpolated p95 was 27.29 s. The converter constructor took 0.34 s, but model loading is
  lazy: first-page conversion took 25.28 s. Treat the first-page value as cold
  start plus inference; do not compare the constructor time as model-init time.
- These are one-pass pilot measurements. They do not meet the planned three-run
  median/p95 protocol or the 200-page performance target.

## References and artifacts

- Raw results: `document-pipeline-pilot/raw_pages/`
- Machine-readable run details: `document-pipeline-pilot/run-metadata.json`
- Kaggle kernel: <https://www.kaggle.com/code/ltrngnhn/vietnamese-enterprise-pilot-docling>
- Input dataset: <https://www.kaggle.com/datasets/ltrngnhn/vietnamese-enterprise-document-pipeline-pilot-v1>
