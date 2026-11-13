# Invoice 50 new VietOCR benchmark

Shared OCR: lenhanm1/enterprise-printed-ocr-vietocr-tesseract @ 6deb1cb10ecbf240aead77525e80aa4c58adfb23
Qwen3-1.7B revision: 70d244cc86ccca08cf5af4e1e306ecf908b1ad5e

| Model | Success | Whole invoice exact | Item row exact | Description CER | Description WER | Mean end-to-end s |
|---|---:|---:|---:|---:|---:|---:|
| modal | 50/50 | 10.0% | 96.1% | 0.003 | 0.005 | 22.3294 |
| qwen17b | 50/50 | 44.0% | 90.7% | 0.003 | 0.005 | 28.3814 |
| gemini | 50/50 | 76.0% | 96.1% | 0.003 | 0.005 | 17.4498 |
