# docling-vietocr benchmark: shared-html-owner-reviewed

**Run:** `docling-vietocr-egret-large-kaggle-owner-reviewed-51-20261025` · **Predictions:** 51 pages · **Inference success:** 51
**Runtime:** 1205.738s on Tesla T4 · peak inference RSS unavailable

## Independent layer scores

| Layer | Cohort | Metrics |
|---|---:|---|
| OCR | 51 pages | CER 12.18%; WER (PyVi) 22.33%; whitespace error 18.42% |
| Layout | 51 pages | micro P/R/F1 30.28% / 40.27% / 34.57% |
| Table | 60 tables on 38 pages | detection P/R/F1 86.21% / 83.33% / 84.75%; cell CER 67.18%; cell WER (whitespace) 76.04%; exact grids 1.67% |

## End-to-end cohort

38 pages have reviewed OCR, layout, and table references. Multiple reviewed tables on a page are all included.

| Layer | Metrics |
|---|---|
| OCR | CER 12.25%; WER (PyVi) 22.00% |
| Layout | micro P/R/F1 29.75% / 37.11% / 33.02% |
| Table | detection P/R 86.21% / 83.33%; cell CER 67.18%; cell WER (whitespace) 76.04% |

## Notes

- Owner-reviewed working references from the shared HTML review flow.
- OCR block sorting uses high-confidence per-page OCR OSD orientation when available; otherwise top-to-bottom, left-to-right.
- Reading order is not separately scored because the current HTML references contain no reviewed reading_order sequence.
- End-to-end cohort requires reviewed OCR, layout, and at least one reviewed table; it includes all reviewed tables per page.
