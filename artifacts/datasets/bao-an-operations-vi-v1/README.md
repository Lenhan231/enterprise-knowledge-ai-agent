# Bảo An: synthetic Vietnamese operations handbook

## Start here

- bao-an-operations.vi.pdf: exactly 50 A4 pages, Vietnamese; 48 digital pages and two image-only form pages (43–44).
- handbook.vi.md and source.json: editable reference text and structured authoring source, including page/segment IDs. These include scan transcriptions and must NOT be indexed alongside the PDF in an OCR experiment.
- REVIEW.md: 30 draft intents / 60 VI+EN question texts with source evidence; four unanswerable intents. Only VI document retrieval exists here, so there are two query-language directions, not four.
- questions.draft.json: requirements and alternative evidence. Offsets are segment-local Unicode indexes in source.json, not parser offsets and not retrieval chunk IDs. This is not directly compatible with the old evidence-v3 scorer.
- review.csv: independent label/translation/alternative/answerability review checklist.
- validation.json and manifest.json: structural checks and initial file hashes.

## Content and testing intent

Pages 1–4: document control and definitions; 5–14: HR/expenses; 15–24: procurement; 25–36: warehouse/returns; 37–44: IT/security; 45–50: exceptions, matrices, forms. Every policy, threshold, organization, person, and event is fictional. This is a new synthetic dataset, not evidence of real enterprise performance and not part of the Review2 measured results.

Tests cover similar rules with different scope, inclusive/exclusive thresholds, exact item IDs, arithmetic with stated inputs, table header/row association, multiple sections, the approval matrix continuing across pages47–48, and image-only form extraction. The two clean grayscale scans are approximately173 DPI; they test OCR necessity, not severe noise or handwriting. Other mixed table/prose pages remain digital.

The PDF deliberately repeats some rules in its matrix. Initial alternative labels are not exhaustive; reviewers must search all sections. Do not require one exact chunk if a different passage fully supports the answer. Multi-section questions need all required components; table evidence includes a header and row.

## Before experiments

1. Review the PDF's business consistency and both language versions of each question. Mark independent review truthfully; don't assume assistant labels are certified.
2. Add valid equivalent evidence; confirm unanswerable questions are unsupported. The original corpus was written together with questions, so this is a controlled synthetic challenge, not an independently authored held-out test.
3. Freeze a reviewed version and new manifest before inference. Keep questions, answers, source.json and Markdown out of the search index; ingest ONLY the PDF for the PDF/OCR test.
4. Record parser/OCR mode and model versions. Map parsed evidence back to authored page/segment text with verified alignment. Record table, header, mixed-content, scan and multi-page extraction failures separately.
5. Run the current system unchanged as baseline, recording chunk count, lengths, candidate recall@30, complete evidence@10, Recall/MRR/nDCG, and latency. Score answer correctness, citations, refusal and OCR separately using reviewed labels. No predictions or measured results are supplied here.
6. Tune on separate development questions. Preserve an untouched reviewed test subset; bilingual versions of one intent belong together. Do not tune and report the same questions as independent test evidence.

## Reproduce

From the repository root on Windows, using the existing PyMuPDF installation:

```
.venv/Scripts/python.exe -X utf8 scripts/evaluation/generate_operations_handbook.py --output artifacts/datasets/bao-an-operations-vi-v1-rebuild
```

The builder uses Arial from C:/Windows/Fonts, refuses to overwrite a nonempty folder, and makes no network/model/database calls. Content is authored in scripts/evaluation/operations_handbook_content.py. Document hashes can vary with PDF serializer IDs across builds; each generated manifest describes its own outputs. After authoring edits, regenerate into a new version rather than overwriting frozen inputs.
