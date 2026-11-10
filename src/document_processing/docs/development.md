# Local development and runtime

Run commands from the repository root unless a command says otherwise. The
main local inspection UI is `testing_parser_streamlit.py`; it calls the parser
directly and stores review runs separately from production uploads.

## Run Upload Test locally

```sh
PYTHONPATH=src .venv/bin/streamlit run \
  src/document_processing/testing_parser_streamlit.py \
  --server.address 127.0.0.1 --server.port 8502
```

By default, local review data is under
`src/document_processing/.owner_store/`. Set `DOCUMENT_PROCESSING_STORE` to
use a different folder. Upload Test can select pages from a PDF before
processing and can select the `document`, `invoice`, or `image_caption`
intent. Invoice extraction uses Docling and a text-only Qwen worker; image
captioning uses the separate Vintern environment below.

## Vintern environment

The app looks for `.venv-vintern/bin/python` unless
`DOCUMENT_PROCESSING_VINTERN_PYTHON` points to another interpreter. The
separate environment pins the older Transformers version required by the
Vintern remote model code:

```sh
uv venv .venv-vintern --python 3.11
uv pip install --python .venv-vintern/bin/python \
  --index-url https://download.pytorch.org/whl/cpu \
  torch==2.3.1 torchvision==0.18.1
uv pip install --python .venv-vintern/bin/python \
  -r artifacts/evaluation/invoices/vintern-runtime-requirements.txt
```

These commands install CPU PyTorch. A GPU runtime needs a matching CUDA PyTorch
build and host driver/runtime; changing `vintern_device` to `cuda` is not by
itself sufficient. See the [Vintern pipeline](vintern-pipeline.md).

## Build the parser image

From the repository root:

```sh
docker build -f docker/Dockerfile.document-processing -t document-processing .
docker run --rm document-processing
```

The image's default command starts the FastAPI document-processing service on
port 8000. It does not include the full application or Streamlit. Model caches
should be mounted to persist downloads between local container runs.

## Where to inspect a failure

1. Confirm the caller's selected `intent` and parser config.
2. Check the Upload Test result: parser metadata records engine, route, model,
   and review status where available.
3. Check application logs for the upload/job ID, then the document-processing
   service logs for `/parse` status and worker traceback.
4. For Vintern, distinguish queue/proxy wait from actual model inference; the
   worker timeout and CPU/GPU device are described in the
   [Vintern guide](vintern-pipeline.md).

Do not use production or SSH as a local verification step. Use the explicit
deployment workflow for a separately authorized production change.
