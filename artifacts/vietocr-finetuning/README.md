# Latest enterprise printed OCR fine-tuning

This archive records the latest printed Vietnamese and English OCR fine-tuning experiment: paired Kaggle notebooks, outputs from completed version 3 runs, aggregate metrics, and the previously published Hugging Face snapshot.

## Kaggle notebooks

- [`kaggle/vietocr/`](kaggle/vietocr/) — VietOCR fine-tuning notebook and metadata.
- [`kaggle/tesseract/`](kaggle/tesseract/) — Tesseract fine-tuning notebook and metadata.
- [`kaggle/benchmark-metrics.json`](kaggle/benchmark-metrics.json) — 1,299-line test/validation metrics.
- [`kaggle/vietocr-output-v3/`](kaggle/vietocr-output-v3/) — completed Kaggle version 3 VietOCR checkpoint, config, metrics, run metadata, and training log.
- [`kaggle/tesseract-output-v3/`](kaggle/tesseract-output-v3/) — completed Kaggle version 3 Tesseract model, metrics, run metadata, and captured `tesstrain` log.
- [`kaggle/dataset-and-kernel-notes.md`](kaggle/dataset-and-kernel-notes.md) — expected Kaggle input structure.

Both notebook metadata files link the current private printed OCR dataset. The notebooks save their weights and metrics as Kaggle working outputs and no longer upload anything to Hugging Face. Tesseract's verbose `tesstrain` commands are redirected to `/kaggle/working/tesstrain-training.log`; on failure the last log lines are shown.

## Experiment protocol

The private input is the printed-only `Enterprise Printed OCR Lines` dataset. Splits are grouped by source PDF; the test set is held out from training and checkpoint selection. The archive excludes the source images, labels, and per-line prediction audits.

| Split | Rows | Printed Vietnamese | English |
|---|---:|---:|---:|
| Train | 6,096 | 4,479 | 1,617 |
| Validation | 1,489 | 500 | 989 |
| Test | 1,299 | 1,239 | 60 |

VietOCR used VGG Seq2Seq with `vgg19_bn`, batch size 32, max learning rate `1e-4`, a 300-step frozen CNN phase, then unfreezing in 250-step blocks. Validation used the unweighted mean WER of the Vietnamese-print and English domains; after two checks without improvement, training stopped and restored the best checkpoint. The selected checkpoint was step 1,750 (validation macro-domain WER 39.37%).

Tesseract used the Vietnamese `vie` LSTM start model, `ratio_train=0.9`, and `max_iterations=5000`, with early stopping disabled.

## Held-out test results

CER and WER are normalized character and word error rates; lower is better. Exact match is the fraction of lines transcribed exactly; higher is better. Values show each recognizer's pretrained baseline followed by its version 3 fine-tuned result.

| Recognizer | Domain | Lines | CER baseline → v3 | WER baseline → v3 | Exact match baseline → v3 |
|---|---|---:|---:|---:|---:|
| VietOCR | All | 1,299 | 5.59% → **1.56%** | 10.12% → **4.36%** | 52.58% → **68.36%** |
| VietOCR | Printed Vietnamese | 1,239 | 5.65% → **1.60%** | 10.13% → **4.34%** | 51.82% → **67.80%** |
| VietOCR | English | 60 | 4.28% → **0.58%** | 10.00% → **5.00%** | 68.33% → **80.00%** |
| Tesseract | All | 1,299 | 2.94% → **2.68%** | 8.88% → **7.45%** | 47.04% → **56.12%** |
| Tesseract | Printed Vietnamese | 1,239 | 3.02% → **2.79%** | 8.84% → **7.59%** | 46.81% → **55.04%** |
| Tesseract | English | 60 | 1.34% → **0.43%** | 10.00% → **3.27%** | 51.67% → **78.33%** |

## Run notes and limitations

- The current dataset's manifest counts 100 corrected train labels, 2 validation labels, and 10 test labels. `dataset-info.json` still declares 102 train corrections. The notebooks report this stale metadata and use the row-level manifest count; the saved metrics record 100/2/10.
- Tesseract's `tesstrain` log contains 72 `Compute CTC targets failed` messages. Training completed and produced the reported test metrics; inspect [`kaggle/tesseract-output-v3/training-log.txt`](kaggle/tesseract-output-v3/training-log.txt) before using the model for another domain.
- The English test subset has only 60 lines, so its scores are less stable than the larger Vietnamese subset.
- The Tesseract training command echoes many generated box-file commands. The notebook now redirects that output to `/kaggle/working/tesstrain-training.log` and prints the tail if training fails.
- Version 3 no longer uploads weights to Hugging Face. The [`huggingface-release/`](huggingface-release/) files are the earlier published snapshot, not the version 3 outputs.

The earlier Hugging Face snapshot is pinned to revision `6deb1cb10ecbf240aead77525e80aa4c58adfb23`.

[`manifest.json`](manifest.json) records byte sizes and SHA-256 hashes for all archived Kaggle and Hugging Face files. Private training data, source documents, and credentials are excluded.
