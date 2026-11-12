# docling-vietocr benchmark: shared-html-owner-reviewed

**Run:** `docling-vietocr-egret-threshold05-kaggle-owner-reviewed-51-20261025` · **Predictions:** 51 pages · **Inference success:** 51
**Runtime:** 1404.664s on Tesla T4 · peak inference RSS unavailable

## Independent layer scores

| Layer | Cohort | Metrics |
|---|---:|---|
| OCR | 51 pages | CER 12.56%; WER (PyVi) 24.14%; whitespace error 18.98% |
| Layout | 51 pages | micro P/R/F1 26.00% / 39.67% / 31.41% |
| Table | 60 tables on 38 pages | detection P/R/F1 95.35% / 68.33% / 79.61%; cell CER 55.12%; cell WER (whitespace) 64.40%; exact grids 3.33% |

## End-to-end cohort

38 pages have reviewed OCR, layout, and table references. Multiple reviewed tables on a page are all included.

| Layer | Metrics |
|---|---|
| OCR | CER 14.68%; WER (PyVi) 26.04% |
| Layout | micro P/R/F1 23.61% / 35.64% / 28.40% |
| Table | detection P/R 95.35% / 68.33%; cell CER 55.12%; cell WER (whitespace) 64.40% |

## Notes

- Owner-reviewed working references from the shared HTML review flow.
- OCR block sorting uses high-confidence per-page OCR OSD orientation when available; otherwise top-to-bottom, left-to-right.
- Reading order is not separately scored because the current HTML references contain no reviewed reading_order sequence.
- End-to-end cohort requires reviewed OCR, layout, and at least one reviewed table; it includes all reviewed tables per page.
