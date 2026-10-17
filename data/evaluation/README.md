# Evaluation data

The SQL decision questions are in
[`commerce_decision_benchmark.json`](commerce_decision_benchmark.json). The
matching document-level retrieval labels are in
[`commerce_retrieval_cases.json`](commerce_retrieval_cases.json); they cover the
same nine cases and reference only active sources in the Commerce manifest.
Those sources are attributed external practices, not the synthetic dataset's
company policy. Labels assess retrieval relevance, not answer quality.

The OCR fixtures are two-page, image-only synthetic Commerce Demo PDFs in
[`ocr/`](ocr/), with separate clean and degraded visual-transcription labels.
They are for upload/OCR robustness checks only; they cannot rank production OCR
engines or support business decisions. Archived evaluation files are historical
and are not the active Commerce benchmark.

The initial Vietnamese enterprise page-layout detection set is in
[`layout/`](layout/). It contains 13 rendered pages with source and image hashes;
bounding-box labels are pending. A separate labeled ViFinTab track compares
table-region detectors; its PP-DocLayout S/M/L results are in
[`layout results`](../../artifacts/evaluation/layout/results/report.md). It does
not score full page-layout classes. A separate HCMUS real-only validation run
checks transfer to Vietnamese academic pages; see the
[`HCMUS layout report`](../../artifacts/evaluation/layout/hcmus-results/report.md).
Its metrics are supplemental and not enterprise-report evidence. CPU runs on the
same deterministic 100-page sample are summarized in the
[`CPU/GPU comparison`](../../artifacts/evaluation/layout/hcmus-results/cpu-100/report.md).
