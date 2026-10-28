# docling-vietocr benchmark: shared-html-owner-reviewed

**Run:** `docling-vietocr-beamsearch-kaggle-owner-reviewed-51-20261024` · **Predictions:** 51 pages · **Inference success:** 51
**Runtime:** 1188.602s on Tesla T4 · peak inference RSS unavailable

## Independent layer scores

| Layer | Cohort | Metrics |
|---|---:|---|
| OCR | 51 pages | CER 17.38%; WER (PyVi) 27.79%; whitespace error 23.85% |
| Layout | 51 pages | micro P/R/F1 31.67% / 39.52% / 35.16% |
| Table | 60 tables on 38 pages | detection P/R/F1 89.58% / 71.67% / 79.63%; cell CER 61.46%; cell WER (whitespace) 69.86%; exact grids 1.67% |

## End-to-end cohort

38 pages have reviewed OCR, layout, and table references. Multiple reviewed tables on a page are all included.

| Layer | Metrics |
|---|---|
| OCR | CER 15.95%; WER (PyVi) 26.31% |
| Layout | micro P/R/F1 31.55% / 35.85% / 33.56% |
| Table | detection P/R 89.58% / 71.67%; cell CER 61.46%; cell WER (whitespace) 69.86% |

## Notes

- Owner-reviewed working references from the shared HTML review flow.
- OCR block sorting uses high-confidence per-page OCR OSD orientation when available; otherwise top-to-bottom, left-to-right.
- Reading order is not separately scored because the current HTML references contain no reviewed reading_order sequence.
- End-to-end cohort requires reviewed OCR, layout, and at least one reviewed table; it includes all reviewed tables per page.
