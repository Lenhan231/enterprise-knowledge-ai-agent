# Downloaded English VietStyle pack — local readiness audit

Date: 2026-10-19. Source: Downloads/VietStyle_Inventory_Documents_English.zip. Archive/file hashes are in source-manifest.json; original extracted files are preserved in sources/en/. This is a local-only preparation: no model load, embedding, database access/write, inference API, or model selection.

## Update: corrected local English version created

With user authorization, the translation defects have now been corrected in `corrected-en-v1/`. See `BUILD_NOTES.md`, `english-build-manifest.json`, and the corrected ZIP. The observations below describe the original downloaded pack, which is retained untouched. No benchmark has run on the corrected version yet.

## Original downloaded-pack outcome

The pack contains all five expected documents but is NOT a fully English counterpart. Do not describe a full-pack run as a clean VI/EN cross-language experiment. No GPU benchmark has been run on this pack. Default recommendation is to get the English text corrected first; an as-is run would be explicitly exploratory on mixed-language data.

| Document | Local parser chunks | Inspection |
| --- | ---: | --- |
| Policy manual DOCX | 19 | Main inspected policy sections are English; facts/formulas/version and simulation warnings appear consistent. Not a full human translation certification. |
| SOP PDF | 6 | Substantial Vietnamese body remains, including data-conflict procedure, required transaction fields, table cells and retention rules. Vietnamese glyphs are broken even in the rendered PDF, not merely during extraction. First-page visual proof: sop-first-page.png. |
| Policy registry CSV | 12 | Predominantly English; INV-POL-003 SLA still says `P1 trong 1 ngày làm việc`, INV-POL-012 says `Mỗi yêu cầu`. |
| Inventory workbook XLSX | 485 | Same parser section counts as the frozen VN workbook: 424 Inventory Control, 50 Exception Log, 6 Policy Matrix, 3 README, 2 KPI Summary. Some Vietnamese cells remain; see english-quality-audit.json. |
| Training deck PPTX | 8 | Main operating slides are English, but data-quality bullets on slide 2 and automation/roadmap bullets on slide 8 remain Vietnamese. |

The archive supplies neither README.txt nor translated benchmark questions/answers. README is also missing in the original frozen VN benchmark; retain that missing-label limitation until a new label version is explicitly defined.

## Checks and limits

- Existing built-in DocumentProcessor used locally, no captioning/images or OCR. The English PDF has native selectable text, and visual inspection confirms the defects are already in the supplied PDF.
- With ocr_fallback disabled, the existing PDF parser unexpectedly requires tesseract_table_psm and ocr_table_render_scale for table metadata. The local parsing call supplies these defaults explicitly; no production code was changed and OCR was not run.
- Final EN parser output: 530 chunks versus the prior frozen VN 532. Different chunk counts/boundaries are expected from translation; do not match evidence by final chunk index.
- Sets of extracted numeric tokens match for CSV and XLSX; observed DOCX/PPTX differences include equivalent dates rendered as 2022-12-31 versus 31/12/2022, and 16 Oct 2026 versus 16/10/2026. This is a spot alignment check, not proof that every row/cell/fact is identical.
- paired-questions-draft.json contains 20 assistant-translated EN questions paired with unchanged VN questions/reference answers. It is a draft for human review, not an independently supplied gold set. No external translation API was used.
- Old file/page coverage metrics are coarse. The next scored dataset should have answer-bearing spans/rows and reviewed alternative evidence, versioned separately from the historical snapshots.

## Request to the document author

Please finish translating the remaining Vietnamese content in the English SOP PDF, CSV SLA cells, workbook cells, and slides 2/8. Regenerate the PDF with Unicode-capable embedded fonts and verify its rendered text and copy/paste text. Keep the original facts, numbers, tables, policy IDs, formulas, warnings and approval rules unchanged. Provide the corresponding English 20 questions plus reference answers/evidence, or review the paired question draft. Confirm whether README.txt should be supplied; do not silently remove its existing labels.

## Planned local benchmark after correction

Freeze a new version of aligned VI/EN inputs and validate token lengths for each model including required prefixes. Rank only the target-language five-document corpus for each of the four directions so a duplicate in the query language cannot hide a cross-language miss. Reuse the existing local candidate runner where possible, record any new scope/scoring logic and tests, and keep dense encoder tests separate from translated hybrid and generation. No team Supabase changes are needed.
