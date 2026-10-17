# MinerU V11 CPU control: V0 vs V1

## Execution record

Kaggle kernel `letrongnhan/mineru-preprocessing-tuning-v1`, version 11,
completed all 12/12 development and validation groups with return code 0 and
zero fallback items. It ran with accelerator `None` (CPU), MinerU Basic 4.0.12.
V0 is the unmodified input control; V1 applies the deskew arm. No locked-test
inputs were included.

The run summary is in
[`kernel-summary.json`](raw/kernel-v11-cpu/download-attempt-1792193079/mineru-preprocessing/kernel-summary.json),
the validation-only scores and paired issuer-bootstrap intervals are in
[`cpu-v11-variant-scores.json`](cpu-v11-variant-scores.json), and the selected
download audit is in
[`targeted-download-report.json`](raw/kernel-v11-cpu/download-attempt-1792193079/targeted-download-report.json).
All 1,354 output ZIPs passed archive integrity checks. The download retained
the prediction artifacts and run metadata while excluding duplicated input
PDFs and the offline runtime bundle.

## Quality results

Values are percentages. Lower is better for CER/WER; higher is better for
table and layout metrics. These are CPU-run results, scored with the existing
development/validation references.

| Track | Split | V0 | V1 | V1 − V0 |
|---|---|---:|---:|---:|
| OCR micro CER / WER | Development (299 crops) | 18.33 / 56.86 | 18.62 / 57.66 | +0.28 / +0.80 pp |
| OCR micro CER / WER | Validation (100 crops) | 19.97 / 57.05 | 20.10 / 57.86 | +0.13 / +0.81 pp |
| OCR macro CER / WER | Development | 28.03 / 65.99 | 28.47 / 67.07 | +0.44 / +1.08 pp |
| OCR macro CER / WER | Validation | 15.84 / 53.22 | 16.05 / 54.25 | +0.21 / +1.03 pp |
| Table cell accuracy / exact shape | Development (89 tables) | 48.55 / 53.93 | 49.58 / 56.18 | +1.03 / +2.25 pp |
| Table cell accuracy / exact shape | Validation (29 tables) | 38.76 / 41.38 | 37.52 / 37.93 | −1.23 / −3.45 pp |
| Layout micro F1 | Development (121 pages) | 70.41 | 68.97 | −1.44 pp |
| Layout micro F1 | Validation (39 pages) | 67.63 | 67.37 | −0.26 pp |

Exact-grid rate was 0% for both variants on both table splits. The paired
10,000-resample issuer bootstrap found V1's development micro-CER increase
was +0.28 pp (95% CI +0.04 to +0.62 pp) and development micro-WER increase
was +0.80 pp (95% CI +0.46 to +1.17 pp). On validation, micro-WER increased
by +0.81 pp (95% CI +0.19 to +1.98 pp); micro-CER's interval crossed zero.
The table and layout validation intervals crossed zero. The exploratory
reading-order diagnostic on the 100 development pages was 808/1,031 matched
blocks (78.4%) and 96.91% pairwise accuracy for V0, versus 800/1,031 (77.6%)
and 97.20% for V1. Reading order has no validation labels yet.

This deskew arm does not show a consistent quality improvement: prose OCR is
worse, table results trade off between development and validation, and layout
F1 is slightly lower. The V1 candidate therefore does not justify proceeding
to further MinerU preprocessing variants by itself.

## Resource results

Times sum the development and validation groups for each track. Peak RSS is
the maximum sampled process-tree RSS across those two groups. The run is a
single pass, not the three-repeat performance benchmark.

| Track | Variant | Preprocessing seconds | Batch inference seconds | Peak process-tree RSS |
|---|---|---:|---:|---:|
| OCR | V0 | 10.95 | 3,556.51 | 2,563.8 MiB |
| OCR | V1 | 502.68 | 3,470.81 | 2,553.8 MiB |
| Tables | V0 | 1.81 | 3,435.62 | 2,096.6 MiB |
| Tables | V1 | 152.08 | 3,392.24 | 2,149.3 MiB |
| Layout | V0 | 5.85 | 5,845.10 | 2,455.0 MiB |
| Layout | V1 | 327.04 | 5,840.37 | 2,429.1 MiB |

GPU process and device memory are `null`; Kaggle did not provide CUDA. Treat
all times and memory as CPU diagnostics, not as comparisons with the T4
baseline or deployment capacity estimates.

## Comparability and decision

V0 is a control for the paired V1 comparison, but it is not an exact replay of
the saved T4 baseline. Using the same scorer, CPU V0 and the saved baseline
scores are close but not identical. A byte-level comparison of non-image ZIP
members also found differences for 165/399 shared OCR outputs, 28/118 shared
table outputs, and 119/160 shared layout outputs. The cause of those raw-output
differences is not established. Keep V0/V1 as an exploratory, within-CPU
comparison; do not substitute V0 scores for the frozen T4 baseline.

The scorer reports `waiting_for_all_six_V4_candidates` and selects no variant.
Do not resume V2–V4 until the shared follow-up metric gate in
[`follow-up-metrics.md`](../../follow-up-metrics.md) is closed and MinerU
remains on the shortlist. If retained, select only on development/validation.
Any comparison against an untuned PP-StructureV3 or Docling baseline must be
reported as tuned MinerU versus default baselines. The existing locked test is
already visible and cannot support a fresh confirmatory claim.
