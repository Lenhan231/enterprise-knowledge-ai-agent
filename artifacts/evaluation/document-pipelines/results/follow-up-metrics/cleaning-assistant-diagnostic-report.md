# PDF cleaning component: assistant diagnostic

## Scope

This assistant diagnostic covers all 10 pages (five development, five validation)
in the cleaner-output-blind pilot. It uses assistant visual labels against source
images and native PDF text; it is not independent human review.

The labels are in
[`cleaning-assistant-diagnostic.json`](cleaning-assistant-diagnostic.json),
and scorer output is in
[`cleaning-assistant-diagnostic-scores.json`](cleaning-assistant-diagnostic-scores.json).
The scorer preserves `assistant_visual_adjudication` provenance and reports
`assistant_adjudicated_cleaning_diagnostic` status.

## Results

| Page | Reviewed OCR spans | Labels | Residual spans in cleaned output |
|---|---:|---|---:|
| LAYOUTV2-107 (PVChem) | 7 | 7 duplicate | 4/7 duplicates |
| LAYOUTV2-022 (Bình Minh Plastics) | 1 | 1 noise | 0/1 noise |
| LAYOUTV2-066 (Hòa Phát) | 13 | 13 duplicate | 8/13 duplicates |
| LAYOUTV2-151 (Vicostone) | 4 | 4 duplicate | 0/4 duplicates |
| LAYOUTV2-157 (Vietcombank) | 22 | 22 duplicate | 0/22 duplicates |
| LAYOUTV2-086 (TRA-SAS) | 39 | 19 duplicate, 20 noise | 0/19 duplicates; 0/20 noise |
| LAYOUTV2-183 (Viettel Post) | 33 | 3 duplicate, 30 noise | 0/3 duplicates; 30/30 noise |
| LAYOUTV2-169 (VEAM) | 32 | 31 duplicate, 1 noise | 29/31 duplicates; 1/1 noise |
| LAYOUTV2-134 (Techcombank) | 26 | 26 new_valid chart spans | 26/26 exact spans retained |
| LAYOUTV2-011 (Bảo Long) | 164 | 2 new_valid, 40 duplicate, 122 noise | 0/2 valid exact spans; 35/40 duplicates and 68/122 noise remain |
| **Total** | **341** | **139 duplicate, 174 noise, 28 new_valid** | **76/139 duplicates; 99/174 noise; 26/28 valid exact spans retained** |

The chart on LAYOUTV2-134 contains OCR-only labels, values, and footnote text
absent from the native PDF text. All 26 assistant-labeled chart spans (472
characters) occur exactly in cleaned output. On LAYOUTV2-011, the two
assistant-labeled OCR-only spans (33 characters: `INSURANCE` and the slogan) do
not occur as exact spans. The cleaned output contains transformed fragments
(`BAO LONG INSUR ANCE PONG CHIA SE ĐỒNG HÀNH -`), so this strict exact-span
scorer flags them as not retained; it does not establish that all semantic
content was removed. Across this assistant-labeled pilot, exact span retention is 26/28
(92.86%), character-weighted exact retention is 472/505 (93.47%), and the
corresponding exact-span false-deletion rate is 2/28 (7.14%). Duplicate OCR
remains at 76/139 spans and noise at 99/174 spans. These diagnostic rates use
assistant labels and an exact matching scorer; they are not human-reviewed
quality estimates and must not be combined with parser scores.

## Next step

Independently review the 10-page pilot before treating any result as
human-reviewed. Refine retention scoring to distinguish deletion from OCR text
reordering/spacing changes, then score the remaining candidate pages if the
rubric and metric behavior are acceptable. Page-counter removal still has no examples and remains not
evaluated.
