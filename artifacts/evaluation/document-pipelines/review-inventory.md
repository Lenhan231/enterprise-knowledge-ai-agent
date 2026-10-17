# Existing label inventory and review queue

**Purpose:** decide what can be reviewed now for the official three-pipeline
benchmark. These are candidate labels, not accepted ground truth.

## Candidate coverage in this checkout

| Track | Existing candidates | Verified/eligible now | Target | Current gap |
|---|---|---:|---:|---:|
| OCR | 740 distinct non-Commerce crops, 529 source pages, 73 source PDFs, 60 issuer labels | 500 assistant-adjudicated crops; no human-reviewed crops | 500 crops, at least 100 pages and 30 documents | All three baseline pipelines scored on development, validation, and locked test; labels are not human-reviewed |
| Tables | 1,688 source-PDF table candidates scanned | 150 valid assistant-adjudicated table crops from 42 documents/issuers; TBL-014 rejected as a photo; TAB-149 corrected; TBL-201/TAB-151 accepted after full-page and 18×5 grid review | 150 tables from at least 30 documents | All three pipelines scored all 150 references; TAB-151 results are included in `table-comparison-150.json`; locked-test scores are unchanged |
| Reading order | 100-page target | 100 assistant-adjudicated development pages; not independently human-reviewed | 100 pages | All three pipeline outputs scored; development diagnostic only, with matched-block coverage reported |
| Layout | Official v2 set has 200 pages | 200 assistant-adjudicated pages: 121 development, 39 validation, and 40 locked-test; no independent human review | 200 pages | Full-page scores for all three pipelines are available; labels still need independent review for human-validated claims |
| Performance | Pilot timings and one 200-page layout run | PP-StructureV3, MinerU, and Docling: 3 warmed repeats complete | Same 200 layout pages, 3 warmed runs per pipeline | Interpret comparable medians, tails, and resource peaks with per-engine execution-path caveats |

The OCR count is de-duplicated by source file/hash, PDF page, and crop rectangle.
The scan found 77 `*_ground_truth.json` files and 925 raw page/region rows; after
excluding the 13 synthetic Commerce fixture rows, that is 912 enterprise
candidate rows and 740 distinct crops. The count includes provisional PDF text
layer references, visual one-reviewer transcriptions, and mixed provenance.
The manifests all currently set `primary_metric_selection_eligible: false`;
the initial review queues are candidate-only and exclude all 10 source PDFs
used in the 20-page pilot and the three missing source paths. The scoring set
at `ocr/reference/` contains 500 crops from 324 pages, 57 PDFs, and 56
issuers. It retains 496 existing assistant-reviewed transcripts and adds four
source-text crops checked against images. Each engine receives an image-only
180-DPI PDF; ground-truth labels stay outside Kaggle. Issuer-level splits are
299 development, 100 validation, and 101 locked test. Labels are
assistant-adjudicated under the owner instruction, not human-reviewed.

The table package at [`tables/reference/`](tables/reference/) contains 150 valid
isolated 180-DPI image-only PDF crops from 42 issuers, split by issuer into 89
development, 29 validation, and 32 locked-test tables. TBL-014 was excluded
after full-page review showed it was a photograph. TBL-201/TAB-151 is a complete
18×5 financial-ratio table visually checked against the source page and extracted
cell grid. Most other cell grids come from PyMuPDF source-text extraction;
merged-cell spans are not independently checked, so this supports cell/grid
scoring but not a human-verified TEDS/TEDS-Struct claim. The private Kaggle
dataset is `ltrngnhn/vietnam-enterprise-table-reference-v1`. All three
pipelines have output on the 150 current references; the full comparison is in
`results/table-150-v1/table-comparison-150.json`.

The 13-page layout pilot is assistant-adjudicated, not human-reviewed. All 13 pilot pages now have full-page labels in the v2 reference. Eight accepted labels were transferred from the pilot reference after verifying exact PDF hashes and page numbers; five HPG pages were reannotated directly on their v2 source images. The set has no standalone formula boxes. The table-stratified page inputs are assembled at
[`layout/inputs/`](layout/inputs/): 200 pages, including 114 table-source pages
from the 150-table crop set (115 unique source pages total; TAB-151 was added
after layout inputs were frozen) and all 13 pilot pages, split by issuer
121/39/40. The private
Kaggle dataset is `ltrngnhn/vietnam-enterprise-layout-200-pages-v2`. The v2 reference has 200 assistant-adjudicated pages: 121 development (108 non-pilot and all 13 pilot pages), 39 validation, and 40 locked-test pages. It contains 678 title, 1,121 text, 200 table, and 231 figure boxes, plus 14 supplemental signature regions (2,244 total). Reading-order labels cover 100 development pages. The separate 8-page enterprise-signature set has 17 candidate signature boxes and needs review; signature remains supplemental to the four core layout classes. The 123-page HCMUS set (1,065 boxes) is Vietnamese academic material and remains a separate transfer track, not enterprise-report coverage. External signature validation images also remain separate.

PP-StructureV3 has produced proposals for all 200 prose-heavy v1 full-page
inputs; it proposed 19 table boxes on 14 pages. The assistant-generated overlay
contact sheets and page queue are in [`layout/exploratory-review/`](layout/exploratory-review/).
They are review aids only; using the detector's own boxes as ground truth would
bias its score. On the v2 table-stratified input, PP-StructureV3 completed
200/200 pages; its raw outputs and run metadata are in
[`results/layout-200-pages-v2/pp-structurev3/`](results/layout-200-pages-v2/pp-structurev3/).
The pilot score is recorded in
[`results/layout-200-pages-v2/report.md`](results/layout-200-pages-v2/report.md); treat it as diagnostic only.
Accepted table extents are also mapped to full-page coordinates in
`data/evaluation/layout/vn-enterprise-layout-v2-table-reference.json`: 149
known-positive boxes on 114 pages; the TBL-014 photo false positive is excluded. On the 119 development/validation boxes,
PP-StructureV3 recalled 43, Docling 112, and MinerU 113; this is recall-only
because these pages are not exhaustively labeled. Docling and MinerU completed
200/200 inference pages, and raw outputs for all engines are downloaded and
validated. The three outputs were scored on the 59-page development subset and separately on the current 39-page validation set; see partial evaluations 032 and 051 (035–050 are earlier validation results).
The official v2 set now has its own 200-page overlay queue at
[`layout/full-page-review-v2/`](layout/full-page-review-v2/), with source-page
and image hashes. These remain model proposals, not reference annotations.
The v2 overlay set includes assistant-adjudicated labels for all 200 pages; the locked-test scores are reported in `results/layout-200-pages-v2/report.md`. Reading-order labels and scores cover 100 development pages; they are not a held-out test result.

## Review sequence

1. **OCR:** run the three pipelines on `ocr/reference/` and score development
   and validation first. The current untuned baselines have been scored once on
   locked test; do not tune against that split. Keep table-only regions out of
   prose OCR.
   The consolidated [`ocr/candidate-review/`](ocr/candidate-review/) is the candidate queue, not
   the scoring input; it retains 520 unique candidates and the earlier review
   fields. The canonical scoring input remains `ocr/reference/`.
2. **Tables:** create full cell grids for 150 tables from at least 30 documents,
   including empty cells and merged spans. Review numeric text against the
   source images. Do not treat extracted Markdown or selected row anchors as
   table ground truth.
3. **Layout and order:** review the 13 existing enterprise pages and add pages
   until 200 have boxes for title, text, table, and figure. On 100 of those
   pages, also label ordered text/layout blocks. Keep formula and signature as
   separate supplemental classes until each has 100 reviewed boxes.
4. **Performance:** freeze the same 200 page inputs and model versions, then
   run three warmed measurements per pipeline. Record end-to-end time, peak
   host RAM, and peak GPU memory separately.

## Source files to review

- OCR crop labels: [`data/evaluation/ocr/`](../../../data/evaluation/ocr/)
- OCR review sheets and crop previews: [`artifacts/evaluation/ocr/review/`](../ocr/review/)
- 520-crop candidate review queue: [`ocr/candidate-review/README.md`](ocr/candidate-review/README.md), [`review.csv`](ocr/candidate-review/review.csv), and [`queue.json`](ocr/candidate-review/queue.json)
- Rebuild script: [`prepare_document_pipeline_ocr_review.py`](../../../tools/processing/prepare_document_pipeline_ocr_review.py)
- Enterprise layout pilot: [`vn-enterprise-layout-pilot-v1.json`](../../../data/evaluation/layout/vn-enterprise-layout-pilot-v1.json)
- Expanded enterprise layout labels: [`expanded-v1/datasets/vietnamese-enterprise-pilot/annotations.json`](../../../data/evaluation/layout/expanded-v1/datasets/vietnamese-enterprise-pilot/annotations.json)
- Candidate table row references: the `table_rows` entries in `data/evaluation/ocr/*_ground_truth.json`
- Official benchmark targets and split protocol: [`plan.md`](plan.md)
