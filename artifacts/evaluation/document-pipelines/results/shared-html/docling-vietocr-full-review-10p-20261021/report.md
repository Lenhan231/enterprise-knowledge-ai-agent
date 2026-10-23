# docling-vietocr benchmark: shared-html-owner-reviewed

**Run:** `docling-vietocr-full-review-10p-20261021` · **Predictions:** 10 pages · **Inference success:** 10
**Runtime:** 457.21s on CPU · peak process RSS 5015.2 MiB

## Independent layer scores

| Layer | Cohort | Metrics |
|---|---:|---|
| OCR | 10 pages | CER 9.09%; WER (PyVi) 14.14%; whitespace error 12.75% |
| Layout | 10 pages | micro P/R/F1 23.58% / 34.12% / 27.88% |
| Table | 12 tables on 9 pages | detection P/R/F1 100.00% / 91.67% / 95.65%; cell CER 31.85%; cell WER (whitespace) 37.36%; exact grids 0.00% |

## End-to-end cohort

9 pages have reviewed OCR, layout, and table references. Multiple reviewed tables on a page are all included.

| Layer | Metrics |
|---|---|
| OCR | CER 10.03%; WER (PyVi) 14.81% |
| Layout | micro P/R/F1 21.15% / 30.99% / 25.14% |
| Table | detection P/R 100.00% / 91.67%; cell CER 31.85%; cell WER (whitespace) 37.36% |

## Notes

- Owner-reviewed working references from the shared HTML review flow.
- OCR block sorting uses high-confidence per-page OCR OSD orientation when available; otherwise top-to-bottom, left-to-right.
- Reading order is not separately scored because the current HTML references contain no reviewed reading_order sequence.
- End-to-end cohort requires reviewed OCR, layout, and at least one reviewed table; it includes all reviewed tables per page.
