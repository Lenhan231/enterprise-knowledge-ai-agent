# Vietnamese enterprise document pipeline benchmark

## Decision

**Tune MinerU Basic next.** This is a research and tuning choice, not a
production deployment decision. The choice is based on development and
validation quality: MinerU leads OCR on the 100 validation crops, has the best
validation table cell accuracy and table-found rate, and the highest validation
full-page layout micro F1. It also has the highest reading-order block coverage
on the 100-page development diagnostic, with pairwise order accuracy close to
Docling. Its main trade-off is latency: PP-StructureV3 is much faster in the
persistent parser-call benchmark. MinerU's per-page CLI runner adds substantial
startup overhead; a separate batch run is faster and uses less GPU memory.

The tuning gate is MinerU's **frozen validation baseline** below. Make changes
using development data, select configurations using validation, and keep every
quality metric separate. The existing locked test has already been inspected
for the untuned baseline; it is not a clean final test for tuned results. A new
held-out set is required for final post-tuning claims. Nothing in this report
selects a production pipeline. The current V0/V1 CPU control is an exploratory
preprocessing ablation; hold MinerU V2–V4 until the required follow-up metrics
have been piloted across all three default pipelines. See the
[`follow-up metrics plan`](../follow-up-metrics.md) for the decision sequence.

## Dataset and evaluation status

| Track | Evaluated set | Current result status |
|---|---|---|
| OCR | 500 text crops: 299 development, 100 validation, 101 locked test | All three pipelines have saved outputs and CER/WER scores |
| Tables | 150 valid table crops: 89 development, 29 validation, 32 locked test | All three have outputs; cell position and grid dimensions scored, not TEDS |
| Layout | 200 pages: 121 development, 39 validation, 40 locked test | Four classes scored at IoU 0.50; fixed-output P/R/F1, not AP/mAP |
| Reading order | 100 development pages, 1,031 reference blocks | Coverage and pairwise order scored; no locked-test labels |
| Performance | Same 200 layout pages, Kaggle Tesla T4 | Three warmed repeats per pipeline rerun 2026-10-15 |

References are assistant-adjudicated and are not independently human-reviewed.
The OCR crops are 180-DPI image-only PDFs, so pipelines cannot use the original
PDF text layer. The table reference excludes one industrial-park photo and
includes TAB-151. Merged-cell spans and every table-cell transcript have not
been independently checked. The enterprise full-page layout score covers
title, text, table, and figure; its reference has 14 supplemental signature
regions and no formula boxes. Formula detection was separately evaluated as a
five-class transfer benchmark on HCMUS; see
[`formula-v2-report.md`](../../layout/hcmus-results/formula-v2-report.md).
Do not interpret that academic-document score as enterprise formula accuracy.
The 200-page layout inputs are also rasterized page images embedded in PDFs;
those scores do not evaluate native text-layer parsing for digital-born PDFs.
That follow-up requires source-page PDFs that preserve the original text layer.

## Why MinerU is the tuning candidate

The choice is made from development/validation results, not the locked-test
scores:

- **OCR validation (100 crops):** MinerU has 19.91% micro CER and 56.99% micro
  WER, compared with PP-StructureV3 at 28.87% / 73.53% and Docling at 28.67% /
  66.28%. Its macro CER/WER are also lowest: 15.79% / 53.19%.
- **Table validation (29 tables):** MinerU finds 29/29 and reaches 38.76% cell
  accuracy. Docling finds 24/29 at 32.79%; PP-StructureV3 finds 11/29 at 8.74%.
  MinerU and Docling tie at 41.38% exact-shape, and no pipeline has an exact
  grid. The table metric mixes detection, OCR, and structure reconstruction.
- **Layout validation (39 pages):** MinerU has the highest four-class micro
  F1 at 0.673 (P/R 0.645/0.704), compared with PP-StructureV3 at 0.621 and
  Docling at 0.578. MinerU leads title and table F1; PP-StructureV3 leads text
  and figure F1, so MinerU is the strongest overall balance rather than the
  leader on every class.
- **Reading order (100 development pages):** MinerU matches 808/1,031 blocks
  (78.4% coverage) and orders matched blocks at 97.2%. Docling has 97.8%
  pairwise accuracy but only 72.4% coverage; PP-StructureV3 has 58.6% coverage.
  This diagnostic has no validation or locked-test labels and is not a tuning
  gate.
- **Resources:** the new per-page CLI run reports 2,638 MiB process-tree RSS
  and 922 MiB GPU-process memory for MinerU, compared with 3,009 / 4,120 MiB
  for PP-StructureV3. The earlier directory-batch MinerU run used 3,232 MiB
  RSS and 1,370 MiB GPU-process memory while processing 3.48–3.67 seconds per
  document. These are different invocation modes and are not a pure model
  compute comparison.

PP-StructureV3 remains the speed-first alternative: in the new persistent
parser-call run its median was 1.57–1.63 seconds/page. MinerU's one-CLI-per-page
measurement was 20.46–20.54 seconds/page, including per-input process startup
and output writing. The directory-batch MinerU result is 3.48–3.67
seconds/document, still slower than PP's parser-call path. We accept this
latency trade-off for the next tuning round because OCR, table, and layout
quality are the current selection priorities. Re-measure both pipelines with
matching end-to-end boundaries before using these figures for deployment
capacity planning.

## OCR scores — 500 crops

Lower is better. “Dev + val” is the 399-crop combined score; per-split
validation is shown separately for tuning. Scores are percentages.

| Pipeline | Split (n) | Micro CER | Micro WER | Macro CER | Macro WER |
|---|---:|---:|---:|---:|---:|
| PP-StructureV3 | Dev (299) | 28.60 | 73.91 | 42.74 | 85.88 |
| PP-StructureV3 | Val (100) | 28.87 | 73.53 | 26.88 | 73.86 |
| PP-StructureV3 | Locked test (101) | 26.99 | 73.79 | 26.32 | 75.21 |
| PP-StructureV3 | Dev + val (399) | 28.65 | 73.84 | 38.76 | 82.87 |
| MinerU Basic | Dev (299) | 18.36 | 56.88 | 28.05 | 66.01 |
| MinerU Basic | Val (100) | **19.91** | **56.99** | **15.79** | **53.19** |
| MinerU Basic | Locked test (101) | **18.00** | **56.41** | **16.14** | **55.98** |
| MinerU Basic | Dev + val (399) | **18.66** | **56.90** | **24.98** | **62.79** |
| Docling | Dev (299) | 27.03 | 66.81 | 39.13 | 77.70 |
| Docling | Val (100) | 28.67 | 66.28 | 28.07 | 63.87 |
| Docling | Locked test (101) | 26.47 | 65.88 | 30.10 | 67.51 |
| Docling | Dev + val (399) | 27.35 | 66.71 | 36.36 | 74.23 |

## Table recognition scores — 150 valid tables

Cell accuracy compares normalized text at row/column positions. Exact-shape
checks row/column dimensions; exact-grid requires all cells and shape to match.
No pipeline reached a nonzero exact-grid rate. Values are percentages; table
found is predicted tables/reference tables.

| Pipeline | Split (n) | Tables found | Cell accuracy | Exact-shape | Exact-grid |
|---|---:|---:|---:|---:|---:|
| PP-StructureV3 | Dev (89) | 45/89 | 12.86 | 24.72 | 0 |
| PP-StructureV3 | Val (29) | 11/29 | 8.74 | 27.59 | 0 |
| PP-StructureV3 | Locked test (32) | 19/32 | 26.65 | 50.00 | 0 |
| PP-StructureV3 | All (150) | 75/150 | 15.01 | 30.67 | 0 |
| MinerU Basic | Dev (89) | 89/89 | **48.93** | **55.06** | 0 |
| MinerU Basic | Val (29) | **29/29** | **38.76** | 41.38 | 0 |
| MinerU Basic | Locked test (32) | 32/32 | 46.00 | 71.88 | 0 |
| MinerU Basic | All (150) | 150/150 | **46.74** | 56.00 | 0 |
| Docling | Dev (89) | 81/89 | 47.81 | 50.56 | 0 |
| Docling | Val (29) | 24/29 | 32.79 | 41.38 | 0 |
| Docling | Locked test (32) | 32/32 | **47.13** | **84.38** | 0 |
| Docling | All (150) | 137/150 | 45.31 | 56.00 | 0 |

Docling leads locked-test cell accuracy and exact-shape, but that split is not
used to choose the tuning candidate. These results are not TEDS/TEDS-Struct.

## Layout scores — 200 pages, IoU 0.50

Each cell lists precision / recall / F1. Signature and formula are not among
the four scored classes.

### Development + validation (160 pages)

| Pipeline | Micro | Title | Text | Table | Figure |
|---|---:|---:|---:|---:|---:|
| PP-StructureV3 | 0.645 / 0.619 / 0.632 | 0.671 / 0.530 / 0.592 | 0.607 / 0.710 / 0.655 | 0.939 / 0.385 / 0.546 | 0.717 / 0.626 / 0.669 |
| MinerU Basic | 0.637 / 0.765 / **0.696** | 0.799 / 0.654 / **0.719** | 0.539 / 0.788 / 0.641 | 0.946 / 0.981 / **0.963** | 0.679 / 0.802 / **0.736** |
| Docling | 0.409 / 0.814 / 0.545 | **0.756 / 0.777 / 0.767** | 0.291 / 0.812 / 0.429 | 0.890 / 0.957 / 0.922 | 0.497 / 0.813 / 0.617 |

### Locked test (40 pages; reported for completeness)

| Pipeline | Micro | Title | Text | Table | Figure |
|---|---:|---:|---:|---:|---:|
| PP-StructureV3 | 0.452 / 0.489 / 0.470 | 0.373 / 0.339 / 0.355 | 0.430 / 0.580 / 0.494 | 0.875 / 0.359 / 0.509 | 0.577 / 0.612 / 0.594 |
| MinerU Basic | 0.480 / 0.636 / 0.547 | 0.533 / 0.429 / 0.475 | 0.393 / 0.676 / 0.497 | 0.900 / 0.923 / **0.911** | 0.554 / 0.735 / **0.632** |
| Docling | 0.284 / 0.662 / 0.398 | 0.512 / 0.554 / **0.532** | 0.188 / 0.659 / 0.293 | **0.919 / 0.872 / 0.895** | 0.366 / 0.755 / 0.493 |

The locked test is already inspected for this baseline; do not use it to tune
or to make a new production claim. Full-page scores are fixed-output box
matches, not AP/mAP, because the exports do not provide a common confidence
score and threshold sweep.

The separate known-positive table-region recall track finds 28/30 locked
regions for MinerU (0.933), 27/30 for Docling (0.900), and 13/30 for
PP-StructureV3 (0.433). This is recall-only: unmatched predictions cannot be
counted as false positives because the pages are not exhaustively annotated.

## Reading order — 100 development pages

| Pipeline | Matched/reference blocks | Coverage | Correct pairs | Pairwise accuracy |
|---|---:|---:|---:|---:|
| PP-StructureV3 | 604/1,031 | 58.6% | 2,172/2,244 | 96.8% |
| MinerU Basic | 808/1,031 | **78.4%** | 4,217/4,339 | 97.2% |
| Docling | 746/1,031 | 72.4% | 3,488/3,566 | **97.8%** |

Pairwise accuracy is conditional on matched blocks. Reading order has no
validation or locked-test annotations and is only a development diagnostic.

## Performance — rerun 2026-10-15

Same 200 layout pages, Kaggle Tesla T4, one-page warm-up, three measured
repeats. Memory sampled every second across setup, warm-up, and inference.
“GPU process / device” separates PID-matched process memory from system-wide
GPU memory. Throughput is 200 pages divided by pass wall time. Every repeat
completed 200/200 pages.

| Pipeline and invocation | Setup | Warm-up | Median s/page (three repeats) | P95 s/page (three repeats) | Pass wall seconds | Pages/s | Peak process-tree RSS | Peak GPU process / device |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| PP-StructureV3, persistent parser | 39.58 s | 5.78 s | 1.634 / 1.569 / 1.568 | 2.645 / 2.509 / 2.553 | 339.7 / 326.8 / 326.2 | 0.589 / 0.612 / 0.613 | 3,009.3 MiB | 4,120 / 4,123 MiB |
| MinerU Basic, one CLI per page | ~0 s* | 47.76 s | 20.536 / 20.499 / 20.462 | 24.843 / 24.882 / 24.742 | 4,156.1 / 4,138.3 / 4,151.1 | 0.048 / 0.048 / 0.048 | 2,638.3 MiB | 922 / 937 MiB |
| Docling, persistent parser | 25.75 s | 37.50 s | 17.395 / 16.829 / 16.742 | 29.811 / 27.013 / 27.940 | 3,535.8 / 3,299.7 / 3,290.0 | 0.057 / 0.061 / 0.061 | 7,206.9 MiB | 938 / 941 MiB |

*MinerU setup is the parent runner's setup time; each separate CLI launch is
included in its per-page latency. A separate directory-batch MinerU run
processed documents in 3.48–3.67 seconds/document with 3,232.2 MiB RSS and
1,370 MiB GPU-process memory. It uses a different timing boundary and writes
ZIP outputs, so do not compare it as if it were the same parser call.

Resource figures are sampled peaks; process-tree RSS can count shared pages
more than once. These run paths do not represent isolated model compute.

## MinerU tuning acceptance gate

Use the development split to change configuration and the validation split to
select it. At the report precision, a candidate configuration must not regress
any of these frozen MinerU validation metrics:

| Track | Validation baseline | Better direction |
|---|---|---|
| OCR, 100 crops | Micro CER/WER 19.91% / 56.99%; macro CER/WER 15.79% / 53.19% | Lower |
| Tables, 29 references | 29/29 found; cell accuracy 38.76%; exact-shape 41.38%; exact-grid 0% | Higher |
| Layout, 39 pages at IoU 0.50 | Micro P/R/F1 64.51% / 70.36% / 67.31% | Higher |

Layout per-class validation P/R/F1 is title 81.97% / 60.24% / 69.44%, text
55.22% / 71.43% / 62.29%, table 90.20% / 95.83% / 92.93%, and figure
54.55% / 78.26% / 64.29%. Require no regression for each value.

Reading order is excluded from the gate until validation labels exist. Compare
performance only after a configuration passes quality gates. Keep task metrics
separate: do not make a weighted single score. The current locked test is not a
fresh final test after any tuning.

Machine-readable gate values for all three baseline pipelines are in
[`tuning-baseline-validation.json`](tuning-baseline-validation.json).

## Canonical artifacts and detailed reports

- [Plan, scope, data locations, and protocol](../plan.md)
- [Follow-up proposal metrics and their phased evaluation plan](../follow-up-metrics.md)
- [MinerU V11 V0/V1 CPU control report](mineru-preprocessing/cpu-v11-report.md) and
  [`validation-only scores`](mineru-preprocessing/cpu-v11-variant-scores.json); exploratory only, not a replacement for the frozen T4 baseline
- [OCR report and per-crop scores](ocr-500-crops-v1/report.md) and
  [`ocr-comparison.json`](ocr-500-crops-v1/ocr-comparison.json)
- [Table report and per-table scores](table-150-v1/report.md) and
  [`table-comparison-150.json`](table-150-v1/table-comparison-150.json)
- [Full-page layout report and per-page results](layout-200-pages-v2/report.md)
- [Reading-order report and per-page results](reading-order/report.md)
- [Three-repeat performance JSON and raw logs](layout-200-pages-v2/performance-rerun-20261015/)
- [Performance aggregate JSON](layout-200-pages-v2/performance-rerun-20261015/performance-rerun-summary.json)
- [MinerU batch follow-up](layout-200-pages-v2/performance-repeats/mineru-batch/)

The raw pipeline outputs, manifests, references, overlays, and source-hash
provenance are retained. Partial per-page layout-evaluation snapshots were
removed because the canonical 200-page comparison supersedes them.
