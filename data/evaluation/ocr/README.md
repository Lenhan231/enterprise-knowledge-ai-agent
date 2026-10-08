# OCR fixtures

`commerce_synthetic_policy_scan_demo.pdf` is an image-only, two-page synthetic fixture for OCR Lab and upload-path evaluation. Its visible warnings mark it as test-only; its prose and logistics table values are invented. It is not an official policy, must not be indexed into the Commerce knowledge base, and must not be used as business evidence.

`commerce_scan_ground_truth.json` contains a visual transcription of both rendered pages, including the three sample table rows. Run `uv run python tools/processing/evaluate_ocr.py --engines tesseract --output artifacts/evaluation/ocr/commerce-scan-ocr-smoke.json` to compare the local OCR output against the fixture. This checks that the evaluator, page rendering, text OCR, and table-anchor scoring work end to end; it is not an OCR engine benchmark or a production quality claim.

`commerce_synthetic_degraded_scan_demo.pdf` is a deterministic, image-only scan simulation derived from the same invented pages. It adds grayscale, mild page skew, low contrast, light blur, seeded speckles, and JPEG artifacts; it is still not a physical scan or company document. Regenerate it with `uv run python tools/processing/generate_commerce_scan_fixture.py`. Its visual transcription labels are in `commerce_degraded_scan_ground_truth.json`. This second fixture checks whether mild skew/noise breaks the OCR table path without changing source content or adding invented business evidence to RAG.

Run `uv run python tools/processing/evaluate_scan_document_processing.py --output artifacts/evaluation/ocr/pipeline/commerce-scan-parser-smoke.json` to exercise the same `DocumentProcessor` path used for PDF uploads. Its CER/WER compare the source text chunks only; generated structured-table serialization is excluded and table rows/numeric cells are scored separately. If a structured table chunk replaced its source text chunk, that page is marked unscored for CER/WER instead of reporting a misleading text error rate. The clean fixture currently recovers its prose and all 3 table rows / 9 numeric cells exactly; that result validates only this synthetic smoke fixture.

A sequential strict-scoring replay on 2026-10-08 recovered both clean synthetic pages with 0 CER/WER, all 3 table rows, 9/9 values, and 3/3 headers at 3.255 seconds per page ([report](../../../artifacts/evaluation/ocr/pipeline/commerce-synthetic-clean-scan-current-after-quality-guard-20261008.json)). Prose is scored against a prose-only reference; table headers, rows, and numeric cells are scored independently so table content is not counted as missing OCR text. Numeric cells contaminated by extra action text fail the exact-value check; passing rows, cells, and headers is required for the table anchor quality gate. This scan simulation tests parser behavior only and must not be presented as physical-scan accuracy.

The degraded fixture's latest upload-path replay (2026-10-07) used Tesseract 5.5.3, page PSM 11 at 1.5× and table PSM 3 at 2.5×. It scored micro CER 0.000831 / WER 0.010309 (mean 2.584 seconds/page), matched 3/3 table anchor rows and 9/9 numeric cells, and extracted the table title. Raw OCR matched 3/4 header strings; the structured output contains all four expected fields, with `Region` represented by the row-label column. The replay is saved [here](../../../artifacts/evaluation/ocr/pipeline/commerce-degraded-scan-current-20261007.json). The earlier 2026-10-05 run was exact on text and remains available as a historical artifact ([run](../../../artifacts/evaluation/ocr/pipeline/commerce-degraded-scan-v2-20261005.json)). Reproduce the latest settings with `uv run --frozen python tools/processing/evaluate_scan_document_processing.py --dataset data/evaluation/ocr/commerce_degraded_scan_ground_truth.json --all-pages --output /tmp/commerce-degraded-scan-current.json`. The evaluator supports semantic first-column labels such as `Region`, not only `label`. A live Tester API upload separately produced two persisted page previews, three parser chunks and one structured table with those headers and rows ([artifact](../../../artifacts/evaluation/ocr/pipeline/commerce-degraded-scan-upload-live-20261005.json)); both previews returned HTTP 200 `image/png`. The run is isolated in OCR test tables, not indexed in RAG. This remains a small synthetic robustness check, not evidence of real-document accuracy.

A sequential production-parser replay on 2026-10-08 against the same degraded fixture scored 0 CER/WER on both pages, 3/3 anchor rows, and 9/9 numeric cells at 4.016 seconds per page ([current run](../../../artifacts/evaluation/ocr/pipeline/commerce-degraded-scan-current-20261008.json)). It uses the declared English OCR setting and the same PDF upload parser, but remains a cleanly authored synthetic scan simulation, not a physical scan or engine-selection result. Reproduce with the command above and change the output path.

On 2026-10-08, PDF parsing began honoring configured `ocr_language` values; the evaluator maps English cases to `eng` and Vietnamese cases to `vie+eng`, and records the per-case setting. The clean and degraded English fixtures scored 0 CER/WER and 9/9 exact numeric cells each ([clean](../../../artifacts/evaluation/ocr/pipeline/commerce-english-scan-current-20261008.json), [degraded](../../../artifacts/evaluation/ocr/pipeline/commerce-english-degraded-scan-current-20261008.json)). The web upload path still uses its bilingual default. These exact scores are on authored synthetic references only; the real-source Sam's Club screenshot row remains incomplete at 3/6 numeric cells with 3.5× rendering ([run](../../../artifacts/evaluation/ocr/pipeline/commerce-sams-grid-english-3.5x-20261008.json)). The unmodified Sam's PDF page has 862 native-text characters and an embedded image covering 20.2% of its area. Mixed-page processing now checks that image, but Tesseract's mean word confidence on its crop is only 26.3/100, so the 60/100 gate rejects it; a fresh `DocumentProcessor` run retained one native PyMuPDF chunk and emitted no OCR chunk or structured table. This is safe abstention, not successful extraction. The 3/6 screenshot-crop result above remains incomplete, and a forced full-page OCR run also produced no structured table.

A clean synthetic mixed page verifies that embedded-image table OCR is appended without losing native text and yields all three labeled rows. A companion regression injects low-confidence word boxes and verifies the OCR text/table are omitted while the parser retains a page diagnostic. On the real Sam's page, the current parser records a 26.3/100 mean-confidence rejection and preserves the native text chunk; Admin Processing and OCR Lab surface the reason. Confidence is a heuristic gate: it rejects this crop, but does not establish accuracy across other scans or languages.

The current clean fixture was also checked through the live Tester endpoints using the persisted two-page run. Both stored page previews returned HTTP 200 `image/png`; the run contains three chunks and one structured table with three rows. The Tester role receives HTTP 403 from the production dashboard route. These results are recorded in [the live API check](../../../artifacts/evaluation/ocr/pipeline/commerce-synthetic-policy-scan-tester-live-20261007.json). This verifies API and database persistence for this test-only fixture, not the rendered browser page or OCR accuracy on a real business scan.

A fresh OCR Lab API run on 2026-10-08 persisted run `8e69d764-70d5-4e28-89da-5fae5970283e`: 2 pages, 3 chunks, 1 structured table, with the page-2 preview returning HTTP 200 `image/png`. Readback confirmed the text chunk retains the synthetic-scope warning while excluding the noisy table transcription; the structured row keeps `Median transit days = 3.0`. This verifies the updated parser and persisted output through Tester APIs; it is still a synthetic scan simulation, not a browser recheck or real-scan accuracy result.

On 2026-10-07 an Admin uploaded the degraded fixture through the OCR Lab browser UI. The saved isolated run showed two page previews (992×1404), three chunks, and one structured table with three rows. At desktop width, each expanded page places the raw preview beside extracted output; text chunks remain collapsible above tables. Below 900 px the two sections stack, and a 500 px Firefox viewport had no document-wide horizontal overflow (488 px document width). This validates the UI and isolated OCR persistence for the synthetic fixture, not production-document accuracy.

The same degraded PDF was also uploaded through Admin's normal **Upload Documents** flow with `EMBEDDING_BACKEND=local` on 2026-10-07. The UI returned `ready` for both pages, with 3 parser passages, 3 indexed passages, 3 OCR passages, and 1 extracted table; the parser preview showed Tesseract output and the structured table. A read-back confirmed those counts in Supabase. The upload was then made inactive in Knowledge Management, so it cannot be retrieved; its test row remains for inspection and is restricted to `admin`. The already-cached multilingual MiniLM model embedded the passages locally (a separate cold-process probe used about 1.5 GiB RSS and 7 seconds for the first vector), avoiding the exhausted Hugging Face Inference API quota. This verifies the actual Admin upload → OCR/parser → local embedding → database → UI path for this generated fixture. It does not establish real-scan OCR quality or policy-answer quality, and the fixture must remain inactive because its content is invented.

The upload parser now runs Tesseract OSD on pages selected for OCR. A two-page
generated regression rotates the first page 90° and splits one table across
both pages. It verifies correction recovers the first segment, links both
segments, inherits the title, and keeps page-local rows and bounding boxes.
Companion tests verify standalone rotation, upright-page behavior, and all
quarter-turn coordinate transforms. Reproduce with
`uv run --frozen python -m unittest tests.test_pdf_upload_processing`.
The Tester HTTP upload route is also exercised with the real parser and an
isolated mocked repository:
`uv run --frozen python -m unittest tests.test_app_request_models.AskRequestTest.test_ocr_lab_http_upload_persists_rotated_scan_parser_output_outside_corpus`.
That verifies request-to-parser-to-save payload wiring, not a live Supabase
write or browser interaction.
These generated checks are not a physical scan benchmark; OSD does not correct
arbitrary angles; the deskew check is limited to small skew in synthetic
fixtures. A uniquely matching page-edge table continuation inherits its
title and keeps both page-local row sets and source links. Ambiguous or
column-mismatched segments are left unlinked; the parser does not merge them
into one structured record. Orientation detection adds one Tesseract process
call per scanned page; sparse landscape pages can trigger up to two short
rotation retries.

### Real-source screenshot table check

[`commerce_sams_inventory_grid_anchors.json`](commerce_sams_inventory_grid_anchors.json)
labels one visible row in the embedded inventory-grid screenshot on page 7 of
the active [Sam's Club Supplier Hub guide](../../commerce_knowledge/manifest.json).
The PDF is born-digital and the screenshot is low-resolution; this is not a
physical scan or a Commerce policy. The crop is rasterized before upload-parser
OCR, and the one row was transcribed visually by a single AI agent without
independent human review. At the
current table scale (2.5×), the parser matched 0/1 rows and 0/6 numeric cells.
At 3.5× it matched the KETER label and its three item identifiers (1/1 rows,
3/6 cells), but missed the three stock-quantity values and all seven source
column headers. This is evidence of a current screenshot-table limitation, not
a general setting comparison; production defaults remain unchanged. The
artifacts preserve both runs. Exploratory table PSM 4, 11, and 12 each recovered
only two of the six numeric cells at 3.5×. Grayscale/contrast changes retained
the same three identifiers; hard thresholding did not recover the missing
quantities or headers. Using English-only Tesseract instead of the configured
Vietnamese/English language set produced the same three identifiers. These
alternatives do not justify changing production settings. The evaluator accepts
3.5× to match the OCR Lab controls. Reproduce after fetching the registered source:

```bash
PYTHONPATH=src uv run python tools/ingestion/ingest_commerce_knowledge.py \
  --download-only --ids SAMS-SUPPLIER-HUB-USER-GUIDE-2022
uv run python tools/processing/evaluate_scan_document_processing.py \
  --dataset data/evaluation/ocr/commerce_sams_inventory_grid_anchors.json \
  --case-id SAMS-SUPPLIER-HUB-2022-PAGE-7-INVENTORY-GRID-KETER \
  --output /tmp/sams-inventory-grid-default.json
uv run python tools/processing/evaluate_scan_document_processing.py \
  --dataset data/evaluation/ocr/commerce_sams_inventory_grid_anchors.json \
  --case-id SAMS-SUPPLIER-HUB-2022-PAGE-7-INVENTORY-GRID-KETER \
  --table-render-scale 3.5 --output /tmp/sams-inventory-grid-3.5x.json
```

On 2026-10-08, the same crop was rerun with English OCR and table PSM 3, 4, 6, 11, and 12 at 3.5×. PSM 3 remained best at 3/6 numeric cells; PSM 4, 6, 11, and 12 each matched at most 2/6, so no tested setting recovers the three visible stock-quantity zeros or the source headers. This confirms that changing Tesseract PSM or language is not the next useful fix; improve full-table image/layout handling before considering a production setting change. A raw TSV check on the same crop found no standalone `0` tokens, while OCR on isolated, 8× enlarged crops of the three visible KETER stock cells read `0`, `0`, and `0`. Isolated-cell OCR is diagnostic only and is not implemented in the upload pipeline.

The optional PP-StructureV3 path was also run on this one-page crop after its missing `paddlex[ocr]` dependency was added to the `ocr-paddle` extra. With chart recognition disabled and CPU oneDNN disabled, inference completed in 44.34 seconds at 2,387 MiB peak RSS, but returned one flattened paragraph and no structured table. Enabling chart recognition first loaded the 1.4 GiB PP-Chart2Table weights and the process was killed (exit 137); chart recognition is now opt-in. This result does not justify using Paddle for Commerce uploads yet; it is a single low-resolution screenshot, not a model comparison or physical-scan result.

A separate same-crop raw-engine smoke run compared EasyOCR and Tesseract at
180 DPI. Neither recovered the complete row; EasyOCR matched 3/7 cell strings
and Tesseract 1/7, with no row-exact match ([report](../../../artifacts/evaluation/ocr/pipeline/commerce-sams-inventory-grid-engines-180dpi-20261007.json)).
These cell counts ignore row/column association and are not comparable to the
upload parser's structured-table result. The dataset has no full-text reference,
so CER/WER are intentionally unavailable; a successful CLI exit means the
table anchors were scored, not that the OCR quality passed. The row labels and
the screenshot itself still lack independent human review.

### Mixed-content page in a public Commerce source

The [Shopee Uni Vietnam inventory guide](https://cdngarenanow-a.akamaihd.net/shopee/seller/seller_cms/acf62e028643871447fd5886ed466a10/Qu%E1%BA%A3n%20L%C3%BD%20T%E1%BB%93n%20Kho.pdf) is an active, attributed inventory reference in the corpus. PDF page 11 (printed page 9) is a mixed PowerPoint export with embedded screenshot images and vector text, not a physical scan. To ensure the selected screenshot phrases are evaluated by OCR, the page is rasterized before the production parser runs. On four manually reviewed phrase anchors, Tesseract recovered 4/4 with PSM 11 at 1.5× (1.764 s) and PSM 3 at 1.5× (5.022 s), 2/4 with PSM 6 at 1.5× (5.249 s), and 3/4 with PSM 11 at 2.5× (2.439 s). PSM 11 at 1.5× is fastest among the settings with full anchor recall; keep the upload default unchanged because one historical platform-specific page is not a general-accuracy benchmark ([dataset](commerce_shopee_inventory_page_anchors.json), [comparison](../../../artifacts/evaluation/ocr/pipeline/shopee-page11-rasterized-tesseract-settings-20261007.json)).

A separate [selected-region transcription](commerce_shopee_inventory_page_transcriptions.json) manually transcribes the heading/instruction and replenishment callouts from the rendered page. The OCR evaluator rasterizes these crops first, because the source PDF retains vector text in those regions. Under the current upload settings (page PSM 11 at 1.5×; table PSM 3 at 2.5×), the two crops scored micro-CER 0.015873 and micro-WER 0.041096 in 0.943 seconds per crop ([run](../../../artifacts/evaluation/ocr/pipeline/shopee-page11-selected-region-ocr-20261007.json)). This is a single-reviewer transcription of two clear text regions; the screenshot remains separately scored by anchors, and this does not validate physical scans or justify a global OCR setting change. Reproduce the two-region run after downloading the manifest corpus with:

```bash
PYTHONPATH=src .venv/bin/python tools/ingestion/ingest_commerce_knowledge.py --download-only
PYTHONPATH=src .venv/bin/python tools/processing/evaluate_scan_document_processing.py \
  --dataset data/evaluation/ocr/commerce_shopee_inventory_page_transcriptions.json \
  --case-id SHOPEE-UNI-INVENTORY-MANAGEMENT-VN-PDF-PAGE-11-HEADING \
  --case-id SHOPEE-UNI-INVENTORY-MANAGEMENT-VN-PDF-PAGE-11-STATUS-CALLOUTS \
  --output /tmp/shopee-page11-selected-region-ocr.json
```

The same five Shopee image-only/selected-region labels now run through the model-comparison evaluator and Kaggle bundle without being mistaken for a synthetic ground-truth set. Both engines used the same five 180-DPI raster crops:

| Engine | Runtime | Micro-CER / WER | Mean OCR time/crop | Model init | Peak host RSS, process / child (MiB) | PyTorch GPU allocated / reserved (MiB) |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| Tesseract 5.5.3, PSM 3 | Local CPU | 0.019802 / 0.052632 | 0.817 s | N/A | 554.5 / 554.5 | N/A |
| PaddleOCR 3.7.0 | Kaggle CPU | 0.128713 / 0.526316 | 12.200 s | 48.429 s | 2,506.4 / 2,506.4 | N/A |
| EasyOCR 1.7.2 | Kaggle Tesla T4 | 0.022277 / 0.063158 | 0.772 s | 10.738 s | 1,495.0 / 1,495.0 | 1,139.5 / 1,404.0 |
| Surya 0.17.1 | Kaggle Tesla T4 | 0.027228 / 0.063158 | 2.956 s | 56.051 s | 4,385.6 / 1,239.3 | 1,768.6 / 1,846.0 |

Tesseract read the three image-only slide headings exactly; PaddleOCR scored worst across the five crops. EasyOCR and Surya had slightly higher overall CER/WER than Tesseract; each GPU engine made some different page-level errors. Surya used the most peak process and allocator-reported GPU memory. PyTorch allocator telemetry does not include non-PyTorch engine allocations, and mean OCR time excludes model initialization. Hardware, runtime and memory are descriptive, not a controlled performance comparison. These are single-reviewer labels explicitly ineligible for primary model selection; use the results as exploratory real-source comparisons until a second reviewer adjudicates the text. Reports: [Tesseract](../../../artifacts/evaluation/ocr/pipeline/shopee-inventory-exploratory-tesseract-20261008.json), [PaddleOCR](../../../artifacts/evaluation/ocr/pipeline/shopee-inventory-exploratory-paddleocr-20261008.json), [EasyOCR](../../../artifacts/evaluation/ocr/pipeline/shopee-inventory-exploratory-easyocr-20261008.json), [Surya](../../../artifacts/evaluation/ocr/pipeline/shopee-inventory-exploratory-surya-20261008.json). Reproduce Tesseract with `uv run --frozen python tools/processing/evaluate_ocr.py --dataset data/evaluation/ocr/commerce_shopee_inventory_page_transcriptions.json --engines tesseract --dpi 180 --tesseract-psm 3 --output /tmp/shopee-ocr.json`. `package_ocr_benchmark.py --dataset ...page_transcriptions.json` creates the private Kaggle bundle; source PDF checksums are verified from each page label.

That same official PDF contains image-only slide pages 3, 5, and 13 with no
extractable text layer. Their full-page Vietnamese headings were visually
transcribed into the same dataset and sent through the production `DocumentProcessor`
without adding a hidden text layer. Tesseract recovered each exactly (CER/WER
0.0; mean 2.429 seconds/page) ([run](../../../artifacts/evaluation/ocr/pipeline/shopee-inventory-image-only-pages-ocr-20261007.json)). These three
simple title pages are evidence that the real-source upload parser invokes OCR
on raster-only PDF pages; the references are single-reviewer, the PDF was
exported from PowerPoint, and none is a physical scan. Reproduce with:

```bash
PYTHONPATH=src .venv/bin/python tools/ingestion/ingest_commerce_knowledge.py --download-only --ids SHOPEE-UNI-INVENTORY-MANAGEMENT-VN
PYTHONPATH=src .venv/bin/python tools/processing/evaluate_scan_document_processing.py \
  --dataset data/evaluation/ocr/commerce_shopee_inventory_page_transcriptions.json \
  --case-id SHOPEE-UNI-INVENTORY-MANAGEMENT-VN-PDF-PAGE-3-TITLE \
  --case-id SHOPEE-UNI-INVENTORY-MANAGEMENT-VN-PDF-PAGE-5-TITLE \
  --case-id SHOPEE-UNI-INVENTORY-MANAGEMENT-VN-PDF-PAGE-13-TITLE \
  --output /tmp/shopee-inventory-image-only-pages.json
```

Reproduce the separate screenshot-anchor tuning check with:

```bash
PYTHONPATH=src .venv/bin/python tools/ingestion/ingest_commerce_knowledge.py --download-only
PYTHONPATH=src .venv/bin/python tools/processing/evaluate_scan_document_processing.py \
  --dataset data/evaluation/ocr/commerce_shopee_inventory_page_anchors.json \
  --case-id SHOPEE-UNI-INVENTORY-MANAGEMENT-VN-PDF-PAGE-11 \
  --output /tmp/shopee-inventory-page11-ocr.json
```

The guide is historical and applies only to Shopee sellers; it is not policy for the synthetic Commerce dataset. The score measures only four selected phrases on this one page; the screenshot and full-page transcription have not been independently reviewed.

The same page's embedded inventory grid now has a separate exploratory table
label set for its two visible product rows ([labels](commerce_shopee_inventory_grid_anchors.json),
[current parser run](../../../artifacts/evaluation/ocr/pipeline/shopee-inventory-grid-anchor-current-after-quality-guard-20261008.json)).
At upload defaults, the parser returned no structured table: 0/2 row labels and
0/12 visible cells matched; only 1/4 selected raw-text anchors matched. A
3.5x page render with PSM 6 recovered all four selected raw-text anchors but
an experimental two-row parser produced a table-shaped object but failed its
structure check: 0/7 exact headers and 10/12 exact cell values. In both rows,
the action label “Sửa” was joined to the final numeric cell; the previous scorer
incorrectly counted these contaminated cells as exact. The parser's two-row
fallback was removed, and the evaluator now rejects text-contaminated numeric
cells and reports header recall plus a combined anchor-quality gate
([rescored rejected run](../../../artifacts/evaluation/ocr/pipeline/shopee-inventory-grid-anchor-35x-p6-table6-rejected-20261008.json)).
A small table-PSM sweep (3, 4, 6, 11, 12) at both 2.5x and 3.5x returned no
structured tables. This separates OCR text recovery from table reconstruction:
readable cells are not yet row/column structure. It is not a physical scan
benchmark, and the labels remain single-reviewer and unadjudicated. Reproduce
the default run with:

```bash
uv run python tools/processing/evaluate_scan_document_processing.py \
  --dataset data/evaluation/ocr/commerce_shopee_inventory_grid_anchors.json \
  --case-id SHOPEE-UNI-INVENTORY-MANAGEMENT-VN-PDF-PAGE-11-GRID \
  --output /tmp/shopee-inventory-grid-current.json
```

### Image-heavy inventory guide pages

The official [Amazon FBA Restock Tool Guide](https://m.media-amazon.com/images/G/01/sell/pdf/FBA-Restock-Guide-EN.pdf) provides an attributed inventory-replenishment example. Pages 6–7 were rasterized to remove the PDF's partial text layer and run through the production `DocumentProcessor` with the upload defaults (Tesseract PSM 11, 1.5×; English). It recovered all 9 selected phrase anchors (3/3 on the process infographic and 6/6 on the Seller Central workflow screenshot) at 2.811 seconds per page ([labels](commerce_amazon_fba_restock_page_anchors.json), [run](../../../artifacts/evaluation/ocr/pipeline/amazon-fba-restock-selected-page-upload-smoke-20261008.json)). CER/WER are unavailable because these are partial anchor labels, not full-page transcription. A later default-parser rerun retained 3/3 native-text anchors on page 6 and 6/6 OCR anchors on page 7; a new mixed-page novelty gate suppressed low-value screen OCR on page 6. Native-layer duplicates remain, and neither page yielded a structured table. This is a selected-region check on an image-heavy PDF, not a physical-scan benchmark, full-page quality score, or evidence that Amazon's settings apply to the synthetic Commerce business. Reproduce after downloading the active manifest source:

```bash
PYTHONPATH=src .venv/bin/python tools/ingestion/ingest_commerce_knowledge.py \
  --download-only --ids AMAZON-FBA-RESTOCK-TOOL-GUIDE-2020
PYTHONPATH=src .venv/bin/python tools/processing/evaluate_scan_document_processing.py \
  --dataset data/evaluation/ocr/commerce_amazon_fba_restock_page_anchors.json \
  --case-id AMAZON-FBA-RESTOCK-TOOL-GUIDE-2020-PAGE-6 \
  --case-id AMAZON-FBA-RESTOCK-TOOL-GUIDE-2020-PAGE-7 \
  --output /tmp/amazon-fba-restock-selected-page-upload-smoke.json
```

## OCR engine comparison: active Commerce policy PDFs

Four engines were run separately on Kaggle against the same 9 pages from
`commerce_policy_scan_ground_truth.json`, rendered at 180 DPI. The reports
record source-PDF and rendered-page hashes; the paired comparison rejects runs
whose inputs differ. The retained reports are [Tesseract](../../../artifacts/evaluation/ocr/comparisons/commerce-active-policy-scan-20261005/commerce-ocr-commerce-policy-scan-v1-tesseract.json), [PaddleOCR](../../../artifacts/evaluation/ocr/comparisons/commerce-active-policy-scan-20261005/commerce-ocr-commerce-policy-scan-v1-paddleocr.json), [EasyOCR](../../../artifacts/evaluation/ocr/comparisons/commerce-active-policy-scan-20261005/commerce-ocr-commerce-policy-scan-v1-easyocr.json), [Surya](../../../artifacts/evaluation/ocr/comparisons/commerce-active-policy-scan-20261005/commerce-ocr-commerce-policy-scan-v1-surya.json), and the [paired comparison](../../../artifacts/evaluation/ocr/comparisons/commerce-active-policy-scan-20261005/comparison.json). Re-run the notebook to reproduce them; the nine pages are synthetic image-only policies, so this is a smoke comparison rather than a representative scan benchmark.

| Engine | Version / device | micro-CER | micro-WER | Mean sec/page | Peak process RSS |
| --- | --- | ---: | ---: | ---: | ---: |
| Tesseract (PSM 11) | 5.3.4 / CPU | 0.003672 | 0.014768 | 1.502 | 471 MB |
| PaddleOCR | 3.7.0 / CPU | 0.088340 | 0.417194 | 48.625 | 3,810 MB |
| EasyOCR | 1.7.2 / Tesla T4 | 0.002225 | 0.016878 | 2.131 | 1,786 MB |
| Surya | 0.17.1 / Tesla T4 | 0.003560 | 0.008439 | 3.557 | 4,596 MB |

On this fixture, EasyOCR has the lowest CER, Surya the lowest WER, and Tesseract the lowest latency and memory use. These results do not identify a universal winner: the 9 pages are synthetic image-only policies, their text references came from authored HTML and were not independently human-reviewed, Tesseract/PaddleOCR ran on CPU while EasyOCR/Surya ran on a Tesla T4, and this set has no tables. It is a smoke comparison of these implementations, not representative scan accuracy or proof that the UI's upload processor should change engines. Validate labels with human transcription and add real, permissioned skewed/noisy/cropped/table scans before a production engine decision.

The current checked-in policy PDFs and labels were updated after that comparison: the old and current dataset/source hashes differ. A local OCR-only replay using the upload parser's page scale (1.5× / 108 DPI) and PSM 11 is recorded [here](../../../artifacts/evaluation/ocr/pipeline/commerce-policy-ocr-production-config-20261008.json). Tesseract 5.5.3 scored micro-CER 0.060520 and micro-WER 0.075028 over all 9 pages (2.572 sec/page). At 2× / 144 DPI, CER changed only to 0.060285 while latency rose to 2.935 sec/page; this small, authored fixture does not justify changing the default. PSM 6 at the same 108 DPI scored micro-CER 0.065112 and micro-WER 0.087906, worse than PSM 11 (report: [PSM 6](../../../artifacts/evaluation/ocr/pipeline/commerce-policy-ocr-psm6-108dpi-20261008.json)); keep PSM 11 for this tested corpus. These are OCR-engine text scores, not the full upload processor score. The references remain authored HTML, not independently reviewed, and the PDFs are rasterized simulations rather than physical scans. Reproduce each Kaggle engine run with [`kaggle_ocr_benchmark.ipynb`](../../../notebooks/kaggle_ocr_benchmark.ipynb); set `ENGINE` and `REQUIRE_GPU` for one run per kernel.

### Focused Tesseract check on inventory-policy page 2

The current active PDF's page 2 is scan-only. A fresh parser read surfaced two
diacritic/character errors in “chi phí vận chuyển” and “dịch vụ”. On this one
page, PSM 11 at 1.5× scored CER 0.001663 / WER 0.007692; PSM 11 at 2.5× fixed
those two phrases but scored worse overall (CER 0.003325 / WER 0.011538).
PSM 6 scored worse than the existing configuration. Keep the upload default at
PSM 11 / 1.5×; a single authored-text synthetic page is too narrow to justify
a global change. The four measured configurations and source hashes are in
[`the focused report`](../../../artifacts/evaluation/ocr/pipeline/commerce-inventory-policy-page2-tesseract-check-20261005.json).

## Live Admin upload through the corpus pipeline

On 2026-10-06, the local Admin upload API processed
`commerce_synthetic_degraded_scan_demo.pdf` as document
`UPLOAD-3053e0c739514020be438c8c174d515b`. It returned `ready`: 2 pages, 3
parser/indexed chunks, all 3 marked OCR-derived, and 1 structured table. The
table matched all three fixture rows exactly under headers `Region`, `Delivered
sample orders`, `Median transit days`, and `Avg fee units`. The original file
round-tripped from private Storage with SHA-256
`86383a8a65d42791d05549369dcd9f3ebc0b597b846ca7fa06e351e8a1c9fd7d`; Admin
received it as PDF while Viewer received 404. The document was uploaded with
Admin-only access and no Commerce decision tags, then marked inactive after
verification. It remains available for parser inspection but is excluded from
Commerce retrieval. This is a live API/database smoke using synthetic data,
not a browser-click test, physical-scan benchmark, or business evidence.

A second live upload exercised a full image-only three-page policy PDF:
`inventory-allocation.pdf` was stored as Admin-only document
`UPLOAD-7acb31b3878646a0b9d93f0081252cd0`. The API returned `ready` with 3
pages, 5 parser/indexed chunks, 5 OCR-derived chunks, and no tables. Each page
was compared with the fixture's authored-HTML reference: CER/WER were 0.0068 /
0.0230, 0.0017 / 0.0077, and 0.0014 / 0.0068 (aggregate CER 0.0036). This copy
is now inactive and Admin-only, so it remains reviewable in Document Processing
without entering Analyst retrieval. The reference was not human-reviewed and
the PDF is digitally rasterized rather than a physical scan; these scores show
the upload path on this fixture, not general OCR accuracy.
