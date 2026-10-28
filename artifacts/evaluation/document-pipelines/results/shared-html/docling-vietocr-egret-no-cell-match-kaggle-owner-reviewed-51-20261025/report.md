# docling-vietocr benchmark: shared-html-owner-reviewed

**Run:** `docling-vietocr-egret-no-cell-match-kaggle-owner-reviewed-51-20261025` · **Predictions:** 51 pages · **Inference success:** 51
**Runtime:** 1285.434s on Tesla T4 · peak inference RSS unavailable

## Independent layer scores

| Layer | Cohort | Metrics |
|---|---:|---|
| OCR | 51 pages | CER 45.70%; WER (PyVi) 48.76%; whitespace error 43.52% |
| Layout | 51 pages | micro P/R/F1 24.15% / 39.23% / 29.90% |
| Table | 60 tables on 38 pages | detection P/R/F1 95.35% / 68.33% / 79.61%; cell CER 100.11%; cell WER (whitespace) 100.07%; exact grids 0.00% |

## End-to-end cohort

38 pages have reviewed OCR, layout, and table references. Multiple reviewed tables on a page are all included.

| Layer | Metrics |
|---|---|
| OCR | CER 58.64%; WER (PyVi) 57.26% |
| Layout | micro P/R/F1 21.69% / 35.01% / 26.78% |
| Table | detection P/R 95.35% / 68.33%; cell CER 100.11%; cell WER (whitespace) 100.07% |

## Notes

- Owner-reviewed working references from the shared HTML review flow.
- OCR block sorting uses high-confidence per-page OCR OSD orientation when available; otherwise top-to-bottom, left-to-right.
- Reading order is not separately scored because the current HTML references contain no reviewed reading_order sequence.
- End-to-end cohort requires reviewed OCR, layout, and at least one reviewed table; it includes all reviewed tables per page.
