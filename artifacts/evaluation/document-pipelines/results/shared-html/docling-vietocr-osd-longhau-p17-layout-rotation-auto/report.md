# docling-vietocr benchmark: shared-html-owner-reviewed

**Run:** `docling-vietocr-osd-longhau-p17-layout-rotation-auto` · **Predictions:** 1 pages · **Inference success:** 1
**Runtime:** 39.951s on CPU · peak process RSS 2177.6 MiB

## Independent layer scores

| Layer | Cohort | Metrics |
|---|---:|---|
| OCR | 1 pages | CER 42.14%; WER (PyVi) 43.00%; whitespace error 46.67% |
| Layout | 1 pages | micro P/R/F1 20.00% / 25.00% / 22.22% |
| Table | 1 tables on 1 pages | detection P/R/F1 100.00% / 100.00% / 100.00%; cell CER 7.30%; cell WER (whitespace) 29.03%; exact grids 0.00% |

## End-to-end cohort

1 pages have reviewed OCR, layout, and table references. Multiple reviewed tables on a page are all included.

| Layer | Metrics |
|---|---|
| OCR | CER 42.14%; WER (PyVi) 43.00% |
| Layout | micro P/R/F1 20.00% / 25.00% / 22.22% |
| Table | detection P/R 100.00% / 100.00%; cell CER 7.30%; cell WER (whitespace) 29.03% |

## Notes

- Owner-reviewed working references from the shared HTML review flow.
- Reading order is not scored because the current HTML references contain no reviewed reading_order sequence.
- End-to-end cohort requires reviewed OCR, layout, and at least one reviewed table; it includes all reviewed tables per page.
