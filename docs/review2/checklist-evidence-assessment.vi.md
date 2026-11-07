# Đối chiếu câu hỏi và checklist Review 2 — phần Huy

Ngày đối chiếu: 24/10/2026. Tài liệu được đọc trực tiếp: [Report Tasks cho Review lần 2.docx trên Google Docs](https://docs.google.com/document/d/14kHUIu00ToNM7N3qnDWoMMO-Wg8WldcP/edit).

Đây là hướng dẫn điền cho phần tokenization/embedding/retrieval, không phải xác nhận toàn nhóm đã hoàn tất. Không chỉnh Google Docs, không chạy inference mới. Bổ sung kiểm tra database read-only ngày24/10: [bằng chứng kiểm đếm](dataset-count-verification-20261024.json). Database có7 bản ghi documents, nhưng chỉ5 tài liệu ready với532 retrieval chunks; hai bản ghi failed/parsed chưa có vector. Tổng parser chunks toàn database là546, không phải532.

Cập nhật phạm vi ngày26/10: xem [lời thuyết trình mới](huy-speaking-notes-20261026.vi.md). Main được kiểm tra tại1ffe05b mặc định translated_hybrid_rerank/RAGtop5/cap24.000ký tự; benchmark Huy vẫn top10. Các mục cần deployment/generation owner xác nhận dưới đây phản ánh chứng cứ đã đọc trong repo, không phủ nhận các phép đo mới của thành viên khác.

## Phạm vi thống nhất với dataset chung của nhóm

**Phần giới thiệu dữ liệu dùng 5 tài liệu tiếng Việt đã ready / 532 retrieval chunks trên Supabase**, đã đối chiếu bằng truy vấn read-only ngày24/10 và snapshot đã lưu. Đây là phạm vi dataset sẵn sàng truy hồi, không phải toàn bảng documents. Không tính năm bản EN thử nghiệm riêng thành tài liệu đã triển khai của nhóm.

| Tài liệu chung | Định dạng | Chunk VI |
|---|---|---:|
| Inventory Management Policy Manual | DOCX | 18 |
| SOP Cycle Count and Stock Adjustment | PDF | 9 |
| Policy Rules Registry | CSV | 12 |
| Inventory Control and Reorder Planner | XLSX | 485 |
| Inventory Policy Training Deck | PPTX | 8 |
| **Tổng** | **5 tài liệu VI** | **532** |

Số token E5 của phần VI: **224.845 token đầu vào**, gồm prefix/special tokens; dài nhất **476/512**, không overlength. Đây không phải số token duy nhất của raw files.

**Phần thực nghiệm retrieval phải phân biệt riêng:** Huy dùng thêm năm bản EN tương ứng (531 chunk), tạo corpus đánh giá 10 phiên bản tài liệu / 1.063 chunk. Các số 80 ca, 69/80, latency, bootstrap và11 failures là kết quả của thí nghiệm song ngữ này. Không gán chúng cho phép đo chỉ trên5 tài liệu VI.

Nếu hỏi riêng trên corpus VI, [metrics CSV](../../artifacts/evaluation/heldout-review2-v1/runs/review2-reviewed-r1-sql-20261022/metrics.csv) có hai nhóm `vi->vi` và `en->vi`; final method đạt17/20 mỗi nhóm, tổng34/40. Đó là lát cắt target-VI của cùng run, không phải một lần benchmark mới; không tự điền Recall/latency tổng hợp từ bảng all80.

## Nguồn mở nhanh

- [Mục lục bằng chứng tiếng Anh](README.md).
- [Báo cáo Huy](huy-retrieval-report.vi.md): cấu hình chunking, schema, thí nghiệm và giới hạn.
- [Báo cáo run cuối](../../artifacts/evaluation/heldout-review2-v1/runs/review2-reviewed-r1-sql-20261022/REPORT.vi.md).
- [Metrics CSV](../../artifacts/evaluation/heldout-review2-v1/runs/review2-reviewed-r1-sql-20261022/metrics.csv).
- [Protocol](../../artifacts/evaluation/heldout-review2-v1/protocol.json), [cấu hình run](../../artifacts/evaluation/heldout-review2-v1/runs/review2-reviewed-r1-sql-20261022/config.json).
- [Thống kê token/model](retrieval-report-stats.json).
- [Kiểm tra nhãn](../../artifacts/evaluation/heldout-review2-v1/validation.json), [tình trạng review](../../artifacts/evaluation/heldout-review2-v1/review-status.json), [overlap audit](../../artifacts/evaluation/heldout-review2-v1/overlap-audit.json).
- [Phân tích kết quả/bootstrap](../../artifacts/evaluation/heldout-review2-v1/runs/review2-reviewed-r1-sql-20261022/analysis.json), [candidate diagnostics](../../artifacts/evaluation/heldout-review2-v1/runs/review2-reviewed-r1-sql-20261022/candidate-diagnostics.json).

## 1. Các ô checklist RAG đầu tài liệu: điền gì?

| Mục Google Docs | Nội dung có thể điền | Mức chứng cứ và nguồn |
|---|---|---|
| 1.1 Chunking | Parser chia theo câu/cấu trúc bảng; văn bản mặc định mục tiêu 1.100 ký tự. Sau đó đếm token theo embedding model, chia thêm nếu quá giới hạn, giữ header và ánh xạ nguồn. E5 cap 512, có dự phòng prefix/special tokens. | Đã có implementation và token audit; chưa có chunk-size/overlap ablation để gọi cấu hình tối ưu. Xem báo cáo Huy §2, [parser chunking docs](../../src/core/document_processing/docs/chunking.md), [embedding chunker](../../src/core/tokenization/embedding_chunker.py). |
| 1.2 Embedding | intfloat/multilingual-e5-base; 768 chiều; L2 normalization; prefix query:/passage:; pinned revision; pretrained, không fine-tune trong benchmark. | Đủ cho cấu hình đã dùng. Protocol + thống kê token/model + [E5 rollout](../e5-production-rollout.md). |
| 1.3 Vector DB | Dataset chung có5 tài liệu VI/532 chunk trên Supabase theo snapshot; PostgreSQL/pgvector, cosine similarity và document/company/access scope. | Tách khỏi benchmark riêng chạy SQL production trên TEMP tables với corpus song ngữ frozen; không coi10 phiên bản benchmark là10 tài liệu đã upload chung. Xem [E5 rollout](../e5-production-rollout.md) và cấu hình run. |
| 1.4 Schema metadata | document_id, filename, company/allowed_roles; page/section/table/row khi parser có; source_parser_index, source_spans, source_content_sha256; model/token metadata và manifest. documents → document_parser_chunks → document_chunks + vector. | Đủ mô tả trường/vai trò; không khẳng định mọi chunk có đủ mọi trường. Báo cáo Huy §3.2. Metadata frozen còn nhãn Qwen cũ, actual vectors là E5 đã xác minh. |
| 1.5 Grounding | Trong benchmark đã lưu, retrieval được chấm trên top10 evidence có nguồn. Prompt, context packing, citation validation và refusal thuộc generation; số context runtime cấu hình riêng. | Chỉ một phần. Không đánh dấu chất lượng grounding/refusal đã chứng minh từ retrieval score; cần An/LLM owner bổ sung prompt, output và kết quả chấm thực. |
| 1.6 File output JSONL/Parquet | Đầu ra parser VI được lưu dạng JSONL; các artifacts đánh giá retrieval gồm corpus JSONL, câu hỏi/evidence/results JSON và metrics CSV. | Dẫn [parser VI](../../artifacts/evaluation/heldout-review2-v1/inputs/parser_vi.jsonl) cho phần dữ liệu chung. [Corpus](../../artifacts/evaluation/heldout-review2-v1/inputs/corpus.jsonl) của benchmark chứa cảVI+EN nên ghi rõ phạm vi. Không cần tạo Parquet chỉ để điền checklist; JSON thường và JSONL khác nhau. |

## 2. Câu hỏi giai đoạn 1 — dữ liệu

### Dữ liệu offline của nhóm có bao nhiêu mẫu? Nếu nhóm chỉ dùng public dataset thì ghi rõ, không bịa số liệu offline.

**Đủ số tài liệu/chunk của dataset chung theo snapshot; nguồn raw/size/page do data owner bổ sung.**

Trả lời: “Dataset chung sẵn sàng truy hồi của nhóm gồm5 tài liệu nghiệp vụ mô phỏng VietStyle bằng tiếng Việt, thuộc5 định dạng DOCX, PDF, CSV, XLSX và PPTX, có532 retrieval chunks. Kiểm tra Supabase ngày24/10 xác nhận5 tài liệu này ở trạng thái ready. Toàn bảng documents có thêm2 bản ghi chưa index, không tính vào dataset ready đang trình bày. Đây là dữ liệu mô phỏng, không phải dữ liệu doanh nghiệp thực hoặc chỉ dùng public dataset.”

Nguồn: báo cáo Huy §2.1, retrieval-report-stats.json phần `languages.vi`, E5 rollout. Nếu hỏi thêm phạm vi benchmark, giải thích riêng5 bản EN thử nghiệm,20ý/40text/80case. Không cộng Bảo An/VietStyle PDF mới vào dataset chung hoặc benchmark đã chốt.

### Nhận xét mất cân bằng của các em là định lượng hay định tính? Câu "dữ liệu mất cân bằng nhẹ" sẽ bị trừ điểm. Phải là kiểu: "Lớp A: 8.200 mẫu (82%), lớp B: 500 mẫu (5%), tỷ lệ imbalance ratio 16:1".

**Đủ để mô tả phân bố corpus/câu hỏi; không phải bài toán class classification.**

Trả lời: “Trong532 chunk tiếng Việt của dataset chung, XLSX có485 chunk, chiếm khoảng91,17%; DOCX18, PDF9, CSV12 và PPTX8. Như vậy phân bố chunk lệch mạnh về workbook, dù mỗi định dạng có một file. Đây là phân bố loại tài liệu/chunk, không phải nhãn class classification. Riêng bộ hỏi benchmark retrieval có bốn nhóm, mỗi nhóm5ý.”

Nguồn: báo cáo Huy §2.1 và protocol. Đã có số liệu nhưng biểu đồ phân bố vẫn cần dựng nếu muốn đánh dấu mục biểu đồ xong.

### Có kiểm tra trùng lặp giữa các tập không? Ảnh gần giống nhau nằm ở cả Train và Test làm kết quả ảo.

**Có kiểm tra một phần; không có chứng cứ “hoàn toàn không leakage”.**

Trả lời: “Không huấn luyện supervised nên không có train/val/test kiểu training. Bộ 48 ca cũ dùng development; bộ mới được chốt trước inference và có overlap audit với câu cũ. Corpus vẫn đã biết, có chủ đề liên quan development. Sáu ý có chunk evidence bảng giống hệt VI/EN; các phiên bản cùng ý không được coi là độc lập. Vì vậy chưa kết luận generalization sang corpus mới.”

Nguồn: overlap-audit.json, báo cáo Huy §4–5. Không dùng hash hoặc similarity chữ làm bằng chứng độc lập ngữ nghĩa tuyệt đối.

### Nhãn do ai gán, kiểm tra chất lượng thế nào? Nếu một người gán thì nói rõ, nếu nhiều người thì phải có Cohen's/Fleiss' Kappa.

**Đủ chứng cứ để mô tả quy trình hiện có; chưa có independent annotation/Kappa.**

Trả lời: “Trợ lý hỗ trợ soạn và đối chiếu nhãn với nguồn; người dùng duyệt hướng sửa H10/H13/H19. Có 61 yêu cầu evidence, 148 source spans; kiểm tra mapping và full/empty oracle trên 40 cặp intent/ngôn ngữ, cùng 10 kiểm tra hai đoạn cho nhóm multi-chunk. Chưa có hai annotator độc lập hoặc Kappa, nên không gọi đây là nhãn được chứng nhận độc lập.”

Nguồn: validation.json và review-status.json. Structural validation không thay thế đánh giá độc lập về tính đúng/đủ của nhãn.

### Vì sao chọn kỹ thuật xử lý mất cân bằng này? Cần lý do gắn với đặc thù dữ liệu, không phải "vì phổ biến".

**Trả lời được lý do không oversample; không đánh dấu đã áp dụng kỹ thuật/đo before-after.**

Trả lời: “Đây là retrieval trên corpus tài liệu, không phải classifier cần cân bằng class. Nhân bản chunk làm đổi thống kê BM25 và thứ hạng, nên em giữ corpus nguyên trạng, phân bổ câu hỏi theo nhóm và báo kết quả riêng từng nhóm.”

Nguồn: báo cáo Huy §2.1 và bảng category trong metrics CSV. Đây là cách đánh giá theo nhóm, không phải bằng chứng đã xử lý phân bố corpus cho cân bằng.

### Vì sao chọn chunk size và overlap này? Có thử nghiệm so sánh không?

**Trả lời được implementation/lý do; chưa có thí nghiệm chứng minh tối ưu.**

Trả lời: “Parser ưu tiên câu và nhóm hàng bảng với mục tiêu văn bản 1.100 ký tự. Sentence grouping thông thường không overlap; nếu một câu quá dài thì fallback fixed có thể dùng overlap120ký tự dù metadata strategy vẫn ghi sentence/overlap0. Bước embedding dùng tokenizer đúng model, có overlap token mặc định32; nhánh body sau header dùng overlap thích ứng không quá32. Mục đích là giữ ngữ cảnh và tránh truncation. Chưa có ablation riêng chunk size/overlap nên chưa nói các giá trị này tối ưu.”

Nguồn: báo cáo Huy §2.2, parser docs và embedding chunker. Không đánh đồng giới hạn 512 token của encoder với kích thước văn bản thuần cho phép.

### Tổng số token là bao nhiêu? Chi phí hoặc thời gian embedding ước tính?

**Token: đủ. Thời gian: có phép đo lịch sử, không phải một phép đo mới của final run. Chi phí tiền: chưa tính.**

Trả lời: “Phần dataset chung5 tài liệu VI có224.845 token đầu vào E5 sau prefix/special tokens, dài nhất476/512, không overlength. Tổng này tính cả header/overlap lặp. Pilot E5 lịch sử ngày18/10 trên532chunk VI ghi14,15giây corpus encoding vớiRTX2060/FP32/batch2. Đây không phải phép đo ingestion live hiện tại và chưa tính tổng chi phí tiền.”

Nguồn: retrieval-report-stats.json, `languages.vi.prefixed_sequence_tokens_total`. Nếu hỏi thí nghiệm song ngữ: VI+EN tổng449.203 token; candidate E5 gốc ghi khoảng22,12giây embedding cả1.063 chunk trên RTX2060/FP32/batch2. Không gán22,12giây cho riêng532 chunk VI hoặc chia đôi thời gian để giả định phép đo mới. Final run dùng lại document vectors.

Nguồn timing VI lịch sử: [comparison ngày18/10](../../artifacts/evaluation/embedding-comparison-20261018/comparison.md). Không trộn hai lần encoding/corpus thành một phép đo mới.

### Schema metadata gồm những trường nào? Nếu câu hỏi nằm ngoài tài liệu thì hệ thống phản hồi ra sao (chống hallucination)?

**Schema: đủ. Khả năng từ chối/hallucination: cần generation owner.**

Trả lời phần Huy: “Metadata gồm danh tính tài liệu và quyền, vị trí trang/section/bảng khi có, mapping về parser qua source spans, cùng model/token metadata. Benchmark hiện chỉ đo retrieval cho các câu có evidence; chưa đo câu ngoài tài liệu hoặc tỷ lệ refusal/hallucination.”

**Câu đang điền trong Google Docs cần giảm mức khẳng định.** Gợi ý thay “sẽ từ chối trả lời” bằng: “Hệ thống có cơ chế hướng dẫn trả lời theo nguồn và kiểm tra citation nhằm giảm hallucination. Chất lượng từ chối khi ngoài tài liệu và faithfulness cần đối chiếu kết quả generation; benchmark retrieval chưa chứng minh các khả năng này.” Cần LLM owner xác nhận implementation hiện tại trước khi chốt.

## 3. Câu hỏi giai đoạn 2 — baseline

### Kết quả của các em thấp hơn paper bao nhiêu điểm phần trăm? Thấp hơn không phải là lỗi, nhưng không giải thích được mới là lỗi.

**Chưa có bằng chứng để điền một con số.** Có hai đối chứng chạy trên corpus thử nghiệm riêng mở rộng từ dataset nhóm (Dense E5 và Dense+BGE), nhưng chưa có bảng tái dựng hai paper trên dataset/metric tương thích. Không lấy điểm paper trên corpus khác trừ với86,25% full evidence rồi gọi gap. Ghi “Chưa hoàn tất Paper-vs-Group comparison”.

### Nguyên nhân chênh lệch là gì? Hãy phân loại: (a) domain gap, dataset khác paper; (b) hyperparameters khác; (c) tiền xử lý khác; (d) paper dùng pretrained/tập huấn luyện lớn hơn. Có bằng chứng hay chỉ suy đoán?

**Chưa đủ cho gap analysis định lượng.** Có thể liệt kê khác biệt corpus/metric/cấu hình sau khi chọn paper, nhưng chưa chứng minh nguyên nhân một chênh lệch chưa đo. Không điền “do domain gap” như kết luận đã thực nghiệm.

### Chạy mấy lần, seed nào? Nên chạy ít nhất 3 seed và báo cáo mean ± std. Một lần chạy duy nhất rất dễ bị phản biện.

**Đủ trả lời trung thực, chưa đạt khuyến nghị ba lần.**

Trả lời: “Một pass mỗi ca/nhánh, dùng seed 20261022 cho thứ tự nhánh và bootstrap. Model pretrained, không training. Chưa có ba lần chạy độc lập và mean±std giữa run. Bootstrap 10.000 lần theo 20 intent chỉ lượng hóa bất định theo câu hỏi, không thay thế đo lặp.”

Nguồn: protocol, run config, analysis.json. Mean/median/p95 latency qua các ca không phải mean±std giữa ba run.

### Baseline đã được tune công bằng chưa? Nếu baseline chưa tune mà proposed method đã tune thì so sánh thiếu công bằng.

**Có kiểm soát điều kiện; chưa chứng minh ngân sách tuning ngang nhau.**

Trả lời: “Các nhánh dùng cùng corpus, nhãn, E5 vectors, scope, final k và môi trường; câu hỏi/nhãn/bản dịch được chốt trước inference, không chỉnh theo điểm bộ này. Tuy vậy, pipeline có lịch sử phát triển trên corpus đã biết; chưa có nghiên cứu equal-budget hyperparameter tuning cho mọi baseline.”

Nguồn: protocol và báo cáo Huy §4–5. Không nói chưa train đồng nghĩa chưa chọn tham số hoặc không có development bias.

### Nếu kết quả thực nghiệm CAO hơn paper thì sao? Hãy kiểm tra ngay khả năng rò rỉ dữ liệu.

**Chưa có phép đối chiếu paper để khẳng định cao hơn.** Trả lời rằng chưa so trực tiếp; cung cấp overlap audit và các giới hạn corpus/nhãn đã biết khi hỏi về rò rỉ. Không khẳng định “không leakage” dựa riêng việc freeze.

## 4. Câu hỏi giai đoạn 3 — proposed method

### V1 có "tín hiệu cải thiện" không? Ở chỉ số nào, hơn bao nhiêu? Nếu V1 không tốt hơn baseline, hãy trung thực nói rõ và phân tích. Đó vẫn là kết quả khoa học hợp lệ, miễn là có giải thích và hướng khắc phục.

**Đủ cho benchmark mở rộng riêng.** “Em đánh giá retrieval bằng cách bổ sung5 bản EN tương ứng với5 tài liệu VI của dataset chung. Trên corpus thử nghiệm10 phiên bản tài liệu/1.063 chunk, translated hybrid+BGE đạt69/80ca đủ evidence@10, so với dense52/80: thêm17ca, +21,25 điểm phần trăm. Recall@10 tăng khoảng0,6563→0,8823; MRR@10 khoảng0,5586→0,9000. So dense+BGE tăng ròng7ca, +8,75pp. Đây là retrieval evidence, không phải độ chính xác câu trả lời LLM, cũng không phải kết quả chỉ trên5 tài liệu VI.”

Nguồn: metrics.csv, `group=all`. Nên dùng tên cấu hình cụ thể thay vì gọi các phiên bản V1/V2 tùy ý.

### Cải thiện này có ý nghĩa thống kê không, hay chỉ nằm trong dao động giữa các seed? Mức tăng 0,3% với std là 0,5% thì chưa kết luận được gì.

**Có phân tích bất định theo intent, chưa có đo dao động giữa nhiều run.** “Bootstrap theo 20 intent: gain vs dense +21,25pp, 95% CI [10;35]; vs dense+BGE +8,75pp, CI [0;20]. Khoảng sau chạm 0 nên chưa khẳng định vượt dense+BGE chắc chắn. Đây là kết quả có điều kiện trên bộ nhỏ, không chứng minh generalization.”

Nguồn: analysis.json, `paired_intent_bootstrap`. Không gọi bootstrap là ba seed hoặc independent model runs.

### V2 sửa lỗi nào của V1? Mỗi phiên bản phải trả lời được: "Lỗi X quan sát ở V1 → giả thuyết nguyên nhân → thay đổi Y ở V2 → kết quả". Không chấp nhận kiểu "thử thêm cho thử".

**Có hướng đề xuất; chưa có implementation/kết quả V2 sau benchmark này.** “Cả 11 ca thiếu evidence từ pool30; bảng cần đúng Product ID hoặc ghép nhiều ID. Đề xuất lookup theo cột ID, tách query nhiều ID rồi ghép ứng viên, giữ ID/thuật ngữ khi dịch. Chưa triển khai/đo phiên bản này, nên chỉ ghi next work.”

Nguồn: candidate-diagnostics.json và báo cáo cuối. Không gọi thêm BGE là V2 của các lỗi chỉ mới phát hiện ở final run.

### Ablation study đã tách riêng đóng góp của từng thành phần chưa? Bảng cần có từng module thêm vào một, để biết cái nào thực sự hiệu quả.

**Một phần.** “Thêm BGE vào dense: 52→62/80; thêm BGE vào translated hybrid: 63→69/80, không mất full-evidence case nào so raw hybrid. Có kiểm soát corpus/E5/scope/final k. Chưa có original-query-only hybrid nên chưa tách dịch khỏi BM25/RRF; chưa ablate chunk size hoặc embedding model trong bộ 80 ca.”

Nguồn: metrics.csv, analysis.json, protocol. Checklist nên ghi “đã có reranker ablation; chưa đầy đủ từng module”.

### Failure case các em chọn là ngẫu nhiên hay cherry-pick? Nên phân nhóm lỗi (ví dụ: 40% do nhiễu nền, 30% do lớp thiểu số, 20% nhãn sai...) thay vì chỉ show vài ví dụ.

**Đủ.** “Phân tích cả 11 ca chưa đủ evidence: H04 VI→EN 1 ca; H08 target VI 2 ca; H11 4 ca; H14 4 ca. Tất cả thiếu trong top30; SQL diagnostic khớp 11/11 top30 của run gốc. Ví dụ H04: gold dense19→fusion33; một số dòng ID khác ngoài200.”

Nguồn: analysis.json, candidate-diagnostics.json. Quan sát thiếu pool là có bằng chứng; quy hết nguyên nhân cho dịch/reranker thì chưa có ablation chứng minh.

### Kết luận khả thi của các em dựa trên số liệu nào? Phải có latency, model size đo thực tế, trên phần cứng cụ thể.

**Đủ cho warm retrieval, chưa đủ toàn hệ thống/production capacity.** “RTX2060, FP32, BGE batch4: final mean/median/p95 3.609/3.578/4.605 ms. Cached weights E5 khoảng 1.061 MiB, BGE khoảng 2.166 MiB. Chưa gồm startup/API dịch/generation; chưa concurrency/cold-start. Peak PyTorch 2,212 GiB ghi với nạp model tuần tự, không phải giữ đồng thời hai model production.”

Nguồn: metrics.csv, run config, retrieval-report-stats.json. Không cộng latency của thành viên khác máy thành số end-to-end đã đo.

### Hệ thống đã tách thành các service riêng chưa: Ingestion, Retrieval, LLM Generation, API Gateway/Frontend?

**Chưa có bằng chứng hoàn tất bốn service độc lập.** Có module code theo chức năng, nhưng module không đồng nghĩa service triển khai riêng. Đối chiếu [Compose](../../docker-compose.yml) và [Dockerfile](../../docker/Dockerfile); deployment owner xác nhận sơ đồ thực chạy. Không đánh dấu microservices xong chỉ vì có Docker.

### docker-compose up có chạy được từ máy sạch không? Có Dockerfile cho từng service không?

**Có cấu hình; chưa xác minh clean-machine run trong lần kiểm tra này.** Dẫn Compose/Dockerfile và yêu cầu log/record thực từ người triển khai. Workflow có bước build/smoke, nhưng cần lịch sử run thành công để chứng minh nó đã chạy.

### Pipeline CI/CD (GitHub Actions/GitLab CI) có chạy thật không: lint, unit test, build image, deploy? Cho xem lịch sử run xanh.

**Có workflow; chưa kiểm tra lịch sử run xanh hiện tại.** [.github/workflows/ci.yml](../../.github/workflows/ci.yml) có compile check, unittest, JS syntax check, build container và proxy smoke. Không mô tả compile check là full lint, hoặc suy build/smoke thành đã deploy production. Cần run URL, commit SHA, job status và phạm vi bước thực chạy do deployment owner xác nhận.

### Đã đánh giá chất lượng retrieval và generation chưa (Recall@k, MRR, faithfulness...)?

**Retrieval: đủ. Generation: cần nguồn riêng.** “Retrieval có P/R@10, MRR, nDCG, full evidence và component coverage trên80ca thuộc corpus thử nghiệm VI+EN riêng. Generation do thành viên phụ trách cung cấp correctness/faithfulness/citation metrics trên bộ hỏi riêng. Hai phần cùng dựa trên5 tài liệu VI của dataset chung; retrieval có thêm5 bản EN phục vụ thí nghiệm. Không coi hai phần đã có cùng corpus đánh giá/cùng câu hỏi, và chưa có end-to-end evaluation trên tập chung.”

Nguồn retrieval: metrics.csv. Không dùng 86,25% làm generation accuracy hoặc faithfulness.

## 5. Bảng tự đánh giá cuối Google Docs: trạng thái nên điền

Nếu cột chỉ có Chưa làm / Đang làm / Xong, dùng “Đang làm — một phần” cho hạng mục tổng còn thiếu. Chỉ tick Xong kèm ghi rõ phạm vi retrieval, không thay mặt cả nhóm.

| Hạng mục | Trạng thái đề nghị | Nội dung ghi cột bằng chứng / còn thiếu |
|---|---|---|
| Bảng thống kê nguồn dữ liệu | Đang làm — một phần | Dataset chung:5 tài liệu VI/532 chunk; DOCX18, PDF9, CSV12, XLSX485, PPTX8. Data owner bổ sung nguồn raw, dung lượng, số trang. Ghi riêng extension EN của benchmark, không nhập10 phiên bản vào số tài liệu chung trên Supabase. |
| Quy trình làm sạch và gán nhãn | Đang làm — một phần | Có parser pipeline và evidence label/validation; cần data owner xác nhận flow cleaning/dedup/noise thực tế. Chưa independent annotation/Kappa. |
| Phân tích mất cân bằng định lượng | Có số liệu dataset chung; đang hoàn thiện trình bày | Workbook485/532 ≈91,17%;4 định dạng khác47/532 ≈8,83%. Riêng bộ hỏi retrieval có4nhóm ×5ý. Nếu chưa biểu đồ thì chưa tick xong toàn mục trình bày. |
| Xử lý mất cân bằng, biểu đồ trước/sau | Không áp dụng oversampling trong retrieval | Giữ corpus, báo theo nhóm; ghi lý do. Không tick Xong cho kỹ thuật/biểu đồ before-after chưa làm. Nếu bắt buộc tick một ô, ghi rõ “N/A” tại cột bằng chứng và thống nhất với GV. |
| Baseline 1 chạy xong | Xong — đối chứng retrieval | Dense E5: 52/80, metrics.csv. Không đồng nghĩa đã tái dựng paper1. |
| Baseline 2 chạy xong | Xong — đối chứng retrieval | Dense+BGE: 62/80, metrics.csv. Không đồng nghĩa đã tái dựng paper2. |
| Bảng Paper vs Thực nghiệm | Chưa có bằng chứng hoàn tất | Cần chọn paper và giải thích khác biệt dataset/metric; không lấy bảng bốn pipeline thay thế mục này. |
| Gap Analysis | Chưa có bằng chứng hoàn tất | Cần hoàn thiện cùng Paper-vs-Group; không khẳng định domain gap là nguyên nhân đã được chứng minh. |
| Proposed V1 chạy xong | Xong — retrieval | Translated hybrid+BGE: 69/80; full run report, config và verification. |
| Failure case analysis | Xong — retrieval | Cả11 losses, candidate diagnostics; phần OCR/LLM do từng owner bổ sung. |
| V2 và các bản tiếp theo | Có đề xuất; chưa implementation/result | Identifier-aware lookup/multi-ID merge, không điền điểm V2. |
| Bảng ablation tổng hợp | Đang làm — một phần | Có đối chiếu reranker; chưa tách translation/BM25/RRF. |
| Latency/model size | Xong phạm vi warm retrieval; toàn nhóm cần bổ sung | Metrics CSV + stats; chưa startup/concurrency/end-to-end. |
| Slide18–25 trang | Đang làm | Bản Canva revision163 đọc trong đợt chuẩn bị26/10 có28trang gồm backup. Tách phần chính/backup, kiểm số trang và các placeholder trước khi tick Xong. |
| Docker, microservices, CI/CD | Cần deployment owner xác nhận | Có config/workflow, chưa đủ log/run evidence và chưa chứng minh bốn service độc lập. |
| Paper Springer6–8trang | Có điều kiện / chưa xác nhận nhóm có làm | Checklist chỉ áp dụng nếu nhóm viết paper; không tự đánh dấu đã hoàn tất. |

## 6. Câu trả lời ngắn khi GV hỏi đang ở đâu, khó nhất là gì?

“Dataset chung có5 tài liệu VI/532chunk. Phần retrieval dùng pretrained E5 + translated lexical retrieval + RRF + BGE; em bổ sung5 bản EN để đánh giá bốn hướng ngôn ngữ trên80ca/20ý. Trên corpus thử nghiệm riêng đó, kết quả đủ evidence tăng52→69/80, đã phân tích toàn bộ11ca còn thiếu. Khó nhất là truy hồi đúng nhiều dòng Product ID: evidence bị loại trước reranker. Nhóm đang hoàn thiện báo cáo từng thành phần; đánh giá end-to-end trên bộ hỏi chung, Paper-vs-Group và bằng chứng triển khai còn cần bổ sung.”

Không dùng trạng thái phần Huy để kết luận các thành viên khác chưa có kết quả; họ cần cung cấp bằng chứng riêng. Không có thí nghiệm mới hoặc chỉnh Google Docs trong lần đối chiếu này.
