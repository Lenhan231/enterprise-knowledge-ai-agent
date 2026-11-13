# Bảng dùng cho slide Review 2

| Phương pháp | P@10 | R@10 | MRR@10 | nDCG@10 | Full evidence | Median / p95* |
|---|---:|---:|---:|---:|---:|---:|
| E5 dense | 10.00% | 80.21% | 0.6189 | 0.6565 | 39/48 | 0.53 / 0.99 s |
| E5 dense + BGE | 11.87% | 94.79% | 0.9583 | 0.9503 | 46/48 | 1.44 / 1.90 s |
| Translated hybrid + BGE | 12.50% | 100.00% | 0.9896 | 0.9906 | 48/48 | 3.42 / 4.17 s |

*Warm E5+SQL+BGE stages, RTX2060/FP32, temp replica của corpus frozen. Chưa gồm API dịch mới và LLM generation; không là latency đầy đủ của app.

Điểm cần nói:
- 12 paired intents / 48 directional cases, không phải 48 câu độc lập. Development evaluation trên corpus mô phỏng.
- P@10 có ceiling 12,5% theo gold 1–2 support chunks/case; không thể suy ra 87,5% context sai.
- Translated hybrid chưa rerank đã đạt 47/48; BGE lên 48/48 và giúp giữ gold trong context cap.
- Downside: chậm hơn, có lỗi dịch thuật, một ca nDCG giảm dù evidence đủ; gain 46→48 có cluster-bootstrap CI95 [0;10,42] điểm phần trăm.
- 48/48 evidence retrieval không phải 100% answer accuracy.
- Một lỗi validator cần An kiểm tra: mocked answer được phép cite source đã bị context cap loại bỏ. Probe offline; không là real-LLM failure rate.

Chi tiết: [REPORT.vi.md](REPORT.vi.md).
