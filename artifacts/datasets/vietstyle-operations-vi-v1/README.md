# VietStyle operating policy — Vietnamese translation

Translated from the user's downloaded `VietStyle_Enterprise_Operating_Policy_v1.0.docx` on 23 October 2026. This is a translation of that document, not the separate synthetic Bảo An handbook and not a rewrite using its rules.

## Deliverables

- `VietStyle_Enterprise_Operating_Policy_v1.0_VN.pdf`: Vietnamese PDF, 54 physical pages, including cover, contents, 50 numbered policy pages and appendices.
- `VietStyle_Enterprise_Operating_Policy_v1.0_VN.docx`: editable Word version, retaining the original paragraph/table structure and heading styles.
- `VietStyle_Enterprise_Operating_Policy_v1.0_VN.md`: plain-text reading version.
- `translation.tsv`: authored Vietnamese translations indexed to the original Word paragraphs. Repeated labels are translated by the builder.
- `translation-alignment.json`: original/Vietnamese paragraph pairs and source DOCX hash.
- `verification.json`: structural, numeric and PDF text checks.
- `manifest.json`: hashes of generated files and builder.

## Preserved details

Policy identifiers, database/table/column identifiers, version1.0, effective date23October2026, amounts, numerical thresholds, periods, exceptions and approval roles follow the English source. Vietnamese number formatting uses periods for thousands. Legal or technical statements in the source have been translated, not independently established as correct. No source-policy inconsistencies were silently corrected.

The downloaded English files were left unchanged. Word exported the Vietnamese DOCX using the installed Microsoft Word; page layout can differ slightly even though the physical page count remains54. Heading labels “TRANG CHÍNH SÁCH01–50” are policy-page identifiers and differ from physical PDF page numbers because of front matter.

## Checks and experiment status

All1,228 original paragraph entries and56 tables remain in the Word document. All1,174 nonempty paragraph translations/retained identifiers occur in the PDF after whitespace normalization. All50 numbered policy headings occur in order. Numerical token differences only reflect three written-month date translations (October→10; December→12); numerical values elsewhere match after thousands-separator normalization. Six representative PDF pages were inspected visually.

This is not an OCR/retrieval/generation benchmark result. No model, external translation API, production database or existing frozen benchmark was used or changed. Questions from the Bảo An handbook do not transfer automatically: VietStyle has different approval thresholds and procedures. Prepare and independently review labels for this actual document before scoring.

## Rebuild

`scripts/evaluation/translate_vietstyle_policy.py --source PATH_TO_ORIGINAL.docx` applies the paragraph translations and refuses to overwrite an existing translated DOCX. The exact source file is required because mapping indexes refer to it. Use a new dataset folder/version for later edits. Word PDF export is a separate local step; the original formatting depends on Word and available fonts.
