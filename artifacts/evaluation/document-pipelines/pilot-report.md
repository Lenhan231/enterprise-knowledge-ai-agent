# Vietnamese enterprise document pipeline pilot

> This is the original exploratory report. Its OCR reference used column-first
> order for a table on page 3 and its table score checked four row anchors only.
> The updated assistant-adjudicated pilot diagnostic is
> [`pilot-v2-report.md`](pilot-v2-report.md); neither report is an official
> benchmark or human-reviewed result.

**Status:** pilot complete; not a model-selection result.

## Setup

All three pipelines received the same 20 one-page PDFs from
[`pilot-v1/manifest.json`](pilot-v1/manifest.json): 11 born-digital pages, 6
known physical scans, and 3 image-only pages. The set contains about 9 table
regions across 6 pages. Inference ran on Kaggle workers reporting Tesla T4 GPUs.
Raw outputs and run metadata are retained in each engine's result directory.

| Pipeline | Configuration | Success |
|---|---|---:|
| PP-StructureV3 | PaddleOCR 3.4.1 / PaddleX 3.4.3 / Paddle GPU 3.3.1; PP-DocLayout-S, PP-OCRv5 mobile, table recognition on | 20/20 |
| MinerU Basic | MinerU 4.0.12, Basic tier, one CLI process per page | 19/20 |
| Docling | Docling 2.129.0; RapidOCR 3.9.2 ONNX Runtime (`vi`), CUDA accelerator, table structure on | 20/20 |

MinerU failed on `longhau-financials-p015` with `Unsupported warp settings`.
Per-page process isolation let the other 19 pages complete. Its total runtime
includes 20 process/model starts. The MinerU Standard tier is a separate failed
attempt: its local llama.cpp VLM process exited with code `-11`; Basic results
do not describe Standard behavior. Paddle initially failed because installing
its CUDA 12.6 wheel replaced Kaggle Torch's NCCL 2.28.9 with 2.25.1. The rerun
restored Torch's required CUDA packages and passed the import check before
inference.

## Exploratory scores

OCR uses the same two single-reviewer full-page references from one Long Hau
scan. Text is normalized with NFC, case folding, whitespace collapse, and
Markdown/HTML presentation cleanup; punctuation and Vietnamese diacritics are
preserved. CER/WER are shown separately by page because two pages do not support
a representative aggregate.

| Page | PP-StructureV3 CER / WER | MinerU Basic CER / WER | Docling CER / WER |
|---|---:|---:|---:|
| Long Hau cover (p1) | 13.38% / 47.22% | 29.30% / 47.22% | 19.11% / 47.22% |
| Long Hau board report (p3) | 30.06% / 69.30% | 13.69% / 45.15% | 22.47% / 57.11% |

The table check is exact presence and order of four manually transcribed row
anchors in flattened OCR/Markdown text from Long Hau balance-sheet p6. It does
not verify that the pipeline placed values in the correct cells; it is **not**
TEDS or cell accuracy.

| Pipeline | Exact anchor rows |
|---|---:|
| PP-StructureV3 | 2/4 (50%) |
| MinerU Basic | 3/4 (75%) |
| Docling | 4/4 (100%) |

The Docling 4/4 result is only a selected-row check on one page; it does not
establish table reconstruction quality. Full cell-grid labels are still needed
for TEDS, structure, and cell-content metrics.

## Runtime and memory observations

These are single-run pilot timings, not the planned three-run performance
benchmark. Per-page p95 uses linear interpolation. Memory is process peak RSS;
GPU peak memory was not captured.

| Pipeline | Init/setup recorded | Median/page | p95/page | Total inference/run | Peak RSS |
|---|---:|---:|---:|---:|---:|
| PP-StructureV3 | 30.12 s | 1.63 s | 2.84 s | 74.41 s | 3,192 MiB |
| MinerU Basic | Included in each page | 16.07 s | 25.98 s | 366.57 s | Not measured for child process |
| Docling | Converter setup 0.34 s; model loads lazily | 15.60 s | 27.29 s | 342.10 s | 6,270 MiB |

MinerU's CLI subprocess starts once per page, so its latency cannot be fairly
compared with the persistent PP and Docling processes. Its recorded 103 MiB RSS
is only the parent runner and is deliberately excluded as a model memory value.
Docling's constructor duration also misses lazy model loading; its first page
includes the cold start.

## What the pilot establishes

- All three output adapters can produce comparable OCR text for two shared
  full-page references, and a simple table-anchor scorer can inspect a shared
  page. The raw output format differs substantially across the engines.
- OCR ranks reverse between the two pages; the tiny reference set cannot select
  a production OCR engine.
- Table extraction needs complete, reviewed cell grids before pipeline scores
  can be compared reliably.
- Layout and reading-order scoring were not run. There are 13 AI-assisted
  layout annotations marked review-required and no reviewed reading-order
  labels.

## Next benchmark work

Keep the plan targets in [`plan.md`](plan.md): 500 reviewed OCR crops, 150
complete tables, 100 reading-order pages, and 200 reviewed layout pages. Audit
the candidates and gaps in [`review-inventory.md`](review-inventory.md), create
issuer/document-level development, validation, and locked-test splits, then run
all three engines on the same frozen inputs. Capture GPU memory, use three
warmed runs for runtime, and normalize each engine's table and layout structures
before scoring. Do not use this pilot to choose the production pipeline.

## Artifacts

- Machine-readable comparison: [`pilot-comparison.json`](pilot-comparison.json)
- Dataset/input manifest: [`pilot-v1/manifest.json`](pilot-v1/manifest.json)
- PP-StructureV3 raw output: [`results/pp-structurev3/document-pipeline-pilot/`](results/pp-structurev3/document-pipeline-pilot/)
- MinerU Basic raw output: [`results/mineru-basic/document-pipeline-pilot/`](results/mineru-basic/document-pipeline-pilot/)
- Docling raw output: [`results/docling/document-pipeline-pilot/`](results/docling/document-pipeline-pilot/)
- Kaggle dataset: <https://www.kaggle.com/datasets/ltrngnhn/vietnamese-enterprise-document-pipeline-pilot-v1>
- Kaggle kernels: [PP-StructureV3](https://www.kaggle.com/code/ltrngnhn/vietnamese-enterprise-pilot-paddle-structure), [MinerU Basic](https://www.kaggle.com/code/ltrngnhn/vietnamese-enterprise-pilot-mineru), [Docling](https://www.kaggle.com/code/ltrngnhn/vietnamese-enterprise-pilot-docling)
