# Document processing

This package parses supported files into ordered elements and structured
tables. Its ownership ends at normalized document-processing output; chunking
and persistence are handled by separate modules in the application.

For supported formats and OCR settings, see the [processing guide](docs/document-processing.md).
Shared provenance fields are listed in [`docs/metadata.md`](docs/metadata.md).
See [`architect.md`](architect.md) for the current parser flow and extraction intents.

## Flow

```text
DocumentProcessor.process(file)
    ├── intent=document (default)
    │     └── DoclingProcessor
    │           ├── page OSD → rotate detector view, map boxes back to source coordinates
    │           ├── PP-DocLayoutV3 → native layout_detections + Docling clusters
    │           ├── OCR-region OSD → RapidOCR line detection → printed/handwriting routing → VietOCR; TableFormer → {elements, tables}
    │           ├── chart + matched title → union crop at 3× → OpenParser/PaddleOCR-VL 1.6 table
    │           │     └── Groq + existing VietOCR lines → text-cell spelling corrections
    │           │           (direct Groq vision extraction if OpenParser key is unavailable)
    │           └── result_mapper → {elements, tables}
    ├── intent=invoice
    │     └── Vintern in isolated Transformers runtime → invoice_extraction
    └── intent=receipt
          └── Vintern in isolated Transformers runtime → receipt_extraction
    └── common cleanup + provenance

application → core.chunking → persist chunks/tables
```

Production upload and Upload Test call this parser package and the separate
chunking module. Upload Test stores isolated results. This package does not
handle chunking, tokenization, embeddings, or retrieval indexing.

Upload Test accepts self-contained SVG images and renders them as PNG for
Docling while retaining SVG source metadata. External references, scripts,
stylesheets and document type declarations are rejected. Corpus upload does
not yet accept SVG. Upload Test also accepts single-frame WebP images, rendered
as PNG before parsing; corpus upload does not yet accept WebP.

## Package map

| Path | Responsibility |
| --- | --- |
| `document_processor.py` | Dispatch supported files to Docling, invoice extraction, or receipt extraction; normalize output and provenance. |
| `invoice/processor.py` | Render invoice pages and dispatch them to the isolated Vintern runtime. |
| `invoice/vintern_worker.py` | Load Vintern and extract invoice fields page by page. |
| `receipt/processor.py` | Render receipt pages and dispatch them to the isolated Vintern runtime. |
| `receipt/vintern_worker.py` | Load Vintern and extract receipt fields page by page. |
| `docling_adapter/processor.py` | Configure Docling stages, chart recognition, and scanned embedded-image routing. |
| `docling_adapter/layout_model.py` | Adapt PP-DocLayoutV3 detections into Docling layout clusters. |
| `docling_adapter/chart_recognition.py` | Recognize chart blocks in chart boxes, including a matched or shared title. |
| `docling_adapter/digital_born/` | DOCX structure enrichment. |
| `docling_adapter/scanned/` | OCR line detection and cleanup; Office embedded-image OCR. |
| `docling_adapter/result_mapper.py` | Normalize OCR and structured results into shared elements and tables. |
`pipeline_id` records the configured parser engine; `parser` identifies the
component that produced an element or table. See [`docs/metadata.md`](docs/metadata.md).

The parser also returns raw `layout_detections` from PP-DocLayoutV3 with
the model's class label, confidence, page bbox, and coordinate convention. This
keeps all 25 detector classes inspectable even when Docling maps a class to a
compatible internal label. The owner review UI can overlay these raw labels
separately from normalized parser elements. A same-page geometry heuristic links
figure/table title boxes to the closest horizontally aligned chart, figure, or
table. The link is recorded on the detection; when OCR text is available, the
title element and target metadata (and table context) also record the association
without merging the boxes.
PP-DocLayoutV3 uses `figure_title` for figure, table, and chart titles; it does
not provide a separate `table_title` class.
The shared element taxonomy has 12 labels; the layout benchmark keeps its
separate five-label mapping.

OCR text elements assigned to the same raw PP-DocLayoutV3 `text` box are
merged in reading order; text on separate lines stays on separate lines. Other
layout labels, including tables, footer and number, are not merged this way.

VietOCR first joins nearby detector fragments that share a text line, then
classifies each resulting line crop as printed or handwritten. This prevents
small detached marks from being recognized as independent words. Printed
lines use the existing `vgg_seq2seq` recognizer; handwritten lines use the
Vietnamese handwriting fine-tune `DungHugging/vietocr-handwritten-finetune`
(`vgg_transformer`). The ResNet-18 style classifier is
`VItaldob/text-type-classifier-resnet18`; both model revisions are pinned and
cached under `HF_HOME`. If either download or model load fails, OCR falls back
to the existing Seq2Seq recognizer. The classifier was trained on European
language lines, so its Vietnamese routing quality still needs a held-out
evaluation before the classifier itself can be considered production-validated.

Before PP-DocLayoutV3 runs, PaddleOCR `PP-LCNet_x1_0_doc_ori` checks each
rendered page and rotates it when needed. Page previews and detected boxes use
the corrected page orientation. VietOCR also uses PP-LCNet's orientation
classifier on each OCR region before RapidOCR line detection. A region is rotated only if confidence is
at least 0.7; quarter-turn predictions are ignored for horizontal crops because
they can be wrong even at high confidence. VietOCR uses
detected layout boxes, falling back to full-page OCR if none are detected; text
outside detected boxes may be missed. Tesseract uses full-page OCR. Docling skips
extracting native PDF text cells.
The OCR engine remains configurable (`vietocr` or `tesseract`). OCR for
embedded Office pictures and standalone images follows the `docling_ocr`
setting. PDF images are not sent through a second embedded-image pass. The OCR
route is recorded in `pdf_processing_route` in parser metadata.

For each PP-DocLayoutV3 chart region, the document path removes overlapping
full-page OCR line results, then renders the page at 3× for chart extraction.
The crop starts from the chart bbox; when a title detection has a unique,
geometrically aligned match, the crop becomes the union of the title and chart
bboxes. If one title spans multiple adjacent charts, one group crop covers the
title and all matched charts. The parser preserves the original chart bboxes
separately. It emits a distinct `chart` element; generic
pictures remain `figure` elements and captions remain separate. Docling still
receives its supported internal picture label for chart regions.
Set `docling_chart_recognition=false` to keep chart regions without chart text.
With `OPEN_PARSER_API_KEY`, the chart crop goes to OpenParser's PaddleOCR-VL 1.6
endpoint for a structured table. When `GROQ_API_KEY` is set, Groq receives that
table, the crop, and existing OCR lines; it can correct indexed text cells only.
Numeric cells and the OpenParser table structure remain unchanged. If OpenParser
is not configured or unavailable, Groq extracts a structured chart directly
from the crop and OCR lines. This avoids loading PaddleOCR-VL locally in the
document-processing container. Docker Compose forwards both API keys and the
Groq model setting to that service.

## Invoice and receipt intents

The local owner-store UI defaults to **General document · current pipeline**.
Choose **Invoice · Vintern extraction** for invoice fields, or **Receipt ·
Vintern extraction** for retail receipt fields. Results are stored under
`invoice_extraction.pages` or `receipt_extraction.pages`; a JSON summary is also
written to `elements` for search and chunking. Every extraction is marked for
human review because the model has not been validated on a held-out set. Both
intents currently accept PDF and image files only.

The notebook pins Transformers 4.47, while the main app environment uses
Transformers 5. Keep the model in a separate virtualenv:

```sh
uv venv .venv-vintern --python 3.11
# CPU runtime; for CUDA, install the matching PyTorch wheel for the host instead.
uv pip install --python .venv-vintern/bin/python \
  --index-url https://download.pytorch.org/whl/cpu \
  torch==2.3.1 torchvision==0.18.1
uv pip install --python .venv-vintern/bin/python \
  -r artifacts/evaluation/invoices/vintern-runtime-requirements.txt
PYTHONPATH=src .venv/bin/streamlit run \
  src/document_processing/testing_parser_streamlit.py \
  --server.address 127.0.0.1 --server.port 8502
```

The app automatically uses `.venv-vintern/bin/python` when present. Set
`DOCUMENT_PROCESSING_VINTERN_PYTHON` only when the isolated runtime is elsewhere.
The default model is `5CD-AI/Vintern-1B-v2`. Set
`DOCUMENT_PROCESSING_VINTERN_MODEL` to a local fine-tuned model directory or a
different Hugging Face model id. The default model's custom code is pinned to
revision `5ec005391798968cd62f41cb71b22c1cee0b13d8`; the worker allows its
guarded optional Flash Attention import to fall back to standard attention, so
the CPU runtime does not need `flash-attn`. PDF pages are rendered at 2× before inference.
Pages are extracted independently; cross-page field merging and arithmetic
validation are not implemented yet.

## Module Docker image

Build from the repository root:

```sh
docker build -f docker/Dockerfile.document-processing -t document-processing .
docker run --rm document-processing
```

The image contains `document_processing`, Docling, PaddleOCR PP-DocLayoutV3,
PaddleOCR-VL chart parsing,
VietOCR, and Vietnamese/English Tesseract (available as an OCR engine). It
does not install the full application's dependencies or include the FastAPI app,
database credentials, or Streamlit. OCR defaults to VietOCR in this image;
set `DOCUMENT_PROCESSING_OCR_ENGINE=tesseract` to select Tesseract instead.
The default command checks imports; success prints
`PASS: Docling, PP-DocLayoutV3, PaddleOCR-VL, VietOCR, and document_processing imports`
and exits with code 0.
This check does not run Docling inference on a real document.
VietOCR 0.3.13 pins `gdown==4.4.0`, which imports `pkg_resources`; keep
`setuptools<81` until that VietOCR dependency is upgraded.

Override the command to use the parser from your own Python script:

```sh
docker run --rm -v "$PWD:/work" \
  -v document-processing-cache:/root/.cache \
  -v document-processing-paddlex-cache:/root/.paddlex \
  document-processing python /work/your_script.py
```

Your script can call `DocumentProcessor().process(filename, content, metadata)`
and save the parsed output as JSON for the separate chunking image.
Docling and PaddleOCR model weights download when conversion first needs them;
mount cache volumes at `/root/.cache` and `/root/.paddlex` to retain them between
runs. This image has no HTTP server or exposed port.

For the independent chunking image, see
[`core/chunking/README.md`](../core/chunking/README.md#module-docker-image).

## Local owner store UI

Install the optional Streamlit UI and run it on loopback:

```sh
PYTHONPATH=src \
  .venv/bin/streamlit run src/document_processing/testing_parser_streamlit.py \
  --server.address 127.0.0.1 --server.port 8502
```

By default, source files and Docling JSON output are saved under
`src/document_processing/.owner_store/`. Set `DOCUMENT_PROCESSING_STORE` to
use another local folder. PDF uploads can select arbitrary pages, such as
`2, 5, 9`, before Docling runs, which is useful for reviewing a few pages of a
large document. Leaving the field blank processes the full PDF.
