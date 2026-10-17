# Vietnamese enterprise document pipeline pilot — reference v2

**Status:** pilot diagnostics only; not a model-selection result or official
benchmark. References were assistant-adjudicated after the project owner
instructed us to proceed without human review. No human review is claimed.

This version uses row-wise order for the certificate-date table on Long Hau
page 3 and the complete 30-row, five-column grid for the Long Hau financial
table on page 6. Raw model outputs were reused; the pipelines were not rerun.
The earlier [`pilot-report.md`](pilot-report.md) and
[`pilot-comparison.json`](pilot-comparison.json) remain unchanged.

## OCR reference results

| Page | PP-StructureV3 CER / WER | MinerU Basic CER / WER | Docling CER / WER |
|---|---:|---:|---:|
| Long Hau cover (p. 1) | 13.38% / 47.22% | 29.30% / 47.22% | 19.11% / 47.22% |
| Long Hau board report (p. 3) | 26.19% / 68.62% | 9.13% / 40.18% | 18.06% / 53.27% |

The p. 3 reference orders the certificate/date cells by row. Page-level values
are diagnostics over only two pages and must not be treated as a prose-corpus
score. Table text is excluded from the official prose OCR aggregate.

## Table results

The p. 6 output grid is aligned to the reference by exact first-column row code.
For a missing row key, all five cells in that reference row count incorrect.
Cell matching applies NFC, case folding, and whitespace collapse while
preserving punctuation and diacritics. Empty reference cells are included.

| Pipeline | Table detected | Row keys | Exact cells | Exact value cells* |
|---|---:|---:|---:|---:|
| PP-StructureV3 | Yes | 25/30 (83.3%) | 50/150 (33.3%) | 19/60 (31.7%) |
| MinerU Basic | Yes | 26/30 (86.7%) | 90/150 (60.0%) | 44/60 (73.3%) |
| Docling | Yes | 30/30 (100%) | 113/150 (75.3%) | 53/60 (88.3%) |

*The value-cell score covers the last two columns, including empty and dash
cells. These are row-key-aligned exact-cell diagnostics on one table; they are
not TEDS or TEDS-Struct and do not measure merged-cell structure. The separate
four-row anchor check remains 2/4 for PP-StructureV3, 3/4 for MinerU, and 4/4
for Docling.

## Runtime and failure observations

| Pipeline | Pages succeeded | Median seconds/page | p95 seconds/page | Recorded peak host RSS |
|---|---:|---:|---:|---:|
| PP-StructureV3 | 20/20 | 1.63 | 2.84 | 3,192 MiB |
| MinerU Basic | 19/20 | 16.07 | 25.98 | Not measured for child process |
| Docling | 20/20 | 15.60 | 27.29 | 6,270 MiB |

These are single-run pilot measurements. MinerU starts a separate process for
each page, while PP-StructureV3 and Docling use persistent processes. Docling
loads models lazily, so its first-page time includes initialization. GPU peak
memory was not captured. The MinerU failure remains
`longhau-financials-p015` (`Unsupported warp settings`).

## Limits and next work

- OCR references cover only two pages; the table grid covers one table.
- Layout metrics and reading-order accuracy are unavailable because the pilot
  has no reviewed labels for those tracks.
- The table-cell scores measure text and row-key alignment, not tree structure.
- Assistant adjudication can contain transcription errors. The owner chose to
  proceed without human review; keep this provenance beside every score and
  avoid claiming human-validated ground truth.
- Continue building the planned 500 OCR crops, 150 complete table grids, 100
  reading-order pages, and 200 layout pages. Keep pilot documents out of the
  locked final test set.

Machine-readable results: [`pilot-v2-comparison.json`](pilot-v2-comparison.json).
References: [`pilot-v1/references/`](pilot-v1/references/) and
[`pilot-v1/table-reference-draft.json`](pilot-v1/table-reference-draft.json).
