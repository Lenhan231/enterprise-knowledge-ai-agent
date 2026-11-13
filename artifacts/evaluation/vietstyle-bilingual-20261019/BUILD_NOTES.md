# Corrected English VietStyle simulation pack v1

Local simulated-data counterpart, created 2026-10-19 with user authorization. Original downloads remain untouched in sources/en/. Use the five files in corrected-en-v1/ as retrieval documents; benchmark-questions-en-v1.json is evaluation data and MUST NOT be indexed as evidence.

The existing English DOCX was copied unchanged. Remaining Vietnamese text was translated in two CSV SLA cells, workbook text cells, and slides 2/8. Workbook cell coordinates/types/stored values/formulas are unchanged. Policy IDs and every other CSV field are unchanged. The SOP was translated from the frozen original Vietnamese text/tables and rebuilt as a selectable-text PDF with its 8 sections and 3 complete tables. Its layout/page boundaries differ from the original, so old page/chunk labels cannot be reused. No arbitrary policy facts, thresholds, numbers or approval rules were added.

Twenty English questions and reference answers accompany the files. They are assistant-created translations, not independent human-certified gold. Source-file expectations are inherited from the VN benchmark; README_EN.txt remains unavailable. BUILD_NOTES.md describes packaging, not an operational policy README, and must not substitute for that missing expected source.

Validation is recorded in english-build-manifest.json and corrected-parse-validation.json. PDF page layouts were visually inspected. Office document XML was validated and parsed by the existing app readers; Office slide rendering was not automated. Diacritic screening found no remaining Vietnamese characters in visible text; this diagnostic does not prove perfect semantic equivalence. The original translation defects are documented in READINESS.md, which describes the initial download, not these corrected files.

Rebuild from the repository root with:

```bash
.venv/bin/python scripts/retrieval/build_vietstyle_english.py
```

Uses only the standard library and the existing PyMuPDF dependency. No external translation API, model download, embeddings, benchmark GPU run, application code change, or database action. The pack is intended for the user's local experiment; the team's Vietnamese corpus remains unchanged.
