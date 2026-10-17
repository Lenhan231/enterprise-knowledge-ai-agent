# Layout pipeline benchmark: v2 200-page run

**Status:** all three Kaggle kernels completed 200/200 inputs and warmed three-pass performance runs. The canonical v2 reference now covers 200/200 pages (121 development, 39 validation, 40 locked test), with 2,244 assistant-adjudicated regions including 14 supplemental signatures. Full-page scores are available for all three engines at IoU 0.50. Labels are not independently human-reviewed; these are fixed-output precision/recall/F1 scores, not AP/mAP. The separate table-crop reference has 150 valid tables; one photo candidate was excluded and a complete financial-ratio table was added.

## Full-page layout score on all 200 pages

All 200 v2 input pages now have source-image-based assistant-adjudicated boxes. The issuer-level split is 121 development, 39 validation, and 40 locked-test pages. Across the reference there are 678 title, 1,121 text, 200 table, and 231 figure regions, plus 14 supplemental signatures. Signature regions are not included in the four-class score. Ground truth provenance is recorded in `data/evaluation/layout/vn-enterprise-layout-v2-adjudicated-reference.json` and the page-level audit.

The scorer matches same-class boxes at IoU ≥ 0.50 using a fixed one-to-one greedy assignment. The pipeline exports do not expose a common confidence score, so all mapped boxes are included. This is a fixed-output region match score, not a confidence-swept AP/mAP evaluation. See [`full-page-200-comparison.json`](full-page-200-locked-test/full-page-200-comparison.json) and the individual split outputs in [`full-page-200-locked-test/`](full-page-200-locked-test/).

### Locked test (40 pages)

| Pipeline | Class | TP | FP | FN | Precision | Recall | F1 |
|---|---|---:|---:|---:|---:|---:|---:|
| PP-StructureV3 | Title | 38 | 64 | 74 | 0.373 | 0.339 | 0.355 |
| PP-StructureV3 | Text | 102 | 135 | 74 | 0.430 | 0.580 | 0.494 |
| PP-StructureV3 | Table | 14 | 2 | 25 | 0.875 | 0.359 | 0.509 |
| PP-StructureV3 | Figure | 30 | 22 | 19 | 0.577 | 0.612 | 0.594 |
| PP-StructureV3 | **Micro** | **184** | **223** | **192** | **0.452** | **0.489** | **0.470** |
| MinerU Basic | Title | 48 | 42 | 64 | 0.533 | 0.429 | 0.475 |
| MinerU Basic | Text | 119 | 184 | 57 | 0.393 | 0.676 | 0.497 |
| MinerU Basic | Table | 36 | 4 | 3 | 0.900 | 0.923 | 0.911 |
| MinerU Basic | Figure | 36 | 29 | 13 | 0.554 | 0.735 | 0.632 |
| MinerU Basic | **Micro** | **239** | **259** | **137** | **0.480** | **0.636** | **0.547** |
| Docling | Title | 62 | 59 | 50 | 0.512 | 0.554 | 0.532 |
| Docling | Text | 116 | 501 | 60 | 0.188 | 0.659 | 0.293 |
| Docling | Table | 34 | 3 | 5 | 0.919 | 0.872 | 0.895 |
| Docling | Figure | 37 | 64 | 12 | 0.366 | 0.755 | 0.493 |
| Docling | **Micro** | **249** | **627** | **127** | **0.284** | **0.662** | **0.398** |

MinerU Basic has the highest four-class micro F1 on this locked split (0.547); its table F1 is 0.911. This is evidence for this 40-page set and this scorer, not a universal model ranking. Docling emits substantially more text and figure boxes, reducing precision against the paragraph/block taxonomy.

### Development + validation (160 pages, diagnostic)

| Pipeline | Micro P | Micro R | Micro F1 | Title F1 | Text F1 | Table F1 | Figure F1 |
|---|---:|---:|---:|---:|---:|---:|---:|
| PP-StructureV3 | 0.645 | 0.619 | 0.632 | 0.592 | 0.655 | 0.546 | 0.669 |
| MinerU Basic | 0.637 | 0.765 | 0.696 | 0.719 | 0.641 | 0.963 | 0.736 |
| Docling | 0.409 | 0.814 | 0.545 | 0.767 | 0.429 | 0.922 | 0.617 |

Development/validation is diagnostic and must not be used to tune after the locked-test comparison. The per-class outputs include TP/FP/FN and per-page details. Because the test labels were assistant-adjudicated rather than independently human-reviewed, borderline box boundaries and class choices may affect scores. No AP/mAP is reported because there is no common confidence score and threshold sweep.

## Accuracy on the same eight pages

References come from [`vn-enterprise-layout-pilot-v1-adjudicated-reference.json`](../../../../../data/evaluation/layout/vn-enterprise-layout-pilot-v1-adjudicated-reference.json), generated from the canonical pilot manifest plus the assistant adjudication exclusions. It contains 36 regions across title, text, table, and figure. The expanded COCO export disagrees on the cover page and was not used. Review was assistant visual adjudication, not independent human review.

Predictions are matched by class at IoU ≥ 0.50. Pipeline exports do not expose a common per-box confidence score, so every mapped region is included; these are fixed-output precision/recall/F1, not AP/mAP. Boxes are normalized to page coordinates. Page furniture and captions are excluded. Signatures and formulas are outside the four scored classes. Mappings are recorded in each JSON result and implemented in [`evaluate_document_pipeline_layout.py`](../../../../../tools/processing/evaluate_document_pipeline_layout.py).

| Pipeline | Class | TP | FP | FN | Precision | Recall | F1 |
|---|---|---:|---:|---:|---:|---:|---:|
| PP-StructureV3 | Title | 1 | 9 | 11 | 0.100 | 0.083 | 0.091 |
|  | Text | 8 | 19 | 6 | 0.296 | 0.571 | 0.390 |
|  | Table | 2 | 0 | 5 | 1.000 | 0.286 | 0.444 |
|  | Figure | 2 | 1 | 1 | 0.667 | 0.667 | 0.667 |
|  | **Micro** | **13** | **29** | **23** | **0.310** | **0.361** | **0.333** |
| MinerU Basic | Title | 2 | 11 | 10 | 0.154 | 0.167 | 0.160 |
|  | Text | 10 | 38 | 4 | 0.208 | 0.714 | 0.323 |
|  | Table | 7 | 0 | 0 | 1.000 | 1.000 | 1.000 |
|  | Figure | 3 | 3 | 0 | 0.500 | 1.000 | 0.667 |
|  | **Micro** | **22** | **52** | **14** | **0.297** | **0.611** | **0.400** |
| Docling | Title | 3 | 19 | 9 | 0.136 | 0.250 | 0.176 |
|  | Text | 10 | 136 | 4 | 0.068 | 0.714 | 0.125 |
|  | Table | 7 | 0 | 0 | 1.000 | 1.000 | 1.000 |
|  | Figure | 3 | 10 | 0 | 0.231 | 1.000 | 0.375 |
|  | **Micro** | **23** | **165** | **13** | **0.122** | **0.639** | **0.205** |

Docling's exported text nodes are much finer-grained than the reference paragraph boxes (146 mapped text regions vs 14 references). This inflates false positives under raw-node scoring; the score measures the exported pipeline regions as-is and should not be read as a detector-only comparison. The table and figure scores also come from only seven and three reference regions, respectively. No model winner can be selected from this subset.

Machine-readable results: [`PP-StructureV3`](pp-structurev3/pilot-layout-scores.json), [`MinerU`](mineru/pilot-layout-scores.json), and [`Docling`](docling/pilot-layout-scores.json).

## Table-region recall on 114 v2 pages

The table reference [`vn-enterprise-layout-v2-table-reference.json`](../../../../../data/evaluation/layout/vn-enterprise-layout-v2-table-reference.json) transfers 150 visually accepted table extents from the table-crop review to the matching full-page 180-DPI images. Source-page render dimensions were checked against each v2 input; a visual overlay check confirmed the mapped region for TBL-001. Labels are assistant-adjudicated, not human-reviewed.

There are 119 known-positive table regions across 91 development/validation pages and 30 locked-test regions across 23 pages. This is a positive-only subset, not an exhaustive inventory of every table on those pages. `TAB-151` is in the 150-crop table-recognition reference but its source page is not among the 200 layout inputs, so it does not add a layout known-positive box. Regions match at class-specific IoU ≥ 0.50. Report recall against known boxes; unmatched predictions are listed but not counted as false positives, so precision cannot be calculated.

| Pipeline | Known tables matched | Missed known tables | Known-positive recall | Unmatched table predictions, not scored as FP | Table predictions |
|---|---:|---:|---:|---:|---:|
| PP-StructureV3 | 43/119 | 76 | 0.361 | 17 | 60 |
| Docling | 112/119 | 7 | 0.941 | 43 | 155 |
| MinerU Basic | 113/119 | 6 | 0.950 | 40 | 153 |

These results measure recall on selected accepted table regions, not full-page table precision. MinerU and Docling recall more of these known regions than PP-StructureV3, while both also emit more unmatched table regions; their status cannot be judged without exhaustive labels. Do not select a winner from this recall-only subset. Machine-readable scores: [`PP-StructureV3`](pp-structurev3/table-known-positive-recall.json), [`MinerU`](mineru/table-known-positive-recall.json), and [`Docling`](docling/table-known-positive-recall.json).

### Locked-test table regions (30 valid known positives)

The 30 valid locked-test boxes were scored once after freezing the current pipeline
outputs. This remains known-positive recall only; unmatched predictions are not
false positives because page labels are not exhaustive.

| Pipeline | Matched | Missed | Known-positive recall | Unmatched predictions, not scored as FP | Predictions |
|---|---:|---:|---:|---:|---:|
| PP-StructureV3 | 13/30 | 17 | 0.433 | 3 | 16 |
| Docling | 27/30 | 3 | 0.900 | 10 | 37 |
| MinerU Basic | 28/30 | 2 | 0.933 | 12 | 40 |

These are held-out partial results for table regions only. The locked set is no
longer available for tuning; full-page layout labels are still required for
precision, AP/mAP, and the remaining layout classes. Machine-readable scores:
[`PP-StructureV3`](pp-structurev3/table-known-positive-recall-locked-test.json),
[`MinerU`](mineru/table-known-positive-recall-locked-test.json), and
[`Docling`](docling/table-known-positive-recall-locked-test.json).

## Historical one-pass performance (superseded)

These early one-pass timings are retained as run history. The canonical warmed
three-repeat resource measurements are in the [benchmark report](../benchmark-report.md)
and raw rerun artifacts under [`performance-rerun-20261015/`](performance-rerun-20261015/).
The older run did not sample VRAM.

| Pipeline | Successful pages | Init (s) | Median (s/page) | P95 (s/page) | Total (s) | Peak host RSS (MiB) | Peak VRAM |
|---|---:|---:|---:|---:|---:|---:|---|
| PP-StructureV3 | 200/200 | 38.01 | 1.60 | 2.61 | 383.57 | 3,397.9 | Not recorded |
| Docling | 200/200 | 0.31 | 17.12 | 29.12 | 3,505.81 | 6,559.6 | Not recorded |
| MinerU Basic | 200/200 | Not separated | 21.21 | 25.81 | 4,322.35 | 103.6* | Not recorded |

All ran on Kaggle GPU kernels. PP-StructureV3 used PP-DocLayout-S, PP-OCRv5 mobile, and table recognition. Docling used CUDA acceleration, OCR with RapidOCR ONNX Runtime, and table structure recognition. MinerU used the Basic Torch backend and launched the CLI once per page, so its timings include repeated startup; its reported RSS is the parent runner only and excludes child parser processes. Docling's constructor time may omit lazy model initialization. Thus, these are measurements of the submitted execution paths, not a controlled warmed-throughput ranking. Exact metadata and per-page timing rows are in each engine's `run-metadata.json`; the consolidated summary is [`performance-summary.json`](performance-summary.json).

## Remaining benchmark work

- Layout full-page scoring is complete for the 200-page v2 set. Review the assistant-adjudicated boxes independently before presenting the scores as human-validated; the current report must retain the assistant-adjudication caveat.
- Reading order is scored on 100 development pages for all three pipelines; see [`../reading-order/report.md`](../reading-order/report.md). It remains a development diagnostic, not a locked-test result.
- The table reference contains 150 valid tables. TAB-151's one-page outputs have been added to all three saved pipeline results; the 32-table locked test is unchanged. See [`../table-150-v1/report.md`](../table-150-v1/report.md).
- OCR, table, and layout baselines are complete. The canonical repeated performance measurements and MinerU tuning decision are consolidated in [`../benchmark-report.md`](../benchmark-report.md). Do not tune or choose a production winner from the locked test.
