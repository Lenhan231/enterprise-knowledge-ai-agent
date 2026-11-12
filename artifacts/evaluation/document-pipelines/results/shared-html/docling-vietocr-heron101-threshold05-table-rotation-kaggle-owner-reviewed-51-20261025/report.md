# docling-vietocr benchmark: shared-html-owner-reviewed

**Run:** `docling-vietocr-heron101-threshold05-table-rotation-kaggle-owner-reviewed-51-20261025` · **Predictions:** 51 pages · **Inference success:** 51
**Runtime:** 1123.959s on CPU · peak inference RSS unavailable

## Independent layer scores

| Layer | Cohort | Metrics |
|---|---:|---|
| OCR | 51 pages | CER 8.79%; WER (PyVi) 18.90%; whitespace error 15.24% |
| Layout | 51 pages | micro P/R/F1 33.29% / 39.67% / 36.20% |
| Table | 60 tables on 38 pages | detection P/R/F1 92.00% / 76.67% / 83.64%; cell CER 59.03%; cell WER (whitespace) 69.43%; exact grids 3.33% |

## End-to-end cohort

38 pages have reviewed OCR, layout, and table references. Multiple reviewed tables on a page are all included.

| Layer | Metrics |
|---|---|
| OCR | CER 9.38%; WER (PyVi) 19.09% |
| Layout | micro P/R/F1 34.31% / 36.90% / 35.56% |
| Table | detection P/R 92.00% / 76.67%; cell CER 59.03%; cell WER (whitespace) 69.43% |

## Notes

- Owner-reviewed working references from the shared HTML review flow.
- OCR block sorting uses high-confidence per-page OCR OSD orientation when available; otherwise top-to-bottom, left-to-right.
- Reading order is not separately scored because the current HTML references contain no reviewed reading_order sequence.
- End-to-end cohort requires reviewed OCR, layout, and at least one reviewed table; it includes all reviewed tables per page.
