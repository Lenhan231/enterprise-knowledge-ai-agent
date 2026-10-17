# Table recognition benchmark: 150 valid Vietnamese enterprise crops

## Scope and result

The original Kaggle run processed 150 isolated 180-DPI image-only PDFs per pipeline. A full-page quality review found that candidate `TBL-014` / input `TAB-010` is an industrial-park photograph with narrative text, not a table. It is excluded from the scoring reference. The reference now contains 150 valid tables from 42 source documents and issuers: 89 development, 29 validation, and 32 locked-test tables. The additional `TBL-201` / `TAB-151` financial-ratio table was checked against its source page, and all three pipelines were run on that single development input. Existing table splits were retained; the locked test is unchanged.

`TAB-149` has its corrected complete 26×6 crop and grid. Its outputs come from the dedicated correction rerun. `TAB-151` outputs come from separate one-page Kaggle kernels, so these reruns do not replace or re-score the locked-test outputs. All three engines have output files for all 150 references.

### Development (89 tables)

| Pipeline | Outputs found | Tables found | Micro cell accuracy | Exact-grid rate | Exact-shape rate | Mean absolute row error | Mean absolute column error |
|---|---:|---:|---:|---:|---:|---:|---:|
| PP-StructureV3 | 89/89 | 45/89 | 12.86% | 0.00% | 24.72% | 6.97 | 3.78 |
| MinerU Basic | 89/89 | 89/89 | 48.93% | 0.00% | 55.06% | 1.92 | 1.26 |
| Docling | 89/89 | 81/89 | 47.81% | 0.00% | 50.56% | 2.28 | 1.60 |

### Validation (29 tables)

| Pipeline | Outputs found | Tables found | Micro cell accuracy | Exact-grid rate | Exact-shape rate | Mean absolute row error | Mean absolute column error |
|---|---:|---:|---:|---:|---:|---:|---:|
| PP-StructureV3 | 29/29 | 11/29 | 8.74% | 0.00% | 27.59% | 6.79 | 3.17 |
| MinerU Basic | 29/29 | 29/29 | 38.76% | 0.00% | 41.38% | 0.66 | 0.48 |
| Docling | 29/29 | 24/29 | 32.79% | 0.00% | 41.38% | 1.14 | 1.48 |

### Locked test (32 tables)

| Pipeline | Outputs found | Tables found | Micro cell accuracy | Exact-grid rate | Exact-shape rate | Mean absolute row error | Mean absolute column error |
|---|---:|---:|---:|---:|---:|---:|---:|
| PP-StructureV3 | 32/32 | 19/32 | 26.65% | 0.00% | 50.00% | 6.22 | 2.00 |
| MinerU Basic | 32/32 | 32/32 | 46.00% | 0.00% | 71.88% | 1.91 | 0.81 |
| Docling | 32/32 | 32/32 | 47.13% | 0.00% | 84.38% | 0.28 | 0.12 |

### All valid references (150 tables)

| Pipeline | Outputs found | Tables found | Micro cell accuracy | Exact-grid rate | Exact-shape rate | Mean absolute row error | Mean absolute column error |
|---|---:|---:|---:|---:|---:|---:|---:|
| PP-StructureV3 | 150/150 | 75/150 | 15.01% | 0.00% | 30.67% | 6.77 | 3.28 |
| MinerU Basic | 150/150 | 150/150 | 46.74% | 0.00% | 56.00% | 1.67 | 1.01 |
| Docling | 150/150 | 137/150 | 45.31% | 0.00% | 56.00% | 1.63 | 1.26 |

On development and validation, MinerU Basic has the highest micro cell accuracy. On the locked test, Docling is slightly higher than MinerU Basic and has the highest exact-shape rate. No pipeline reproduced a complete grid exactly. For TAB-151, Docling matched 67/90 cell positions (74.44%), MinerU matched 64/90 (71.11%), and PP-StructureV3 returned no table (0/90). These results do not support an unqualified production choice.

## Label and metric limits

Table boundaries were assistant-adjudicated, not independently human-reviewed. `TBL-014` was rejected after full-page visual review showed it was a photograph rather than a table. `TBL-201` was accepted after source-page review confirmed a complete 18×5 financial-ratio table; its PyMuPDF cell grid was checked against the crop, but not independently human-reviewed cell by cell. Other grids mostly come from source-PDF text extraction; merged-cell spans have not been independently checked. The scorer aligns cells by row and column after Unicode and whitespace normalization. Extra and missing cells count as errors. Therefore cell accuracy mixes detection, OCR, and grid reconstruction; it is not TEDS/TEDS-Struct.

## Runtime and resource context

The timing snapshot below is from the original 150-input runs, including the now-excluded `TAB-010` and excluding the supplemental `TAB-151`; it is descriptive execution-path metadata, not a runtime measurement recomputed on the current 150-reference subset. All kernels ran on Kaggle Tesla T4 (15,360 MiB reported). MinerU launches the CLI/model process for each crop, so its timing includes repeated startup. Its RSS is the parent process only and excludes child processes. Docling may lazily initialize models after the recorded constructor time. Peak VRAM was not recorded.

| Pipeline | Configuration | Init time | Median s/table | P95 s/table | Total run | Peak host RSS |
|---|---|---:|---:|---:|---:|---:|
| PP-StructureV3 | PaddleOCR 3.4.1 / PaddleX 3.4.3; PP-DocLayout-S, PP-OCRv5 mobile; table recognition on | 28.66 s | 0.58 | 1.40 | 148.78 s | 3,299 MiB |
| MinerU Basic | MinerU 4.0.12; one CLI/model process per crop | included per crop | 17.96 | 20.52 | 2,808.82 s | 103.7 MiB parent only |
| Docling | Docling 2.129.0; RapidOCR 3.9.2, ONNX Runtime, CUDA | 0.31 s reported | 3.22 | 7.19 | 618.63 s | 3,793 MiB |

The one-page `TAB-151` supplemental runs also used Kaggle Tesla T4. PP-StructureV3 initialized in 34.21 s and processed the page in 4.41 s; MinerU Basic took 64.94 s for its per-page CLI run; Docling recorded 0.31 s constructor setup and 27.58 s conversion. These are one-page supplemental timings, not comparable throughput estimates.

## Artifacts

- Current 150-reference comparison: [`table-comparison-150.json`](table-comparison-150.json)
- Previous 149-reference comparison retained for history: [`table-comparison-149.json`](table-comparison-149.json)
- Original 150-input comparison retained for historical provenance: [`table-comparison.json`](table-comparison.json)
- TAB-149 correction rerun: [`tab149-correction/`](tab149-correction/)
- TAB-151 one-page reruns: [`table-151-addition/`](table-151-addition/)
- Raw engine outputs: [`pp-structurev3/`](pp-structurev3/), [`mineru-basic/`](mineru-basic/), [`docling/`](docling/)
- Canonical scoring references: [`../../tables/reference/`](../../tables/reference/)
