---
pipeline_tag: image-to-text
language:
- vi
- en
tags:
- vietocr
- tesseract
- OCR
- vietnamese
- english
license: other
---

# Enterprise Printed OCR Models

Fine-tuned VietOCR VGG Seq2Seq and Tesseract LSTM weights for Vietnamese and English printed line crops. Training data combines reviewed labels from real enterprise report PDFs, AI-generated invoice samples, and supplemental AI-generated English samples; some image crops were deliberately rotated from -70 to +70 degrees. Train, validation, and test were grouped by source PDF.

The repository includes model weights, compact configuration, aggregate validation/test metrics, and a benchmark report. It does not include source PDFs, images, labels, or per-line predictions.

## Test snapshot

| Model | Domain | Lines | Baseline WER | Fine-tuned WER | Baseline CER | Fine-tuned CER | Baseline exact | Fine-tuned exact |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| VietOCR | Vietnamese printed | 1239 | 10.13% | 4.58% | 5.65% | 1.87% | 51.82% | 68.68% |
| VietOCR | English printed | 60 | 10.00% | 5.96% | 4.28% | 1.25% | 68.33% | 71.67% |
| VietOCR | Overall | 1299 | 10.12% | 4.63% | 5.59% | 1.85% | 52.58% | 68.82% |
| Tesseract | Vietnamese printed | 1239 | 8.84% | 7.48% | 3.02% | 2.75% | 46.81% | 56.01% |
| Tesseract | English printed | 60 | 10.00% | 3.65% | 1.34% | 0.49% | 51.67% | 78.33% |
| Tesseract | Overall | 1299 | 8.88% | 7.36% | 2.94% | 2.65% | 47.04% | 57.04% |

VietOCR's best checkpoint was selected at step 750 with validation-WER early stopping. Tesseract ran 5,000 iterations without early stopping. The English test subset has 60 lines; see [report.md](report.md) for split details, validation results, and limitations.

## Quick start: VietOCR

Install PyTorch for your environment, then install the model library and Hugging Face client:

```bash
python -m pip install vietocr==0.3.13 huggingface_hub pillow
```

Run recognition on a cropped, single-line image:

```python
import torch
from huggingface_hub import hf_hub_download
from PIL import Image
from vietocr.tool.config import Cfg
from vietocr.tool.predictor import Predictor

repo_id = "lenhanm1/enterprise-printed-ocr-vietocr-tesseract"
weights = hf_hub_download(repo_id, "vietocr/vgg-seq2seq-enterprise-print.pth")
config = Cfg.load_config_from_name("vgg_seq2seq")
config["weights"] = weights
config["device"] = "cuda:0" if torch.cuda.is_available() else "cpu"
predictor = Predictor(config)
with Image.open("line.png") as image:
    print(predictor.predict(image.convert("RGB")))
```

## Quick start: Tesseract

Install Tesseract on the machine (for Debian/Ubuntu, `sudo apt-get install tesseract-ocr`) and the Hugging Face client:

```bash
python -m pip install huggingface_hub
```

Download the fine-tuned language file and run it on a cropped, single-line image. `--psm 7` is the single-line page segmentation mode used in this benchmark.

```python
import subprocess
from pathlib import Path
from huggingface_hub import hf_hub_download

repo_id = "lenhanm1/enterprise-printed-ocr-vietocr-tesseract"
model_path = Path(hf_hub_download(repo_id, "tesseract/vie_enterprise_print.traineddata"))
result = subprocess.run(
    ["tesseract", "line.png", "stdout", "-l", "vie_enterprise_print",
     "--psm", "7", "--tessdata-dir", str(model_path.parent)],
    check=True, capture_output=True, text=True,
)
print(result.stdout.strip())
```

Both models were fine-tuned and benchmarked on line crops. For a full page, first detect and crop text lines, then recognize each crop.

## Files

- `vietocr/vgg-seq2seq-enterprise-print.pth` — fine-tuned VietOCR weights.
- `tesseract/vie_enterprise_print.traineddata` — fine-tuned Tesseract model.
- `config/` and `metrics/` — compact run settings and aggregate metrics.
