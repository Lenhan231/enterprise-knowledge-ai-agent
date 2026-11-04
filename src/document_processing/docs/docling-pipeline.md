# Docling, layout and OCR pipeline

This page describes the `intent=document` route. The dispatcher is
[`DocumentProcessor`](../document_processor.py); the Docling stages are
assembled in [`docling_adapter/processor.py`](../docling_adapter/processor.py).

## PDF path

```text
PDF bytes
  → page orientation detection and corrected page view
  → PP-DocLayoutV3 regions + raw layout_detections
  → OCR text / TableFormer tables
  → optional chart crop recognition
  → result_mapper
  → normalized elements + tables + metadata
```

- The registered PP-DocLayoutV3 adapter turns layout detections into Docling
  clusters and preserves raw labels, confidence, and page-space boxes for
  review. `docling_layout_score_threshold` defaults to `0.25`.
- Native PDF text cells are skipped. The selected OCR route is recorded as
  `metadata.pdf_processing_route`.
- With VietOCR, OCR uses layout regions when available and falls back to
  full-page OCR if no usable regions are detected. With Tesseract, OCR uses the
  full page. `DOCUMENT_PROCESSING_OCR_ENGINE` selects the container default;
  `docling_ocr_engine` can override it per request. The Docker image sets the
  environment default to `vietocr`; the adapter's code fallback is `tesseract`.
- VietOCR's Docling plugin uses RapidOCR for line detection, merges nearby
  fragments on a shared line, classifies line crops as printed or handwritten,
  then selects a VietOCR recognizer. Printed lines use `vgg_seq2seq`; the
  handwritten route uses `DungHugging/vietocr-handwritten-finetune`. If the
  classifier/model cannot load, it falls back to the printed recognizer. The
  current classifier was trained on European-language lines; Vietnamese
  routing still needs held-out evaluation.
- TableFormer Accurate reconstructs tables in detected table regions and
  matches OCR text to cells. A missed layout region can limit table output.
- `result_mapper.py` normalizes Docling items, merges OCR fragments belonging
  to one raw `text` region, and applies scanned-output cleanup. It does not
  merge separate text boxes into one element.

Page orientation and OCR-region orientation are separate checks. Page
corrections are returned in `page_orientation_corrections`; crop orientation
uses a confidence threshold and ignores quarter-turn corrections for already
horizontal line crops.

## Chart path

Layout detections identify chart regions. A geometric association can match a
nearby title; the chart and matched title are cropped together and rendered at
3×. The result mapper removes overlapping full-page OCR lines for the chart
crop and returns a separate `chart` element.

- With `OPEN_PARSER_API_KEY`, the crop is sent to OpenParser's PaddleOCR-VL 1.6
  endpoint for a structured table.
- With `GROQ_API_KEY`, Groq can correct indexed text cells using the crop and
  OCR references; numeric cells and table structure are preserved. If
  OpenParser is unavailable, Groq can extract the chart directly from the
  crop.
- Set `docling_chart_recognition=false` to skip chart extraction and retain
  the detected region. `docling_chart_llm_correction` controls the correction
  step.

This route calls external services; it does not load PaddleOCR-VL in the
document-processing container.

## Office and standalone images

DOCX/PPTX/XLSX/CSV/TXT/Markdown use Docling's native document conversion.
DOCX semantics are enriched in `docling_adapter/digital_born/docx_semantics.py`.
When embedded-picture OCR is enabled, Office pictures use the configured OCR
engine. PDFs do not receive a second embedded-image OCR pass. Standalone SVG
and WebP are normalized to PNG before Docling; SVG input is restricted to
self-contained content by `render_svg` in `document_processor.py`.

## Runtime settings

| Setting | Effect |
| --- | --- |
| `DOCUMENT_PROCESSING_OCR_ENGINE` / `docling_ocr_engine` | `vietocr` or `tesseract` |
| `docling_ocr` | Enable/disable OCR for the request |
| `docling_device` | Docling accelerator (`cpu` by default; `cuda` when configured and available) |
| `docling_num_threads` | CPU thread count; defaults to 2 |
| `docling_layout_score_threshold` | PP-DocLayoutV3 score threshold; defaults to 0.25 |
| `docling_table_structure` | Enable TableFormer; defaults to true |
| `docling_page_images` | Include rendered page previews in parser output |
| `docling_chart_recognition` | Enable chart-region extraction |
| `docling_chart_llm_correction` | Enable Groq text-cell correction |

Request callers can set these in parser config. The production Docker image
also sets environment defaults; check `docker/Dockerfile.document-processing`
and the caller before assuming a local run uses production settings.

## Known limits

- Text outside detected layout regions can be missed on the VietOCR route when
  some regions exist; full-page fallback only runs when no usable region exists.
- Layout/table quality depends on PP-DocLayoutV3 detections and TableFormer.
- Printed/handwritten classification is not yet validated on a representative
  Vietnamese test set.
- OCR and chart extraction preserve parser evidence; they do not produce a
  validated business schema such as invoice fields. See the
  [Vintern guide](vintern-pipeline.md) for the separate current invoice route.
