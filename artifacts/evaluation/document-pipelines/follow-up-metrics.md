# Follow-up Metrics from the Proposal

## Why this work follows the current comparison

The main benchmark already compares PP-StructureV3, MinerU Basic, and Docling
on the same OCR, table, full-page layout, reading-order, and performance tracks.
The recommendation to tune MinerU is an **intermediate research choice** based
on those shared development/validation results. It is not a production choice.

The metrics below are a separate backlog of capabilities the core comparison
does not cover. Their absence does not invalidate the existing comparison or
the completed V0/V1 MinerU CPU control. It does mean that production
selection must wait until the project decides which of these capabilities are
required and evaluates the applicable ones consistently. Do not compare a
tuned MinerU result against untuned competitors as if it were a matched final
pipeline comparison.

## Decision for the current MinerU run

The V11 CPU control completed 12/12 V0/V1 development and validation groups.
Its scores and limits are recorded in
[`cpu-v11-report.md`](results/mineru-preprocessing/cpu-v11-report.md). The
deskew arm does not show a consistent quality gain. These results keep the
paired CPU ablation useful but do not replace the frozen T4 baselines or decide
which parser should be used in production.

Tuning MinerU first was not wasted work, but it is only an **exploratory
preprocessing ablation**. It answers whether deskew/contrast transforms help
MinerU on the existing core metrics. It does not settle whether MinerU is the
best production parser, and it does not evaluate the follow-up capabilities.
Keep its V0/V1 results and any later variants under the MinerU track; do not
discard them or use them to claim a three-pipeline win.

There is no need to choose exactly two pipelines now. The existing baseline
already compares all three. The V0/V1 CPU control is complete; use the sequence
below, and shortlist parsers only after the required follow-up checks. Next,
compare **digital-born PDF parsing** across all three defaults. Separately
check **data cleaning** as a shared downstream quality gate; it must not rank
the parser engines. Reuse the same pilot outputs and expand only after the
references are reviewable. Formula layout detection already has a separate
HCMUS transfer benchmark; keep an enterprise formula score and formula OCR
recognition conditional on corpus inventory and product need. Keep figure
captions conditional on product need; exclude
caller-supplied metadata from parser ranking; keep chunking in its downstream
track.

After that shared comparison, shortlist one or two candidates. Continue
MinerU V2–V4 only if MinerU remains a candidate. To claim that tuning makes
MinerU better than a competing pipeline, give that comparator a comparable
tuning budget; otherwise report “best tuned MinerU configuration versus
default baselines.” Select on development/validation only. Existing locked-test
outputs have already been inspected, so any score on them is retrospective;
use a new issuer-held-out set for a confirmatory thesis claim.

This keeps the work already spent on MinerU useful while preventing its tuning
results from hiding the unmeasured capabilities or biasing the pipeline choice.

## Concrete next steps after the current run

The existing three-pipeline baseline is the comparison point; do not restart
the whole benchmark or rerun PP-StructureV3 and Docling just because MinerU was
tuned first. Finish and archive the current V0/V1 batch, then use this sequence
to decide what work is justified:

1. **Close V0/V1 as an execution control — complete.** All 12 groups completed
   with zero fallback items; predictions were downloaded, integrity-checked,
   and scored on development/validation. The run used Kaggle `None`/CPU, so
   report its runtime and memory only as CPU diagnostics. V0 differs from the
   saved T4 outputs and must not replace that baseline.
2. **Close the shared follow-up gaps across all three default pipelines.** First,
   review the native-text pilot references and source-type labels, then score
   the same eligible source-preserving PDFs through the saved default outputs
   for all three pipelines. Second, annotate valid/removable spans on the
   mixed-text cleaning candidates and evaluate the existing production
   deduplication/meaningfulness helpers once as a shared component. Also finish
   the missing validation/test reading-order references and prediction-blind
   review of locked-test labels; calculate GriTS only after table HTML and
   merged spans are reviewed. These are the currently in-scope gaps. Do not run
   full inference until each pilot review confirms its sample and scorer; reuse
   saved outputs wherever they contain the needed fields.
3. **Revisit the parser shortlist using matched evidence.** Combine all three
   default baselines with digital-born results and the required quality gates.
   The cleaning score does not rank parsers. Keep all three in the comparison
   until the evidence supports shortlisting one or two; there is no requirement
   to choose exactly two. Mark each other proposed metric as required,
   conditional, or deferred so “not evaluated” is not mistaken for a zero.
4. **Continue tuning only after the shortlist.** V1 is only the deskew arm; it
   cannot establish the best preprocessing variant. If MinerU remains on the
   shortlist and preprocessing is still in scope, run the preregistered V2–V4
   groups on development/validation and apply the existing validation
   selector. If another parser is preferred, stop MinerU tuning and tune that
   parser instead. For a tuned-versus-tuned claim, give the comparator a
   comparable tuning budget; otherwise label the result “tuned candidate
   versus default baselines.” Keep the already-viewed locked test retrospective
   and use a new issuer-held-out set for confirmatory claims.
5. **Run only product-required conditional tracks.** Metadata, figure captions,
   enterprise formula detection/OCR, and chunking are not blockers unless the
   product scope requires them. Formula detector transfer and formula-crop OCR
   already have separate academic/external results; they do not fill an
   enterprise metric gap. Record deferred metrics as “not evaluated,” not as
   zero or as evidence that a pipeline lacks the capability.

This sequence means the current MinerU work remains a useful within-pipeline
ablation, while the final pipeline choice still rests on all three existing
baselines plus the shared follow-up checks. No pipeline is selected for
production by completing V0/V1 alone.

## Execution order

1. **V0/V1 control batch — complete.** Its CPU scores and resource diagnostics
   are archived in the linked run report. Do not submit the remaining V2–V4
   tuning batches until the shared-metric gate below is complete and MinerU
   remains shortlisted.
2. **Set product scope for each follow-up area.** Mark it required, separate
   component, or deferred. In particular, semantic chunking is downstream of
   parsing and belongs in a separate chunking/embedding evaluation; it must not
   be used to rank parser pipelines.
3. **Inventory candidate data before setting sample counts.** Record source
   documents, pages/regions, issuer split, born-digital versus scanned status,
   and label availability. Freeze issuer-level development, validation, and
   test membership before running any pipeline. The current 200-page layout
   source set has at least 100 extractable PDF text characters on 190 pages
   (112 development, 39 validation, 39 locked test; 53 source PDFs), and no
   extractable text on 10. This is a text-layer candidate count, not proof that
   pages are born-digital or reviewed ground truth. The accepted layout
   reference has 231 figure boxes ([canonical labels](../../../data/evaluation/layout/vn-enterprise-layout-v2-adjudicated-reference.json));
   26 caption boxes occur only in `excluded_annotations`, so they are
   unaccepted candidates rather than caption references. Its 356 excluded
   annotations include 127 header/footer, 41 page-number, and 59 decoration
   boxes. These are region proposals, not text-span cleaning references. No
   formula class is present in accepted or excluded enterprise layout
   annotations. Formula layout detection is already benchmarked on the
   separate 916-page HCMUS dataset: five detectors share the same five-class
   evaluation, including formula; see
   [`formula-v2-report.md`](../layout/hcmus-results/formula-v2-report.md).
   The 25-page formula subset has 121 boxes, but it is Vietnamese academic
   content, so it is transfer evidence rather than an enterprise score. The
   259-crop formula OCR benchmark is another separate, camera-captured task;
   do not merge it with layout detection or enterprise OCR. Metadata
   references still need an inventory if automatic metadata extraction is in
   scope.
4. **Run a small pilot for each in-scope metric on the same source pages for
   all three pipelines.** Reuse the existing 20-page PP-StructureV3, MinerU
   Basic, and Docling outputs where their raw fields are sufficient. Rerun only
   when a required field was not retained. Check that normalizers/scorers
   handle real examples, and keep pilot results out of the final aggregate.
5. **Freeze references and metric definitions, then run the full comparison.**
   Use prediction-blind human review for labels that cannot be taken from a
   trustworthy source record. Preserve raw outputs, normalized outputs,
   per-item scores, split provenance, and unsupported-capability cases.
6. **Revisit the pipeline decision using the shared core results plus only the
   follow-up metrics declared required in step 2.** Shortlist one or two
   pipelines based on matched evidence. Only then resume V2–V4 if MinerU is
   shortlisted, or tune the selected alternative. Compare a tuned candidate to
   its frozen default baseline; identify any competitor left at default. Before
   making a confirmatory thesis claim, evaluate the frozen choice on a new
   issuer-held-out set because the current locked test has already been seen.

## Proposed priority for the production decision

Use this as a starting recommendation for the stated enterprise knowledge
assistant use case; confirm each item against actual ingestion requirements
before spending time labeling a full dataset.

| Priority | Area | Decision rule |
|---|---|---|
| Required before choosing a production parser | Digital-born PDF parsing | The current corpus includes PDFs with extractable text and pages without it. Measure both paths so the selected parser is not chosen only for scanned pages. |
| Separate metadata component; gate only if auto-extraction is required | Metadata extraction | Upload currently receives some context such as company and fiscal year from the caller. Do not count caller-supplied values as parser extraction. Compare parser-derived title, reporting period, page count, and source-page provenance only if the product needs them automatically. |
| Required for the production PDF flow; separate component | Data cleaning | Evaluate production OCR/native-text deduplication and trailing page-counter removal. Measure valid-content retention, false deletion, and residual duplicate/noise spans; do not use this component score to rank parser engines. |
| Separate transfer track, already benchmarked | Formula layout detection | Use the shared HCMUS five-class scores for research on formula-region detection; add enterprise labels only if formula regions occur in the enterprise corpus and must be detected. |
| Conditional component | Formula OCR recognition | Promote only if formula text must be searchable. Keep exact-string/symbol error metrics separate from box detection and the enterprise text CER/WER score. |
| Conditional | Image caption generation | Promote only if users need to retrieve facts from figures/images. If needed, test caption association/faithfulness as a shared downstream component when parsers do not produce captions. |
| Separate downstream track | Semantic segmentation / chunking | Evaluate after parser output is fixed, with fixed tokenizer and embedding settings. Do not use it to rank the parser engines. |

The initial corpus inventory supports feasibility but not final sample counts:
190 text-layer pages and 231 accepted figure regions are candidates. Do not
claim those counts as reviewed references. Freeze metric-specific sample sizes
after checking document availability and label effort in the pilot.

**Do not reuse the 200-page layout outputs as digital-born parsing results.**
The original source PDFs have at least 100 extractable text characters on 190
pages (112 development, 39 validation, 39 locked test), across 53 PDFs. But
[`prepare_document_pipeline_layout_inputs.py`](../../../tools/processing/prepare_document_pipeline_layout_inputs.py)
renders each source page to a 180-DPI JPEG and embeds that image in its
one-page PDF. A local check found zero extractable characters in all 200
packaged layout PDFs. Those pipeline outputs therefore evaluate image-based
processing only. A source-preserving candidate package is now prepared at
[`native-text-candidates-v1/`](results/follow-up-metrics/native-text-candidates-v1/)
with [`manifest.json`](results/follow-up-metrics/native-text-candidates-v1/manifest.json):
151 development/validation pages (112/39) from 41 PDFs and 40 issuers. Source
hashes were verified; each one-page PDF retains the source text layer. The
100-character rule identifies extractable-text candidates, not confirmed
born-digital pages or reviewed references. Do not run or score these as the
digital-born benchmark until the pilot source review validates the source-type
and reference process and a reviewable sample is selected. The package excludes
all 39 locked-test pages. Use a new issuer-held-out set for confirmatory
claims.

The existing common pilot already ran all three default pipelines on the same
20 PDFs and retained raw outputs; reuse those outputs for the first follow-up
pilot instead of paying for another inference pass. Its manifest marks 11 pages
as born-digital across four documents/issuers, six as physical scans, and three
as image-only. A local PyPDFium spot check reproduced substantial text on the
11 born-digital pages, but also returned 12 characters for one page labeled
image-only. Treat source-type labels as candidates and visually confirm them.
The pilot has no reviewed noise/valid-content span labels, so it can validate
the cleaning annotation and scoring format only after those spans are added;
it cannot yet produce a data-cleaning quality score.

An assistant visual spot-check of `vnm-fs-2011-vi-scan-diagnostic-p010` showed
that its only 12 extracted characters are `Tai-Lieu.com`, a footer watermark
on an otherwise image-only scanned financial statement. This supports keeping
it out of the digital-born candidate count, but the review packet still needs
an independent reviewer to confirm the label.

An assistant visual source-type check now covers all 20 pages in
`native-text-pilot-v2`, with source PDF text-layer character counts recorded in
[`digital-born-pilot-source-type-check.json`](results/follow-up-metrics/digital-born-pilot-source-type-check.json).
It confirms the packet split of 11 born-digital candidates, six physical scans,
and three image-only packaged PDFs. This check did not correct or verify the
native-text transcripts and is not human review; the updated 11-page CER/WER
proxy is recorded in [`digital-born-pilot-v1-proxy-report.md`](results/follow-up-metrics/digital-born-pilot-v1-proxy-report.md)
and remains invalid as a quality score. `image_only` describes the
packaged PDF's lack of a text layer, not the original page's production method.

The production cleaning scope is now pinned to the code path that runs during
PDF ingestion: [`PDFTextExtractor`](../../../src/core/document_processing/processors/pdf/text_extractor.py)
removes OCR fragments already represented by native PDF text, gates whether
OCR additions are meaningful, and removes a trailing page-counter footer. The
helpers are [`PDFOCRProcessor._remove_ocr_duplicates()` and
`_has_meaningful_ocr_additions()`](../../../src/core/document_processing/processors/pdf/scanned/ocr.py).
Evaluate those production operations as a shared component, not as a parser
ranking metric. Annotate valid and removable spans on mixed/native-plus-OCR
pages; report valid-content recall, false-deletion rate, residual-duplicate
rate, and residual-noise rate. Existing unit fixtures exercise a few examples
but are not a corpus-level reference set. The reproducible inventory at
[`cleaning-candidates-v1.json`](results/follow-up-metrics/cleaning-candidates-v1.json)
contains 77 development/validation page candidates (61/16) across 34 issuers.
It uses the production image-region and OCR-routing helpers, records candidate
image boxes, and contains no pipeline predictions; visual review must confirm
that the image regions actually contain relevant text before labels are made.
No development/validation source page in the current 200-page set has a
trailing text line matching the production page-counter-removal rule, so that
operation needs separate examples or must be reported as not evaluated. The
app's
`DocumentProcessor._clean_text`, called by `prepare_upload_test_output()` from
the Upload Test route, only normalizes line breaks, whitespace, NUL, and
nonbreaking spaces. It is not a substitute for this production evaluation.

The production-path extraction and cleaned output for all 77 candidates are
saved at
[`production-output.json`](results/follow-up-metrics/cleaning-pilot-v1/production-output.json).
A cleaner-output-blind 10-page rubric pilot is ready at
[`human-review/cleaning-pilot-v3/review.html`](human-review/cleaning-pilot-v3/review.html):
five development and five validation pages from distinct issuers, including the
only full-page OCR candidate. It shows source images, read-only native-text
context, and raw OCR spans, but omits the cleaned output. Classify each OCR span
as `new_valid`, `duplicate`, or `noise`. The score script is
[`evaluate_document_pipeline_cleaning.py`](../../../tools/processing/evaluate_document_pipeline_cleaning.py);
it supports a clearly labeled partial pilot and reports valid OCR addition
recall, false-deletion rate, and residual duplicate/noise separately by split.
An assistant-only visual diagnostic now covers all 10 pilot pages. It labels
139 duplicate spans, 174 noise spans, and 28 OCR-only valid spans; 76 duplicates
and 99 noise spans remain as exact occurrences. Exact retention is 26/28 spans
(472/505 characters). On the Bảo Long page, two logo/slogan spans appear in
transformed order/spacing in cleaned output, so the exact-match scorer counts
them as not retained without proving semantic deletion. These assistant labels
are diagnostic only and do not satisfy independent human review. Results and
limitations are in
[`cleaning-assistant-diagnostic-report.md`](results/follow-up-metrics/cleaning-assistant-diagnostic-report.md).
The review packet initially groups OCR by output line. Visual inspection of
the Techcombank chart page `LAYOUTV2-134` found lines that combine multiple
labels and numeric values, some garbled. The packet now supports **Split at
cursor**, preserving the OCR text while allowing each fragment to receive its
own class. If a reviewer still cannot assign a class reliably, leave the page
unchecked rather than force a label. After a reviewer completes the 10-page
pilot, create the full 77-page review from saved outputs; no OCR inference rerun
is needed. The current candidate inventory has zero trailing page-counter
examples, so that behavior remains not evaluated unless a separately sourced
set is added.

The native-text pilot scorer is saved at
[`evaluate_document_pipeline_native_text_pilot.py`](../../../tools/processing/evaluate_document_pipeline_native_text_pilot.py).
It was run against the 11 born-digital candidate pages and saved per-page output
at [`digital-born-pilot-v1-source-type-checked-proxy.json`](results/follow-up-metrics/digital-born-pilot-v1-source-type-checked-proxy.json).
All three pipelines returned text for all 11 born-digital pilot pages. The
source-only 11-page proxy remains invalid as an accuracy comparison: its text
layers have not all been checked, and HPG pages 3 and 5 have reading-order
mismatch. Separately, HPG page 6 was visually checked as a linear, single-column
page and scored from its unchanged text layer. This one-page assistant
diagnostic reports CER/WER of 19.18%/69.45% for PP-StructureV3, 3.50%/0.72%
for MinerU, and 0.31%/1.43% for Docling. It reuses saved outputs, but one page
from one issuer is not a model-selection result and assistant review is not
independent human review. The source-type check is recorded separately. Review
and correct the remaining transcripts and reading order before interpreting a
larger CER/WER score; score block order separately. Reproduce the original
source-text proxy with:

```bash
uv run --extra evaluation python tools/processing/evaluate_document_pipeline_native_text_pilot.py
```

A prediction-blind transcript review packet is ready at
[`human-review/native-text-pilot-v2/review.html`](human-review/native-text-pilot-v2/review.html).
It includes the 20 source page images and candidate PDF text only, with no
pipeline predictions. This v2 packet extracts candidate text with PyMuPDF,
matching the scorer and the project's declared PDF library; the older v1
PDFium packet is retained unchanged. An assistant checked source-type appearance
on all 20 pages, but an independent reviewer still needs to correct/confirm the
transcripts and reading order before a valid score. The packet can be regenerated
with `uv run python tools/processing/prepare_document_pipeline_native_text_review.py`.
After exporting its JSON, pass it to the scorer with
`--reviewed-reference <export.json>`; the scorer validates dataset/page IDs,
reviewer IDs, source-type values, and nonempty transcripts, then scores only
pages reviewed as `born_digital`. It reuses the saved pipeline output, so no
inference rerun is needed for this pilot. The reviewed run defaults to
`digital-born-pilot-v1-reviewed.json`, preserving the unreviewed proxy file.
The same scorer also accepts the source-preserving 151-page candidate manifest
and a matching review export; its output-root layout and command are documented
in [`native-text-candidates-v1/README.md`](results/follow-up-metrics/native-text-candidates-v1/README.md).
No candidates are eligible for a human-reviewed quality score until their
source types and transcripts are independently reviewed; saved pilot outputs
already exist for all three pipelines.

## Existing output capability inventory

The saved 200-page baseline outputs show what can be inspected without another
inference run. These are output counts/configuration checks, not accuracy
scores:

- **PP-StructureV3:** 200 page outputs have `use_formula_recognition: false`,
  so the current baseline cannot score formula recognition. It emits image and
  title-related blocks, but no reviewed figure-caption associations.
- **MinerU Basic:** the saved middle JSON contains 254 image blocks across 200
  pages. There is no separate formula block type in that output; this does not
  establish that formulas are unsupported, since formula text may be emitted
  as ordinary text.
- **Docling:** 399 picture elements across 200 pages; 39 have a caption
  reference in the serialized output. These associations still need visual
  validation against the source page and are not caption-generation scores.

The saved 20-page pilot also does not support a document-level metadata score.
PP-StructureV3's page outputs expose the input path and page index; MinerU's
19 successful outputs use the one-page input filename stem as `document.title`
and report `page_count: 1`; Docling's 20 outputs expose the one-page input
filename and binary hash and each contain one page. These are page-wrapper
provenance values, not independently extracted report title, fiscal period,
full-document page count, or original source-page provenance. A metadata
benchmark therefore needs full-document inputs and reviewed document-level
references if automatic metadata extraction is a product requirement.

Use these outputs to design the pilot. Rerun a pipeline only when a required
capability is disabled or its saved format does not contain the needed data.

## Metric work packages

| Area | Comparable evaluation | Data and labels needed | Scope rule |
|---|---|---|---|
| Digital-born parsing | Page/text coverage, block coverage, CER/WER against source text, and reading-order accuracy; report born-digital and scanned PDFs separately. | Inventory native text layers and review a stratified subset against rendered pages. Reuse the 200-page layout sources only where their original PDF text layer is trustworthy. | Compare all three parsers on identical PDFs. Office formats need separate references and a separate report. |
| Image caption generation | Figure-to-caption association accuracy and human-rated caption faithfulness/relevance; report figure-detection coverage separately. | Select real report figures and their source captions; human review each pairing and rating rubric. The existing figure boxes only identify candidates. | If a parser has no caption-generation output, report that capability as unsupported or evaluate a shared captioner separately; do not infer a score from figure boxes. |
| Formula layout detection | AP50 and fixed-threshold precision/recall/F1 on matched formula boxes. | Existing shared HCMUS five-class detector outputs and labels; new enterprise formula boxes only if required and observed. | Keep the academic transfer result separate from enterprise four-class layout metrics. |
| Formula OCR recognition | Normalized exact-match rate and symbol-level CER on linearized formula strings. | Existing 259 external camera-captured formula crops with author-checked LaTeX; enterprise formula crops and transcripts would be needed for an enterprise claim. | This measures transcription, not region detection or mathematical equivalence. Do not pool with prose CER/WER. |
| Metadata extraction | Field-level exact match / precision / recall / F1, plus source-page and coordinate correctness where a field is spatially grounded. | Freeze a schema of fields the parser is expected to derive (for example document title, reporting period, page count, and page provenance); create reviewed values with provenance. | Current upload context can include caller-provided company, fiscal year, source URL/type, and access roles. Exclude these from parser-extraction scores unless a pipeline derives them independently; evaluate input validation separately. |
| Production PDF data cleaning | Valid-content recall, false-deletion rate, residual-duplicate rate, and residual-noise rate at span level. | Annotate valid text and removable OCR/native-text duplicates or trailing page counters on mixed/native-plus-OCR pages. | Score the production `PDFTextExtractor` operations as a shared component; do not use this score to rank parsers. Upload Test whitespace normalization is a separate, simpler stage. |
| Semantic document segmentation / chunking | Boundary precision/recall/F1 with a declared tolerance, section continuity, token-limit compliance, and duplication rate. Retrieval impact is a later separate metric. | Reviewed section-boundary references and fixed tokenizer/embedding settings for any later retrieval experiment. | This is downstream of parser output. Evaluate chunkers in a separate track; do not use it as a parser-only score. |

## Current readiness

| Metric | Status now | Next action |
|---|---|---|
| Digital-born parsing | Source-type counts are assistant-checked (11 born-digital, 6 physical scans, 3 image-only). The 11-page source-text proxy remains invalid because transcripts/order are unchecked and HPG pages 3/5 are multi-column. HPG page 6 is separately visually checked and scored as a one-page assistant diagnostic; it is not human-reviewed or a pipeline-selection result. | Review the remaining pilot transcripts and reading order; score CER/WER on matched blocks or verified linear pages, and evaluate block order separately. Then reuse saved outputs if the sample/scorer are sufficient; otherwise run all three defaults on the confirmed common subset. |
| Production PDF cleaning | Production output exists for 77 candidate pages. A 10-page assistant visual diagnostic labels 139 duplicate spans, 174 noise spans, and 28 OCR-only spans. It found 76 residual duplicates and 99 residual noise spans; 26/28 OCR-only spans (472/505 characters) remain as exact text. The two non-exact Bảo Long logo/slogan spans appear transformed/reordered in cleaned output, so exact-span loss does not prove semantic deletion. Labels are assistant-adjudicated, not human-reviewed. See [`cleaning-assistant-diagnostic-report.md`](results/follow-up-metrics/cleaning-assistant-diagnostic-report.md). | Complete prediction-blind review of the 10-page pilot, including legitimate OCR-only text, then score with `--allow-partial-review`. If labels and metric behavior are acceptable, review the full 77-page set. Page-counter removal remains unmeasured because the current candidates have no examples. |
| Reading order | Scored on 100 development pages only; validation/test labels are still blank. | Review and label the 39 validation plus 40 locked-test pages, then run the evaluator for each pipeline. |
| Locked-test OCR, table, and layout review | Prediction-blind packets exist, but no reviewed exports have been supplied. | Review references before calling them human-reviewed; calculate GriTS only after all 32 table HTML grids and spans are checked. |
| Formula layout / formula OCR | HCMUS transfer and external formula-crop benchmarks exist; neither is an enterprise-document score. | Defer enterprise labels unless formula content is found and required in the production corpus. |
| Captions / metadata | Not evaluated; current saved outputs do not support comparable document-level scores. | Defer unless the product requires these extraction features. |
| Chunking | Outside parser selection and not part of this pipeline comparison. | Evaluate later as a separate chunking/embedding study. |

Do not interpret a prepared packet, output, or scorer as a completed metric. A
metric moves to complete only after its reference is reviewed, scoring runs
against all required examples, and the result is recorded with its limitations.

## Reporting rules

- Do not combine these areas or the existing core tracks into one weighted
  score. Publish per-metric results and the supported/unsupported status.
- Use the same documents, pages, references, and splits for every pipeline in
  any direct comparison. If a capability is only available through a distinct
  downstream model, report a component comparison rather than attributing it
  to the document parser.
- Do not use locked-test errors to change transforms, thresholds, schemas, or
  scoring rules. The previously viewed test split remains retrospective; a
  new held-out issuer set is needed for confirmatory final claims.
- Keep the current core benchmark report as the source of existing results;
  this file records follow-up scope and readiness, not completed scores.
