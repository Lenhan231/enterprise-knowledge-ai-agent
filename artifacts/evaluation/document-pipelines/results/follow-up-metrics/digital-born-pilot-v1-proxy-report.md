# Digital-born PDF pilot: source-type-checked proxy

## Status

This is an exploratory text-layer proxy, not a reviewed quality benchmark. The
20 source pages were visually checked for source type by the assistant; the
native-text transcripts were not manually corrected. The source-type audit is
in [`digital-born-pilot-source-type-check.json`](digital-born-pilot-source-type-check.json),
and per-page scores are in
[`digital-born-pilot-v1-source-type-checked-proxy.json`](digital-born-pilot-v1-source-type-checked-proxy.json).

## Protocol

The pilot contains 11 born-digital candidate pages from four issuers, six
physical scans, and three image-only packaged PDFs. All three pipelines use the
same saved pilot outputs; no inference was rerun. The reference is the source
PDF text layer, normalized with the existing pilot scorer. Pooled micro CER/WER
and mean per-page macro CER/WER are reported. Tables remain in this proxy, so
its score is not directly comparable with the prose-only OCR crop benchmark.

## Results

Lower is better. Values are percentages.

| Pipeline | Pages found | Micro CER | Micro WER | Macro CER | Macro WER |
|---|---:|---:|---:|---:|---:|
| PP-StructureV3 | 11/11 | 40.66 | 78.74 | 41.88 | 79.06 |
| MinerU Basic | 11/11 | 31.11 | 35.37 | 32.97 | 37.83 |
| Docling | 11/11 | 29.24 | 36.25 | 31.75 | 38.54 |

## Interpretation and limits

All three saved outputs were found on every included page. Docling has the
lowest proxy CER; MinerU has the lowest proxy WER. These small-sample differences
do not establish a winner. The reference is not visually corrected, native PDF
text order can differ from visible reading order, and tables/layout contribute
to the transcript. Visual inspection confirms this is present in the actual
sample: `hpg-ar-2024-p003` is a multi-column table of contents, and its extracted
text groups headings, section numbers, labels, and page numbers in an order
different from the visible columns. `hpg-ar-2024-p005` also has two body-text
columns. Thus page-level CER/WER confounds recognition with reading order on
these pages. The output is useful for checking that the adapter and scorer run
across all three saved pipelines, but it is not a valid digital-born quality
score or production-selection evidence.

## Next gate

A reviewer must correct page text and reading order on the pilot pages. Keep
block-order accuracy separate; calculate CER/WER on matched text blocks or on
pages with verified linear reading order. If the pilot reference and scorer are
accepted, use the source-preserving
151-page development/validation candidate package; keep all 39 locked-test
pages excluded. Otherwise revise the reference/scorer before scaling.
