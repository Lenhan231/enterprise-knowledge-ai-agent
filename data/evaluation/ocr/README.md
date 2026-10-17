# OCR fixtures

## Current model-screening status

As of 2026-10-12, the corpus contains 78 labeled manifests with 930 page or
region records and 60 distinct company-name labels. All 78 set
`primary_metric_selection_eligible` to `false`; their CER/WER results are
exploratory and cannot, by themselves, establish the production OCR winner.
Several new annual-report sets use unproofread native PDF text and need manual
adjudication before they can support model selection.

### Pooled 163-crop comparison: Tesseract, EasyOCR, PaddleOCR, and Surya

All four engines completed the same 163 Vietnamese enterprise crops at 180 DPI
with 0 page errors. Surya scored the lowest pooled micro-CER/WER (8.07%/10.86%);
Tesseract was next (9.09%/14.36%), followed by EasyOCR (10.47%/17.69%) and
PaddleOCR (17.09%/53.70%). PaddleOCR had the shortest measured OCR time per
crop (0.362 s), but ran on a Tesla T4 while Tesseract ran on CPU, so latency
and resource figures are descriptive rather than a controlled device comparison.
The one-reviewer references remain `primary_metric_selection_eligible: false`;
see the [full report](../../../artifacts/evaluation/ocr/large-corpus-163/report.md),
[paired comparison JSON](../../../artifacts/evaluation/ocr/large-corpus-163/comparison.json),
and [dataset manifest](vn-enterprise-ocr-large-v1_ground_truth.json).
The auxiliary text-only table check covered 33 expected rows/99 cells: Surya
matched 31 rows and 98 cell strings; EasyOCR 31/97, Tesseract 21/93, and
PaddleOCR 0/66. This does not evaluate table layout or cell reconstruction.
A follow-up Kaggle CPU tuning sweep for Tesseract is documented in the [large-corpus report](../../../artifacts/evaluation/ocr/large-corpus-163/report.md#tesseract-parameter-tuning-follow-up) and [parameter summary](../../../artifacts/evaluation/ocr/large-corpus-163/results/tesseract-tuning-summary.md); it uses PSM 3 and is a separate experiment from the PSM 11 four-engine comparison above.

### FPT Retail Annual Report 2024: 10 provisional Vietnamese prose crops

FPT Retail's [official site](https://frt.vn/) identifies the issuer; its 2024 annual report was disclosed in a [Vietnamese PDF hosted by FPTS](https://file.fpts.com.vn/FileStore2/File/2025/03/26/20250326_20250326_-_FRT_-_Bao_cao_thuong_nien_nam_2024_signed.pdf). Ten prose regions from PDF pages 7, 8, 9, 12, 14, 18, 20, 24, 27, and 30 are labeled ([manifest](frt-ar-2024-prose-10_ground_truth.json); [references and review sheets](../../../artifacts/evaluation/ocr/review/frt-ar-2024-prose-10/references.md)). Samples include regular prose and two white-on-blue text regions. The born-digital PDF has a native text layer and is not physical-scan data. References are provisional and require human visual adjudication; this dataset is exploratory and ineligible for primary model selection.

Local Tesseract 5.5.3 (`vie+eng`, PSM 3, 180 DPI, CPU) scored provisional micro-CER/WER 0.0044/0.0149 and macro-CER/WER 0.0054/0.0182, averaging 2.380 seconds/crop with 514 MiB evaluator-process peak RSS ([report](../../../artifacts/evaluation/ocr/pipeline/frt-ar-2024-prose-10-cpu/tesseract-local.json)). The two blue-background crops had visibly higher CER than the plain prose crops; this small sample does not establish general OCR quality. Reproduce with `uv run python tools/processing/evaluate_ocr.py --dataset data/evaluation/ocr/frt-ar-2024-prose-10_ground_truth.json --engines tesseract --dpi 180 --output /tmp/frt-tesseract.json`.

### Binh Minh Plastics Annual Report 2024: 10 provisional Vietnamese text crops

The issuer's [shareholder page](https://binhminhplastic.com.vn/co-dong) lists its annual reports and hosts the [Vietnamese 2024 report PDF](https://binhminhplastic.com.vn/Data/Sites/1/media/co-dong/bctn/20250415-bmp-ar-2024-vn-%28final%29.pdf). Ten text regions from PDF pages 14, 15, 16, 18, 20, 24, 25, 56, 60, and 63 are labeled ([manifest](bmp-ar-2024-prose-10_ground_truth.json); [references and review sheets](../../../artifacts/evaluation/ocr/review/bmp-ar-2024-prose-10/references.md)). The PDF has a native text layer and is digitally published, not physical-scan data. Visual inspection found that page 63's extracted text repeated each sentence; the duplicated passage was corrected against its crop. The remaining references still need a full human proofreading pass, so this set is exploratory and ineligible for primary model selection.

Local Tesseract 5.5.3 (`vie+eng`, PSM 3, 180 DPI, CPU) scored provisional micro-CER/WER 0.0175/0.0741 and macro-CER/WER 0.0167/0.0709, averaging 2.139 seconds/crop with 516 MiB evaluator-process peak RSS ([report](../../../artifacts/evaluation/ocr/pipeline/bmp-ar-2024-prose-10-cpu/tesseract-local.json)). These ten regions span prose, a bulleted section, and sustainability content in one report. Reproduce with `uv run python tools/processing/evaluate_ocr.py --dataset data/evaluation/ocr/bmp-ar-2024-prose-10_ground_truth.json --engines tesseract --dpi 180 --output /tmp/bmp-tesseract.json`.

### Pha Lai Thermal Power Annual Report 2024: 10 provisional Vietnamese-English text crops

PPC's [official disclosure notice](https://ppc.evn.vn/tin-vbpq/ppc-cong-bo-thong-tin-bao-cao-thuong-nien-nam-2024-tieng-viet-enlish-.-chi-tiet-tai-file-dinh-kem.2.html) publishes its 2024 annual report. The local copy came from the [FPTS-hosted report PDF](https://file.fpts.com.vn/FileStore2/File/2025/04/16/20250416_PPC_250416_Annual_Report_2024.pdf) after the issuer's PDF host failed TLS hostname verification. Ten text regions from PDF pages 10, 11, 12, 22, 23, 29, 31, 33, 48, and 49 are labeled ([manifest](ppc-ar-2024-bilingual-text-10_ground_truth.json); [references and review sheets](../../../artifacts/evaluation/ocr/review/ppc-ar-2024-prose-10/references.md)). The report is Vietnamese-English, so several samples include translated English text or headings. It has a native text layer and is digitally published, not physical-scan data. References remain provisional and need visual proofreading; the set is exploratory and ineligible for primary model selection.

Local Tesseract 5.5.3 (`vie+eng`, PSM 3, 180 DPI, CPU) scored provisional micro-CER/WER 0.0191/0.0688 and macro-CER/WER 0.0182/0.0658, averaging 0.773 seconds/crop with 515 MiB evaluator-process peak RSS ([report](../../../artifacts/evaluation/ocr/pipeline/ppc-ar-2024-bilingual-text-10-cpu/tesseract-local.json)). These results include bilingual passages and are not directly comparable with Vietnamese-only sets. Reproduce with `uv run python tools/processing/evaluate_ocr.py --dataset data/evaluation/ocr/ppc-ar-2024-bilingual-text-10_ground_truth.json --engines tesseract --dpi 180 --output /tmp/ppc-tesseract.json`.

### Bao Long Insurance Annual Report 2024: 10 provisional Vietnamese text crops

The insurer's [annual-report listing](https://baolonginsurance.com.vn/nha-dau-tu/bao-cao-thuong-nien) lists its 2024 report, available as an [issuer-hosted PDF](https://bctn2024.baolonginsurance.com.vn/pdf/BCTN-BAOLONG-2024.pdf). Ten text crops from PDF pages 3, 13, 23, 24, 26, 35, 37, and 40 are labeled ([manifest](baolong-ar-2024-text-10_ground_truth.json); [reference text and review crops](../../../artifacts/evaluation/ocr/review/baolong-ar-2024/references.md)). The PDF has a native text layer and is digitally published, not physical-scan data. The references remain unadjudicated; the set is exploratory and ineligible for primary model selection.

Local Tesseract 5.5.3 (`vie+eng`, PSM 3, 180 DPI, CPU) scored provisional micro-CER/WER 0.0322/0.1404 and macro-CER/WER 0.0337/0.1463, averaging 1.872 seconds/crop with 494 MiB evaluator-process peak RSS ([report](../../../artifacts/evaluation/ocr/pipeline/baolong-ar-2024-text-10-cpu/tesseract-local.json)). The mix includes uppercase, colored-panel, and prose regions; scores are specific to these ten crops and do not measure physical-scan OCR, full-page reading order, or table extraction. Reproduce with `uv run python tools/processing/evaluate_ocr.py --dataset data/evaluation/ocr/baolong-ar-2024-text-10_ground_truth.json --engines tesseract --dpi 180 --output /tmp/baolong-tesseract.json`.

### Tien Phong Plastic Annual Report 2024: 10 provisional Vietnamese text crops

The issuer's [shareholder-relations page](https://nhuatienphong.vn/co-dong.html) lists the [Vietnamese 2024 annual report](https://admin.nhuatienphong.vn/img/posts/1_f2284364f5cd0dd5e057ecb4e3e165f0BCTN%202024.pdf). Ten text-region crops from PDF pages 32, 34, 39, 41, and 42 are labeled ([manifest](ntp-ar-2024-text-10_ground_truth.json); [reference text and review crops](../../../artifacts/evaluation/ocr/review/ntp-ar-2024/references.md)). The PDF has a native text layer and is digitally published, not a physical scan. The references are provisional and need visual adjudication; the dataset is exploratory and ineligible for primary model selection.

Local Tesseract 5.5.3 (`vie+eng`, PSM 3, 180 DPI, CPU) scored provisional micro-CER/WER 0.0720/0.2888 and macro-CER/WER 0.0686/0.2754, averaging 2.639 seconds/crop with 508 MiB evaluator-process peak RSS ([report](../../../artifacts/evaluation/ocr/pipeline/ntp-ar-2024-text-10-cpu/tesseract-local.json)). The crops include small text and multi-column or colored-panel layouts, so the result is specific to these regions and is not directly comparable to plain prose crops. They do not measure physical-scan OCR or full-page reading order. Reproduce with `uv run python tools/processing/evaluate_ocr.py --dataset data/evaluation/ocr/ntp-ar-2024-text-10_ground_truth.json --engines tesseract --dpi 180 --output /tmp/ntp-tesseract.json`.

### KienlongBank Annual Report 2024: 10 provisional Vietnamese prose crops

KienlongBank's [official investor-relations announcement](https://kienlongbank.com/bao-cao-thuong-nien-nam-2024) confirms its 2024 report. The local copy was downloaded from the [FiinGroup-hosted PDF mirror](https://cmsv5.fiingroup.vn/medialib/FG/2025/2025-04/2025-04-21/184929_000000014810628_Vi__Bao_cao_thuong_nien_KienlongBank_2024.pdf) after the HNX download host failed TLS certificate verification. Ten prose crops from PDF pages 5, 6, 7, 25, and 31 are labeled ([manifest](kienlongbank-ar-2024-prose-10_ground_truth.json); [reference text and review crops](../../../artifacts/evaluation/ocr/review/kienlongbank-ar-2024/references.md)). The PDF has a native text layer and is not physical-scan data. References are copied from that layer and need visual adjudication; the dataset is exploratory and ineligible for primary model selection.

Local Tesseract 5.5.3 (`vie+eng`, PSM 3, 180 DPI, CPU) scored provisional micro-CER/WER 0.0030/0.0104 and macro-CER/WER 0.0030/0.0103, averaging 2.050 seconds/crop with 506 MiB evaluator-process peak RSS ([report](../../../artifacts/evaluation/ocr/pipeline/kienlongbank-ar-2024-prose-10-cpu/tesseract-local.json)). These crops cover five pages of one report and do not measure scan OCR, full-page reading order, layout detection, or table extraction. Reproduce with `uv run python tools/processing/evaluate_ocr.py --dataset data/evaluation/ocr/kienlongbank-ar-2024-prose-10_ground_truth.json --engines tesseract --dpi 180 --output /tmp/kienlongbank-tesseract.json`.

### Bao Viet Holdings Annual Report 2024: 10 provisional Vietnamese prose crops

The issuer's [2024 annual-report announcement](https://baoviet.awe7.com/vi/node/1168) links the official [Vietnamese report PDF](https://baoviet.com.vn/BVH_IR2024_VN.pdf). Ten selectable-text prose regions from PDF pages 3, 7, 13, 15, and 18 are labeled ([manifest](baoviet-ar-2024-prose-10_ground_truth.json); [reference text and review crops](../../../artifacts/evaluation/ocr/review/baoviet-ar-2024/references.md)). The 442-page digital PDF has a native text layer and is not physical-scan data. References were copied from the native layer and remain unadjudicated; the dataset is exploratory and ineligible for primary model selection.

Local Tesseract 5.5.3 (`vie+eng`, PSM 3, 180 DPI, CPU) scored provisional micro-CER/WER 0.0129/0.0461 and macro-CER/WER 0.0130/0.0467, averaging 1.560 seconds/crop with 489 MiB evaluator-process peak RSS ([report](../../../artifacts/evaluation/ocr/pipeline/baoviet-ar-2024-prose-10-cpu/tesseract-local.json)). These crops cover five pages of one report and do not measure scan OCR, full-page reading order, layout detection, or table extraction. Reproduce with `uv run python tools/processing/evaluate_ocr.py --dataset data/evaluation/ocr/baoviet-ar-2024-prose-10_ground_truth.json --engines tesseract --dpi 180 --output /tmp/baoviet-tesseract.json`.

### VietABank Annual Report 2024: 10 provisional Vietnamese text crops

VietABank's investor-relations [annual-report listing](https://vietabank.com.vn/thong-bao-thong-tin/bao-cao-thuong-nien.html) links the issuer-hosted [2024 report PDF](https://www.vietabank.com.vn/Uploads/Download/Investors/Bao%20cao%20thuong%20nien%202024.pdf). Ten selectable-text crops from PDF pages 23, 32, 33, and 42 are labeled ([manifest](vietabank-ar-2024-text-10_ground_truth.json); [reference text and review crops](../../../artifacts/evaluation/ocr/review/vietabank-ar-2024/references.md)). The report mixes text pages and designed image pages; these are text-layer crops, not physical-scan samples. The native-text references are provisional and need visual review, so the dataset is exploratory and ineligible for primary model selection.

Local Tesseract 5.5.3 (`vie+eng`, PSM 3, 180 DPI, CPU) scored provisional micro-CER/WER 0.0090/0.0338 and macro-CER/WER 0.0110/0.0411, averaging 2.337 seconds/crop with 516 MiB evaluator-process peak RSS ([report](../../../artifacts/evaluation/ocr/pipeline/vietabank-ar-2024-text-10-cpu/tesseract-local.json)). The crops cover four pages of one report and do not measure image-only page OCR, full-page reading order, layout detection, or table extraction. Reproduce with `uv run python tools/processing/evaluate_ocr.py --dataset data/evaluation/ocr/vietabank-ar-2024-text-10_ground_truth.json --engines tesseract --dpi 180 --output /tmp/vietabank-tesseract.json`.

### Agribank Annual Report 2024: 10 provisional Vietnamese text crops

The official [Agribank report](https://www.agribank.com.vn/wcm/connect/1c602381-62d0-48a6-990a-ba14a078b603/BCTN2024%2BAgribank%2BV%2Bversion%2BS.pdf?MOD=AJPERES) has 74 pages and a native text layer. Ten text regions from PDF pages 9, 15, 26, 35, and 38 are labeled ([manifest](agribank-ar-2024-prose-10_ground_truth.json); [reference text and review crops](../../../artifacts/evaluation/ocr/review/agribank-ar-2024/references.md)). The PDF is digitally published, not physical-scan data. References are copied from the PDF text layer and remain unadjudicated; the dataset is exploratory and ineligible for primary model selection.

Local Tesseract 5.5.3 (`vie+eng`, PSM 3, 180 DPI, CPU) scored provisional micro-CER/WER 0.0247/0.0922 and macro-CER/WER 0.0257/0.0998, averaging 2.626 seconds/crop with 515 MiB evaluator-process peak RSS ([report](../../../artifacts/evaluation/ocr/pipeline/agribank-ar-2024-prose-10-cpu/tesseract-local.json)). These crops span five pages of one report and do not measure physical-scan OCR, full-page reading order, layout detection, or table extraction. Reproduce with `uv run python tools/processing/evaluate_ocr.py --dataset data/evaluation/ocr/agribank-ar-2024-prose-10_ground_truth.json --engines tesseract --dpi 180 --output /tmp/agribank-tesseract.json`.

### BAC A BANK Annual Report 2024: 10 provisional Vietnamese prose crops

The issuer-hosted [BAC A BANK report](https://baca-bank.vn/SiteAssets/Folder%20Upload/bctn%202024%20vie%20v2.pdf) was cross-checked against the [HNX-hosted copy](https://owa.hnx.vn/ftp/cims/2025/4_W2/000000014773611_VI_BaoCaoThuongNien_2024.pdf). Ten native-text paragraphs from PDF pages 4, 5, 6, 13, and 14 are labeled ([manifest](bab-ar-2024-prose-10_ground_truth.json); [reference text and review crops](../../../artifacts/evaluation/ocr/review/bac-a-bank-ar-2024/references.md)). The report has a native text layer and is digitally published, not a physical scan. References are copied from that layer and still need visual adjudication; this set is exploratory and ineligible for primary model selection.

Local Tesseract 5.5.3 (`vie+eng`, PSM 3, 180 DPI, CPU) scored provisional micro-CER/WER 0.0130/0.0496 and macro-CER/WER 0.0129/0.0490, averaging 2.106 seconds/crop with 514 MiB evaluator-process peak RSS ([report](../../../artifacts/evaluation/ocr/pipeline/bab-ar-2024-prose-10-cpu/tesseract-local.json)). These ten crops cover five pages from one report and do not measure scan OCR, full-page reading order, layout detection, or table extraction. Reproduce with `uv run python tools/processing/evaluate_ocr.py --dataset data/evaluation/ocr/bab-ar-2024-prose-10_ground_truth.json --engines tesseract --dpi 180 --output /tmp/bab-tesseract.json`.

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

## Restored Vinamilk v9 engine comparison

The historical v9 cross-layout Vietnamese financial-scan comparison has been
restored after the repository cleanup. It pairs the same 14 labeled pages at
180 DPI across Tesseract, PaddleOCR, EasyOCR, and Surya. The GPU and CPU result
sets are retained separately because runtime and memory depend on the device.
The comparison files are [GPU runs](../../../artifacts/evaluation/ocr/comparisons/vinamilk-v9/gpu/comparison.json)
and [CPU runs](../../../artifacts/evaluation/ocr/comparisons/vinamilk-v9/cpu/comparison.json);
individual raw reports are in the [`gpu`](../../../artifacts/evaluation/ocr/comparisons/vinamilk-v9/gpu/)
and [`cpu`](../../../artifacts/evaluation/ocr/comparisons/vinamilk-v9/cpu/) folders.
The restored [14-region labels](vinamilk-v9_ground_truth.json) cover six PDFs;
their references combine visual human review with text-layer-assisted review,
and `primary_metric_selection_eligible` is false. The source PDFs are not in
the current raw-data checkout. To reproduce, use the shared
[`Kaggle notebook`](../../../notebooks/kaggle_ocr_benchmark.ipynb) with a bundle
that contains the matching source files; their hashes are recorded in each
report.

| Engine | Accelerated-profile device | CER / WER | Mean OCR sec/page | Peak host RSS | PyTorch GPU allocated / reserved | CPU-only sec/page | CPU-only peak RSS |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Tesseract 4.1.1, PSM 3 | CPU | 0.3619 / 0.4916 | 2.504 | 333 MiB | N/A | 2.468 | 342 MiB |
| PaddleOCR 3.7.0 | CPU | 0.0735 / 0.1819 | 41.890 | 3,754 MiB | N/A | 47.641 | 4,106 MiB |
| EasyOCR 1.7.2 | CUDA | 0.1987 / 0.3371 | 1.896 | 1,615 MiB | 1,863 / 2,570 MiB | 20.155 | 4,033 MiB |
| Surya 0.17.1 | CUDA | 0.0748 / 0.1162 | 4.791 | 4,470 MiB | 3,011 / 3,494 MiB | 106.282 | 6,306 MiB |

These are historical measurements on a mixed-language, cross-layout corpus;
they are useful as a baseline, not as a current production-engine decision.
The source documents and original label set are not part of the active
Commerce corpus. Validate provenance and labels before reproducing or extending
the Vinamilk comparison.
GPU memory values are PyTorch allocator telemetry and do not include every
non-PyTorch CUDA allocation.

## HPT and Annual Report exploratory comparison

Four Kaggle engines processed one 180-DPI page each from the HPT scan and the
English Annual Report. Reports include engine version, runtime device, model
initialization time, page OCR latency, peak host RSS, source/page hashes, and
CER/WER where full-page references exist. Per-engine reports: [HPT scan](../../../artifacts/evaluation/ocr/pipeline/longhau-2008-page6-kaggle-tesseract.json)
([PaddleOCR](../../../artifacts/evaluation/ocr/pipeline/longhau-2008-page6-kaggle-paddleocr.json),
[EasyOCR](../../../artifacts/evaluation/ocr/pipeline/longhau-2008-page6-kaggle-easyocr.json),
[Surya](../../../artifacts/evaluation/ocr/pipeline/longhau-2008-page6-kaggle-surya.json));
[Annual Report](../../../artifacts/evaluation/ocr/pipeline/pvfcco-annual-report-2008-page6-kaggle-tesseract.json)
([PaddleOCR](../../../artifacts/evaluation/ocr/pipeline/pvfcco-annual-report-2008-page6-kaggle-paddleocr.json),
[EasyOCR](../../../artifacts/evaluation/ocr/pipeline/pvfcco-annual-report-2008-page6-kaggle-easyocr.json),
[Surya](../../../artifacts/evaluation/ocr/pipeline/pvfcco-annual-report-2008-page6-kaggle-surya.json)).

| Page / engine | Device | Init sec | OCR sec | Peak host RSS | CER / WER |
| --- | --- | ---: | ---: | ---: | ---: |
| HPT scan · Tesseract 5.3.4 | CPU | N/A | 3.222 | 264 MiB | N/A |
| HPT scan · PaddleOCR 3.7.0 | CPU | 40.717 | 79.157 | 3,314 MiB | N/A |
| HPT scan · EasyOCR 1.7.2 | Tesla T4 | 13.732 | 7.587 | 1,437 MiB | N/A |
| HPT scan · Surya 0.17.1 | Tesla T4 | 57.364 | 8.108 | 4,388 MiB | N/A |
| Annual Report · Tesseract 5.3.4 | CPU | N/A | 2.183 | 260 MiB | 0.0402 / 0.0385 |
| Annual Report · PaddleOCR 3.7.0 | CPU | 39.187 | 74.709 | 3,295 MiB | 0.0407 / 0.0385 |
| Annual Report · EasyOCR 1.7.2 | Tesla T4 | 10.251 | 4.663 | 1,434 MiB | 0.0429 / 0.0490 |
| Annual Report · Surya 0.17.1 | Tesla T4 | 76.911 | 7.862 | 4,385 MiB | 0.0424 / 0.0455 |

The HPT page has only four manually labeled table rows and 12 cells; every
engine matched all of them, so full-page CER/WER is unavailable. Annual Report
page 6 is born-digital and its text-layer reference has not been manually
adjudicated. The eight runs therefore remain exploratory and cannot select an
upload engine. Latency excludes model initialization; GPU memory was not
captured in these reports. Tesseract and PaddleOCR ran on CPU while EasyOCR and
Surya ran on a Tesla T4, so compare resource numbers with that hardware split
in mind.

### HPT cover page 1: CPU-only baseline

All four engines were run on the same labeled HPT cover page at 180 DPI with
CPU execution. This is a fixed-configuration screening pass, not a tuned
comparison: Tesseract used PSM 3; the other engines used their current library
defaults. Each Kaggle kernel had 4 vCPUs, but Kaggle assigned different CPU
models to PaddleOCR than to the other three, so latency is descriptive rather
than a hardware-controlled ranking. Full report and input-hash-checked paired
comparison: [comparison](../../../artifacts/evaluation/ocr/pipeline/hpt-cover-page1-cpu/comparison.json);
raw engine reports are in the same directory. Labels are a single-reviewer
visual transcription and are ineligible for primary model selection.

| Engine | Version | CER / WER | Model init sec | OCR sec/page | Peak host RSS |
| --- | --- | ---: | ---: | ---: | ---: |
| Tesseract (PSM 3) | 5.3.4 | 0.4444 / 0.7059 | N/A | 1.252 | 265 MiB |
| PaddleOCR | 3.7.0 | 0.0588 / 0.2647 | 59.067 | 33.807 | 3,256 MiB |
| EasyOCR | 1.7.2 | 0.0065 / 0.0294 | 13.361 | 30.538 | 2,977 MiB |
| Surya | 0.17.1 | 0.1307 / 0.2647 | 58.637 | 52.245 | 5,486 MiB |

EasyOCR had the lowest text error on this page; Tesseract used the least
memory and inference time but its PSM 3 output was poor. This only prioritizes
what to investigate next: tune Tesseract page segmentation and compare
EasyOCR/PaddleOCR settings on more HPT pages before drawing a model conclusion.
The measured peak RSS includes model initialization; OCR latency is reported
separately and excludes initialization. The page contains no table, and these
metrics do not measure layout detection or table extraction.

On the same page at 180 DPI, a local Tesseract PSM sweep scored PSM 11 best:

| Tesseract PSM | CER / WER | OCR sec/page | Evaluator peak RSS |
| ---: | ---: | ---: | ---: |
| 3 | 0.4314 / 0.7059 | 0.945 | 537 MiB |
| 6 | 0.2680 / 0.5000 | 0.962 | 537 MiB |
| 11 | 0.1176 / 0.2647 | 0.775 | 537 MiB |
| 12 | 0.4379 / 0.7941 | 1.174 | 539 MiB |

These local resource figures include the Python evaluator and are not directly
comparable to Kaggle's host RSS above. PSM 11 is the best tested Tesseract
setting for this cover page, not proof that it is optimal across the PDF. Raw
reports and the paired comparison are in
[`hpt-cover-page1-tesseract-psm-sweep`](../../../artifacts/evaluation/ocr/pipeline/hpt-cover-page1-tesseract-psm-sweep/).

### HPT pages 1 and 3: expanded CPU baseline

The next screen uses the isolated cover page and page 3 of the original
22-page scan, which contains dense Vietnamese prose. Both pages were rendered
at 180 DPI and evaluated with `vie+eng`; every Kaggle kernel ran CPU-only on
four vCPUs reported as Intel Xeon @ 2.20 GHz. Tesseract PSM 3 and PSM 11 are
separate runs; PaddleOCR, EasyOCR and Surya use the evaluator's default
settings. Full paired report: [comparison](../../../artifacts/evaluation/ocr/pipeline/hpt-pages1-3-cpu/comparison.json);
individual reports and the two-page label set are in the same directory and
[`labels`](hpt-pages1-3_ground_truth.json).

| Engine / setting | Version | micro-CER / micro-WER | Init sec | OCR sec/page | Peak process RSS |
| --- | --- | ---: | ---: | ---: | ---: |
| Tesseract PSM 3 | 5.3.4 | 0.1328 / 0.2185 | N/A | 2.182 | 271 MiB |
| Tesseract PSM 11 | 5.3.4 | 0.1045 / 0.1975 | N/A | 2.272 | 270 MiB |
| PaddleOCR | 3.7.0 | 0.1271 / 0.4160 | 51.539 | 54.179 | 3,462 MiB |
| EasyOCR | 1.7.2 | **0.0626 / 0.1050** | 11.294 | 34.316 | 2,993 MiB |
| Surya | 0.17.1 | 0.1045 / 0.1702 | 52.588 | 140.550 | 5,634 MiB |

EasyOCR had the lowest text error across these two pages. Tesseract PSM 11
improved on PSM 3 with almost no change in memory or per-page latency; EasyOCR
used about 2.7 GiB peak RSS, and Surya had the highest CPU latency and memory
here. Latency excludes initialization; peak process RSS includes it. The
labels are a single-reviewer transcription, and two pages from one document
remain a screening sample, not enough to choose a general production model.
The reported metrics measure text only, not layout detection or table
structure. For Vietnamese enterprise report screening, see the comparisons
below; evaluate table/layout extraction separately.

### PVFCCo Annual Report 2024: 14 half-page regions

The official [PVFCCo / Đạm Phú Mỹ Annual Report 2024](https://dpm.vn/public_folder/files_upload/202504/20250410dpmar-2024vnwebpdf1744691930.pdf)
adds 14 selected half-page regions from 10 landscape spreads
([labels](pvfcco-ar-2024-prose-regions-14_ground_truth.json)). The regions
contain Vietnamese prose mixed with headings, graphics, or callouts. Native
PDF text references are unproofread and this set is exploratory, ineligible
for production model selection. Local Tesseract 5.5.3 at 180 DPI / PSM 3
scored micro-CER/WER 0.2966/0.3809, macro CER/WER 0.2969/0.3815, and
3.136 seconds/region with 1,008 MiB process peak RSS
([report](../../../artifacts/evaluation/ocr/pipeline/pvfcco-ar-2024-prose-regions-14-local-tesseract.json)).
Kaggle Tesseract 5.3.4 scored 0.2972/0.3807 at 3.333 seconds/region and
268 MiB process peak RSS; both runs use the same 14 rendered-region hashes
([report](../../../artifacts/evaluation/ocr/pipeline/pvfcco-ar-2024-prose-regions-14-kaggle-tesseract.json)).
EasyOCR 1.7.2 on Tesla T4 scored micro-CER/WER 0.0461/0.0969 and macro
CER/WER 0.0439/0.0951, at 4.956 seconds/region (11.633 seconds
initialization), 1,581 MiB process peak RSS, and 1,863/2,302 MiB peak GPU
allocated/reserved memory. PaddleOCR 3.7.0 on Tesla T4 scored 0.1186/0.4858
(macro 0.1195/0.4873) at 1.907 seconds/region (34.710 seconds
initialization), 2,890 MiB process peak RSS. PyTorch-only GPU memory telemetry
does not include Paddle allocations. The three reports pair on all 14 region
hashes ([comparison](../../../artifacts/evaluation/ocr/pipeline/pvfcco-ar-2024-prose-regions-14-comparison-all-engines.json)).
EasyOCR has the lowest observed text error and PaddleOCR the lowest latency;
these unproofread references still confound text recognition with extraction
and layout errors, so region-level review is needed before ranking production
engines.

### PVFCCo Annual Report 2008: five prose pages, CPU screening

The expanded Annual Report set compares pages 6, 7, 17, 35, and 36 at 180 DPI.
Financial-table pages were excluded from CER/WER. References come from the PDF
text layer and were visually checked for content and reading flow, but not
proofread word by word; this exploratory set is ineligible for primary model
selection. Page 7 uses a distinct, low-contrast design and strongly affects the
aggregate, especially for Tesseract. Labels:
[`five-page set`](pvfcco-annual-report-2008-pages6-7-17-35-36_ground_truth.json).
Hash-checked paired comparison and raw reports:
[`comparison`](../../../artifacts/evaluation/ocr/pipeline/pvfcco-annual-report-pages6-7-17-35-36-cpu/comparison.json).
All runs were CPU-only; latency excludes initialization, while peak process RSS
includes it.

| Engine | Version | micro-CER / micro-WER | Init sec | OCR sec/page | Peak process RSS |
| --- | --- | ---: | ---: | ---: | ---: |
| Tesseract PSM 3 | 5.3.4 | 0.1620 / 0.1687 | N/A | 1.571 | 269 MiB |
| PaddleOCR | 3.7.0 | 0.0453 / 0.0490 | 45.715 | 71.444 | 3,620 MiB |
| EasyOCR | 1.7.2 | 0.0439 / 0.0560 | 11.575 | 35.505 | 3,042 MiB |
| Surya | 0.17.1 | **0.0408 / 0.0435** | 41.509 | 99.401 | 5,851 MiB |

Surya had the lowest micro-CER/WER on this five-page set, with EasyOCR close
and faster. This is a screening result, not a model-selection decision: the
sample is one born-digital report and its native text reference has not been
independently proofread. These metrics measure OCR text, not layout detection
or table structure.

### Vietnamese enterprise annual reports: initial 21-page CPU screening

The 13-page cross-company set samples Vietnamese narrative pages from official
2024 annual reports by [Vinamilk](https://www.vinamilk.com.vn/bao-cao-thuong-nien/bao-cao/2024/doc/vi/full-bao-cao.pdf),
[FPT](https://fpt.com/api/media/bao_cao_thuong_nien_fpt_2024_883024f1dd.pdf),
and [Hòa Phát](https://file.hoaphat.com.vn/hoaphat-com-vn/2025/04/bao-cao-thuong-nien-hpg-2024.pdf).
An additional eight-page set samples the official [Vingroup Annual Report
2024](https://ircdn.vingroup.net/storage/Uploads/0_Bao%20cao%20thuong%20nien/2024/VIE_%20Vingroup%20AR24_250418.pdf).
The PDFs and labels are stored in `data/raw/vietnam_enterprises/` and
[`13-page labels`](vietnam-enterprise-reports-2024-prose-13_ground_truth.json)
and [`Vingroup labels`](vingroup-ar-2024-prose-8_ground_truth.json).

All engines used CPU-only Kaggle kernels, 180-DPI page renders, and the same
selected pages within each set. Tesseract used PSM 3. Metrics are paired and
input-hash checked. Mean OCR latency excludes model initialization; peak
process RSS includes it. The kernels overlapped, so resource figures are
observed screening values, not a hardware-controlled throughput comparison.
These results are exploratory: reference text comes from PDF text layers,
visually spot-checked for language/layout but not proofread word by word.
Multi-column and mixed-image pages can inflate WER when reading order differs.
The samples exclude pages dominated by tables and do not score layout
detection or table extraction.

| Dataset / engine | micro-CER / micro-WER | Init sec | OCR sec/page | Peak process RSS |
| --- | ---: | ---: | ---: | ---: |
| 13 pages · Tesseract 5.3.4, PSM 3 | **0.4308 / 0.5317** | N/A | 6.704 | 353 MiB |
| 13 pages · EasyOCR 1.7.2 | 0.5889 / 0.7394 | 10.768 | 41.288 | 4,229 MiB |
| 13 pages · PaddleOCR 3.7.0 | 0.6349 / 0.9430 | 43.221 | 147.542 | 7,595 MiB |
| 8 pages · Tesseract 5.3.4, PSM 3 | **0.3433 / 0.4035** | N/A | 6.330 | 273 MiB |
| 8 pages · EasyOCR 1.7.2 | 0.6535 / 0.8668 | 11.195 | 68.605 | 4,204 MiB |
| 8 pages · PaddleOCR 3.7.0 | 0.6795 / 0.9752 | 54.675 | 166.356 | 5,696 MiB |

Tesseract had the lowest exploratory text error and resource use on both sets.
Do not treat that as a final production decision until references are
proofread and scanned-page cases are added. Surya was omitted from this run:
its CPU pilot took 676.6 seconds on one Vingroup page. In the earlier
five-page English screening, Surya's micro-CER/WER was 0.0408/0.0435 versus
EasyOCR's 0.0439/0.0560, while its OCR time and RSS were about 2.8× and 1.9×
higher. Per your decision, the remaining Surya jobs were stopped. Per-engine
reports and paired comparisons are in
[`13-page results`](../../../artifacts/evaluation/ocr/pipeline/vietnam-enterprise-reports-2024-prose-13-cpu/)
and [`Vingroup results`](../../../artifacts/evaluation/ocr/pipeline/vingroup-ar-2024-prose-8-cpu/).

### VNG Annual Report 2024: 16 half-page regions

The official [VNG Annual Report 2024](https://vng.com.vn/news/shareholders/2024-annual-report.html)
adds 16 Vietnamese half-page regions across 10 landscape pages
([labels](vng-ar-2024-prose-regions-16_ground_truth.json)). Local Tesseract
5.5.3 at 180 DPI / PSM 3 scored micro-CER/WER 0.1310/0.3138, macro
CER/WER 0.1378/0.3183, and 5.290 seconds/region with 1,009 MiB peak RSS
([report](../../../artifacts/evaluation/ocr/pipeline/vng-ar-2024-prose-regions-16-local-tesseract.json)).
Kaggle Tesseract 5.3.4 scored 0.1218/0.2680 at 4.590 seconds/region and
305 MiB peak RSS on the same 16 rendered-region hashes
([report](../../../artifacts/evaluation/ocr/pipeline/vng-ar-2024-prose-regions-16-kaggle-tesseract.json)).
EasyOCR 1.7.2 on Tesla T4 scored micro-CER/WER 0.0662/0.1044 and macro
CER/WER 0.0706/0.1097 at 5.383 seconds/region (10.704 seconds initialization),
1,764 MiB process peak RSS, and 3,369/4,192 MiB GPU allocated/reserved
([comparison](../../../artifacts/evaluation/ocr/pipeline/vng-ar-2024-prose-regions-16-comparison-tesseract-easyocr.json)).
PaddleOCR 3.7.0 on Tesla T4 scored micro-CER/WER 0.1497/0.5192 and macro
CER/WER 0.1534/0.5214 at 1.734 seconds/region (38.370 seconds initialization),
2,938 MiB process peak RSS, with Paddle GPU allocations not represented by the
PyTorch-only CUDA counter
([report](../../../artifacts/evaluation/ocr/pipeline/vng-ar-2024-prose-regions-16-paddleocr-gpu.json)).
The [three-engine comparison](../../../artifacts/evaluation/ocr/pipeline/vng-ar-2024-prose-regions-16-comparison-all-engines.json)
shows EasyOCR with the lowest observed CER/WER, while PaddleOCR was fastest per
region on this sample. Tesseract ran CPU-only; compare its timing cautiously
against T4 GPU measurements. The references are unproofread native PDF text and
are not eligible for primary model selection.

## Vietcombank and VCBS 2024 screening sets

Two more official Vietnamese annual reports have been added: [Vietcombank
2024](https://www.vietcombank.com.vn/-/media/Project/VCB-Sites/VCB/Nha-Dau-tu/Files/BC-dinh-ky/BC-thuong-nien/2024/VN_VCB-Annual-Report-2024_Full_250426_FN_compressed.pdf)
and [VCBS 2024](https://www.vcbs.com.vn/storage/upload/media/bao-cao-thuong-nien/2024/ar2024-vi.pdf).
Each set contains 10 selected pages, has a source PDF checksum, and is marked
ineligible for primary model selection because its PDF-text references have
not been proofread word by word. Vietcombank uses wide spreads with mixed
columns, photos and charts, so reading order can raise CER/WER even when text
is recognized. Labels: [Vietcombank](vietcombank-ar-2024-prose-10_ground_truth.json)
and [VCBS](vcbs-ar-2024-prose-10_ground_truth.json). Initial Tesseract CPU
scores are micro-CER/WER 0.2894/0.3310 at 5.382 seconds/page and 280 MiB peak
process RSS for Vietcombank, and 0.3642/0.4395 at 6.439 seconds/page and 313
MiB for VCBS. Vietcombank EasyOCR scored 0.5685/0.7266 at 41.063 seconds/page
and 4,187 MiB peak RSS (8.617 seconds model initialization). Vietcombank
PaddleOCR completed at 0.6802/0.9805, 137.265 seconds/page and 5,681 MiB
peak RSS (40.685 seconds model initialization). VCBS EasyOCR has completed:
micro-CER/WER 0.5419/0.6839 at 64.418 seconds/page, 4,229 MiB peak RSS, and
12.171 seconds model initialization. VCBS PaddleOCR scored 0.6170/0.9249 at
175.392 seconds/page and 5,665 MiB peak RSS (47.645 seconds initialization).
Its paired report confirms all three engines used the same ten rendered page
hashes ([comparison](../../../artifacts/evaluation/ocr/pipeline/vcbs-ar-2024-prose-10-cpu/comparison.json)).
On the same pages, Tesseract scored 0.3642/0.4395 at 6.439 seconds/page and
313 MiB. These are exploratory scores against unproofread PDF text; they are
not comparable to the other report sets as a winner ranking. Results are kept separately under
[`Vietcombank CPU runs`](../../../artifacts/evaluation/ocr/pipeline/vietcombank-ar-2024-prose-10-cpu/)
and [`VCBS CPU runs`](../../../artifacts/evaluation/ocr/pipeline/vcbs-ar-2024-prose-10-cpu/).

The dataset has also been expanded with [FPT's official 2025 annual
report](https://fpt.com/api/download?url=%2Fapi%2Fmedia%2FBCTN_2025_ad403f779b.pdf).
Its 10 selected 180-DPI content crops exclude the repeated left navigation
rail; the visual review confirms Vietnamese narrative content, while references
remain native PDF text and unproofread. See [FPT labels](fpt-ar-2025-prose-10_ground_truth.json).
Tesseract completed on CPU with micro-CER/WER 0.3620/0.4855 at 4.121
seconds/page and 270 MiB peak RSS. EasyOCR completed on CPU at 0.4456/0.5747,
35.279 seconds/page and 2,762 MiB peak RSS (11.798 seconds initialization);
PaddleOCR completed on CPU at 0.5834/0.9158, 78.771 seconds/page and 3,307
MiB peak RSS (46.927 seconds initialization). All three paired reports use
the same ten rendered pages ([comparison](../../../artifacts/evaluation/ocr/pipeline/fpt-ar-2025-prose-10-cpu/comparison.json)).
Keep this separate from FPT 2024 because its report layout and year differ.
These remain exploratory scores against unproofread native text.

The next set adds [Hòa Phát's official 2025 annual report](https://file.hoaphat.com.vn/hoaphat-com-vn/2026/04/bao-cao-thuong-nien-2025-1.pdf):
10 visually checked Vietnamese content crops at 180 DPI, with the repeated
navigation rail clipped out. Its native-text labels are exploratory and not
word-by-word proofread ([labels](hoa-phat-ar-2025-prose-10_ground_truth.json)).
Tesseract completed with micro-CER/WER 0.0703/0.0899 at 6.569 seconds/page
and 306 MiB peak RSS ([report](../../../artifacts/evaluation/ocr/pipeline/hoa-phat-ar-2025-prose-10-cpu/tesseract.json)).
EasyOCR scored 0.4998/0.6066 at 54.393 seconds/page and 3,898 MiB peak RSS
(12.503 seconds initialization); PaddleOCR scored 0.5358/0.8580 at 175.353
seconds/page and 8,536 MiB peak RSS (43.924 seconds initialization). Both
reports are paired with Tesseract on the same ten pages
([comparison](../../../artifacts/evaluation/ocr/pipeline/hoa-phat-ar-2025-prose-10-cpu/comparison.json)).

An additional [Hòa Phát 2024 Annual Report](https://file.hoaphat.com.vn/hoaphat-com-vn/2025/04/bao-cao-thuong-nien-hpg-2024.pdf)
sample adds 12 visually inspected content crops from the steel and industrial
group. Ambiguous two-column pages were removed after a reading-order audit;
the repeated navigation rail is cropped out. Native PDF text remains
unproofread, so the sample is exploratory
([labels](hpg-ar-2024-prose-12_ground_truth.json)). Local Tesseract at 180 DPI /
PSM 3 scored micro-CER/WER 0.0335/0.0568 at 3.958 seconds/page and 587 MiB peak
RSS ([report](../../../artifacts/evaluation/ocr/pipeline/hpg-ar-2024-prose-12-cpu/local-tesseract.json)).
The private Kaggle dataset's updated labels and source were verified. Kaggle
Tesseract 5.3.4 on CPU scored micro-CER/WER 0.0328/0.0519 at 5.093 seconds/page
and 315 MiB peak RSS ([report](../../../artifacts/evaluation/ocr/pipeline/hpg-ar-2024-prose-12-cpu/tesseract.json)).
Its 12 rendered-image hashes match the local Tesseract 5.5.3 run; CER/WER are
close, while latency and RSS are host-specific. EasyOCR CPU is still running;
PaddleOCR is prepared and awaiting a free session.

The next sample is [BIDV's official 2024 annual report](https://bidv.com.vn/bidv/quan-he-nha-dau-tu/bao-cao-va-tai-lieu/baocaothuongnien/2025/bctn%2B2024).
The PDF has 91 pages and a native Vietnamese text layer. Seventeen visually
reviewed pages emphasize narrative, risk, workforce, sustainability, and
management discussion, while avoiding financial-table pages. The PDF text is
still an unproofread reference, so this 17-page set is exploratory. Tesseract
CPU has started; its private Kaggle dataset is ready. See [BIDV labels](bidv-ar-2024-prose-17_ground_truth.json).
Tesseract finished all 17 pages with micro-CER/WER 0.2287/0.2493 at 7.178
seconds/page and 312 MiB peak RSS ([report](../../../artifacts/evaluation/ocr/pipeline/bidv-ar-2024-prose-17-cpu/tesseract.json)).
EasyOCR CPU completed on the identical pages with micro-CER/WER 0.6492/0.8452,
75.094 seconds/page and 4,248 MiB peak RSS (11.292 seconds initialization).
The paired comparison is saved at
[comparison](../../../artifacts/evaluation/ocr/pipeline/bidv-ar-2024-prose-17-cpu/comparison.json).
PaddleOCR failed during dependency installation before OCR, so BIDV currently
has no PaddleOCR accuracy result; retry it with the updated PyPI installation
path when a CPU slot opens.

The [REE 2024 Annual Report](https://www.reecorp.com/danh-muc-bao-cao/bao-cao-thuong-nien/)
adds 16 visually reviewed Vietnamese pages covering management messages,
business and energy outlook, governance, and sustainability. The official PDF
has a native text layer, which remains unproofread; this set is exploratory
([labels](ree-ar-2024-prose-16_ground_truth.json)). Its private Kaggle dataset
is ready. Tesseract finished all 16 pages with micro-CER/WER 0.1718/0.2202
at 4.082 seconds/page and 263 MiB peak RSS ([report](../../../artifacts/evaluation/ocr/pipeline/ree-ar-2024-prose-16-cpu/tesseract.json)).
EasyOCR scored 0.2153/0.2575 at 35.604 seconds/page and 3,032 MiB peak RSS
(11.587 seconds initialization). The paired comparison confirms both engines
used the same 16 rendered pages. PaddleOCR completed with micro-CER/WER
0.6105/0.9219 at 94.138 seconds/page and 3,636 MiB peak RSS (48.348 seconds
initialization); see the [three-engine comparison](../../../artifacts/evaluation/ocr/pipeline/ree-ar-2024-prose-16-cpu/comparison.json).

The [Vinamilk 2024 Annual Report](https://www.vinamilk.com.vn/bao-cao-thuong-nien/bao-cao/2024/doc/vi/full-bao-cao.pdf)
adds 12 visually reviewed full-page spreads with Vietnamese narrative content,
including management discussion, governance, and sustainability. The references
come from its native text layer and are unproofread, so this remains exploratory
([labels](vinamilk-ar-2024-prose-12_ground_truth.json)). Its private Kaggle
dataset is ready. Tesseract, EasyOCR, and PaddleOCR CPU kernels have been
submitted as sessions became available.
Tesseract completed on Kaggle CPU with micro-CER/WER 0.3910/0.4574, 4.620
seconds/page, and 394 MiB peak RSS
([report](../../../artifacts/evaluation/ocr/pipeline/vinamilk-ar-2024-prose-12-cpu/tesseract.json)).
A local CPU rerun used the same 12 rendered-image hashes and scored
0.3917/0.4635 at 5.393 seconds/page and 669 MiB RSS; treat the resource
difference as host-specific. The native-text references remain unproofread,
and several full spreads have complex reading order. EasyOCR completed with micro-CER/WER
0.5919/0.7535 at 66.745 seconds/page and 4,312 MiB peak RSS (13.515 seconds
initialization). PaddleOCR completed at 0.6584/0.9653, 168.084 seconds/page,
and 5,899 MiB peak RSS (45.504 seconds initialization). The three-engine
comparison is
[here](../../../artifacts/evaluation/ocr/pipeline/vinamilk-ar-2024-prose-12-cpu/comparison.json).

A second new source sample uses 12 visually reviewed content pages from
[FPT's official 2024 Annual Report](https://fpt.com/api/media/bao_cao_thuong_nien_fpt_2024_883024f1dd.pdf),
including strategy, operating review, and management discussion. Pages retain
the document's repeated navigation rail and mixed charts/photos; native PDF
text remains unproofread and exploratory ([labels](fpt-ar-2024-prose-12_ground_truth.json)).
Its private Kaggle dataset is ready. Tesseract completed with micro-CER/WER
0.2754/0.3215 at 5.742 seconds/page and 310 MiB peak RSS
([report](../../../artifacts/evaluation/ocr/pipeline/fpt-ar-2024-prose-12-cpu/tesseract.json));
EasyOCR completed at 0.4766/0.5891, 47.200 seconds/page and 3,477 MiB peak
RSS (10.866 seconds initialization). The paired comparison is
[here](../../../artifacts/evaluation/ocr/pipeline/fpt-ar-2024-prose-12-cpu/comparison.json).
PaddleOCR CPU completed at 0.6357/0.9492, 171.044 seconds/page, and 7,551 MiB
peak RSS (49.875 seconds initialization). Its report is included in the same
three-engine hash-checked comparison. This run was particularly costly and
scored worse than Tesseract and EasyOCR on this exploratory set.

The [Techcombank 2024 Annual Report](https://techcombank.com/nha-dau-tu/bao-cao-thuong-nien)
adds 12 visually reviewed Vietnamese content spreads, including operating
reviews and management discussion. The source is the bank's official PDF;
native-text references are unproofread and exploratory
([labels](techcombank-ar-2024-prose-12_ground_truth.json)). Its private Kaggle
dataset is ready and the Tesseract CPU kernel has been submitted.
Tesseract completed with micro-CER/WER 0.2894/0.3596 at 7.746 seconds/page and
324 MiB peak RSS
([report](../../../artifacts/evaluation/ocr/pipeline/techcombank-ar-2024-prose-12-cpu/tesseract.json)).
EasyOCR completed at 0.6330/0.8195, 44.813 seconds/page, and 4,229 MiB peak RSS
(7.847 seconds initialization); the paired comparison is
[here](../../../artifacts/evaluation/ocr/pipeline/techcombank-ar-2024-prose-12-cpu/comparison.json).
PaddleOCR completed at 0.6712/0.9776, 180.277 seconds/page, and 5,811 MiB peak
RSS (57.561 seconds initialization). Its report is included in the same
three-engine, hash-checked comparison; these results remain exploratory because
the references are unproofread native PDF text.

The [GELEX 2024 Annual Report](https://gelex.vn/doc-cat/bao-cao-thuong-nien)
adds 12 visually reviewed pages covering management, operating results,
governance, and sustainability. The official report is a born-digital PDF with
native Vietnamese text; references are unproofread and exploratory
([labels](gelex-ar-2024-prose-12_ground_truth.json)). The private Kaggle dataset
is ready, with all three CPU kernels prepared.
Tesseract completed at micro-CER/WER 0.1917/0.2363, 4.820 seconds/page, and
296 MiB peak RSS
([report](../../../artifacts/evaluation/ocr/pipeline/gelex-ar-2024-prose-12-cpu/tesseract.json));
EasyOCR completed at 0.5934/0.7187, 65.518 seconds/page, and 4,218 MiB peak
RSS (12.348 seconds initialization). The paired comparison is
([here](../../../artifacts/evaluation/ocr/pipeline/gelex-ar-2024-prose-12-cpu/comparison.json)).
PaddleOCR remains queued for a CPU session.

The [PNJ 2024 Annual Report](https://www.pnj.com.vn/quan-he-co-dong/bao-cao-thuong-nien/)
adds 12 visually reviewed Vietnamese pages from the jewelry and retail sector,
covering strategy, governance, risk, and business context. The official PDF's
native text is unproofread, so the set is exploratory
([labels](pnj-ar-2024-prose-12_ground_truth.json)). Its private Kaggle dataset
is ready, with all three CPU kernels prepared.

The [Vinhomes 2024 Annual Report](https://vinhomes.vn/vi/bao-cao-thuong-nien)
adds 12 visually inspected narrative and mixed-layout pages from the real-estate
sector. The PDF was downloaded from the report filing at FPTS; its text-layer
references are unproofread, so this is exploratory
([labels](vinhomes-ar-2024-prose-12_ground_truth.json)). Its private Kaggle
dataset is verified to contain the PDF, labels, and evaluator. Tesseract CPU is
complete on Kaggle; at 180 DPI / PSM 3 it scored micro-CER/WER 0.3765/0.4194,
5.063 seconds/page, and 398 MiB peak RSS
([report](../../../artifacts/evaluation/ocr/pipeline/vinhomes-ar-2024-prose-12-cpu/tesseract.json)).
A local Tesseract 5.5.3 run used the identical 12 rendered-image hashes and
scored 0.3765/0.4210, 4.181 seconds/page, and 667 MiB peak RSS. The small
accuracy difference across Tesseract 5.3.4/5.5.3 is a useful reproducibility
check; host-specific latency and memory are not directly comparable
([local report](../../../artifacts/evaluation/ocr/pipeline/vinhomes-ar-2024-prose-12-cpu/local-tesseract.json)).
EasyOCR completed on Kaggle CPU with micro-CER/WER 0.6680/0.8634,
52.096 seconds/page, 4,301 MiB peak RSS, and 11.950 seconds initialization
([report](../../../artifacts/evaluation/ocr/pipeline/vinhomes-ar-2024-prose-12-cpu/easyocr.json)).
This is much worse than Tesseract on this exploratory set; the references are
unproofread native PDF text, so it is a screening signal rather than a model
selection result. PaddleOCR 3.7.0 completed on Kaggle CPU with micro-CER/WER
0.6656/0.9681, 152.125 seconds/page, 5,703 MiB peak RSS, and 50.130 seconds
initialization ([report](../../../artifacts/evaluation/ocr/pipeline/vinhomes-ar-2024-prose-12-cpu/paddleocr.json)).
The [paired comparison](../../../artifacts/evaluation/ocr/pipeline/vinhomes-ar-2024-prose-12-cpu/comparison.json)
contains all three engines on identical 12 page images.

The [Masan Group 2024 Annual Report](https://www.masangroup.com/vi/investor-relations/)
adds 12 visually reviewed Vietnamese pages with consumer, retail, governance,
and sustainability content. The Vietnamese report PDF is from the report filing
([PDF](https://file.fpts.com.vn/FileStore2/File/2025/04/25/20250425_20250425_-_MSN_-_Bao_cao_thuong_nien_2024_%28ban_thiet_ke%29_-_signed.pdf));
native-text references are unproofread and exploratory
([labels](masan-ar-2024-prose-12_ground_truth.json)). Its private Kaggle dataset
is verified to contain the PDF, labels, and evaluator. Local Tesseract at
180 DPI / PSM 3 scored micro-CER/WER 0.1390/0.1646, 4.942 seconds/page
([report](../../../artifacts/evaluation/ocr/pipeline/masan-ar-2024-prose-12-cpu/local-tesseract.json)).
The Kaggle Tesseract run scored 0.1520/0.1703 at 5.336 seconds/page and
294 MiB peak RSS ([report](../../../artifacts/evaluation/ocr/pipeline/masan-ar-2024-prose-12-cpu/tesseract.json));
it used the same 12 rendered-image hashes as the local run. The difference is
consistent with the Kaggle/local Tesseract version split (5.3.4/5.5.3).
EasyOCR 1.7.2 on Kaggle CPU scored micro-CER/WER 0.5884/0.7458 at
47.733 seconds/page, 3,176 MiB peak RSS, and 12.694 seconds initialization.
The [paired comparison](../../../artifacts/evaluation/ocr/pipeline/masan-ar-2024-prose-12-cpu/comparison.json)
confirms exact rendered-image hashes across Tesseract and EasyOCR, but the
native-text references remain unproofread. PaddleOCR CPU is still running.

The [Vietnam Airlines 2024 Annual Report](https://www.vietnamairlines.com/mm/vi/vietnam-airlines/investor-relations/annual-reports)
adds 12 visually inspected Vietnamese pages from the airline sector, covering
strategy, governance, and operations. The report PDF was obtained from its
filing ([PDF](https://file.fpts.com.vn/FileStore2/File/2025/04/21/20250421_20250418_-_HVN_-_Bao_cao_thuong_nien_2024.pdf));
native-text references are unproofread and exploratory
([labels](vietnam-airlines-ar-2024-prose-12_ground_truth.json)). Its private
Kaggle dataset is verified to include the PDF, labels, and evaluator. Local
Tesseract at 180 DPI / PSM 3 scored micro-CER/WER 0.2873/0.3191, 3.744
seconds/page ([report](../../../artifacts/evaluation/ocr/pipeline/vietnam-airlines-ar-2024-prose-12-cpu/local-tesseract.json)).
The three CPU kernels are prepared and await free sessions.

The [Traphaco 2024 Annual Report](https://traphaco.com.vn/media/investor_relation/files/XBjwWN/20250416_tra_ar2024---vn_2.pdf)
adds 12 narrative and mixed-layout pages from the Vietnamese pharmaceutical
sector. The native text layer has repeatable glyph-map errors; selected pages
were visually checked and known substitutions normalized in the references,
but the text was not proofread word by word
([labels](traphaco-ar-2024-prose-12_ground_truth.json)). The private Kaggle
dataset includes the corrected labels and updated evaluator. Local Tesseract
at 180 DPI / PSM 3 scored micro-CER/WER 0.3734/0.4628, 4.915 seconds/page
([report](../../../artifacts/evaluation/ocr/pipeline/traphaco-ar-2024-prose-12-cpu/local-tesseract.json));
the higher errors may reflect mixed-layout reading order as well as recognition.
EasyOCR and PaddleOCR kernels are prepared and await free sessions.

The [DHG Pharma 2024 Annual Report](https://dhgpharma.com.vn/sites/default/files/2025-03/Bao-cao-thuong-nien-2024_0.pdf)
adds 12 visually reviewed pages (PDF pages 8–11, 29–30, 32–33, 41–42, and
48–49) from the pharmaceutical sector. The official report is born-digital;
native-text references are not proofread word by word, so this remains an
exploratory text-recognition screen rather than scanned-PDF or production
evidence ([labels](dhgpharma-ar-2024-prose-12_ground_truth.json)). The private
Kaggle dataset is verified to contain the source PDF, labels, and evaluator.
Local Tesseract 5.5.3 at 180 DPI / PSM 3 scored micro-CER/WER 0.0202/0.0630
at 3.082 seconds/page and 534 MiB peak RSS
([report](../../../artifacts/evaluation/ocr/pipeline/dhgpharma-ar-2024-prose-12-cpu/local-tesseract.json));
Kaggle Tesseract 5.3.4 scored 0.0132/0.0332 at 3.469 seconds/page and 260 MiB
peak RSS ([report](../../../artifacts/evaluation/ocr/pipeline/dhgpharma-ar-2024-prose-12-cpu/tesseract.json)).
Both runs used identical rendered-image hashes, but the engine versions and
hosts differ. EasyOCR 1.7.2 on Kaggle CPU scored 0.0081/0.0179 at 33.268
seconds/page and 3,014 MiB peak RSS (11.552 seconds initialization). The
hash-checked Tesseract/EasyOCR comparison is
[here](../../../artifacts/evaluation/ocr/pipeline/dhgpharma-ar-2024-prose-12-cpu/comparison.json).
PaddleOCR CPU is still running. An initial inspection found corrupted font
mapping in portions of ACB's PDF text layer. Five clean pages were instead
cropped and 16 prose references manually transcribed and visually checked
from the rendered images by one reviewer; these single-reviewed crops remain
exploratory ([labels](acb-ar-2024-manual-prose-regions-16_ground_truth.json)).
The [ACB Annual Report 2024](https://acb.com.vn/nha-dau-tu/bao-cao-thuong-nien-2024)
is issuer-hosted. Local Tesseract 5.5.3 at 180 DPI / PSM 3 scored
micro-CER/WER 0.0061/0.0301 and macro page CER/WER 0.0065/0.0329 at
0.657 seconds/region and 461 MiB process peak RSS
([report](../../../artifacts/evaluation/ocr/pipeline/acb-ar-2024-manual-prose-regions-16-cpu/local-tesseract.json)).
Kaggle Tesseract 5.3.4 CPU scored micro-CER/WER 0.0028/0.0096 at
0.629 seconds/region and 251 MiB process peak RSS. EasyOCR 1.7.2 CPU scored
0.0126/0.0649 at 2.429 seconds/region, 12.129 seconds initialization, and
952 MiB process peak RSS. Both reports pair on all 16 rendered crop hashes
([comparison](../../../artifacts/evaluation/ocr/pipeline/acb-ar-2024-manual-prose-regions-16-cpu/comparison-tesseract-easyocr.json)).
PaddleOCR 3.7.0 CPU scored micro-CER/WER 0.1204/0.5191 at
10.207 seconds/region, 43.137 seconds initialization, and 1,499 MiB process
peak RSS. All three Kaggle reports pair on the same 16 rendered crop hashes
([comparison](../../../artifacts/evaluation/ocr/pipeline/acb-ar-2024-manual-prose-regions-16-cpu/comparison-all-engines.json)).
An EasyOCR 1.7.2 Tesla T4 rerun on those same hashes scored
0.0134/0.0704 at 0.424 seconds/region (10.371 seconds initialization),
1,425 MiB process peak RSS, and 266 MiB peak PyTorch GPU allocation
([report](../../../artifacts/evaluation/ocr/pipeline/acb-ar-2024-manual-prose-regions-16-cpu/easyocr-gpu.json)).
Compared with the CPU run, GPU latency was lower while CER/WER were slightly
higher; single-run host measurements are descriptive, and the one-reviewer
labels remain exploratory. PaddleOCR 3.7.0 on Tesla T4 returned the same
CER/WER as CPU (0.1204/0.5191) on the same 16 crop hashes, with latency
reduced to 0.299 seconds/region (34.725 seconds initialization). Process peak
RSS was 2,735 MiB; the evaluator's PyTorch-only CUDA allocator reported zero
for Paddle, so Paddle VRAM usage is unavailable in this run
([report](../../../artifacts/evaluation/ocr/pipeline/acb-ar-2024-manual-prose-regions-16-cpu/paddleocr-gpu.json)).

The official [Vincom Retail Annual Report 2024](https://ir.vincom.com.vn/bao-cao-thuong-nien/)
adds 12 visually inspected pages from its Vietnamese 84-page report
([labels](vincom-retail-ar-2024-prose-12_ground_truth.json)). The selected
pages contain narrative text mixed with photos, callouts, and some tables.
Their references come from the native PDF text layer and have not been
proofread word by word, so this is exploratory and ineligible for model
selection. Local Tesseract 5.5.3 at 180 DPI / PSM 3 scored micro-CER/WER
0.6815/0.8963, macro page CER/WER 0.6776/0.8951, and 5.880 seconds/page with
1,007 MiB process peak RSS
([report](../../../artifacts/evaluation/ocr/pipeline/vincom-retail-ar-2024-prose-12-local-tesseract.json)).
Kaggle Tesseract 5.3.4 CPU scored 0.6819/0.8974 at 4.778 seconds/page and
308 MiB process peak RSS; its PDF and rendered-page hashes match the local
run ([report](../../../artifacts/evaluation/ocr/pipeline/vincom-retail-ar-2024-prose-12-cpu-tesseract.json)).
EasyOCR 1.7.2 on Tesla T4 scored micro-CER/WER 0.5492/0.7071 and macro
CER/WER 0.5395/0.6979, at 9.322 seconds/page, 12.288 seconds initialization,
1,677 MiB process peak RSS, and 2,689/3,348 MiB PyTorch GPU allocated/reserved
memory. It improved text scores over Tesseract but was slower on these pages;
both references remain unproofread and the full-page spread layout confounds
the scores. The reports pair on all 12 image hashes
([comparison](../../../artifacts/evaluation/ocr/pipeline/vincom-retail-ar-2024-prose-12-comparison-tesseract-easyocr.json),
[EasyOCR](../../../artifacts/evaluation/ocr/pipeline/vincom-retail-ar-2024-prose-12-easyocr-gpu.json)).
PaddleOCR 3.7.0 on Tesla T4 scored 0.1706/0.5355 at 2.960 seconds/page
(35.133 seconds initialization), 3,006 MiB process peak RSS; PyTorch-only
GPU memory telemetry does not measure Paddle allocations. All three reports
pair on the same 12 rendered-page hashes
([comparison](../../../artifacts/evaluation/ocr/pipeline/vincom-retail-ar-2024-prose-12-comparison-all-engines.json),
[PaddleOCR](../../../artifacts/evaluation/ocr/pipeline/vincom-retail-ar-2024-prose-12-paddleocr-gpu.json)).
The high error rate may reflect the full-page two-page spread layout and
unreviewed reference reading order; it should not be interpreted as a clean
text-accuracy estimate. The source is issuer-hosted; its PDF hash is recorded
in the label manifest.

The [HDBank 2024 Annual Report](https://cdn.hdbank.com.vn/hdbank/bctn/2024/pdf/BCTN-HDBANK-2024.pdf)
adds 12 visually reviewed left-page regions from the official 155-page PDF,
covering risk, governance, operations, and sustainability
([labels](hdbank-ar-2024-prose-12_ground_truth.json)). The PDF text is not
proofread. Its text-layer block order was corrected to match the rendered
reading order on pages 30, 107, and 108; the references remain exploratory
and are not eligible for production selection. Local Tesseract 5.5.3 at
180 DPI / PSM 3 scored micro-CER/WER 0.1202/0.1480 at 3.143 seconds/page,
842 MiB process peak RSS and 637 MiB child peak RSS
([report](../../../artifacts/evaluation/ocr/pipeline/hdbank-ar-2024-prose-12-cpu/local-tesseract.json)).
The private Kaggle dataset contains the PDF, labels, and evaluator. Tesseract,
EasyOCR, and PaddleOCR CPU kernels are running.

The official [PV Power 2024 Annual Report](https://pvpower.vn/pow-media/to-ir/18-4-25---BCTN-2024---VIET.pdf)
adds 24 half-page samples from 12 visually inspected landscape spreads
([labels](pvpower-ar-2024-prose-halves-24_ground_truth.json)). The PDF places
two facing report pages on each landscape sheet, so the benchmark clips each
half separately. Native PDF text is unproofread and column order can still
inflate CER/WER; this set is exploratory. Local Tesseract 5.5.3 at 180 DPI /
PSM 3 scored micro-CER/WER 0.3242/0.3795, 2.743 seconds per half-page, and
841 MiB process peak RSS ([report](../../../artifacts/evaluation/ocr/pipeline/pvpower-ar-2024-prose-halves-24-cpu/local-tesseract.json)).
The labels and source need more reading-order review before treating the score
as model accuracy. A separate full-spread pilot is retained at
`pvpower-ar-2024-prose-12_ground_truth.json`; its un-clipped pages are less
comparable because each OCR image contains two report pages. The private
Kaggle bundle is verified to contain the source PDF, labels, and evaluator.
EasyOCR 1.7.2 on Kaggle CPU scored micro-CER/WER 0.3831/0.4670, 31.625
seconds per half-page, 3,035 MiB peak RSS, and 11.224 seconds initialization
([report](../../../artifacts/evaluation/ocr/pipeline/pvpower-ar-2024-prose-halves-24-cpu/easyocr.json)).
Kaggle Tesseract 5.3.4 scored 0.3229/0.3738 at 3.109 seconds per
half-page and 266 MiB peak RSS. PaddleOCR 3.7.0 CPU scored 0.5616/0.8766
at 62.225 seconds per half-page, 38.975 seconds initialization, and 3,640
MiB peak RSS. All three exact-render results are paired
([comparison](../../../artifacts/evaluation/ocr/pipeline/pvpower-ar-2024-prose-halves-24-cpu/comparison-all-engines.json));
reading-order issues and unproofread references remain a major limitation.

The [VOSA 2024 Annual Report](https://vosa.com.vn/uploads/tailieu/B%C3%81O%20C%C3%81O%20TH%C6%AF%E1%BB%9CNG%20NI%C3%8AN%20N%C4%82M%20%202024%20-%20Final..pdf)
adds two full-page references from a scanned Vietnamese business report. Its
embedded text layer has broken character mappings, so the references were
transcribed from the rendered page images rather than copied from PDF text
([labels](vosa-ar-2024-scan-manual-2_ground_truth.json)). One reviewer checked
both pages; the set is too small and unadjudicated for model selection. Local
Tesseract 5.5.3 at 180 DPI / PSM 3 scored micro-CER/WER 0.0257/0.0976 at 2.438
seconds per page and 842 MiB process peak RSS
([report](../../../artifacts/evaluation/ocr/pipeline/vosa-ar-2024-scan-manual-2-cpu/local-tesseract-psm3.json)).
Kaggle Tesseract 5.3.4 scored 0.0167/0.0576 at 3.003 seconds per page and
268 MiB peak RSS ([report](../../../artifacts/evaluation/ocr/pipeline/vosa-ar-2024-scan-manual-2-cpu/tesseract.json));
both runs used identical rendered-image hashes. The version/host split and
two-page sample limit this to an exploratory check. PaddleOCR 3.7.0 on Kaggle
CPU scored micro-CER/WER 0.0997/0.4243 at 63.781 seconds per page, 3,506 MiB
peak RSS, and 48.041 seconds initialization
([report](../../../artifacts/evaluation/ocr/pipeline/vosa-ar-2024-scan-manual-2-cpu/paddleocr.json)).
The paired Tesseract/PaddleOCR comparison confirms identical page-image hashes
([comparison](../../../artifacts/evaluation/ocr/pipeline/vosa-ar-2024-scan-manual-2-cpu/comparison-tesseract-paddleocr.json));
EasyOCR 1.7.2 CPU scored 0.0093/0.0388 at 35.292 seconds/page,
10.864 seconds initialization, and 3,024 MiB peak RSS. The three-engine
comparison confirms identical page-image hashes
([comparison](../../../artifacts/evaluation/ocr/pipeline/vosa-ar-2024-scan-manual-2-cpu/comparison-all-engines.json)).
These two pages are a small scan pilot, not a model-selection set.

An expanded VOSA set adds the visually transcribed page 6 for risk and
sustainability prose ([three-page labels](vosa-ar-2024-scan-manual-3_ground_truth.json)).
Local Tesseract 5.5.3 at 180 DPI / PSM 3 scored micro-CER/WER 0.0283/0.1014,
2.810 seconds per page, and 842 MiB peak RSS
([report](../../../artifacts/evaluation/ocr/pipeline/vosa-ar-2024-scan-manual-3-cpu/local-tesseract.json)).
Its private Kaggle bundle is verified. EasyOCR 1.7.2 on Kaggle CPU scored
micro-CER/WER 0.0112/0.0477
at 39.668 seconds per page, 3,051 MiB peak RSS, and 12.148 seconds
initialization ([report](../../../artifacts/evaluation/ocr/pipeline/vosa-ar-2024-scan-manual-3-cpu/easyocr.json)).
Its page hashes match local Tesseract on all three clips
([paired comparison](../../../artifacts/evaluation/ocr/pipeline/vosa-ar-2024-scan-manual-3-cpu/comparison-tesseract-easyocr.json)).
PaddleOCR 3.7.0 CPU completed at micro-CER/WER 0.1104/0.4681, 71.683
seconds/page, 53.683 seconds initialization, and 3,533 MiB peak RSS. The
EasyOCR/PaddleOCR exact-render pairing is
[here](../../../artifacts/evaluation/ocr/pipeline/vosa-ar-2024-scan-manual-3-cpu/comparison-easyocr-paddleocr.json).
The comparison across all three engines is
[here](../../../artifacts/evaluation/ocr/pipeline/vosa-ar-2024-scan-manual-3-cpu/comparison-all-engines.json).
This is only a three-page, single-reviewer screen and not a model-selection
result.

The [SPC 2024 Annual Report](https://file.fpts.com.vn/FileStore2/File/2025/04/15/SPC_2025-4-15_36e8106_VN_BaoCaoThuongNien_2024.pdf)
adds two manually transcribed scanned pages from an agrochemical manufacturer.
The source PDF has facing pages on one landscape sheet; labels cover printed
pages 11 and 12 as separate half-page crops
([labels](spc-ar-2024-scan-manual-2_ground_truth.json)). One reviewer visually
checked the full references, so this is exploratory. Local Tesseract 5.5.3 at
180 DPI / PSM 3 scored micro-CER/WER 0.0616/0.1272, 1.397 seconds per page,
and 843 MiB process peak RSS
([report](../../../artifacts/evaluation/ocr/pipeline/spc-ar-2024-scan-manual-2-cpu/local-tesseract.json)).
The private Kaggle bundle is verified and all engines use the same 180-DPI
half-page crops. Kaggle Tesseract 5.3.4 scored micro-CER/WER 0.0554/0.1060
at 1.418 seconds/page and 259 MiB process peak RSS. EasyOCR 1.7.2 CPU scored
0.0279/0.0617 at 18.094 seconds/page, 11.134 seconds initialization, and
1,756 MiB peak RSS. The exact-render comparison is
[here](../../../artifacts/evaluation/ocr/pipeline/spc-ar-2024-scan-manual-2-cpu/comparison-tesseract-easyocr.json).
PaddleOCR 3.7.0 CPU scored 0.1413/0.5202 at 37.479 seconds/page, 51.252
seconds initialization, and 2,506 MiB peak RSS. The exact-render comparison
across all three engines is
[here](../../../artifacts/evaluation/ocr/pipeline/spc-ar-2024-scan-manual-2-cpu/comparison-all-engines.json).
EasyOCR has the lowest CER/WER on these two pages but is much slower and uses
more memory than Tesseract. This single-reviewer two-page scan remains
exploratory, not enough for model selection.

The [VSC / Vicostone 2024 Annual Report](https://www.phs.vn/tin-tuc/vcs-bao-cao-thuong-nien-2024/6264984)
adds eight visually selected single-column text crops from four landscape
spreads ([labels](vsc-ar-2024-prose-columns-8_ground_truth.json)). The PDF
source SHA-256 is recorded in the labels and the private Kaggle bundle contains
the source, labels, and evaluator. References come from the PDF text layer and
are not proofread word by word, so these scores are exploratory. Local
Tesseract 5.5.3 at 180 DPI / PSM 3 scored micro-CER/WER 0.0030/0.0113 at
0.975 seconds per crop and 506 MiB process peak RSS
([report](../../../artifacts/evaluation/ocr/pipeline/vsc-ar-2024-prose-columns-8-cpu/local-tesseract.json)).
Kaggle Tesseract 5.3.4 scored 0.0034/0.0118 at 0.919 seconds per crop and
252 MiB peak RSS. EasyOCR 1.7.2 CPU scored 0.0116/0.0581 at 4.700
seconds/crop, 11.606 seconds initialization, and 1,038 MiB peak RSS. The
exact-render comparison is
[here](../../../artifacts/evaluation/ocr/pipeline/vsc-ar-2024-prose-columns-8-cpu/comparison-tesseract-easyocr.json);
all eight rendered hashes also match the local Tesseract run. PaddleOCR CPU
scored 0.1231/0.5456 at 20.469 seconds/crop, 47.504 seconds initialization,
and 1,608 MiB peak RSS. The three-engine exact-render comparison is
[here](../../../artifacts/evaluation/ocr/pipeline/vsc-ar-2024-prose-columns-8-cpu/comparison-all-engines.json).
Tesseract had the lowest observed error and resource use on these eight
single-column crops. The unproofread text-layer references make this an
exploratory screen only. These crops evaluate text recognition, not full-page
layout or reading order.

The [SJ1 / Hung Hau Agriculture 2024 Annual Report](https://files.vcbs.com.vn/algonews/hnx/2024/12/26/NTQwOTQ1_000000014338650_VI_BaoCaoThuongNien_2024.pdf)
adds ten visually selected prose-column crops covering development, operations,
and environmental/social responsibility
([labels](sj1-ar-2024-prose-columns-10_ground_truth.json)). This adds an
agriculture and seafood issuer to the enterprise corpus. The report is
born-digital, and references are unproofread native text, so results remain
exploratory. Local Tesseract 5.5.3 at 180 DPI / PSM 3 scored micro-CER/WER
0.0043/0.0175 at 1.035 seconds per crop and 501 MiB process peak RSS
([report](../../../artifacts/evaluation/ocr/pipeline/sj1-ar-2024-prose-columns-10-cpu/local-tesseract.json)).
The private Kaggle bundle was verified to contain the report, labels, and
evaluator. Kaggle Tesseract 5.3.4 scored 0.0027/0.0104 at 1.097 seconds/crop
and 253 MiB peak RSS. EasyOCR 1.7.2 CPU scored 0.0195/0.0880 at 6.627
seconds/crop, 11.814 seconds initialization, and 1,249 MiB peak RSS. Their
exact-render comparison is
[here](../../../artifacts/evaluation/ocr/pipeline/sj1-ar-2024-prose-columns-10-cpu/comparison-tesseract-easyocr.json).
PaddleOCR 3.7.0 CPU scored 0.1242/0.5298 at 26.136 seconds/crop,
51.601 seconds initialization, and 1,897 MiB peak RSS. The exact-render
comparison across all three engines is
[here](../../../artifacts/evaluation/ocr/pipeline/sj1-ar-2024-prose-columns-10-cpu/comparison-all-engines.json).
Tesseract had the lowest observed error and resource use on these ten
single-column crops. References are unproofread native PDF text, so this is
exploratory and not a model-selection result. These crops measure text
recognition, not layout detection or full-page reading order.

The [HGM / Ha Giang Mechanical and Mineral 2024 Annual Report](https://owa.hnx.vn/ftp/cims/2025/3_W5/000000014671229_VI_BaoCaoThuongNien_2024.pdf)
adds four manually transcribed half-page crops from its scanned audited
financial statements ([labels](hgm-ar-2024-scan-manual-4_ground_truth.json)).
One reviewer visually checked the references; the sample is exploratory and
ineligible for primary model selection. All engines use the same 180-DPI
half-page renders, with matching image hashes. Kaggle Tesseract 5.3.4 scored
0.0431/0.0739 CER/WER at 2.724 seconds/crop and 276 MiB peak RSS. EasyOCR
1.7.2 CPU scored 0.0721/0.1855 at 27.031 seconds/crop, 9.413 seconds
initialization, and 3,051 MiB peak RSS. Their paired comparison is
[here](../../../artifacts/evaluation/ocr/pipeline/hgm-ar-2024-scan-manual-4-cpu/comparison-tesseract-easyocr.json).
PaddleOCR 3.7.0 CPU scored 0.1426/0.4705 at 72.552 seconds/crop,
48.230 seconds initialization, and 3,581 MiB peak RSS. The paired comparison
across all three engines is
[here](../../../artifacts/evaluation/ocr/pipeline/hgm-ar-2024-scan-manual-4-cpu/comparison-all-engines.json).
Tesseract had the lowest observed error and resource use on these four crops.
The sample is too small and single-reviewed to select a production engine.
These scans contain stamps and signatures; the benchmark measures text
recognition only, not table or layout extraction.

The [Gemadept 2024 Annual Report](https://www.gemadept.com.vn/wp-content/uploads/2025/04/GMD_Bao-cao-thuong-nien-2024.pdf)
adds 16 prose regions across governance, financial analysis, port operations,
shipping, logistics, risk, and environmental reporting
([labels](gmd-ar-2024-prose-regions-16_ground_truth.json)). The 80-page,
issuer-hosted PDF is a two-page-spread layout; each crop isolates one selected
text region. The PDF text layer has not been proofread and shows spacing or
glyph artifacts in some spans, so this set is exploratory and ineligible for
primary model selection. Local Tesseract 5.5.3 at 180 DPI / PSM 3 scored
micro-CER/WER 0.0736/0.0983 at 3.028 seconds/crop; evaluator process peak RSS
was 958 MiB ([report](../../../artifacts/evaluation/ocr/pipeline/gmd-ar-2024-prose-regions-16-cpu/local-tesseract.json)).
The private Kaggle dataset was verified to contain the PDF, labels, and
evaluator. Kaggle Tesseract 5.3.4 scored 0.0721/0.0933 at 2.633 seconds/crop
and 253 MiB peak RSS; all 16 Kaggle rendered-image hashes match the local run
([report](../../../artifacts/evaluation/ocr/pipeline/gmd-ar-2024-prose-regions-16-cpu/tesseract.json)).
EasyOCR 1.7.2 CPU scored 0.0953/0.1824 at 25.123 seconds/crop, 11.106 seconds
initialization, and 3,232 MiB process peak RSS. PaddleOCR 3.7.0 CPU scored
0.1738/0.5543 at 68.784 seconds/crop, 49.958 seconds initialization, and
3,553 MiB process peak RSS. All three engines used CPU and pair on the exact
same 16 source/render hashes
([all-engine comparison](../../../artifacts/evaluation/ocr/pipeline/gmd-ar-2024-prose-regions-16-cpu/comparison-all-engines.json)).
Tesseract had the lowest observed errors and resource use on this sample.
One region (PDF page 34) has an unusually high CER against the PDF text layer;
the reference needs visual review before interpreting aggregate model scores.

The [Viettel Post Annual Report 2024](https://en.viettelpost.com.vn/10992/app-privacy-policy)
adds 16 pages from postal/logistics operations, corporate governance, and
sustainability ([labels](vtp-ar-2024-prose-16_ground_truth.json)). The issuer
announcement links the annual report; the Vietnamese PDF copy used here is
hosted at [24hmoney](https://cdn.24hmoney.vn/upload/file/2025-2/2025-06-26/no-name-1750883098.pdf).
Its text layer has character-mapping artifacts and is unproofread, so this
screen is exploratory and ineligible for model selection. Local Tesseract
5.5.3 at 180 DPI / PSM 3 scored micro-CER/WER 0.1234/0.1694, with macro page
CER/WER 0.2037/0.2570 and 4.700 seconds/page
([report](../../../artifacts/evaluation/ocr/pipeline/vtp-ar-2024-prose-16-cpu/local-tesseract.json)).
The private Kaggle bundle was verified to contain the 98-page source PDF,
labels, and evaluator. Kaggle Tesseract 5.3.4 scored micro-CER/WER
0.1227/0.1669 and macro page CER/WER 0.2027/0.2548 at 4.548 seconds/page
and 270 MiB process peak RSS. Its 16 page IDs, source hashes, and rendered
image hashes match the local Tesseract run. Kaggle EasyOCR 1.7.2 CPU scored
0.5563/0.7113 at 61.313 seconds/page, 15.215 seconds initialization, and
4,181 MiB process peak RSS. The reports pair on all 16 source/render hashes
([comparison](../../../artifacts/evaluation/ocr/pipeline/vtp-ar-2024-prose-16-cpu/comparison-tesseract-easyocr.json)).
Because many PDF reference strings contain glyph-mapping defects, these large
errors are exploratory only. PaddleOCR 3.7.0 CPU scored micro-CER/WER
0.6074/0.9160 at 153.885 seconds/page, 46.691 seconds initialization, and
5,709 MiB process peak RSS. All three Kaggle reports pair on the same 16
source/render hashes
([comparison](../../../artifacts/evaluation/ocr/pipeline/vtp-ar-2024-prose-16-cpu/comparison-all-engines.json)).

The [MWG Annual Report 2024](https://cdnv2.tgdd.vn/mwgvn/investorrelations/files/posts/2025/4/0/64/c2/64c27697a67a3feb53d97256e4de3d7e.pdf)
adds one image-based Vietnamese prose region from the chairperson's letter
([labels](mwg-ar-2024-chair-message-region-1_ground_truth.json)). The 2,175-
character reference was transcribed from and visually checked against the
rendered page by one reviewer. Local Tesseract 5.5.3 at 180 DPI / PSM 3 scored
CER/WER 0.0056/0.0214 at 2.228 seconds; Kaggle Tesseract 5.3.4 scored
0.0047/0.0193 at 2.984 seconds and 255 MiB process peak RSS. Both runs have
the same rendered-image hash
([local report](../../../artifacts/evaluation/ocr/pipeline/mwg-ar-2024-chair-message-region-1-cpu/local-tesseract.json),
[Kaggle report](../../../artifacts/evaluation/ocr/pipeline/mwg-ar-2024-chair-message-region-1-cpu/tesseract.json)).
EasyOCR 1.7.2 CPU scored 0.0113/0.0493 at 20.852 seconds/crop,
11.611 seconds initialization, and 1,601 MiB process peak RSS; its rendered
image hash pairs with Kaggle Tesseract
([comparison](../../../artifacts/evaluation/ocr/pipeline/mwg-ar-2024-chair-message-region-1-cpu/comparison-tesseract-easyocr.json)).
PaddleOCR 3.7.0 CPU scored 0.1265/0.5375 at 55.218 seconds/crop,
44.470 seconds initialization, and 2,110 MiB process peak RSS. All three
Kaggle engines used the same rendered-image hash
([all-engine comparison](../../../artifacts/evaluation/ocr/pipeline/mwg-ar-2024-chair-message-region-1-cpu/comparison-all-engines.json)).
It is useful as a small manually transcribed scan fixture, but one crop and one
reviewer are not enough for model selection.

The same [MWG Annual Report 2024](https://cdnv2.tgdd.vn/mwgvn/investorrelations/files/posts/2025/4/0/64/c2/64c27697a67a3feb53d97256e4de3d7e.pdf)
adds 11 manually transcribed prose blocks from its timeline pages 15–16
([labels](mwg-ar-2024-timeline-regions-11_ground_truth.json)). The regions
cover milestones from 2014 through 2023 and were visually checked by one
reviewer. Local Tesseract 5.5.3 at 180 DPI / PSM 3 scored micro-CER/WER
0.0239/0.0885, macro page CER/WER 0.0230/0.0838, and 0.798 seconds/region
([report](../../../artifacts/evaluation/ocr/pipeline/mwg-ar-2024-timeline-regions-11-cpu/local-tesseract.json)).
Kaggle Tesseract 5.3.4 scored 0.0037/0.0144 at 0.574 seconds/region and
254 MiB process peak RSS. EasyOCR 1.7.2 CPU scored 0.0698/0.2710 at
2.351 seconds/region, 12.129 seconds initialization, and 957 MiB process peak
RSS. Both pair on all 11 rendered-image hashes
([comparison](../../../artifacts/evaluation/ocr/pipeline/mwg-ar-2024-timeline-regions-11-cpu/comparison-tesseract-easyocr.json)).
This dataset remains exploratory and single-reviewed. Its private Kaggle
bundle was verified to contain the 96-page PDF, labels, and evaluator.
PaddleOCR 3.7.0 CPU scored micro-CER/WER 0.1153/0.4735 at 9.193
seconds/region, 48 seconds initialization, and 1,599 MiB process peak RSS
([report](../../../artifacts/evaluation/ocr/pipeline/mwg-ar-2024-timeline-regions-11-cpu/paddleocr.json)).
The text, image hashes, and single-review limitation still make this an
exploratory result.

The [PVI Annual Report 2024](https://pviholdings.com.vn/vi/report) adds 21
prose-rich half-page crops from 12 visually inspected landscape spreads
([labels](pvi-ar-2024-prose-halves-22_ground_truth.json)). The PDF is served by
PVI's official report page. Its native PDF text is unproofread and some halves
have substantial reading-order or graphic contamination, so this dataset is
exploratory and ineligible for primary model selection. Local Tesseract 5.5.3
at 180 DPI / PSM 3 scored micro-CER/WER 0.1428/0.2648, macro page CER/WER
0.1509/0.2743, and 5.682 seconds/crop
([report](../../../artifacts/evaluation/ocr/pipeline/pvi-ar-2024-prose-halves-22-cpu/local-tesseract.json)).
Kaggle Tesseract 5.3.4 CPU scored micro-CER/WER 0.1322/0.2267, macro page
CER/WER 0.1405/0.2367, 4.168 seconds/crop, and 301 MiB process peak RSS
([report](../../../artifacts/evaluation/ocr/pipeline/pvi-ar-2024-prose-halves-22-cpu/tesseract.json)).
Its 21 page IDs, source hashes, and rendered-image hashes match the local
Tesseract run. Kaggle EasyOCR 1.7.2 CPU scored micro-CER/WER 0.2184/0.3308,
macro page CER/WER 0.1885/0.2950, 27.509 seconds/crop, 8.260 seconds
initialization, and 3,082 MiB process peak RSS. It pairs with Tesseract on all
21 source/render hashes
([comparison](../../../artifacts/evaluation/ocr/pipeline/pvi-ar-2024-prose-halves-22-cpu/comparison-tesseract-easyocr.json)).
PaddleOCR 3.7.0 CPU scored micro-CER/WER 0.3940/0.7414, macro page
CER/WER 0.3576/0.7085, 94.724 seconds/crop, 45.328 seconds initialization,
and 3,689 MiB process peak RSS. All three reports pair on the same 21 source
and rendered-image hashes
([comparison](../../../artifacts/evaluation/ocr/pipeline/pvi-ar-2024-prose-halves-22-cpu/comparison-all-engines.json)).
The largest Tesseract errors are on pages 26 and 32, where infographic and
chart content makes native-text reading order a poor OCR reference.

The [Vietjet Annual Report 2024](https://ir.vietjetair.com/File_Upload/thong-tin-tai-chinh/bao-cao-thuong-nien-parent/bao-cao-thuong-nien/VJ%20BAO%20CAO%2024_VIET_DOUBLE%20PAGE%20-%20compressed.pdf)
adds 13 prose-rich half-page crops across eight visually reviewed double-page
spreads ([labels](vietjet-ar-2024-prose-halves-13_ground_truth.json)). The
official issuer PDF has native Vietnamese text; references are unproofread and
some callout-heavy regions have OCR/layout-order mismatch, so this dataset is
exploratory and ineligible for primary model selection. Local Tesseract 5.5.3
at 180 DPI / PSM 3 scored micro-CER/WER 0.1756/0.2215, macro page CER/WER
0.2030/0.2558, and 4.530 seconds/crop
([local report](../../../artifacts/evaluation/ocr/pipeline/vietjet-ar-2024-prose-halves-13-cpu/local-tesseract.json)).
Kaggle Tesseract 5.3.4 CPU scored micro-CER/WER 0.1708/0.1986, macro page
CER/WER 0.1991/0.2340, 2.746 seconds/crop, and 300 MiB process peak RSS. Its
13 page IDs, source hashes, and rendered-image hashes match the local run.
([Kaggle report](../../../artifacts/evaluation/ocr/pipeline/vietjet-ar-2024-prose-halves-13-cpu/tesseract.json)).
Kaggle EasyOCR 1.7.2 CPU scored micro-CER/WER 0.3939/0.4662, macro page
CER/WER 0.4274/0.5070, 38.901 seconds/crop, 13.064 seconds initialization,
and 3,067 MiB process peak RSS. It pairs with Tesseract on all 13 crops
([comparison](../../../artifacts/evaluation/ocr/pipeline/vietjet-ar-2024-prose-halves-13-cpu/comparison-tesseract-easyocr.json)).
PaddleOCR 3.7.0 CPU scored micro-CER/WER 0.4372/0.7435, macro page
CER/WER 0.4671/0.7733, 67.630 seconds/crop, 43.274 seconds initialization,
and 3,676 MiB process peak RSS. All three reports pair on the same 13 crop
hashes ([comparison](../../../artifacts/evaluation/ocr/pipeline/vietjet-ar-2024-prose-halves-13-cpu/comparison-all-engines.json)).

## Benchmark experience and production selection

- Keep OCR text recognition separate from layout detection and table
  extraction. For prose CER/WER, avoid table-heavy pages and ambiguous reading
  order; benchmark tables with row/cell or coordinate-aware measures.
- Give every labeled page or crop a stable unique `id`. OCR reports preserve
  that ID so multiple crops from the same PDF page remain distinct when paired.
- Compare engines on the exact same rendered image hashes, source pages,
  language and resolution. Record model initialization separately from page
  latency and host/GPU memory, and label the device; CPU and GPU resource
  numbers are not a fair speed ranking.
- The Kaggle screening notebook installs CPU PaddlePaddle and does not enable
  CUDA. EasyOCR can use the Kaggle GPU when CUDA-enabled PyTorch is present;
  Tesseract remains the CPU reference. Treat GPU runs as a separate hardware
  comparison and verify the runtime device before accepting their metrics.
- Verify the actual runtime device before accepting a GPU benchmark. A recent
  FPT EasyOCR Kaggle run persisted GPU accelerator metadata but the runtime
  lacked `libnvidia-ml.so` and used CPU-only PyTorch (`2.11.0+cpu`, CUDA false);
  the strict GPU guard rejected it, so it has no OCR result and is excluded.
- A BIDV PaddleOCR Kaggle run failed before OCR because pip repeatedly timed
  out reaching Paddle's CPU wheel index. The failed run has no accuracy result;
  the reusable notebook now installs the matching PaddlePaddle CPU wheel from
  PyPI, where the project publishes a Python 3.13 Linux x86-64 wheel. Retry
  failed Paddle runs with this installation path after a CPU session opens.
- Treat PDF-text references as exploratory until a human proofreads them
  against the rendered page. A visually checked manifest is not proof that
  every reference word and reading order is correct.
- Traphaco's report demonstrates that PDF text layers can contain broken font
  mappings even when the rendered page looks normal. Its evaluator supports an
  explicit `reference_annotation_method`; glyph-normalized references keep the
  correction provenance visible without labeling them as human transcriptions.
- Surya is excluded from new screening runs. Its CPU pilot took 676.6 seconds
  on one Vingroup page. On the earlier five-page English screen, Surya scored
  micro-CER/WER 0.0408/0.0435 versus EasyOCR 0.0439/0.0560, while taking about
  2.8 times the OCR latency and 1.9 times the peak RSS. That small accuracy
  difference did not justify the measured resource cost for continued
  screening; the previous Surya reports remain archived as historical
  evidence.
- **Current production choice: Tesseract as the primary OCR engine** for the
  existing CPU upload path. This is an operational choice, not a statistically
  confirmed winner: every current set remains ineligible for primary-metric
  selection until its references are adjudicated. Tesseract is already used by
  PDF and image uploads, keeps host memory and latency low, and usually had the
  best error/resource trade-off on the born-digital Vietnamese report screens.
  Some scan sets favored EasyOCR on CER/WER (for example LAS and VOSA), but its
  measured CPU/GPU memory and latency costs are much higher; the small,
  single-reviewed scan sets do not justify replacing the universal default.
  Keep EasyOCR as the alternative to revisit if scan-heavy production traffic
  makes that accuracy gain worth the cost. PaddleOCR's high throughput on some
  GPU runs did not offset its weak CER/WER on the reviewed scan screens.
- Production currently uses Tesseract PSM 11 for page/image text and PSM 3 for
  PDF table OCR; most engine comparisons used PSM 3, so their Tesseract scores
  do not directly represent the current upload configuration. No model or
  upload setting was changed as part of this decision. Surya remains excluded
  from new screening because its resource cost was not justified by its
  measured accuracy gains.

### Kinh Bắc (KBC) Annual Report 2024: 16 pages

The issuer-hosted [KBC Annual Report 2024](https://kinhbaccity.vn/Pic/files/20250418-kbc-bao-cao-thuong-nien-2024.pdf)
adds 16 visually screened prose/mixed pages from an 80-page report
([labels](kbc-ar-2024-prose-pages-16_ground_truth.json)). Local Tesseract
5.5.3 at 180 DPI / PSM 3 scored micro-CER/WER 0.0567/0.1116, macro
CER/WER 0.0640/0.1164, and 2.825 seconds/page
([report](../../../artifacts/evaluation/ocr/pipeline/kbc-ar-2024-prose-pages-16-tesseract.json)).
Page-level scores vary substantially; pages with dense graphic or mixed layouts
can distort aggregate CER/WER. The references are unproofread native PDF text,
so this exploratory set is not eligible for primary model selection. Kaggle
Tesseract 5.3.4 scored micro-CER/WER 0.0497/0.0857,
macro CER/WER 0.0574/0.0914, and 3.015 seconds/page on the exact same 16
rendered-image hashes ([report](../../../artifacts/evaluation/ocr/pipeline/kbc-ar-2024-prose-pages-16-kaggle-tesseract.json)).
This differs from local Tesseract 5.5.3 and local hardware; treat latency as
descriptive rather than a direct speed ranking. PaddleOCR 3.7.0 on Tesla T4
scored micro-CER/WER 0.1282/0.4806 and macro CER/WER 0.1342/0.4861 at 1.324
seconds/page (37.661 seconds initialization) and 2,831 MiB process peak RSS
([report](../../../artifacts/evaluation/ocr/pipeline/kbc-ar-2024-prose-pages-16-paddleocr-gpu.json)). The PaddleOCR run was repeated under its dedicated Kaggle kernel `ltrngnhn/kbc-ar-2024-ocr-paddleocr-gpu`; all 16 page IDs, rendered-image hashes, page scores, and aggregate CER/WER exactly matched the earlier run, confirming the result despite the original kernel-slug setup mistake. The clean run measured 33.575 seconds initialization, 1.306 seconds/page, and 2,827 MiB process peak RSS. Paddle's CUDA allocation is not captured by the PyTorch-only allocator counter.
EasyOCR 1.7.2 on Tesla T4 scored micro-CER/WER 0.0296/0.0373 at 4.171
seconds/page (10.192 seconds initialization), with 1,589 MiB process peak RSS
and 1,863/2,300 MiB PyTorch CUDA allocated/reserved
([report](../../../artifacts/evaluation/ocr/pipeline/kbc-ar-2024-prose-pages-16-easyocr-gpu.json)).
The [all-engine paired comparison](../../../artifacts/evaluation/ocr/pipeline/kbc-ar-2024-prose-pages-16-comparison-all-engines.json)
confirms the same 16 rendered-image hashes. EasyOCR had the lowest observed
CER/WER; PaddleOCR was fastest per page. Tesseract ran on CPU while the other
two used a Tesla T4, so latency is descriptive. All metrics remain exploratory
because the reference text is unproofread.

### Hoa Sen Group Annual Report FY2023-2024: 16 half-page regions

The issuer-hosted [Hoa Sen Group Annual Report FY2023-2024](https://hoasengroup.vn/wp-content/uploads/2025/01/bao-cao-thuong-nien-23-24.pdf)
adds 16 visually screened half-page regions from eight A3 landscape pages
([labels](hoa-sen-ar-2023-2024-prose-regions-16_ground_truth.json)). Local
Tesseract 5.5.3 at 180 DPI / PSM 3 scored micro-CER/WER 0.0878/0.2756, macro
CER/WER 0.1135/0.2992, 17.698 seconds/region, and 370 MiB peak RSS
([report](../../../artifacts/evaluation/ocr/pipeline/hoa-sen-ar-2023-2024-prose-regions-16-local-tesseract.json)).
Kaggle Tesseract 5.3.4 scored micro-CER/WER 0.0745/0.1861, macro
CER/WER 0.0941/0.2100, 4.715 seconds/region, and 303 MiB peak RSS on the same
16 rendered-image hashes
([report](../../../artifacts/evaluation/ocr/pipeline/hoa-sen-ar-2023-2024-prose-regions-16-kaggle-tesseract.json)).
Versions and CPU hosts differ, so compare latency descriptively.
The regions are born-digital mixed prose, not physical scans; PDF-text references
are unproofread and the set is not eligible for primary model selection.
EasyOCR 1.7.2 on Tesla T4 scored micro-CER/WER 0.0573/0.1711 and macro
CER/WER 0.0737/0.1869 at 6.058 seconds/region (11.469 seconds initialization),
1,620 MiB process peak RSS, and 1,863/2,304 MiB PyTorch CUDA allocated/reserved
([report](../../../artifacts/evaluation/ocr/pipeline/hoa-sen-ar-2023-2024-prose-regions-16-easyocr-gpu.json)).
PaddleOCR 3.7.0 on Tesla T4 scored micro-CER/WER 0.1290/0.5270 and macro
CER/WER 0.1283/0.5136 at 1.861 seconds/region (34.676 seconds initialization),
3,004 MiB process peak RSS; Paddle GPU allocations are not measured by the
PyTorch-only CUDA counter
([report](../../../artifacts/evaluation/ocr/pipeline/hoa-sen-ar-2023-2024-prose-regions-16-paddleocr-gpu.json)).
The [three-engine paired comparison](../../../artifacts/evaluation/ocr/pipeline/hoa-sen-ar-2023-2024-prose-regions-16-comparison-all-engines.json)
confirms identical 16 rendered-image hashes. EasyOCR had the lowest observed
CER/WER and PaddleOCR the lowest latency; Tesseract ran on CPU while the other
two used Tesla T4, so latency is descriptive. Reference text is unproofread,
and these results remain exploratory.


### Lam Thao Fertilizers and Chemicals (LAS) Annual Report 2024: 10 scan crops

The [LAS Annual Report 2024](https://hnx.vn/vi-vn/m-niem-yet/tin-tuc/Bao%20cao%20thuong%20nien%202024-550807-1.html), distributed by HNX, adds ten manually transcribed Vietnamese prose crops from three image-only pages ([labels](las-ar-2024-prose-crops-10_ground_truth.json); [source PDF](https://owa.hnx.vn/ftp///cims/2025/3_W3/000000014623979_VI_BaoCaoThuongNien_2024.pdf)). References were transcribed and visually checked by one reviewer; no second review was done. The crops were rendered at 180 DPI and paired validation confirms all three engines used the same ten image hashes.

On Kaggle, Tesseract 5.3.4 / CPU scored micro-CER/WER 0.0115/0.0450 at 0.635 seconds/crop and 265 MiB peak RSS ([report](../../../artifacts/evaluation/ocr/pipeline/las-ar-2024-prose-crops-10-cpu/tesseract-kaggle.json)). EasyOCR 1.7.2 / Tesla T4 scored 0.0061/0.0251 at 0.678 seconds/crop, with 11.453 seconds initialization, 1,449 MiB peak RSS, and 447/910 MiB PyTorch CUDA allocated/reserved ([report](../../../artifacts/evaluation/ocr/pipeline/las-ar-2024-prose-crops-10-cpu/easyocr-gpu.json)). PaddleOCR 3.7.0 / Tesla T4 scored 0.1198/0.5212 at 0.296 seconds/crop, with 32.515 seconds initialization and 2,743 MiB peak RSS ([report](../../../artifacts/evaluation/ocr/pipeline/las-ar-2024-prose-crops-10-cpu/paddleocr-gpu.json)). Paddle's CUDA memory is not measured by the PyTorch-only counter. The [paired comparison](../../../artifacts/evaluation/ocr/pipeline/las-ar-2024-prose-crops-10-cpu/comparison-kaggle-tesseract-easyocr-paddleocr.json) verifies identical rendered inputs. Paddle was quickest for OCR inference alone, but its model startup was longest and its text accuracy was much worse; EasyOCR had the lowest observed CER/WER. Tesseract ran on CPU while EasyOCR and PaddleOCR ran on a Tesla T4, so inference latency is descriptive, not a hardware-controlled speed ranking. Model initialization is reported separately from page latency.

A local Tesseract 5.5.3 replay scored micro-CER/WER 0.0155/0.0582 at 1.479 seconds/crop and 317 MiB peak RSS ([report](../../../artifacts/evaluation/ocr/pipeline/las-ar-2024-prose-crops-10-cpu/tesseract.json)); treat its latency separately from Kaggle. These results remain exploratory: ten crops from one document are single-reviewed, do not measure full-page layout or tables, and the physical scan provenance is unverified. The set is ineligible for primary model selection.


### Duc Giang Chemicals Group (DGC) Annual Report 2024: 5 prose crops

The issuer-hosted [DGC Annual Report 2024](https://ducgiangchem.vn/wp-content/uploads/2025/03/20250314-DGC-Bao-cao-thuong-nien-Annual-Report-2024.pdf) adds five manually transcribed crops from PDF page 9 (printed page 7) ([labels](dgc-ar-2024-prose-regions-5_ground_truth.json); [source PDF](../../raw/vietnam_enterprises/dgc/dgc-ar-2024-vi.pdf)). All five crops come from the same page and one reviewer; they are exploratory only. Physical scan provenance is unverified.

Local Tesseract 5.5.3 (`vie+eng`, PSM 3, 180 DPI, CPU) scored micro-CER/WER 0.0464/0.1344 and macro-CER/WER 0.0493/0.1389, averaging 0.597 seconds/crop with 433 MiB peak RSS ([report](../../../artifacts/evaluation/ocr/pipeline/dgc-ar-2024-prose-regions-5-cpu/tesseract-local.json)). This is a one-engine screening result on five crops, not a model-selection result.


### SABECO Annual Report 2024: 4 prose crops

The issuer-hosted [SABECO Annual Report 2024](https://sabeco.com.vn/co-dong/bao-cao-thuong-nien/2024-8) adds four manually transcribed Vietnamese prose crops from PDF page 50 (printed page 98) ([labels](sabeco-ar-2024-prose-crops-4_ground_truth.json); [source PDF](../../raw/vietnam_enterprises/sabeco/sabeco-ar-2024-vi.pdf)). The annual report is a digitally published PDF, not a physical scan. All four crops come from one spread and one reviewer, so the data are exploratory only.

Local Tesseract 5.5.3 (`vie+eng`, PSM 3, 180 DPI, CPU) scored micro-CER/WER 0.0278/0.1226 and macro-CER/WER 0.0246/0.1077, averaging 0.719 seconds/crop with 433 MiB peak RSS ([report](../../../artifacts/evaluation/ocr/pipeline/sabeco-ar-2024-prose-crops-4-cpu/tesseract-local.json)). This single-engine result is a screening datapoint, not a model-selection result.


### PVChem Annual Report 2024: 6 scanned prose crops

The issuer-hosted [PVChem Annual Report 2024](https://pvchem.com.vn/bao-cao-thuong-nien/) adds six manually transcribed crops from image-only financial-statement pages 44 and 46 (printed pages 1 and 3) ([labels](pvchem-ar-2024-scan-prose-crops-6_ground_truth.json); [source PDF](../../raw/vietnam_enterprises/pvchem/pvchem-ar-2024-vi.pdf)). These are scan-like signed report pages inside a mixed PDF; physical scan provenance is unverified. All six crops come from two pages in one report and one reviewer, so they remain exploratory. Financial tables were excluded to keep CER/WER focused on prose.

Local Tesseract 5.5.3 (`vie+eng`, PSM 3, 180 DPI, CPU) scored micro-CER/WER 0.0018/0.0064 and macro-CER/WER 0.0039/0.0133, averaging 0.674 seconds/crop with 499 MiB peak RSS ([report](../../../artifacts/evaluation/ocr/pipeline/pvchem-ar-2024-scan-prose-crops-6-cpu/tesseract-local.json)). Five of six crops scored exact; this small, single-engine sample is not a production model-selection result.


### Vinh Hoan (VHC) Annual Report 2024: 9 digital prose crops

The issuer-hosted [VHC Annual Report 2024](https://www.vinhhoan.com/wp-content/uploads/2025/04/VHC_Bao-cao-Thuong-nien-2024_VN.pdf) adds nine manually checked Vietnamese prose crops from PDF pages 4, 6, and 7 ([labels](vhc-ar-2024-prose-9_ground_truth.json); [source PDF](../../raw/vietnam_enterprises/vhc/vhc-ar-2024-vi.pdf)). This is a digitally published report, not scan data. The references were checked against the rendered crops by one reviewer and have no independent second review; the set is exploratory and ineligible for primary model selection.

Local Tesseract 5.5.3 (`vie+eng`, PSM 3, 180 DPI, CPU) scored micro-CER/WER 0.0594/0.2563 and macro-CER/WER 0.0592/0.2576, averaging 1.239 seconds/crop with 511 MiB evaluator-process peak RSS ([report](../../../artifacts/evaluation/ocr/pipeline/vhc-ar-2024-prose-9-cpu/tesseract-local.json)). The nine crops come from only three pages in one report. This screening result does not measure full-page reading order, layout detection, table extraction, or physical-scan OCR.


### Dong A Paint Joint Stock Company (HDA) Annual Report 2024: 10 prose crops

The Hãng Sơn Đông Á Annual Report 2024, filed with HNX ([source PDF](https://owa.hnx.vn/ftp/cims/2025/4_W3/000000014821618_VI_Baocaothuongnien_2024_SIGNED.pdf)), adds ten visually checked Vietnamese prose crops from PDF pages 15, 22, and 24 ([labels](hda-ar-2024-prose-10_ground_truth.json); [source PDF copy](../../raw/vietnam_enterprises/dong_a_paint/dong-a-paint-ar-2024-vi.pdf)). This PDF has a native text layer and is not a physical scan. One reviewer checked the references against rendered crops; visible source typos were retained. The set is exploratory and ineligible for primary model selection.

Local Tesseract 5.5.3 (`vie+eng`, PSM 3, 180 DPI, CPU) scored micro-CER/WER 0.0174/0.0534 and macro-CER/WER 0.0162/0.0498, averaging 1.187 seconds/crop with 510 MiB evaluator-process peak RSS ([report](../../../artifacts/evaluation/ocr/pipeline/hda-ar-2024-prose-10-cpu/tesseract-local.json)). These ten crops represent three pages from one report and do not measure scan OCR, full-page reading order, layout detection, or table extraction.


### Kien Giang Import & Export Joint Stock Company (Kigimex) Annual Report 2024: 11 prose crops

The Kigimex Annual Report 2024, filed with HNX ([source PDF](https://owa.hnx.vn/ftp/cims/2025/3_W5/000000014689033_VI_BaoCaoThuongNien_2024.pdf)), adds eleven visually checked Vietnamese prose crops from PDF pages 25, 27, 28, 30, and 33 ([labels](kgm-ar-2024-prose-11_ground_truth.json); [source PDF copy](../../raw/vietnam_enterprises/kien_giang_import_export/kgm-ar-2024-vi.pdf)). The report has a native text layer and is not a physical scan. One reviewer checked the references against rendered crops; there was no independent second review. This set remains exploratory and ineligible for primary model selection.

Local Tesseract 5.5.3 (`vie+eng`, PSM 3, 180 DPI, CPU) scored micro-CER/WER 0.0009/0.0040 and macro-CER/WER 0.0007/0.0030, averaging 0.973 seconds/crop with 511 MiB evaluator-process peak RSS ([report](../../../artifacts/evaluation/ocr/pipeline/kgm-ar-2024-prose-11-cpu/tesseract-local.json)). These eleven crops cover five pages from one report and do not measure scan OCR, full-page reading order, layout detection, or table extraction.


### IDICO Corporation Annual Report 2024: 10 digital prose crops

The issuer-hosted [IDICO Annual Report 2024](https://admin.idico.com.vn/uploads/Final_VIE_IDC_Bao_cao_thuong_nien_2024_1_signed_2353272a5f.pdf) adds ten visually checked Vietnamese prose crops from PDF pages 4, 7, and 13 ([labels](idico-ar-2024-prose-10_ground_truth.json); [source PDF copy](../../raw/vietnam_enterprises/idico/idico-ar-2024-vi.pdf)). The PDF has a native text layer and is digitally published, not a physical scan. One reviewer checked the references against rendered crops; there was no independent second review. This set remains exploratory and ineligible for primary model selection.

Local Tesseract 5.5.3 (`vie+eng`, PSM 3, 180 DPI, CPU) scored micro-CER/WER 0.0190/0.0682 and macro-CER/WER 0.0235/0.0837, averaging 0.795 seconds/crop with 478 MiB evaluator-process peak RSS ([report](../../../artifacts/evaluation/ocr/pipeline/idico-ar-2024-prose-10-cpu/tesseract-local.json)). These ten crops cover only three pages of one report and do not measure scan OCR, full-page reading order, layout detection, or table extraction.


### VEAM Annual Report 2024: 10 provisional Vietnamese prose crops

The issuer-hosted [corrected VEAM Annual Report 2024](https://veamcorp.com/uploads/16062026140911890.pdf) adds ten prose regions from PDF pages 4, 8, and 18 ([labels](veam-ar-2024-prose-10_ground_truth.json); [source PDF copy](../../raw/vietnam_enterprises/veam/veam-ar-2024-vi-corrected.pdf)). The report has a native text layer and is digitally published, not a physical scan. Ground truth was drafted from the native text layer and has not yet been visually reviewed; CER/WER are provisional and the set is ineligible for primary model selection.

Local Tesseract 5.5.3 (`vie+eng`, PSM 3, 180 DPI, CPU) scored provisional micro-CER/WER 0.0181/0.0398 and macro-CER/WER 0.0169/0.0390, averaging 3.014 seconds/crop with 412 MiB evaluator-process peak RSS ([report](../../../artifacts/evaluation/ocr/pipeline/veam-ar-2024-prose-10-cpu/tesseract-local.json)). The latency includes a slow outlier and is a single local run; it should not be compared with other hardware runs. Crops isolate prose and do not measure scan OCR, full-page reading order, layout detection, or table extraction.


### Airports Corporation of Vietnam (ACV) Annual Report 2024: 11 raster-only prose crops

The official [ACV annual-report listing](https://acv.vn/vi/co-dong/bao-cao-thuong-nien) hosts the 2024 report through its embedded document ([PDF copy](../../raw/vietnam_enterprises/acv/acv-ar-2024-vi.pdf); [labels](acv-ar-2024-scan-prose-11_ground_truth.json)). The 57-page PDF consists of page images without a text layer. Eleven prose regions from PDF pages 7–9 (printed pages 6–8) were transcribed and visually checked by one reviewer; whether the PDF was produced by physical scanning is unverified. The set is exploratory, has no independent second review, and is ineligible for primary model selection. A [review sheet](../../../../artifacts/evaluation/ocr/review/acv-ar-2024-prose-11/references.md) shows each crop beside its transcription.

Local Tesseract 5.5.3 (`vie+eng`, PSM 3, 180 DPI, CPU) scored micro-CER/WER 0.0344/0.1227 and macro-CER/WER 0.0311/0.1119, averaging 1.794 seconds/crop with 447 MiB evaluator-process peak RSS ([report](../../../artifacts/evaluation/ocr/pipeline/acv-ar-2024-scan-prose-11-cpu/tesseract-local.json)). This is an initial single-engine, single-host screening run; it does not evaluate full-page reading order, layout detection, or table extraction.


### Vietnam Rubber Group (VRG) Annual Report 2024: 11 digital prose crops

The official [VRG annual-report listing](https://vrg.vn/quan-he-co-dong/bao-cao-thuong-nien/) hosts the Vietnamese 2024 annual report ([PDF copy](../../raw/vietnam_enterprises/vrg/vrg-ar-2024-vi.pdf); [labels](vrg-ar-2024-prose-11_ground_truth.json)). Eleven prose regions from PDF pages 17 and 32 cover rubber production, high-tech agriculture, renewable energy, and financial commentary. The report is digitally published with a native text layer, not a physical scan. References were taken from the text layer and visually checked against the crops by one reviewer; there was no independent second review. This set is exploratory and ineligible for primary model selection. A [review sheet](../../../../artifacts/evaluation/ocr/review/vrg-ar-2024-prose-11/references.md) pairs each crop with its reference.

Local Tesseract 5.5.3 (`vie+eng`, PSM 3, 180 DPI, CPU) scored micro-CER/WER 0.0060/0.0226 and macro-CER/WER 0.0064/0.0244, averaging 1.393 seconds/crop with 407 MiB evaluator-process peak RSS ([report](../../../artifacts/evaluation/ocr/pipeline/vrg-ar-2024-prose-11-cpu/tesseract-local.json)). This is a single-engine screening run on selected prose from two pages; it does not measure full-page reading order, layout detection, table extraction, or physical-scan OCR.


### Maritime Transport and Services JSC (TRA-SAS / TRS) Annual Report 2024: 10 digital prose crops

The [HNX filing](https://owa.hnx.vn/ftp/cims/2025/4_W3/000000014805230_1a._TRS_BCTN_2024_VIE_Final_Trang_doi_signed.pdf) adds ten prose regions from PDF pages 17 and 24 ([labels](tra-sas-ar-2024-prose-10_ground_truth.json); [review sheet](../../../../artifacts/evaluation/ocr/review/tra-sas-ar-2024-prose-10/references.md)). HNX download failed local TLS certificate-chain validation, so the local copy was fetched from a [CafeF CDN mirror](https://cafef1.mediacdn.vn/download/180425/trs-bao-cao-thuong-nien-2024-0-557885.pdf); the PDF signature content validates, while the local trust store does not trust the signer certificate issuer. The document has a native text layer and is digitally published, not a physical scan. The references are copied from that text layer and are still awaiting visual and independent review; the set is exploratory and ineligible for primary model selection.

Local Tesseract 5.5.3 (`vie+eng`, PSM 3, 180 DPI, CPU) returned provisional micro/macro CER and WER of 0.0000, averaging 1.863 seconds/crop with 350 MiB evaluator-process peak RSS ([report](../../../artifacts/evaluation/ocr/pipeline/tra-sas-ar-2024-prose-10-cpu/tesseract-local.json)). Because the reference was copied from the PDF text layer and is not reviewed, the zero scores may reflect this digitally typeset source and must not be interpreted as proof of general OCR accuracy. The ten crops cover two pages in one report; they do not measure physical-scan OCR, full-page reading order, layout detection, or table extraction.


### Masan MEATLife Annual Report 2024: 10 raster-only prose crops

The issuer-hosted [Vietnamese Annual Report 2024](https://masanmeatlife.com.vn/wp-content/uploads/2025/10/2024.pdf) adds ten manually transcribed prose regions from PDF pages 8, 9, 12, 13, 14, and 16 ([labels](mml-ar-2024-scan-prose-10_ground_truth.json); [review sheet](../../../../artifacts/evaluation/ocr/review/masan-meatlife-ar-2024-scan-prose-10/references.md)). This 45-page PDF has no native text layer; its metadata names DocuCentre-V 4070 as creator, but whether the pages originated from physical paper scans is unverified. One reviewer corrected Tesseract draft text against each crop. Independent adjudication is still pending, so the set remains exploratory and ineligible for primary model selection.

Local Tesseract 5.5.3 (`vie+eng`, PSM 3, 180 DPI, CPU) scored micro-CER/WER 0.0241/0.0997 and macro-CER/WER 0.0246/0.1019, averaging 1.776 seconds/crop with 526 MiB evaluator-process peak RSS ([report](../../../artifacts/evaluation/ocr/pipeline/mml-ar-2024-scan-prose-10-cpu/tesseract-local.json)). The ten crops cover six pages from one report and do not measure full-page reading order, layout detection, or table extraction.


### Binh Son Refining and Petrochemical JSC (BSR) Annual Report 2024: 10 digital prose crops

The [issuer-hosted Annual Report](https://bsr.com.vn/c/document_library/get_file?groupId=37629&uuid=741f45d0-49ee-5d8d-74b0-52793049c064) adds ten Vietnamese prose regions from PDF pages 12, 22, 23, and 24 ([labels](bsr-ar-2024-prose-10_ground_truth.json); [review sheet](../../../../artifacts/evaluation/ocr/review/bsr-ar-2024-prose-10/references.md)). The 95-page report has a native text layer and is digitally published, not a physical scan. The BSR host failed local TLS certificate-chain validation, so the local PDF copy was fetched from the [Vietstock mirror](https://static2.vietstock.vn/data/HOSE/2024/BCTN/VN/BSR_Baocaothuongnien_2024.pdf). References were taken from the text layer and visually checked by one reviewer; no independent second review has been done. The set remains exploratory and ineligible for primary model selection.

Local Tesseract 5.5.3 (`vie+eng`, PSM 3, 180 DPI, CPU) scored micro-CER/WER 0.0055/0.0087 and macro-CER/WER 0.0058/0.0100, averaging 1.431 seconds/crop with 501 MiB evaluator-process peak RSS ([report](../../../artifacts/evaluation/ocr/pipeline/bsr-ar-2024-prose-10-cpu/tesseract-local.json)). These ten crops cover four pages from one report and do not evaluate scan OCR, full-page reading order, layout detection, or table extraction.


### Vietnam National Textile and Garment Group (Vinatex) Annual Report 2024: 10 digital prose crops

The issuer's [shareholder-relations page](https://vinatex.com.vn/shareholder-relations/) provides its investor documents. This Vietnamese report was downloaded from the [Vietstock PDF mirror](https://static2.vietstock.vn/data/HNX/2024/BCTN/VN/VGT_Baocaothuongnien_2024/1_vgt_2025_4_18_0e3187a_vi_baocaothuongnien_2024.pdf); the digital signature identifies Vinatex, and the signed content validates, although the signer certificate has expired. Ten prose regions from PDF pages 19, 21, 22, 33, 34, and 39 are labeled ([manifest](vgt-ar-2024-prose-10_ground_truth.json); [review sheet](../../../../artifacts/evaluation/ocr/review/vinatex-ar-2024-prose-10/references.md)). The report has a native text layer and is not physical-scan data. One reviewer visually checked the references; independent adjudication remains pending, so this set is exploratory and ineligible for primary model selection.

Local Tesseract 5.5.3 (`vie+eng`, PSM 3, 180 DPI, CPU) scored micro-CER/WER 0.0294/0.0509 and macro-CER/WER 0.0228/0.0419, averaging 1.553 seconds/crop with 452 MiB evaluator-process peak RSS ([report](../../../artifacts/evaluation/ocr/pipeline/vgt-ar-2024-prose-10-cpu/tesseract-local.json)). A crop with a large drop-cap initial has much higher error than the other crops; this is a single-page layout effect within the report. These ten crops do not measure physical-scan OCR, full-page reading order, layout detection, or table extraction.
