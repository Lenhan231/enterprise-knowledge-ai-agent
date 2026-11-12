# docling benchmark: shared-html-owner-reviewed

**Run:** `docling-kaggle-gpu-longhau-p17-20261022` · **Predictions:** 1 pages · **Inference success:** 1
**Runtime:** 28.217s on Tesla T4 (Kaggle) · peak inference RSS unavailable

## Independent layer scores

| Layer | Cohort | Metrics |
|---|---:|---|
| OCR | 1 pages | CER 78.64%; WER (PyVi) 82.94%; whitespace error 82.67% |
| Layout | 1 pages | micro P/R/F1 7.69% / 20.00% / 11.11% |
| Table | 1 tables on 1 pages | detection P/R/F1 100.00% / 100.00% / 100.00%; cell CER 179.92%; cell WER (whitespace) 162.58%; exact grids 0.00% |

## End-to-end cohort

1 pages have reviewed OCR, layout, and table references. Multiple reviewed tables on a page are all included.

| Layer | Metrics |
|---|---|
| OCR | CER 78.64%; WER (PyVi) 82.94% |
| Layout | micro P/R/F1 7.69% / 20.00% / 11.11% |
| Table | detection P/R 100.00% / 100.00%; cell CER 179.92%; cell WER (whitespace) 162.58% |

## Notes

- Owner-reviewed working references from the shared HTML review flow.
- OCR block sorting uses high-confidence per-page OCR OSD orientation when available; otherwise top-to-bottom, left-to-right.
- Reading order is not separately scored because the current HTML references contain no reviewed reading_order sequence.
- End-to-end cohort requires reviewed OCR, layout, and at least one reviewed table; it includes all reviewed tables per page.
