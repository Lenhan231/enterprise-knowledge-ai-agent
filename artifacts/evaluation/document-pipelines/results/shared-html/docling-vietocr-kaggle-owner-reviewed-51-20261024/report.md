# docling benchmark: shared-html-owner-reviewed

**Run:** `docling-vietocr-kaggle-owner-reviewed-51-20261024` · **Predictions:** 51 pages · **Inference success:** 51
**Runtime:** 1186.153s on Tesla T4 · peak inference RSS unavailable

**OCR:** RapidOCR 3.9.2 detection + VietOCR vgg_seq2seq greedy recognition; Tesseract OSD per crop.

## Independent layer scores

| Layer | Cohort | Metrics |
|---|---:|---|
| OCR | 51 pages | CER 12.56%; WER (PyVi) 23.70%; whitespace error 18.81% |
| Layout | 51 pages | micro P/R/F1 31.67% / 43.54% / 36.66% |
| Table | 60 tables on 38 pages | detection P/R/F1 89.58% / 71.67% / 79.63%; cell CER 61.07%; cell WER (whitespace) 69.46%; exact grids 1.67% |

## End-to-end cohort

38 pages have reviewed OCR, layout, and table references. Multiple reviewed tables on a page are all included.

| Layer | Metrics |
|---|---|
| OCR | CER 12.76%; WER (PyVi) 23.81% |
| Layout | micro P/R/F1 31.55% / 40.33% / 35.40% |
| Table | detection P/R 89.58% / 71.67%; cell CER 61.07%; cell WER (whitespace) 69.46% |

## Notes

- Owner-reviewed working references from the shared HTML review flow.
- OCR block sorting uses high-confidence per-page OCR OSD orientation when available; otherwise top-to-bottom, left-to-right.
- Reading order is not separately scored because the current HTML references contain no reviewed reading_order sequence.
- End-to-end cohort requires reviewed OCR, layout, and at least one reviewed table; it includes all reviewed tables per page.
