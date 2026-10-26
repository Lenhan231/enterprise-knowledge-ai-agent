# Kaggle 5-page pipeline pilot

This kernel uses the current shared-HTML Docling/VietOCR settings, including Docling Layout Heron 101 and the pinned Granite Vision 4.1 4B table structure model, with a separate private 5-page input dataset. The five images are one reviewed page from each of five source documents.

Run from this directory after creating/updating the private dataset from `input-package/`:

```bash
kaggle datasets create -p input-package
kaggle kernels push -p .
```

For subsequent dataset changes use `kaggle datasets version -p input-package -m "Update 5-page pilot inputs"`; do not update the full benchmark dataset.

Outputs are smoke-test evidence only. The kernel records five input pages and per-page conversion status; its metrics are not comparable to the full benchmark and must not be used to tune thresholds.
