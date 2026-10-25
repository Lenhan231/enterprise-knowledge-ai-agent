# docling benchmark: shared-html-owner-reviewed

**Run:** `docling-vietocr-kaggle-owner-reviewed-51-20261024` · **Predictions:** 5 pages · **Inference success:** 5
**Runtime:** 116.363s summed selected-page inference on Tesla T4 (source full-run total: 1186.153s; excludes initialization) · peak inference RSS unavailable

**Scored pilot pages:** `E2E-LONG-HAU-2008-p6`, `E2E-LONG-HAU-2008-p8`, `E2E-LONG-HAU-2008-p17`, `E2E-BAO-HO-LAO-DONG-2009-p13`, `E2E-BAO-HO-LAO-DONG-2009-p24`

## Independent layer scores

| Layer | Cohort | Metrics |
|---|---:|---|
| OCR | 5 pages | ordered CER 15.69%; ordered WER (PyVi) 20.59%; order-insensitive bag char/token error 4.54% / 11.02% |
| Layout | 5 pages | micro P/R/F1 15.56% / 21.21% / 17.95% |
| Table | 5 tables on 5 pages | detection P/R/F1 100.00% / 100.00% / 100.00%; cell CER 43.48%; cell WER (whitespace) 54.54%; exact grids 0.00% |

### Layout per-class scores

| Class | Precision | Recall | F1 | Reference regions | Predicted regions |
|---|---:|---:|---:|---:|---:|
| title | 12.50% | 50.00% | 20.00% | 2 | 8 |
| title_table | 0.00% | 0.00% | 0.00% | 5 | 0 |
| text | 3.57% | 7.14% | 4.76% | 14 | 28 |
| table | 100.00% | 100.00% | 100.00% | 5 | 5 |
| figure | 0.00% | 0.00% | 0.00% | 7 | 4 |

## End-to-end cohort

5 pages have reviewed OCR, layout, and table references. Multiple reviewed tables on a page are all included.

| Layer | Metrics |
|---|---|
| OCR | ordered CER 15.69%; ordered WER (PyVi) 20.59%; order-insensitive bag char/token error 4.54% / 11.02% |
| Layout | micro P/R/F1 15.56% / 21.21% / 17.95% |
| Table | detection P/R 100.00% / 100.00%; cell CER 43.48%; cell WER (whitespace) 54.54% |

## Notes

- Owner-reviewed working references from the shared HTML review flow.
- OCR block sorting uses high-confidence per-page OCR OSD orientation when available; otherwise top-to-bottom, left-to-right.
- Reviewed reading_order sequences are present but are not reported as a separate metric; OCR text ordering uses OSD-derived page rotations when available.
- Bag character/token error rates ignore sequence order and are diagnostics, not standard CER/WER or recognizer-only scores; they still include effects of missed/extra detections and table extraction.
- End-to-end cohort requires reviewed OCR, layout, and at least one reviewed table; it includes all reviewed tables per page.
