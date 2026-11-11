# Charter scan OCR diagnostic

The Kaggle notebook runs one OCR engine per submission against the same full-page, 180-DPI render of official Vinamilk Company Charter page 8. Its reference is a single-annotator visual transcription, so this remains a diagnostic rather than engine-selection evidence.

The private Kaggle dataset is `ltrngnhn/vinamilk-charter-scan-page8-assets`. The base kernel metadata is CPU-only. Enable a Tesla T4 GPU for EasyOCR and Surya; Tesseract and the pinned PaddleOCR CPU wheel run without one. Keep Internet enabled for package/model downloads. Set `ENGINE` in the notebook before each run. Compare OCR quality only when the dataset, source PDF and rendered-image hashes match; do not compare runtime across different accelerators.
