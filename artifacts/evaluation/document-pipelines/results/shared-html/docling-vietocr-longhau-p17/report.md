# docling-vietocr benchmark: shared-html-owner-reviewed

**Run:** `docling-vietocr-longhau-p17` · **Predictions:** 1 pages · **Inference success:** 1
**Runtime:** 29.852s on CPU · peak process RSS 2181.1 MiB

## Independent layer scores

| Layer | Cohort | Metrics |
|---|---:|---|
| OCR | 1 pages | CER 85.52%; WER (PyVi) 89.08%; whitespace error 89.33% |
| Layout | 1 pages | micro P/R/F1 16.67% / 25.00% / 20.00% |
| Table | 1 tables on 1 pages | detection P/R/F1 100.00% / 100.00% / 100.00%; cell CER 104.49%; cell WER (whitespace) 118.71%; exact grids 0.00% |

## End-to-end cohort

1 pages have reviewed OCR, layout, and table references. Multiple reviewed tables on a page are all included.

| Layer | Metrics |
|---|---|
| OCR | CER 85.52%; WER (PyVi) 89.08% |
| Layout | micro P/R/F1 16.67% / 25.00% / 20.00% |
| Table | detection P/R 100.00% / 100.00%; cell CER 104.49%; cell WER (whitespace) 118.71% |

## Notes

- Owner-reviewed working references from the shared HTML review flow.
- Reading order is not scored because the current HTML references contain no reviewed reading_order sequence.
- End-to-end cohort requires reviewed OCR, layout, and at least one reviewed table; it includes all reviewed tables per page.
