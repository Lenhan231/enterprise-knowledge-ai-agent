# Enterprise document pipeline benchmark plan

**Status: Baselines are complete for OCR (500 crops), tables (150), layout (200 pages), reading order (100 development pages), and three-repeat performance. MinerU V11 V0/V1 completed all 12 development/validation groups on CPU; its outputs are scored in [the CPU control report](results/mineru-preprocessing/cpu-v11-report.md). CPU resource data are diagnostic only, and V0 does not exactly reproduce the saved T4 outputs. Follow-up metrics and required reference reviews remain open; no production pipeline is selected. Do not resume MinerU V2–V4 until the follow-up gate closes and MinerU remains shortlisted.**
PP-StructureV3, MinerU, and Docling on the same Vietnamese enterprise documents.
The pilot is for validating inputs, output normalization, and scoring rules. It is
not part of the final scores and must not be used to declare a winner.

The current consolidated baseline results are in
[`results/benchmark-report.md`](results/benchmark-report.md); metric-specific
reports and per-item JSON remain the authoritative detailed records.

### MinerU V11 CPU control — completed 2026-10-17

Kaggle reports V11 `COMPLETE`; all 12/12 V0/V1 development/validation groups
returned code 0 with zero fallback items. Results are scored at
[`cpu-v11-variant-scores.json`](results/mineru-preprocessing/cpu-v11-variant-scores.json)
and summarized in the [run report](results/mineru-preprocessing/cpu-v11-report.md).
The run used accelerator `None`; CPU time and RSS are diagnostic only and GPU
memory is unavailable. The selected download excluded duplicate inputs and the
offline runtime; 1,354 output ZIPs passed integrity checks.

## Canonical data folders

Use one folder per track; run IDs stay in `results/` and Kaggle kernel names for provenance.

- OCR: [`ocr/reference/`](ocr/reference/) is the fixed 500-crop scoring set. [`ocr/candidate-review/`](ocr/candidate-review/) is a separate 520-candidate queue; it is not the same crop set. IDs are `OCR-*` for references and `OCR-CAND-*` for candidates.
- Tables: [`tables/reference/`](tables/reference/) is the 150-valid-table scoring set (one false-positive photo excluded); [`tables/candidate-review/`](tables/candidate-review/) holds the 220 candidate regions and decisions.
- Layout: [`layout/inputs/`](layout/inputs/) is the official table-stratified 200-page v2 dataset root shared by all pipelines. The PDFs are in its nested `inputs/` folder; `kaggle-dataset/inputs/` is the upload copy. [`layout/full-page-review-v2/`](layout/full-page-review-v2/) holds v2 visual overlays; accepted labels are in `data/evaluation/layout/`. [`layout/exploratory/`](layout/exploratory/) is the older v1 input run, while [`layout/exploratory-review/`](layout/exploratory-review/) contains v1 proposal overlays and review queues. Neither v1 folder supplies current benchmark labels.

## Benchmark scope and targets

Each metric has its own unit of analysis; do not combine the counts into one
generic sample size.

| Track | Target | Reference labels | Main score |
|---|---:|---|---|
| Pilot | 20 representative pages, including about 10 tables | Review pipeline outputs and scorer behavior | No final score |
| OCR | 500 text crops from at least 100 pages and 30 documents | Adjudicated transcript and crop coordinates, with reviewer provenance | CER and WER |
| Tables | 150 complete tables from at least 30 documents | Existing cell grids; add reviewer-checked HTML with `rowspan`/`colspan` for the 32 locked-test tables in the canonical `reference.jsonl` | Exact cell-text accuracy and grid dimensions on all splits; GriTS-Top and GriTS-Con on the reviewed locked-test tables |
| Reading order | 100 development pages now; add the 39 validation and 40 locked-test layout pages | Ordered page blocks; labels for validation/test created or checked by a reviewer without seeing pipeline predictions | Pairwise block-order accuracy with matched-block coverage |
| Layout | 200 pages | Assistant-adjudicated boxes for title, text, table, and figure | Per-class precision/recall/F1 at IoU 0.50; AP/mAP only where confidence scores allow a comparable sweep |
| Performance | The same 200 layout pages | Identical inputs and recorded runtime environment | Initialization, seconds/page, peak RAM/VRAM |

Keep formula and signature outside the enterprise four-class layout aggregate:
the 200-page enterprise reference has no formula boxes and only 14 signature
regions. Formula detection has a separate five-detector transfer benchmark on
916 HCMUS pages (121 formula boxes in the class-balanced formula subset); do
not present that academic-domain result as enterprise validation. Exclude table text from the prose OCR aggregate;
score it with the table track to avoid counting the same content twice. Retain a
page-level OCR result as a separate end-to-end check where reviewed full-page
transcripts are available.

## Dataset and execution protocol

1. Select real Vietnamese enterprise documents to match the production mix of
   scanned and born-digital PDFs. If a reliable production ratio is unavailable,
   report the two PDF types separately; do not invent a weighted aggregate.
2. Run a 20-page pilot, with roughly 10 tables, through all three pipelines on
   identical source pages. Preserve each tool's original output before mapping
   it into a shared scoring format.
3. Keep label provenance explicit. Existing assistant-adjudicated development and
   validation references remain usable for exploratory tuning. Independently
   human-review the locked-test references for OCR, tables, layout, and reading
   order before scoring preprocessing variants. Reviewers must not see pipeline
   predictions while editing references; preserve both original and corrected
   labels plus reviewer, date, and changed-item provenance. Until this review is
   complete, call the comparison assistant-adjudicated rather than human-validated.
4. Keep the existing issuer-level development/validation/test membership fixed:
   OCR 299/100/101 crops, tables 89/29/32 tables, and layout 121/39/40 pages.
   Never move a source document between splits. Pilot issuers stay out of the
   locked test. Because the current test aggregates have already been viewed,
   use them only for a retrospective, once-only post-tuning comparison; do not
   inspect test-level errors or use test results to choose transforms or thresholds.
   A future thesis claim requiring a completely untouched test needs newly
   collected issuers/documents.
5. Pin model/package versions and record hardware. On Kaggle, use the same GPU
   class where supported. Warm up each pipeline, run each page three times for
   performance, and report median and p95. Record model initialization
   separately from per-page inference and end-to-end time.
6. Store source hashes, labels, raw pipeline outputs, normalized outputs,
   per-item scores, aggregate reports, and runtime metadata. Do not overwrite
   exploratory results when a protocol changes; version the dataset/run.

## Initial readiness and pilot history

This records the starting point and pilot history; current benchmark completion
and remaining review limits are summarized at the top of this plan and in
[`review-inventory.md`](review-inventory.md):

- `../ocr/layout-pipeline-kaggle/` contains an exploratory PP-StructureV3,
  Tesseract, and layout-plus-Tesseract run on 14 Long Hau/Hoa Phat page images.
  Its report has OCR references for two pages and four table anchor rows on one
  page; it is not a MinerU/Docling comparison or a complete benchmark.
- `../../../data/evaluation/layout/vn-enterprise-layout-pilot-v1.json` contains
  13 AI-assisted enterprise page annotations. All 13 pilot pages now have
  assistant-adjudicated full-page labels in the v2 reference; eight accepted
  labels were transferred by exact source PDF/page match and coordinate review.
  Assistant review is not human review.
- `../../../data/evaluation/ocr/vn-enterprise-ocr-large-v1_ground_truth.json`
  and per-document OCR ground-truth files provide candidate crops. Existing
  transcripts must be reviewed/adjudicated before they enter the final test set.
- Existing HCMUS and ViFinTab results are transfer/table-detection tracks; they
  are not enterprise document results and must stay separate.

The 20-page pilot input has now been assembled at
[`pilot-v1/manifest.json`](pilot-v1/manifest.json), with one-page PDFs under
[`pilot-v1/inputs/`](pilot-v1/inputs/). The PDFs retain source page content and
text layers where available. The set contains 11 born-digital pages, 6 known
physical scans, and 3 image-only PDF pages. It includes approximately 9 table
regions across 6 pages, suitable for inspecting pipeline output but not for
complete table scoring. Existing references currently link to 2 full-page OCR
transcripts, 6 pages with OCR crop references, 1 table page with 4 row anchors,
and 13 AI-assisted layout annotations. Reading-order labels are not present.

The private Kaggle input is
[`ltrngnhn/vietnamese-enterprise-document-pipeline-pilot-v1`](https://www.kaggle.com/datasets/ltrngnhn/vietnamese-enterprise-document-pipeline-pilot-v1).
Three separate GPU kernels are prepared under `kernels/`; each writes raw
outputs and runtime metadata to its Kaggle output. PP-StructureV3, MinerU, and
Docling use separate Kaggle environments to avoid dependency conflicts. The
completed [Docling pilot summary](results/docling/pilot-summary.md) records
20/20 successful pages and the limits of its exploratory OCR/table results.
Docling's first attempt exposed a RapidOCR API mismatch; its successful rerun
pins RapidOCR 3.9.2. MinerU Standard loaded its model and then crashed with exit
code `-11` after selecting the local llama.cpp VLM engine. A MinerU Basic batch
attempt processed some pages but stopped at a PDF with `Unsupported warp
settings`; the current retry isolates each page in its own CLI process so that
one parser failure cannot abort later pages. This adds repeated startup time,
so its pilot performance numbers are not directly comparable to persistent
process runs. Treat Basic as a separate variant, not as evidence about
MinerU Standard. The first PP-StructureV3 run failed before inference because
Paddle's CUDA 12.6 dependencies downgraded Kaggle's NCCL runtime and broke its
Torch import (`ncclCommShrink` missing). The current kernel restores the exact
CUDA libraries required by the preinstalled Torch before checking imports and
starting inference. Both reruns completed and their raw outputs were downloaded.
PP-StructureV3 processed 20/20 pages; MinerU Basic processed 19/20, with the
same p15 warp-settings error. The unified scorer is at
[`pilot-comparison.json`](pilot-comparison.json), with interpretation in
[`pilot-report.md`](pilot-report.md). The pilot has comparable artifacts, with
one MinerU page failure, but it does not meet the official label or sample
targets.

The assistant-adjudicated OCR reference set is assembled at
[`ocr/reference/`](ocr/reference/): 500 text crops, 324 source pages,
57 PDFs, and 56 issuers. Each crop is a 180-DPI image-only PDF so the engines
cannot use the source PDF text layer. The issuer-level split has 299 development,
100 validation, and 101 locked-test crops. Ground-truth transcripts remain
outside the Kaggle input. Four additional transcripts were checked against their
crop images and PDF text layers; the remaining 496 keep the existing
assistant-reviewed transcripts. These labels are assistant-adjudicated under
the project-owner instruction, not human-reviewed. All three OCR pipelines
completed 500/500 inputs on Kaggle T4. The baseline configurations were untuned
and then frozen for one locked-test score. On the 101 locked crops,
micro-CER/WER and macro-CER/WER were: PP-StructureV3 26.99%/73.79% and
26.32%/75.21%; MinerU Basic 18.00%/56.41% and 16.14%/55.98%; Docling
26.47%/65.88% and 30.10%/67.51%. MinerU Basic had the lowest error on each
split. This is a baseline result, not proof of production quality. Its timing includes a
separate CLI/model startup for every crop, so it is not directly comparable to
the persistent-process timings of PP-StructureV3 and Docling. Runtime metadata
and the interpretation are recorded in
[`results/ocr-500-crops-v1/report.md`](results/ocr-500-crops-v1/report.md);
per-crop scores are in
[`results/ocr-500-crops-v1/ocr-comparison.json`](results/ocr-500-crops-v1/ocr-comparison.json).
The kernels, raw outputs, and metadata are under
[`kernels/ocr-500-crops-v1/`](kernels/ocr-500-crops-v1/) and the matching
engine directories in `results/ocr-500-crops-v1/`.

The assistant-adjudicated table set is assembled at
[`tables/reference/`](tables/reference/): 150 valid isolated 180-DPI image-only table crops from 42 source documents and issuers, split 89/29/32 by issuer. The original 150-input Kaggle run included TAB-010/TBL-014, which full-page review identified as a photograph rather than a table; its output is excluded from scoring. TAB-151/TBL-201 is a visually confirmed complete financial-ratio table with separate inference runs for all three pipelines.
Candidate regions and cell grids are assistant-adjudicated, not human-reviewed;
most grids use source PDF text extraction. QA found that development table
TAB-149 had an incomplete crop and malformed grid; both are corrected, with a
manually reconstructed 26×6 grid checked against the source page and text. The
private Kaggle input
is `ltrngnhn/vietnam-enterprise-table-reference-v1`; all three pipelines
completed the original 150/150 inputs and the TAB-151 supplemental run. The current comparison scores 150 valid references: 118 development/validation tables and the same 32 locked-test tables. Locked-test cell
accuracy/exact-shape rate were PP-StructureV3 26.65%/50.00%, MinerU Basic
46.00%/71.88%, and Docling 47.13%/84.38%; no engine reconstructed an exact
grid. The comparison and limitations are in
[`results/table-150-v1/report.md`](results/table-150-v1/report.md); per-table
scores and output-found flags are in
[`results/table-150-v1/table-comparison-150.json`](results/table-150-v1/table-comparison-150.json).
The first PP submission was rejected while two OCR kernels occupied the GPU
session limit; subsequent submissions
for all three table kernels completed.
Because merged-cell spans and every cell transcript are not independently
reviewed, the table report uses exact cell-position accuracy and grid
dimensions, not TEDS/TEDS-Struct. The original `table-comparison.json` is retained as the historical 150-input comparison; `table-comparison-149.json` preserves the previous valid-table comparison, and `table-comparison-150.json` adds TAB-151 while excluding false-positive TAB-010. Locked-test results are unchanged. The
corrected input package is versioned on Kaggle. The first Docling rerun failed
because it tried to edit the read-only Kaggle input manifest; the notebook now
copies that manifest into `/kaggle/working` and reads the PDF from the input
dataset. Docling correction completed with 35.3% cell-position accuracy; MinerU with 29.5%; and PP-StructureV3 with 17.3%. The first PP and MinerU reruns failed before inference because the notebook omitted `import shutil` in its input-preparation cell; version 2 fixed the import. The corrected 117-table development/validation comparison is saved at [`results/table-150-v1/tab149-correction/corrected-development-validation-comparison.json`](results/table-150-v1/tab149-correction/corrected-development-validation-comparison.json).

The first 200-page set at [`layout/exploratory/`](layout/exploratory/) was
prose-heavy: PP-StructureV3 proposed only 19 table boxes on 14 pages. Keep that
run exploratory. The table-stratified official input set is now assembled at
[`layout/inputs/`](layout/inputs/): 114 unique pages represented by the table
references present when v2 was assembled,
all 13 pilot pages, and 73 issuer-round-robin text/figure pages (including
LAYOUTV2-072 after TBL-014 was rejected), split 121/39/40 by issuer. Its private Kaggle dataset is
`ltrngnhn/vietnam-enterprise-layout-200-pages-v2`; labels stay outside the
input. PP-StructureV3 (PP-DocLayout-S + PP-OCRv5 mobile + table recognition)
completed all 200 pages on Kaggle T4: 38.01 s initialization, 1.60 s median
and 2.61 s p95 per page, 3,397.9 MiB peak host RSS. This is one run; peak VRAM
was not measured. On the eight already-adjudicated pilot pages embedded in v2,
its four-class micro precision/recall/F1 at IoU 0.50 were 0.310/0.361/0.333;
this small subset is diagnostic only. The reference and method are documented
in [`report.md`](results/layout-200-pages-v2/report.md).
The 150-table crop set has 115 unique source pages. The 200-page layout input
contains 114 of them; TAB-151's source page was added later and is outside that
input set. The accepted extents therefore provide 149 known-positive table
boxes across 114 v2 pages; the TBL-014 photo false positive is excluded. On the 119 development/validation boxes, PP-StructureV3
matched 43 (known-positive recall 0.361) and Docling matched 112 (0.941); these
are recall-only because those pages are not exhaustively labeled. MinerU
matched 113 (0.950). The 30 valid locked-test boxes have now been scored once:
PP-StructureV3 matched 13 (0.433 recall), Docling 27 (0.900), and MinerU 28
(0.933). This remains recall-only, so it cannot establish precision or full
layout quality.
Raw output and per-page runtime metadata are in
[`results/layout-200-pages-v2/pp-structurev3/`](results/layout-200-pages-v2/pp-structurev3/).
Docling and MinerU also completed 200/200 pages; their raw outputs are
downloaded and validated. One-pass timing and both partial accuracy results are
in [`report.md`](results/layout-200-pages-v2/report.md). The earlier v1 one-pass run took 31.50 seconds to initialize
and 1.70 seconds median (2.83 seconds p95) per page, with 3.20 GB peak host RSS
on Kaggle T4; this was not a warmed three-run measurement and peak VRAM was not sampled. The provisional record is
[`pp-structurev3-performance-single-run.json`](results/layout-200-pages-v1/pp-structurev3-performance-single-run.json).
The v1 contact sheets and proposal queue are saved at
[`layout/exploratory-review/`](layout/exploratory-review/); proposals are not ground truth. The
v2 kernels are staged under [`kernels/layout-200-pages-v2/`](kernels/layout-200-pages-v2/).
The v2 full-page reference now covers all 200 pages (121 development, 39 validation, 40 locked test), with 2,244 annotations. The locked-test full-page scores are in [`full-page-200-locked-test/`](results/layout-200-pages-v2/full-page-200-locked-test/). Reading-order labels now cover 100 development pages; the scorer has run for all three pipelines. Both tracks retain the assistant-adjudication caveat.

The earlier `perf3` resource runs and their outputs remain under
[`kernels/layout-200-pages-v2-performance/`](kernels/layout-200-pages-v2-performance/)
and `results/layout-200-pages-v2/performance-repeats/` as historical
measurements. The canonical 2026-10-15 reruns used versioned `perf4` kernels
under [`kernels/layout-200-pages-v2-performance-rerun-20261015/`](kernels/layout-200-pages-v2-performance-rerun-20261015/)
and are downloaded under
[`results/layout-200-pages-v2/performance-rerun-20261015/`](results/layout-200-pages-v2/performance-rerun-20261015/).
Each engine completed three warmed passes over the same 200 pages. Combined
performance results and the MinerU tuning decision are in
[`results/benchmark-report.md`](results/benchmark-report.md); machine-readable
rerun values are in
[`performance-rerun-summary.json`](results/layout-200-pages-v2/performance-rerun-20261015/performance-rerun-summary.json).
The corrected TAB-149 comparison remains at
[`corrected-development-validation-comparison.json`](results/table-150-v1/tab149-correction/corrected-development-validation-comparison.json).

The v2 full-page reference contains 200 assistant-adjudicated pages: 121 development, 39 validation, and 40 locked-test pages. It has 678 title, 1,121 text, 200 table, and 231 figure boxes, plus 14 supplemental signature regions (2,244 annotations total). The development subset contains 108 non-pilot pages and all 13 pilot pages. Validation coverage spans nine issuers: Bao Long, Dong A Paint, Kigimex, TRA-SAS, PVI Holdings, REE, Techcombank, VSC, and Viettel Post. Labels are not independently human-reviewed. Full-page locked-test scores and development/validation diagnostics are consolidated in [`report.md`](results/layout-200-pages-v2/report.md); superseded partial-evaluation snapshots were removed after this final comparison was complete.

The official v2 layout review overlays are at
[`layout/full-page-review-v2/`](layout/full-page-review-v2/). It contains
assistant-adjudicated box overlays for all 200 pages; raw proposal contact sheets
remain review aids rather than ground truth.

## Readiness gates

- [x] Choose and record the 20-page pilot list from real production-like PDFs;
      preserve born-digital PDFs as PDFs rather than rasterizing away text layers.
- [x] Run all three pipelines on the same pilot inputs and save raw outputs and
      runtime metadata; MinerU Basic failed on 1 of 20 pages.
- [x] Implement shared OCR normalization and exploratory table-anchor scoring
      in the pilot evaluator.
- [x] Adjudicate pilot references and select scoring rules under the project-owner
      instruction to proceed without waiting for human review; see [`pilot-adjudication.md`](pilot-adjudication.md).
- [x] Rescore the pilot with row-wise OCR references and a complete table grid;
      see [`pilot-v2-report.md`](pilot-v2-report.md).
- [x] Inventory the existing OCR, table, reading-order, and layout label
      candidates; see [`review-inventory.md`](review-inventory.md).
- [x] Build and split the assistant-adjudicated OCR reference set; see
      [`ocr/reference/`](ocr/reference/).
- [x] Assemble the table-stratified 200-page layout v2 input set with
      issuer-level splits and pilot issuers in development; see
      [`layout/inputs/`](layout/inputs/).
- [x] Run all three pipelines on the 150 valid table references; exclude false-positive TBL-014, publish the current comparison, and preserve the locked-test split.
- [x] Run all three pipelines on the OCR crops and score CER/WER on
      development/validation and the one-time locked baseline test.
- [x] Run all three pipelines on the isolated table crops and score exact
      cell-position accuracy and grid dimensions on development/validation and
      the one-time locked baseline test.
- [x] Assistant-adjudicate full-page boxes for all 200 v2 pages and score all three pipeline outputs; provenance explicitly says labels are not independently human-reviewed.
- [x] Expand the reading-order reference to 100 development pages and score all three pipeline outputs; report it as a development diagnostic with matched-block coverage.
- [x] Create issuer-level development, validation, and locked-test splits for
      OCR, tables, and layout inputs; pilot issuers are kept out of locked test.
- [x] Score the frozen baseline OCR, table, and full-page layout locked-test
      splits once; these baseline aggregates are visible and the split is no
      longer pristine.
- [ ] Independently human-review locked-test OCR transcripts, table cell text and merged spans, layout boxes, and reading-order labels without viewing predictions. Only then describe those references as human-reviewed and calculate locked-test GriTS.
- [ ] Add reading-order annotations for all 39 validation and 40 locked-test layout pages; keep existing 100 development labels unchanged.
- [x] Implement deterministic V0–V4 input generation and per-item provenance in [`prepare_mineru_preprocessing_variants.py`](../../../tools/processing/prepare_mineru_preprocessing_variants.py); smoke-check PDF dimensions/image-only output, visually check V0–V4 transformations on OCR-015/OCR-334, and verify source hashes.
- [x] Prepare prediction-blind review pages for OCR, table, and layout locked-test references plus validation/test reading order in [`human-review/`](human-review/); no engine predictions are included. Integrity audit found all referenced images present: 101 OCR, 32 table, 40 layout, 79 reading-order, and 20 native-text pilot items (zero broken image links).
- [x] Build the private Kaggle kernel for V0–V3 and six V4 threshold candidates on development/validation only; see [`kernels/mineru-preprocessing/`](kernels/mineru-preprocessing/).
- [x] Reuse the existing OCR, table, layout, and split-aware reading-order evaluators in [`score_mineru_preprocessing_variants.py`](../../../tools/processing/score_mineru_preprocessing_variants.py); report paired issuer-cluster bootstrap confidence intervals (10,000 resamples) against V0, and capture preprocessing/inference time plus sampled process/GPU memory in each MinerU run record.
- [x] Cache grayscale features/skew estimates across the 10 variants in the Kaggle run; seed OCR development features from the threshold-calculation pass and reuse each skew estimate for V1/V3/V4.
- [x] Add and smoke-check `--variants`, `--tracks`, and `--splits` in the builder; default scope remains 60 development/validation groups, and locked-test scope is isolated to V0 alone or V0 plus exactly one selected candidate.
- [x] Add `--include-locked-test` scoring and make the selector continue to use validation only; the watcher reads dynamic group counts and enables test scoring only when locked-test outputs exist.
- [x] Add a validation gate selector for predeclared CER/WER, table, layout, and reading-order guardrails; it reports a selected V4, a fixed-transform fallback, or a reason it cannot select.
- [x] Collect and score the split CPU exploratory batches. V10 was canceled at the 12-hour limit; V11 V0/V1 then completed all 12/12 groups with zero fallback items. The 1,354 downloaded ZIPs passed integrity checks and the validation-only score is [`cpu-v11-variant-scores.json`](results/mineru-preprocessing/cpu-v11-variant-scores.json); interpretation and CPU resource measurements are in [`cpu-v11-report.md`](results/mineru-preprocessing/cpu-v11-report.md). No GPU memory was available, so these timings remain CPU diagnostics and are not comparable with the T4 performance baseline.
- [x] Extend the native-text scorer to accept the source-preserving candidate manifest and a matching review export; it scores only reviewed pages marked `born_digital` and supports a separate output root for all three engines. This makes the 151-page candidate package scoreable after labels and inference outputs exist; no candidate inference or scoring has run yet.
- [x] Extend the reading-order evaluator to consume the prediction-blind review export directly, verify all requested validation/test pages and one-to-one block indices, and preserve per-page reviewer provenance without mutating the canonical reference. Its command is documented in [`human-review/README.md`](human-review/README.md); no reviewed reading-order export has been supplied or scored yet.
- [ ] Finish the proposal follow-up metrics before a production-pipeline decision; see [`follow-up-metrics.md`](follow-up-metrics.md). The saved 20-page common pilot was reused for a born-digital diagnostic on 11 manifest-labeled pages (11/11 outputs each); the 11-page source-text transcripts remain unreviewed and HPG pages 3/5 differ from visible column order, so that proxy confounds reading order. HPG page 6 has a separate one-page assistant-reviewed linear-text diagnostic; this is not independent human review or a selection result. A matching PyMuPDF-based, prediction-blind review packet is prepared at [`human-review/native-text-pilot-v2/review.html`](human-review/native-text-pilot-v2/review.html); v1 is retained unchanged. The 200-page layout inputs are image-only. A source-preserving candidate package is prepared at [`results/follow-up-metrics/native-text-candidates-v1/`](results/follow-up-metrics/native-text-candidates-v1/): 151 pages (112 development, 39 validation) from 41 PDFs/40 issuers, with locked test excluded. Its text-layer/source-type labels are unreviewed, so do not infer or score before reviewing the pilot and choosing a reviewable sample. The scorer accepts the prediction-blind pilot review export and reuses saved outputs; no pilot inference rerun is needed. Production PDF cleaning is scoped in `follow-up-metrics.md` to OCR/native-text deduplication. The production helpers identify 77 dev/validation mixed-text/image-region candidates across 34 issuers; the candidate inventory is `results/follow-up-metrics/cleaning-candidates-v1.json`. No candidate trailing page-counter lines occur in the current dev/validation sources, so that cleanup rule needs separate examples or must be excluded from its score. Span labels have an assistant visual diagnostic over all 10 pilot pages at [`cleaning-assistant-diagnostic-report.md`](results/follow-up-metrics/cleaning-assistant-diagnostic-report.md); its exact-span scores are diagnostic only, and no independent human-review export has been supplied. This is separate from the V11 V0/V1 control batch.
- [x] Save production-path Tesseract/native extraction for all 77 cleaning candidates and prepare a cleaner-output-blind 10-page rubric pilot (five development, five validation, 10 issuers, including the only full-page OCR candidate): [`human-review/cleaning-pilot-v3/review.html`](human-review/cleaning-pilot-v3/review.html), [`production-output.json`](results/follow-up-metrics/cleaning-pilot-v1/production-output.json).
- [x] Implement the OCR-span cleaning scorer with strict full-set completeness checks, an explicit pilot-only partial option, and development/validation reporting in [`evaluate_document_pipeline_cleaning.py`](../../../tools/processing/evaluate_document_pipeline_cleaning.py). The scoring method is ready; an assistant-adjudicated diagnostic is recorded separately, but no human-reviewed metric result exists until an independent reviewer export is supplied.
- [x] Visually validate V1 deskew on OCR-334 (0.5°) and V2/V3/V4 contrast behavior on OCR-015; V1/V3/V4 skip OCR-015's corrected 0° estimate. Verify V0 hashes for all 509 development inputs and source-document hashes for 50 original PDFs.
- [ ] After the follow-up-metric gate, resume MinerU V2–V4 ablation only if MinerU remains the research candidate; select on validation and score the previously viewed fixed test once as a retrospective comparison. If another parser becomes the candidate, tune that parser instead and identify the unequal tuning status in the report.
- [x] Implement the GriTS-Top/GriTS-Con scorer against the blind table-review export and saved outputs; it rejects partial or unreviewed references. Package: `grits-metric==0.6.1`; command and missing-detection handling are documented in [`human-review/README.md`](human-review/README.md). Parser smoke check confirmed 19/32 PP-StructureV3 detections and 32/32 each for MinerU/Docling, matching the existing table evaluator; this validates extraction coverage only, not GriTS accuracy.
- [ ] Compute GriTS-Top and GriTS-Con for the 32 human-reviewed locked-test tables; report them as secondary retrospective scores, not tuning gates.

The checked baseline test scores above are historical and already visible.
The planned post-tuning run reuses the same item IDs only as a retrospective
comparison; it does not restore the test's pristine status.

## Metric scoring conventions

- Normalize Unicode consistently (NFC), whitespace, and line breaks; preserve
  Vietnamese diacritics and punctuation for CER/WER. Document any additional
  normalization and publish raw plus normalized scores.
- Align predicted and reference regions before region-level OCR scoring. Report
  missed reference regions and unmatched predictions separately so a pipeline
  cannot improve CER/WER by omitting difficult text.
- Compare table outputs after converting them to cell grids; report exact
  normalized cell-text accuracy and row/column count. Empty cells count as
  cells. Once the 32 locked-test references have human-verified cell text and
  merged spans, additionally report GriTS-Top (structure) and GriTS-Con
  (content). Keep these test-only secondary scores out of tuning decisions.
- Measure reading order only over matched blocks. Report unmatched blocks and
  pairwise ordering disagreements separately.
- For full-page layout, report class-aware precision, recall, and F1 at the
  fixed IoU 0.50 threshold. The 200-page locked test has been scored against
  assistant-adjudicated boxes; these fixed-output scores are not AP/mAP because
  comparable confidence sweeps are unavailable. The separate known-positive
  table subset remains recall-only because it does not exhaustively label all
  table regions on its pages.
- Definitions: CER = character edit distance / reference characters; WER = word
  edit distance / reference words. Micro scores aggregate edit counts before
  division; macro scores average per-crop rates. Table cell accuracy is
  normalized exact cell-text matches at aligned row/column positions divided
  by reference cells; exact-shape requires row and column counts to match;
  exact-grid requires all aligned cells and shape to match. Layout IoU is
  intersection-over-union; TP/FP/FN are class-aware one-to-one matches at IoU
  ≥ 0.50; P=TP/(TP+FP), R=TP/(TP+FN), F1=2PR/(P+R). Reading-order coverage is
  matched reference blocks / reference blocks; pairwise accuracy is correctly
  ordered matched-block pairs / comparable matched-block pairs.
- Performance: report setup/model-load time and warm-up separately, then
  per-page median/p95, complete 200-page pass wall time and throughput. Sample
  process-tree RSS, GPU-process memory, and device-wide GPU memory at 1-second
  intervals. State whether output serialization is included; report per-page
  and batch modes separately when their timing boundaries differ.

## Default baseline and tuning metrics

The complete baseline and selection rationale are in
[`results/benchmark-report.md`](results/benchmark-report.md). All three
pipelines have OCR, table, layout, and reading-order baseline scores. The
2026-10-15 rerun is the canonical performance baseline: each pipeline warmed
one page and completed three measured passes over the same 200 Kaggle Tesla T4
pages. MinerU also has a directory-batch run; keep that execution mode separate
from its per-page CLI timing.

**Tune MinerU Basic next**, using development data for changes and validation
for selection. On validation it has the lowest OCR micro/macro CER and WER, the
best table-found rate and cell accuracy, and the highest layout micro F1. Its
reading-order development block coverage is also highest, though reading order
is not a tuning gate. This is a quality-first research choice. PP-StructureV3
is substantially faster in the persistent parser-call measurement, so compare
matching end-to-end execution modes before any deployment decision.

The frozen MinerU validation baseline is recorded in
[`results/tuning-baseline-validation.json`](results/tuning-baseline-validation.json).
The following study is the next planned experiment; it does not change the
selected pipeline or make a production decision.

### Research question and contribution

**Research question:** On the fixed image-only renderings of Vietnamese
enterprise documents, can a small, quality-aware preprocessing policy improve
MinerU Basic OCR over the unmodified input while preserving table, layout,
reading-order, and resource performance?

The contribution is an interpretable, page-quality-aware preprocessing policy
and a paired multi-task evaluation of its quality/cost trade-offs. This is an
engineering/evaluation contribution, not a new OCR architecture, a claim that
MinerU is universally best, or a claim of a new benchmark dataset. Report where
the policy helps and harms by scan quality and document type.

### Fixed experiment and ablation

Keep MinerU version, Basic tier, model weights, parsing options, language,
render resolution, hardware, runner, and output normalization fixed. Do not add a
second OCR engine, LLM repair, fine-tuning, or layout-specific crop OCR in this
experiment. The existing OCR crops, table crops, and layout-page PDFs are
deliberately image-only benchmark inputs rendered at 180 DPI; keep those exact
inputs as the V0 control and preprocess only derived copies. Never modify the
original source PDFs. This study therefore evaluates image-based OCR and does
not evaluate or make claims about the native-text extraction path for
born-digital PDFs; report results by source scan/image quality where labels
allow.

Run these five paired variants on identical item IDs:

| ID | Variant | Purpose |
|---|---|---|
| V0 | Original input; MinerU Basic defaults | Frozen control |
| V1 | Global deskew on eligible scans | Deskew ablation |
| V2 | Global grayscale contrast normalization on eligible scans | Contrast ablation |
| V3 | Deskew plus contrast normalization on eligible scans | Combined fixed preprocessing |
| V4 | Adaptive policy: independently decide whether to deskew and/or normalize contrast from page-quality features | Proposed method |

Use deterministic, documented operations. Estimate skew from foreground
projections with background polarity inferred from image intensity. Search
angles over ±10° so estimates beyond the supported correction range are
visible; for global deskew variants rotate only when the absolute angle is
0.5°–5°;
normalize contrast with grayscale p1–p99 percentile stretch. Record the
estimated/applied angle and pixel percentiles per page. Candidate deskew
triggers are absolute skew of at least 0.5°, 1.0°, or 1.5° respectively; never
rotate when the estimated angle exceeds 5°. Candidate contrast triggers are
p95–p5 grayscale range below the 25th or 50th percentile of the 299 OCR
development crops; use the same threshold for OCR, table, and layout inputs.
The transform itself remains p1–p99 stretch. This gives six predefined adaptive threshold
combinations. Use blur/edge strength as an error-analysis stratum, not as a
trigger or transform. Do not add deblurring. Inspect feature ranges on
development, freeze the candidate grid before validation, select thresholds
on validation only, and freeze the selected policy before any test inference. Store
transformed inputs separately with source hash, variant, parameters, and
per-page decision reason so every result is reproducible.

### Dataset, metrics, and selection

Use the existing fixed item IDs and issuer-level splits:

- OCR: 299 development, 100 validation, 101 locked-test crops. Report micro
  and macro CER/WER, output coverage, and paired deltas against V0.
- Tables: 89 development, 29 validation, 32 locked-test tables. Report found
  rate, cell-position accuracy, exact-shape, exact-grid, and row/column errors
  on each split. After blind human review of the 32 test grids and merged
  spans, report test-only GriTS-Top and GriTS-Con.
- Layout: 121 development, 39 validation, 40 locked-test pages. Report
  class-aware P/R/F1 at IoU 0.50 for title, text, table, and figure; keep
  the 14 enterprise signature boxes supplemental and formula outside this
  corpus score (the enterprise reference has no formula boxes). Use the
  separate HCMUS five-class benchmark only as formula transfer evidence.
- Reading order: retain the 100-page development diagnostic and add reviewer
  labels to the same layout validation/test pages. Report matched-block
  coverage and pairwise accuracy. Do not tune on test reading-order scores.
- Performance: rerun on the same 200 layout pages with three warmed repeats
  per variant. Report preprocessing time separately from model setup,
  inference, serialization, and total end-to-end time; report median/p95,
  pass throughput, sampled peak RSS, GPU-process memory, and device memory.

Use OCR micro-CER on the 100 validation crops as the primary endpoint. Report
micro-WER and macro CER/WER as co-reported OCR outcomes; do not hide a trade-off
by choosing only the best aggregate. Compare paired item-level deltas and
95% percentile cluster-bootstrap confidence intervals with 10,000 resamples
by issuer, resampling all items from an issuer together rather than individual
crops/pages. Report per-scan-quality strata and all pipeline failures/missing
outputs. Keep each task metric separate; do not
construct a weighted composite score.

Select V4 thresholds using validation only. Among V4 candidates that pass the
quality guardrails, choose the lowest micro-CER; break ties by lower micro-WER,
then lower end-to-end median latency, then fewer applied transforms. Prefer V4
if its validation OCR improves over V0 and the paired confidence interval
supports improvement,
while table, layout, and reading-order quality stay within these pre-registered
validation guardrails relative to V0: micro-CER delta ≤ +1.0 percentage point,
micro-WER delta ≤ +2.0 points, table cell-accuracy delta ≥ −2.0 points,
table-found rate remains 29/29, exact-shape loses at most one of 29 tables,
layout micro-F1 delta ≥ −0.02, each layout-class F1 delta ≥ −0.03, and
reading-order coverage and pairwise-accuracy deltas are each ≥ −0.02.
These are operational tolerances, not claims of statistical equivalence;
publish paired issuer-cluster confidence intervals alongside them. Because
validation chooses among six V4 threshold combinations, those validation
intervals are descriptive after selection, not confirmatory tests. Do not
change a margin after viewing validation variant scores. V1–V3 are
ablation controls; if one is the only variant meeting the OCR and guardrail
criteria, report it as the best fixed transform and state that the adaptive
hypothesis was unsupported. If no variant meets the criteria, report the
negative result and retain V0. If intervals overlap zero, describe the result
as inconclusive rather than a win. Compare resource cost for every
quality-passing variant and include preprocessing overhead in end-to-end cost.

### Test handling and claims

The existing locked-test aggregates have already been inspected for the
baseline, so they are not a pristine test set. Human-review the test references
blind to predictions, freeze the V4 policy using development/validation, and
run the five variants on test only once. Report this as a retrospective,
previously scored test comparison. Do not inspect per-item test errors during
tuning or adjust thresholds after test results. Any stronger confirmatory
thesis claim requires a new issuer/document-level test set that has not been
used for baseline review or tuning. If independent review or new labels are
unavailable, retain the explicit assistant-adjudicated caveat and make no
human-validated or pristine-test claim.

### Implementation sequence and outputs

1. Freeze MinerU/model/package/environment identifiers, source manifests,
   current baseline outputs, and the validation gate JSON.
2. Prepare blind review packages for the existing OCR/table/layout test
   references and add validation/test reading-order labels. Preserve a change
   log and do not show pipeline predictions to reviewers.
3. Implement deterministic V1–V4 transformations and a manifest that records
   eligibility, quality features, transform parameters, and decision reasons.
   Extend the existing `tables/reference/reference.jsonl` test records with
   reviewer-checked table HTML/spans for GriTS; extend the canonical reading
   order reference with reviewed validation/test annotations. Keep all variant
   outputs for this study under one `results/mineru-preprocessing/` run root.
4. Validate transformations visually on development pages, verify source PDF
   hashes remain unchanged, and verify V0 inputs are byte-identical to the
   existing benchmark inputs. Do not treat this as pipeline quality scoring.
5. Run all five variants on development; fix only execution/data issues and
   document any rerun. The shared scorer reuses the existing CER/WER, table
   cell/grid, layout IoU, and development reading-order metrics. Run metadata
   also captures preprocessing/inference wall time and one-second sampled
   process-tree RSS and GPU memory. Use development for threshold-grid
   preparation and exploratory diagnosis.
6. Run validation once for the predeclared candidate grid, compare all
   original metrics, choose/freeze one adaptive policy, and record the choice
   before accessing test outputs.
7. After freezing the policy, run the variants on existing test IDs once. Score
   OCR, tables, layout, and reading order; calculate GriTS-Top/Con only after
   reviewed table references are ready. Label all test results retrospective.
8. Publish a variant manifest, raw outputs, per-item metrics, paired
   confidence intervals, runtime/resource records, review provenance, and a
   report covering positive, null, and negative findings.

### Resume commands

Kaggle caps CPU/GPU notebook execution at 12 hours. V10 was canceled at that
limit; V11 is complete and its output and scores are archived. **Do not submit
V2–V4 yet.** First close the required shared follow-up metrics and revisit the
three-pipeline shortlist. If MinerU remains shortlisted and preprocessing is
still in scope, use the following commands for the preregistered variants,
with at most two variants per kernel version, then start the watcher:

```bash
uv run python tools/processing/build_mineru_preprocessing_kernel.py --variants V2,V3
kaggle kernels push -p artifacts/evaluation/document-pipelines/kernels/mineru-preprocessing
systemctl --user start kaggle-mineru-watch.timer
```

Then run the three V4 pairs using `--variants` values
`V4-skew0.5-contrast25,V4-skew0.5-contrast50`,
`V4-skew1-contrast25,V4-skew1-contrast50`, and
`V4-skew1.5-contrast25,V4-skew1.5-contrast50`. Each generated batch has 12
groups (two variants × three tracks × two splits). V0/V1 are already archived.
After all selected kernel versions are downloaded,
place their `V0/`, `V1/`, `V2/`, `V3/`, and six `V4-*` result directories
directly under one run root, then score without touching the locked test:

```bash
uv run python tools/processing/score_mineru_preprocessing_variants.py \
  --run-root artifacts/evaluation/document-pipelines/results/mineru-preprocessing/raw/mineru-preprocessing \
  --output artifacts/evaluation/document-pipelines/results/mineru-preprocessing/variant-scores.json
```

This run gives single-pass development/validation resource samples. After
validation selects and freezes a candidate, use the existing three-repeat
200-page performance runner for matched performance comparisons. Human review
files are in [`human-review/`](human-review/); do not include locked-test
inference or GriTS until those references are reviewed.

The frozen validation baselines for OCR, tables, and layout are in
[`results/tuning-baseline-validation.json`](results/tuning-baseline-validation.json).
The reading-order baseline is development-only until validation labels are
added. Existing pipeline performance results are in
[`results/layout-200-pages-v2/performance-rerun-20261015/`](results/layout-200-pages-v2/performance-rerun-20261015/).

### Preprocessing implementation note

The first visual pass found that the skew projection treated all pixels below
gray level 200 as foreground. On white text over a dark blue page (OCR-015),
this mistook the background for ink, estimated a false 5° skew, and rotated an
upright crop. The estimator now chooses foreground polarity from page
intensity, fills rotations from the border background color, and searches
±10° while applying corrections only through ±5°. OCR-015 now estimates 0°;
synthetic ±2° pages deskew to 0°, and a 7° page is left unrotated. The visual
checks are recorded as engineering validation, not OCR quality results. The
Kaggle runner now persists feature records keyed by input SHA-256. It seeds the
299 OCR development contrast features from the threshold pass, computes each
remaining feature/skew record once, and reuses those values across candidate
variants. Cached and uncached image outputs were checked for OCR-015 and
OCR-334; cached V1/V3/V4 pixel arrays matched exactly and did not call the skew
estimator again. The scorer filters reading-order annotations by layout split
and will not select a configuration until validation order labels exist; the
current canonical order reference contains only the 100 development pages.
