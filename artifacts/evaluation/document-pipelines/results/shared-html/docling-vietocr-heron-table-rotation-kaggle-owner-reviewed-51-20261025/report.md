# docling-vietocr benchmark: shared-html-owner-reviewed

**Run:** `docling-vietocr-heron-table-rotation-kaggle-owner-reviewed-51-20261025` · **Predictions:** 51 pages · **Inference success:** 51
**Runtime:** 1118.08s on CPU · peak inference RSS unavailable

## Independent layer scores

| Layer | Cohort | Metrics |
|---|---:|---|
| OCR | 51 pages | CER 11.28%; WER (PyVi) 22.41%; whitespace error 17.60% |
| Layout | 51 pages | micro P/R/F1 31.67% / 39.52% / 35.16% |
| Table | 60 tables on 38 pages | detection P/R/F1 89.58% / 71.67% / 79.63%; cell CER 56.52%; cell WER (whitespace) 66.07%; exact grids 1.67% |

## End-to-end cohort

38 pages have reviewed OCR, layout, and table references. Multiple reviewed tables on a page are all included.

| Layer | Metrics |
|---|---|
| OCR | CER 10.99%; WER (PyVi) 22.08% |
| Layout | micro P/R/F1 31.55% / 35.85% / 33.56% |
| Table | detection P/R 89.58% / 71.67%; cell CER 56.52%; cell WER (whitespace) 66.07% |

## Notes

- Owner-reviewed working references from the shared HTML review flow.
- OCR block sorting uses high-confidence per-page OCR OSD orientation when available; otherwise top-to-bottom, left-to-right.
- Reading order is not separately scored because the current HTML references contain no reviewed reading_order sequence.
- End-to-end cohort requires reviewed OCR, layout, and at least one reviewed table; it includes all reviewed tables per page.
