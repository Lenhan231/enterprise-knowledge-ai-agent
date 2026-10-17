# OCR benchmark: 500 Vietnamese enterprise text crops

## Result

This report includes the 399 development/validation crops and the 101-crop
locked test, scored once with the existing untuned baseline configurations.
The labels are assistant-adjudicated under the project owner's instruction and
are not human-reviewed. All inputs are 180-DPI image-only PDFs, so a pipeline
cannot read the source PDF text layer.

### Development and validation (399 crops)

| Pipeline | micro-CER | micro-WER | macro-CER | macro-WER | Outputs found |
|---|---:|---:|---:|---:|---:|
| PP-StructureV3 | 28.65% | 73.84% | 38.76% | 82.87% | 399/399 |
| MinerU Basic | 18.66% | 56.90% | 24.98% | 62.79% | 399/399 |
| Docling | 27.35% | 66.71% | 36.36% | 74.23% | 399/399 |

## Locked test (101 crops)

| Pipeline | micro-CER | micro-WER | macro-CER | macro-WER | Outputs found |
|---|---:|---:|---:|---:|---:|
| PP-StructureV3 | 26.99% | 73.79% | 26.32% | 75.21% | 101/101 |
| MinerU Basic | **18.00%** | **56.41%** | **16.14%** | **55.98%** | 101/101 |
| Docling | 26.47% | 65.88% | 30.10% | 67.51% | 101/101 |

The locked split preserves the development/validation ranking: MinerU Basic has
the lowest OCR error on these crops. This is a baseline pipeline comparison;
no parameter tuning was performed, and it does not establish production
quality outside this dataset.

| Pipeline | Development micro-CER / micro-WER | Validation micro-CER / micro-WER |
|---|---:|---:|
| PP-StructureV3 | 28.60% / 73.91% | 28.87% / 73.53% |
| MinerU Basic | 18.36% / 56.88% | 19.91% / 56.99% |
| Docling | 27.03% / 66.81% | 28.67% / 66.28% |

The locked-test result is the one-time final score for the current untuned
baseline configurations. Any later tuning must be evaluated on new held-out
data; do not reuse this split as an untouched test set.

## Runtime context

All three kernels ran on Kaggle Tesla T4 (15,360 MiB reported per GPU), with
500/500 pages marked successful in their run metadata. These per-crop times are
from one run, without the plan's three-repeat warmed performance protocol; they
are supplementary and must not be presented as the final performance track.

| Pipeline | Model/package | Init time | Median seconds/crop | p95 seconds/crop | Peak host RSS | Total run time |
|---|---|---:|---:|---:|---:|---:|
| PP-StructureV3 | PaddleOCR 3.4.1, PaddleX 3.4.3, PP-DocLayout-S and PP-OCRv5 mobile | 30.44 s | 0.76 s | 2.28 s | 3,310.9 MiB | 537.7 s |
| MinerU Basic | MinerU 4.0.12, Basic tier; one CLI process per crop | included per crop | 15.40 s | 18.37 s | 104.1 MiB parent process only | 8,022.2 s |
| Docling | Docling 2.129.0, RapidOCR 3.9.2 with ONNX Runtime | 0.30 s reported | 3.80 s | 22.97 s | 5,176.4 MiB | 3,626.0 s |

MinerU's per-crop timing includes a new CLI/model startup for each input and is
not directly comparable with the persistent-process PP-StructureV3 and Docling
runs. Its peak RSS records only the parent process, not the child CLI process;
therefore it is not comparable to the other peak-RSS values. The kernel metadata
reports GPU model/capacity but not peak VRAM. Docling's low reported initialization
time does not establish that model downloads or lazy initialization were excluded
from total runtime.

## Scoring and provenance

CER and WER use NFC, case-folding, collapsed whitespace, and retain Vietnamese
diacritics and punctuation. Micro scores aggregate edit counts over reference
characters or words; macro scores average per-crop error rates. Table content is
not separately excluded from these OCR crops by a page-level table detector;
interpret this track as text-crop OCR recognition quality, not full-page region
recall or table-structure quality.

- Per-crop metrics and output-found flags: [`ocr-comparison.json`](ocr-comparison.json)
- PP-StructureV3 raw outputs and runtime metadata: [`pp-structurev3/ocr-500-crops-v1/`](pp-structurev3/ocr-500-crops-v1/)
- MinerU raw ZIP outputs and runtime metadata: [`mineru-basic/ocr-500-crops-v1/`](mineru-basic/ocr-500-crops-v1/)
- Docling raw JSON/Markdown outputs and runtime metadata: [`docling/ocr-500-crops-v1/`](docling/ocr-500-crops-v1/)
- Kaggle kernel definitions: [`../../kernels/ocr-500-crops-v1/`](../../kernels/ocr-500-crops-v1/)
- Dataset manifest and split provenance: [`../../ocr/reference/manifest.json`](../../ocr/reference/manifest.json)
