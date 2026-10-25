# docling benchmark: shared-html-owner-reviewed

**Run:** `docling-kaggle-owner-reviewed-51-20261024` · **Predictions:** 5 pages · **Inference success:** 5
**Runtime:** 51.51s summed selected-page inference on Tesla T4 (source full-run total: 520.772s; excludes initialization) · peak inference RSS unavailable

**Scored pilot pages:** `E2E-BAO-HO-LAO-DONG-2009-p4`, `E2E-LONG-HAU-2008-p6`, `UPLOAD-2-bctc-da-kiem-toan-2008-v-73147462f2-p1`, `UPLOAD-bao-cao-kiem-toan-2025-signed1-4195567125-p1`, `UPLOAD-vinaconex-bctn-2008-83f4d849cd-p39`

## Independent layer scores

| Layer | Cohort | Metrics |
|---|---:|---|
| OCR | 5 pages | CER 13.74%; WER (PyVi) 38.56%; whitespace error 28.34% |
| Layout | 5 pages | micro P/R/F1 7.19% / 27.27% / 11.37% |
| Table | 4 tables on 3 pages | detection P/R/F1 100.00% / 100.00% / 100.00%; cell CER 94.83%; cell WER (whitespace) 116.49%; exact grids 0.00% |

### Layout per-class scores

| Class | Precision | Recall | F1 | Reference regions | Predicted regions |
|---|---:|---:|---:|---:|---:|
| title | 40.00% | 44.44% | 42.11% | 9 | 10 |
| title_table | 0.00% | 0.00% | 0.00% | 3 | 0 |
| text | 2.00% | 18.75% | 3.61% | 16 | 150 |
| table | 100.00% | 100.00% | 100.00% | 4 | 4 |
| figure | 33.33% | 8.33% | 13.33% | 12 | 3 |

## End-to-end cohort

3 pages have reviewed OCR, layout, and table references. Multiple reviewed tables on a page are all included.

| Layer | Metrics |
|---|---|
| OCR | CER 9.70%; WER (PyVi) 28.46% |
| Layout | micro P/R/F1 8.18% / 27.27% / 12.59% |
| Table | detection P/R 100.00% / 100.00%; cell CER 94.83%; cell WER (whitespace) 116.49% |

## Notes

- Owner-reviewed working references from the shared HTML review flow.
- OCR block sorting uses high-confidence per-page OCR OSD orientation when available; otherwise top-to-bottom, left-to-right.
- Reviewed reading_order sequences are present but are not reported as a separate metric; OCR text ordering uses OSD-derived page rotations when available.
- End-to-end cohort requires reviewed OCR, layout, and at least one reviewed table; it includes all reviewed tables per page.
