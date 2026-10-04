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
