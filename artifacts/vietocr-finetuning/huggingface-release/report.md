# Enterprise Printed OCR Fine-tuning Report

## Scope and split

This comparison fine-tunes VietOCR and Tesseract on the same reviewed Vietnamese and English printed line crops. Data includes reviewed lines from real enterprise report PDFs, AI-generated invoice samples, and supplemental AI-generated English samples for coverage; a subset has deliberate rotations from -70 to +70 degrees. Transcript corrections were merged into root annotations and manifests before the run.

Splits are grouped by source PDF. Training contains 4,474 Vietnamese and 1,617 English lines; validation contains 500 Vietnamese and 989 English lines; test contains 1,239 Vietnamese and 60 English lines (6,091 / 1,489 / 1,299 total). Applied corrections: 102 train, 2 validation, and 10 test. No samples were excluded for out-of-vocabulary characters.

## Held-out test results

Metrics use the run's canonical text normalization. Exact match is line-level.

| Domain | VietOCR baseline WER | VietOCR fine-tuned WER | VietOCR baseline CER | VietOCR fine-tuned CER | VietOCR baseline exact | VietOCR fine-tuned exact |
|---|---:|---:|---:|---:|---:|---:|
| Overall (n=1,299) | 10.12% | 4.63% | 5.59% | 1.85% | 52.58% | 68.82% |
| Vietnamese printed (n=1,239) | 10.13% | 4.58% | 5.65% | 1.87% | 51.82% | 68.68% |
| English printed (n=60) | 10.00% | 5.96% | 4.28% | 1.25% | 68.33% | 71.67% |

| Domain | Tesseract baseline WER | Tesseract fine-tuned WER | Tesseract baseline CER | Tesseract fine-tuned CER | Tesseract baseline exact | Tesseract fine-tuned exact |
|---|---:|---:|---:|---:|---:|---:|
| Overall (n=1,299) | 8.88% | 7.36% | 2.94% | 2.65% | 47.04% | 57.04% |
| Vietnamese printed (n=1,239) | 8.84% | 7.48% | 3.02% | 2.75% | 46.81% | 56.01% |
| English printed (n=60) | 10.00% | 3.65% | 1.34% | 0.49% | 51.67% | 78.33% |

On all 1,299 test lines, VietOCR fine-tuning reduced WER from **10.12% to 4.63%** and CER from **5.59% to 1.85%**. Tesseract fine-tuning reduced WER from **8.88% to 7.36%** and CER from **2.94% to 2.65%**. VietOCR has the lower aggregate Vietnamese test WER; Tesseract has the lower English test WER, but that result is based on only 60 lines.

## Validation and checkpoint selection

| Model | Domain | WER | CER | Exact match |
|---|---|---:|---:|---:|
| VietOCR | Vietnamese printed (n=500) | 32.85% | 29.80% | 60.20% |
| VietOCR | English printed (n=989) | 49.45% | 15.73% | 1.72% |
| Tesseract | Vietnamese printed (n=500) | 33.62% | 26.56% | 49.20% |
| Tesseract | English printed (n=989) | 70.17% | 50.71% | 0.51% |

VietOCR used validation-WER early stopping and selected step **750** (best macro domain WER **41.15%**); it stopped after step 1,250 when validation failed to improve twice. Tesseract ran its fixed **5,000-iteration** limit without validation-based early stopping. Its validation performance is weak, especially on English. The validation English set contains 989 AI-generated lines while the held-out English test contains only 60 lines from a different source PDF, so those values reflect a substantial source/style mismatch and should not be treated as a directly comparable estimate of English generalization.

## Training settings

- **VietOCR:** VGG Seq2Seq (`vgg19_bn`), pretrained `vgg_seq2seq`, batch size 32, max learning rate 1e-4; CNN frozen for 300 steps, then unfrozen. Best checkpoint at step 750.
- **Tesseract:** LSTM fine-tuning from `vie`, 5,000 maximum iterations, 90/10 train/evaluation split within the training corpus. No early stopping was configured for this run.

## Interpretation and limits

Both fine-tunes improved their aggregate held-out test metrics over their own pretrained baselines. VietOCR is the stronger overall result on this test cohort. Tesseract improved more modestly overall and substantially on the small English test subset. The English test sample is small, and the English validation samples come from a different source/style, so the English comparison is preliminary. These results support this specific source-PDF-disjoint printed-line benchmark; they do not establish page-level document OCR performance or handwriting recognition quality.

The published model package contains weights, compact configuration, aggregate metrics, and this report. It does not include source PDFs, crops, labels, or per-line predictions.
