# 2011 Vietnamese financial scan OCR diagnostic

This notebook runs one OCR engine at a time on a bounded income-statement crop from PDF page 8 (printed page 7) of a 43-page CafeF-hosted archive copy of Vinamilk’s signed 2011 consolidated financial statements. The PDF is a separate HP scanner capture of the same statement included in the earlier Tai-Lieu.com OCR diagnostic; it is not a new filing or year. The v2 reference covers the visible crop and corrects mismatched prior-period figures in v1. It was adapted from the earlier transcription and checked against this scan, so it is not independent annotation.

Private Kaggle dataset: `ltrngnhn/vinamilk-2011-cafef-scan-assets`. Tesseract and PaddleOCR use CPU by default; enable a Tesla T4 for EasyOCR or Surya. Compare only matching input hashes, and do not treat this one-page, single-filing result as representative model-selection evidence. v1 full-page scores are superseded because the reference covered only part of the page.
