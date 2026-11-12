# docling-vietocr benchmark: shared-html-owner-reviewed

**Run:** `docling-vietocr-full-review-10p-auto-orientation-20261021` · **Predictions:** 10 pages · **Inference success:** 10
**Runtime:** 500.061s on CPU · peak process RSS 3927.9 MiB

## Independent layer scores

| Layer | Cohort | Metrics |
|---|---:|---|
| OCR | 10 pages | CER 5.31%; WER (PyVi) 10.16%; whitespace error 9.20% |
| Layout | 10 pages | micro P/R/F1 22.83% / 34.12% / 27.36% |
| Table | 12 tables on 9 pages | detection P/R/F1 100.00% / 91.67% / 95.65%; cell CER 19.27%; cell WER (whitespace) 27.60%; exact grids 0.00% |

## End-to-end cohort

9 pages have reviewed OCR, layout, and table references. Multiple reviewed tables on a page are all included.

| Layer | Metrics |
|---|---|
| OCR | CER 5.77%; WER (PyVi) 10.46% |
| Layout | micro P/R/F1 20.37% / 30.99% / 24.58% |
| Table | detection P/R 100.00% / 91.67%; cell CER 19.27%; cell WER (whitespace) 27.60% |

## Notes

- Owner-reviewed working references from the shared HTML review flow.
- OCR block sorting uses high-confidence per-page OCR OSD orientation when available; otherwise top-to-bottom, left-to-right.
- Reading order is not separately scored because the current HTML references contain no reviewed reading_order sequence.
- End-to-end cohort requires reviewed OCR, layout, and at least one reviewed table; it includes all reviewed tables per page.
