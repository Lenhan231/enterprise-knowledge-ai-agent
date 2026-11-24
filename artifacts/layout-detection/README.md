# Layout detection benchmark

The v8 benchmark covers 51 pages from eight Vietnamese documents and 712 reference regions. The classes are text (391), title (151), table (60), and figure (110, including stamps and signatures). Text is annotated in paragraph or list blocks. Table cells belong to the table region.

## Results

| Detector | Text F1 | Title F1 | Table F1 | Figure F1 | Macro F1 |
| --- | ---: | ---: | ---: | ---: | ---: |
| PP-DocLayoutV3 (production) | 60.4% | 66.9% | 80.0% | 61.1% | 67.1% |
| Heron-101 | 31.3% | 55.4% | 76.3% | 56.8% | 54.9% |
| DocLayout-YOLO-DocStructBench | 45.1% | 52.8% | 54.5% | 6.6% | 39.8% |

The primary score uses one-to-one matching within each class at IoU ≥ 0.50. At IoU ≥ 0.75, PP-DocLayoutV3 achieves 50.8% text, 47.8% title, 74.3% table, and 51.1% figure F1. Reference revisions were audited on this cohort. These are development benchmark results, with independent held-out validation still needed.

## Examples

- **Page 006 (Bảo Hộ Lao Động, source PDF page 7).** The reference uses one box for a contiguous list. PP-DocLayoutV3 detects separate list items, so the boxes cannot all match the reference under one-to-one IoU scoring. Across this page, PP matches 7 of 13 text regions and its table box overlaps the reference at IoU 0.939. [Text overlay](results/four-classes-v8/example-page-006.png)
- **Page 017 (Phước Hòa, source PDF page 8).** The production table box achieves IoU 0.991. PP labels a partial red stamp as sidebar text despite IoU 0.698 with the stamp reference. The stamp prediction therefore fails class-aware matching. [Page overlays](results/four-classes-v8/comparison.html)

## Evidence and reproduction

- [Comparison HTML](results/four-classes-v8/comparison.html) needs the repository's source images at their relative paths. Open it from a checkout.
- [Metrics](results/four-classes-v8/metrics.json), [mismatches](results/four-classes-v8/mismatches.json), and [inference metadata](results/four-classes-v8/run_metadata.json).
- [Frozen v8 reference](references/layout-four-classes-v8.jsonl) and [v8 audit decisions](references/layout-four-classes-v8-provenance.json). The parent v7 snapshot is identified by hash in the audit log.
- The saved Kaggle CPU outputs in `results/kaggle/layout-detection/` reproduce the scores without running inference again.

From the repository root:

```sh
python artifacts/layout-detection/benchmark/evaluate.py --four-classes \
  --references artifacts/layout-detection/references/layout-four-classes-v8.jsonl \
  --predictions artifacts/layout-detection/results/kaggle/layout-detection \
  --output artifacts/layout-detection/results/four-classes-v8
```
