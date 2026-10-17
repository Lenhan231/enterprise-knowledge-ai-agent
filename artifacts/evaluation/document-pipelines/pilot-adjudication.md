# Pilot reference and scoring review

**Status:** assistant-adjudicated under the project owner’s instruction to proceed without human review. Provenance remains explicit; these pilot scores are exploratory, not final benchmark results.

The project owner instructed us to proceed without waiting for human review. The assistant therefore selected row-major table reading order and the conventions below for this pilot revision. No human review is claimed.

## OCR references

| Page | Reference | Assistant visual pass | Human decision |
|---|---|---|---|
| Long Hau cover, p. 1 | `hpt-longhau-page1-cover-vi` | Visible title, subtitle, audit firm name, and wordmark are represented. Binder and geometric artwork are excluded as non-text content. | Assistant-adjudicated |
| Long Hau board report, p. 3 | `hpt-longhau-page3-board-report-vi` | Prose and visible labels/numbers match. The three certificate rows are transcribed column-first (all certificate names, then the `Ngày cấp` heading and dates), while the page presents them as paired rows. | Assistant-adjudicated: use row-wise order below |

Proposed row-wise transcription for the p. 3 certificate table:

```text
Giấy Chứng nhận Đầu tư số 50221000001 – Điều chỉnh lần 1; Ngày cấp: 3 tháng 5 năm 2007
Giấy Chứng nhận Đăng ký Kinh doanh số 5003000142 – Điều chỉnh lần 1; Ngày cấp: 9 tháng 11 năm 2007
Giấy Chứng nhận Đăng ký Kinh doanh số 5003000142 – Điều chỉnh lần 2; Ngày cấp: 19 tháng 2 năm 2008
```

Do not use the p. 3 full-page CER/WER as a prose-only score until the reference
ordering is adjudicated. The page-level result can remain a separate end-to-end
diagnostic; table text belongs in the table track in the official benchmark.

## Table reference

The Long Hau balance-sheet asset table on p. 6 has four manually transcribed
anchor rows for codes `100`, `110`, `140`, and `270`. Visual inspection confirms
the labels and two year-value cells match the source image. This checks exact
row presence and order only; it does not check all cells, merged cells, or table
structure, so it must not be reported as TEDS or cell accuracy.

A full 5-column, 30-row draft grid is available at [`table-reference-draft.json`](pilot-v1/table-reference-draft.json).

Status: assistant-adjudicated under owner instruction; not human-reviewed.

## Proposed pilot scoring conventions

1. Normalize Unicode to NFC, case-fold, collapse whitespace, and remove only
   Markdown/HTML presentation syntax. Preserve Vietnamese diacritics and
   punctuation.
2. Compare OCR against the visually adjudicated text in source reading order.
   Keep prose CER/WER separate from table text; report a full-page score only as
   an explicitly labeled end-to-end diagnostic.
3. Keep the p. 6 four-row anchor check as a pilot sanity check. Official table
   evaluation requires complete reviewed cell grids and structure metrics.
4. Treat missing regions and extra predicted regions separately from text
   similarity; a pipeline must not improve its score by omitting difficult
   content.

Selected for pilot v2 by assistant under owner instruction. OCR reference is versioned at [`ocr-ground-truth-v2.json`](pilot-v1/references/ocr-ground-truth-v2.json); table anchors at [`table-ground-truth-v2.json`](pilot-v1/references/table-ground-truth-v2.json). These references remain pilot-only.
