# docling-vietocr benchmark: shared-html-owner-reviewed

**Run:** `docling-vietocr-egret-medium-kaggle-owner-reviewed-51-20261024` · **Predictions:** 51 pages · **Inference success:** 51
**Runtime:** 1162.402s on Tesla T4 · peak inference RSS unavailable

## Independent layer scores

| Layer | Cohort | Metrics |
|---|---:|---|
| OCR | 51 pages | CER 12.66%; WER (PyVi) 23.24%; whitespace error 19.27% |
| Layout | 51 pages | micro P/R/F1 24.15% / 39.23% / 29.90% |
| Table | 60 tables on 38 pages | detection P/R/F1 95.35% / 68.33% / 79.61%; cell CER 52.52%; cell WER (whitespace) 61.87%; exact grids 3.33% |

## End-to-end cohort

38 pages have reviewed OCR, layout, and table references. Multiple reviewed tables on a page are all included.

| Layer | Metrics |
|---|---|
| OCR | CER 12.93%; WER (PyVi) 23.17% |
| Layout | micro P/R/F1 21.69% / 35.01% / 26.78% |
| Table | detection P/R 95.35% / 68.33%; cell CER 52.52%; cell WER (whitespace) 61.87% |

## Notes

- Owner-reviewed working references from the shared HTML review flow.
- OCR block sorting uses high-confidence per-page OCR OSD orientation when available; otherwise top-to-bottom, left-to-right.
- Reading order is not separately scored because the current HTML references contain no reviewed reading_order sequence.
- End-to-end cohort requires reviewed OCR, layout, and at least one reviewed table; it includes all reviewed tables per page.
