# docling benchmark: shared-html-owner-reviewed

**Run:** `docling-tesseract-full-review-10p-auto-orientation-20261021` · **Predictions:** 10 pages · **Inference success:** 10
**Runtime:** 243.966s on CPU · peak process RSS 1912.0 MiB

## Independent layer scores

| Layer | Cohort | Metrics |
|---|---:|---|
| OCR | 10 pages | CER 12.05%; WER (PyVi) 35.47%; whitespace error 26.53% |
| Layout | 10 pages | micro P/R/F1 8.44% / 30.59% / 13.23% |
| Table | 12 tables on 9 pages | detection P/R/F1 100.00% / 91.67% / 95.65%; cell CER 22.54%; cell WER (whitespace) 37.04%; exact grids 0.00% |

## End-to-end cohort

9 pages have reviewed OCR, layout, and table references. Multiple reviewed tables on a page are all included.

| Layer | Metrics |
|---|---|
| OCR | CER 11.86%; WER (PyVi) 33.31% |
| Layout | micro P/R/F1 7.09% / 28.17% / 11.33% |
| Table | detection P/R 100.00% / 91.67%; cell CER 22.54%; cell WER (whitespace) 37.04% |

## Notes

- Owner-reviewed working references from the shared HTML review flow.
- OCR block sorting uses high-confidence per-page OCR OSD orientation when available; otherwise top-to-bottom, left-to-right.
- Reading order is not separately scored because the current HTML references contain no reviewed reading_order sequence.
- End-to-end cohort requires reviewed OCR, layout, and at least one reviewed table; it includes all reviewed tables per page.
