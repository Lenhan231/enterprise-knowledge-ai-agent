# docling-vietocr benchmark: shared-html-owner-reviewed

**Run:** `docling-vietocr-osd-longhau-p15-table-auto` · **Predictions:** 1 pages · **Inference success:** 1
**Runtime:** 67.746s on CPU · peak process RSS 3981.8 MiB

## Independent layer scores

| Layer | Cohort | Metrics |
|---|---:|---|
| OCR | 1 pages | CER 10.45%; WER (PyVi) 21.36%; whitespace error 18.93% |
| Layout | 1 pages | micro P/R/F1 30.00% / 27.27% / 28.57% |
| Table | 3 tables on 1 pages | detection P/R/F1 100.00% / 100.00% / 100.00%; cell CER 36.74%; cell WER (whitespace) 53.14%; exact grids 0.00% |

## End-to-end cohort

1 pages have reviewed OCR, layout, and table references. Multiple reviewed tables on a page are all included.

| Layer | Metrics |
|---|---|
| OCR | CER 10.45%; WER (PyVi) 21.36% |
| Layout | micro P/R/F1 30.00% / 27.27% / 28.57% |
| Table | detection P/R 100.00% / 100.00%; cell CER 36.74%; cell WER (whitespace) 53.14% |

## Notes

- Owner-reviewed working references from the shared HTML review flow.
- OCR block sorting uses high-confidence per-page OCR OSD orientation when available; otherwise top-to-bottom, left-to-right.
- Reading order is not separately scored because the current HTML references contain no reviewed reading_order sequence.
- End-to-end cohort requires reviewed OCR, layout, and at least one reviewed table; it includes all reviewed tables per page.
