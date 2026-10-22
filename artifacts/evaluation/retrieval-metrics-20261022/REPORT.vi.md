# Benchmark retrieval bổ sung — 22/10/2026

## Kết luận chính

Giữ nguyên 12 paired intents / 24 câu chữ VI–EN / 48 directional cases và bộ evidence đã freeze. Đã bổ sung Precision@10, Recall@10, MRR@10, nDCG@10; chạy lại thật E5 + SQL + BGE trên RTX 2060 cho 48 cases. Không gọi API dịch/LLM mới, không tải model và không sửa dữ liệu production.

## 1. Metric và cách đọc

- **Qrels:** một chunk được xem là relevant nếu source spans của nó có ít nhất một ký tự không phải khoảng trắng giao với một evidence span bắt buộc. Bao gồm mọi alternative và các chunk mang một phần span bị tách. Map trên toàn corpus target-language, không tạo gold từ kết quả của từng phương pháp.
- **Precision@10:** số annotated support chunks tìm được / 10. Unjudged chunks được tính nonrelevant khi tính metric này, nhưng nhãn không exhaustive nên không được suy ra chúng là sai/nguy hiểm.
- **Recall@10:** số support chunks tìm được / tổng support chunks đã annotate, macro theo case. Mẫu số này bao gồm alternative; không đồng nghĩa phải lấy tất cả alternatives mới trả lời được.
- **MRR@10:** nghịch đảo vị trí support chunk đầu tiên trong top10, bằng 0 nếu không có. Đây là MRR có cutoff 10, không phải MRR toàn corpus.
- **nDCG@10:** binary support relevance, có giảm giá theo thứ hạng. Một alternative trùng ý vẫn được tính relevant; metric có thể thưởng redundancy.
- **Full evidence@10:** scorer gốc yêu cầu AND giữa các components, OR giữa các bundles thay thế; kiểm tra coverage trên source characters. Đây vẫn là chỉ số chính cho độ đủ bằng chứng.
- **Component coverage:** có cả macro theo case trong results.json và micro số components đạt / 112. Không nhầm 107/112 với trung bình macro theo case.

Có 24 bộ qrels intent×target-language: 18 bộ có 1 support chunk, 6 bộ có 2. Hai ngôn ngữ query dùng cùng gold cho cùng intent/target. Vì k=10, ceiling trung bình của Precision@10 theo nhãn là **12,5%**. Precision 12,5% không có nghĩa 87,5% context là sai; thường câu chỉ cần 1–2 chunk.

## 2. Bảng so sánh sáu cấu hình

| Phương pháp | P@10 | R@10 | MRR@10 | nDCG@10 | Đủ evidence@10 | Components |
|---|---:|---:|---:|---:|---:|---:|
| BM25, query gốc | 9.79% | 79.17% | 0.6592 | 0.6850 | 39/48 | 89/112 |
| E5 dense | 10.00% | 80.21% | 0.6189 | 0.6565 | 39/48 | 91/112 |
| Hybrid, query gốc (identity control) | 10.21% | 83.33% | 0.7819 | 0.7799 | 41/48 | 94/112 |
| Translated hybrid, chưa rerank | 12.08% | 97.92% | 0.8785 | 0.9023 | 47/48 | 109/112 |
| E5 dense + BGE | 11.87% | 94.79% | 0.9583 | 0.9503 | 46/48 | 107/112 |
| Translated hybrid + BGE | 12.50% | 100.00% | 0.9896 | 0.9906 | 48/48 | 112/112 |

Hybrid query gốc dùng chính production translated-hybrid fusion với identity queries, cùng weights/candidate sizes/scope; đây là control offline loại bỏ dịch, không là một run legacy hybrid SQL độc lập. BM25 và fusion mới dùng lexemes/queries đã lưu; score reranker của hai nhánh lấy từ paired Colab run đã được verify. Không thay nhãn sau khi xem kết quả.

## 3. Theo hướng ngôn ngữ

| Phương pháp | VI→VI | EN→EN | VI→EN | EN→VI |
|---|---:|---:|---:|---:|
| BM25, query gốc | 12/12 | 12/12 | 8/12 | 7/12 |
| E5 dense | 12/12 | 11/12 | 8/12 | 8/12 |
| Hybrid, query gốc (identity control) | 12/12 | 12/12 | 10/12 | 7/12 |
| Translated hybrid, chưa rerank | 12/12 | 12/12 | 11/12 | 12/12 |
| E5 dense + BGE | 12/12 | 12/12 | 12/12 | 10/12 |
| Translated hybrid + BGE | 12/12 | 12/12 | 12/12 | 12/12 |

**Downside có thật:** hybrid không dịch ở EN→VI chỉ đạt 7/12, thấp hơn dense 8/12. Case F01 EN→VI mất full evidence so với dense. Kết hợp lexical gốc không bảo đảm tăng chất lượng cross-language.

## 4. Ablation và các ca giảm điểm

- Dense → dense+BGE: 39→46 full cases (+7).
- Hybrid identity-query → translated hybrid: 41→47 (+6), trên control cùng fusion/scope. Tín hiệu đến từ việc thay lexical query; chưa có reranker cho identity-hybrid control.
- Translated hybrid → thêm BGE: 47→48 (+1 full case), đồng thời cải thiện thứ hạng và context delivery.
- Dense+BGE → translated-hybrid+BGE: 46→48 (+2), sửa F03/F08 EN→VI; không mất full evidence case nào.
- **F12 EN→VI:** dense+BGE đặt hai support chunks ở rank1,2; translated+BGE ở rank1,3. nDCG giảm **1.0000→0.9197**, nhưng evidence vẫn đủ. Hai support chunks là nguồn thay thế, nên đây là giảm ranking metric, không là lỗi câu trả lời/evidence.
- **F03 VI→EN trước rerank:** hybrid identity đưa gold rank2, translated hybrid rank4; MRR 0.50→0.25, nDCG 0.6309→0.4307, dù vẫn đủ evidence. BGE đưa gold về rank1.
- **F03 EN→VI ở cấu hình cuối:** gold vẫn rank2, MRR case=0.5. Đạt top10 không đồng nghĩa support chunk luôn đứng đầu.
- **F08 dịch thuật:** bản dịch đã lưu dùng “cổ phiếu” cho inventory “stock”. Retrieval vẫn thành công, nhưng lỗi thuật ngữ còn tồn tại. 24/24 API calls thành công không phải 24/24 bản dịch đúng.

## 5. Độ bất định

Paired percentile bootstrap 10.000 lần, seed 20261022, resample theo **12 intent clusters**, giữ bốn directional cases của mỗi intent cùng nhau. Không coi 48 cases là 48 mẫu độc lập. Các intent vẫn chia sẻ nguồn và đã được dùng để phát triển, nên đây chỉ là mô tả uncertainty có điều kiện, không là kiểm định generalization độc lập.

| So sánh | Delta full-evidence | 95% interval |
|---|---:|---:|
| Dense → Dense+BGE | +14.58 điểm % | [4.17, 27.08] |
| Dense+BGE → Translated+BGE | +4.17 điểm % | [0.00, 10.42] |
| Hybrid gốc → Translated hybrid | +12.50 điểm % | [4.17, 22.92] |
| Translated hybrid → thêm BGE | +2.08 điểm % | [0.00, 6.25] |

Mức tăng 46→48 có interval chứa 0: chưa đủ để tuyên bố một cải thiện tổng quát có độ chắc chắn cao. Freeze/hash giữ khả năng tái lập; không biến development set thành held-out test.

## 6. Downside khi đưa context cho LLM

Dùng **RAGService.generate_answer thật**, mock provider/cache, giữ giới hạn hiện hành 5000 ký tự và format source headers. Chấm lại exact source spans của phần prefix thực sự được gửi. Đây là kiểm tra prompt context, không sinh/chấm câu trả lời và không gọi LLM.

| Phương pháp | Full ở top10 | Full sau context packing | Mất thêm do cap | Dừng trước generation |
|---|---:|---:|---:|---:|
| BM25, query gốc | 39/48 | 38/45 trường hợp có packing | 1 | 3 |
| E5 dense | 39/48 | 36/46 trường hợp có packing | 3 | 2 |
| Hybrid, query gốc (identity control) | 41/48 | 41/47 trường hợp có packing | 0 | 1 |
| Translated hybrid, chưa rerank | 47/48 | 46/48 trường hợp có packing | 1 | 0 |
| E5 dense + BGE | 46/48 | 46/48 trường hợp có packing | 0 | 0 |
| Translated hybrid + BGE | 48/48 | 48/48 trường hợp có packing | 0 | 0 |

- Dense mất thêm: F01 EN→VI, F03 VI→EN, F09 VI→VI.
- Translated hybrid chưa BGE mất thêm F08 EN→VI: full top10 47/48 nhưng full sau cap còn 46/48.
- Cấu hình translated+BGE giữ 48/48 evidence sau cap trong bộ này; dense+BGE giữ 46/48. Không bảo đảm mọi tài liệu dài hơn vẫn vậy.
- Các ca dừng trước generation do no-context/record-type guard được đánh dấu riêng, không được giả định đã gửi đủ context.

### Lỗi citation validation tái lập được (không là real-LLM error rate)

Probe dùng cap thực 5000 ký tự, hai context synthetic S1/S2, S1 dài 6000 ký tự.
Packing chỉ gửi S1. Mocked provider trả `Synthetic answer [S2]`; RAG vẫn chấp nhận
`source_ids=["S2"]` trong khi result.contexts chỉ có S1. Nguyên nhân trong
`src/core/rag/rag_service.py`: `allowed_source_ids` lấy từ `contexts` ban đầu thay
vì `prompt_contexts` sau packing.

Đây là correctness risk của validator, không là một lỗi đo được trên 48 câu hoặc
một estimate về faithfulness của LLM thật. Chưa sửa code production trong task
benchmark. Nên chuyển An sửa validator theo contexts đã gửi và thêm regression
test trước khi demo; sau đó giữ nguyên bộ benchmark để kiểm tra lại.

Kết quả: `citation-validation-probe.json`. Tái lập hoàn toàn offline:

```bash
PYTHONPATH=src .venv/bin/python artifacts/evaluation/retrieval-metrics-20261022/reproduce_citation_validation.py
```

## 7. Latency mới đo, không lấy timing Colab gộp

NVIDIA GeForce RTX 2060, FP32, batch4; E5 và BGE pinned revisions, cache-only. 48 cases × 3 arms, thứ tự arm counterbalance bằng RNG seed cố định. Mỗi arm chạy lại SQL và BGE độc lập, không dùng lại logits giữa arms. E5 encode query đo mới một lần/case và dùng cùng quan sát đó cho ba arms. Model warm; CUDA synchronized.

SQL production chạy trên **temporary tables trong session Supabase**, chứa 1063 passages/10 documents frozen, scope 5 target-language documents. Bảng public production không được ghi; transaction rollback cuối run. IDs/cache/size của replica khác production thật, nên không coi là SLA hay latency hoàn chỉnh của API.

| Phương pháp | Median warm stages | p95 warm stages | SQL/candidate median | BGE median |
|---|---:|---:|---:|---:|
| E5 dense | 0.533 s | 0.988 s | 0.524 s | 0.000 s |
| E5 dense + BGE | 1.441 s | 1.899 s | 0.342 s | 1.079 s |
| Translated hybrid + BGE | 3.420 s | 4.166 s | 2.354 s | 1.056 s |

Model initialization + warmup: **75.3 s**, không nằm trong warm request numbers. PyTorch peak allocated: **3.25 GiB** (không phải toàn bộ GPU/process memory). Max BGE pair **500/1024 tokens**, không truncation.

Tất cả **144 top10 rankings mới** (48×3) khớp chính xác ranking frozen và mọi ranking metric/full-evidence tương ứng. Integrated selector translated_hybrid_rerank được smoke-check khớp với pipeline stage-isolated ở case đầu. Xem `../retrieval-latency-20261022/live-frozen-parity.json`.

**Chưa gồm:** API dịch mới, answer generation, UI/API gateway, concurrency, cold app startup đầy đủ. Chỉ một pass qua 48 câu; p95 mô tả tập nhỏ, chưa là performance certification. Hai nhánh dense dùng cùng SQL nhưng timing khác vì cache/network/order; không được kết luận BGE làm SQL nhanh hơn.

Bản dịch dùng cache frozen. 24 API calls trong preparation ngày 21/10 có median ~0,449 s, mean ~0,501 s, max ~1,615 s; đây là dữ liệu lịch sử, không cộng các median đó vào bảng rồi gọi là latency end-to-end hôm nay.

## 8. Điều chưa được chứng minh và ưu tiên

1. **Chi phí đổi lấy +2 cases:** median warm stages tăng từ ~1,44 s dense+BGE lên ~3,42 s translated+BGE, trước cả network API dịch nếu cache miss. Ba lần tìm kiếm SQL và thêm dependency dịch là chi phí thực.
2. **Scope thuận lợi:** năm tài liệu target-language đã biết và admin role; frozen bilingual corpus mô phỏng. API hiện không cấp verified language map, nên không tự nhận kết quả này là production mixed-language/unscoped accuracy.
3. **Nhãn ít và có curated alternatives:** qrels 1–2 chunks/case, unjudged không exhaustive; không kết luận P@10 thấp là rác, nDCG cao là trả lời đúng.
4. **Chưa đo generation:** context đủ không bảo đảm faithfulness/citation/độ đủ ý. Phần này cần kết quả của An.
5. **Chưa có independent held-out/no-answer/load test:** không thêm vào mẫu số hoặc tự gán nhãn mới để kết quả đẹp hơn.

Trước review: giữ cấu hình đã chốt, dùng bảng metric + latency có chú thích và hai failure examples; không cần thử thêm model. Sau review: independent questions, unscoped routing, terminology translation, broader corpus/ACL and concurrency validation. Có thể nghiên cứu bỏ SQL branch có scope rỗng và cache/parallel I/O; chưa benchmark hoặc đổi production code cho những tối ưu đó.

## 9. Tái lập và file đầu ra

```bash
PYTHONPATH=src:tests HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 .venv/bin/python -m unittest test_fresh_retrieval_metrics test_fresh_reviewed_reranker test_translated_fresh_reranker test_evidence_metrics
PYTHONPATH=src:tests HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 .venv/bin/python scripts/retrieval/evaluate_fresh_retrieval_metrics.py --output-dir artifacts/evaluation/<new-metrics-folder>
PYTHONPATH=src:tests HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 .venv/bin/python scripts/retrieval/benchmark_fresh_stage_latency.py --output-dir artifacts/evaluation/<new-latency-folder> --limit 48
```

Latency command yêu cầu CUDA, cached E5/BGE, DATABASE_URL có quyền tạo TEMP tables. Không tải model và không gọi Groq. Dùng folder mới, không ghi đè kết quả cũ.

- `results.json`: toàn bộ metric theo case/method/direction, bootstrap, context-loss.
- `metrics.csv`: bảng tổng hợp dùng làm slide.
- `qrels.json`: mapping gold hỗ trợ được dẫn xuất từ nhãn frozen.
- `../retrieval-latency-20261022/`: actual inference/SQL timing, parity và run provenance.
- `../../archive/retrieval-metrics-20261022-initial/`: bản phân tích đầu, chỉ probe context cho ba arms; giữ để đối chiếu. Bản hiện tại thêm probe mọi ablation; core metrics không đổi.

Các manifest/nhãn/rankings nguồn giữ nguyên hash. Production code/model/index không bị thay đổi trong task benchmark này.
