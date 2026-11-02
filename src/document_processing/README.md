# Document processing

This package parses supported files into ordered elements and structured
tables. Its ownership ends at normalized document-processing output; chunking
and persistence are handled by separate modules in the application.

For supported formats and OCR settings, see the [processing guide](docs/document-processing.md).
Shared provenance fields are listed in [`docs/metadata.md`](docs/metadata.md).
See [`architect.md`](architect.md) for the current parser flow and invoice branch.

## Flow

```text
DocumentProcessor.process(file)
    ├── intent=document (default)
    │     └── DoclingProcessor
    │           ├── PP-DocLayoutV3 → native layout_detections + Docling clusters
    │           ├── Docling OCR + TableFormer → {elements, tables}
    │           ├── chart + matched title → union crop at 3× → PaddleOCR-VL v1.5
    │           │     └── Groq vision + existing OCR line candidates → text-cell spelling corrections
    │           └── result_mapper → {elements, tables}
    └── intent=invoice
          └── Vintern in isolated Transformers runtime → invoice_extraction
    └── common cleanup + provenance

application → core.chunking → persist chunks/tables
```

Production upload and Upload Test call this parser package and the separate
chunking module. Upload Test stores isolated results. This package does not
handle chunking, tokenization, embeddings, or retrieval indexing.

## Package map

| Path | Responsibility |
| --- | --- |
| `document_processor.py` | Dispatch supported files to Docling or invoice extraction; normalize output and provenance. |
| `invoice/processor.py` | Render invoice pages and dispatch them to the isolated Vintern runtime. |
| `invoice/vintern_worker.py` | Load Vintern and extract invoice fields page by page. |
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

PDFs always use full-page OCR; Docling skips extracting native PDF text cells.
The OCR engine remains configurable (`vietocr` or `tesseract`). OCR for
embedded Office pictures and standalone images follows the `docling_ocr`
setting. PDF images are covered by the full-page OCR pass and are not sent
through a second embedded-image pass. The route is recorded as
`pdf_processing_route: full_page_ocr` in parser metadata.

For each PP-DocLayoutV3 chart region, the document path removes overlapping
full-page OCR line results, then renders the page at 3× for PaddleOCR-VL v1.5.
The crop starts from the chart bbox; when a title detection has a unique,
geometrically aligned match, the crop becomes the union of the title and chart
bboxes. If one title spans multiple adjacent charts, one group crop covers the
title and all matched charts. The parser preserves the original chart bboxes
separately. It emits a distinct `chart` element; generic
pictures remain `figure` elements and captions remain separate. Docling still
receives its supported internal picture label for chart regions.
Set `docling_chart_recognition=false` to keep chart regions without chart text.
When `GROQ_API_KEY` is set, the chart crop, PaddleOCR-VL table, and OCR text lines
inside the crop are sent to `GROQ_VISION_MODEL` (default `qwen/qwen3.8-27b`).
Groq returns indexed text-cell corrections only. The parser applies them to
PaddleOCR-VL's original table; cells containing digits, row/column positions,
and the original table structure remain unchanged. Missing credentials or a
Groq error keeps the PaddleOCR-VL result. Docker Compose forwards these two
environment variables to the document-processing service.

## Invoice intent

The local owner-store UI defaults to **General document · current pipeline**.
Choose **Invoice · Vintern extraction** to extract draft fields directly from
PDF/image pages. Results are stored under `invoice_extraction.pages`; a JSON
summary is also written to `elements` for search and chunking. Every extraction
is marked for human review because the notebook's fine-tuned checkpoint has not
been validated on a held-out invoice set. This branch currently accepts PDF and
image files only.

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
VietOCR, and Vietnamese/English Tesseract (used for orientation detection). It
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
