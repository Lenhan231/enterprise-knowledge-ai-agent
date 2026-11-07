# Benchmark Review 2 — bộ mới reviewed-r1

**Đã hoàn tất 80/80 ca; kiểm tra lại logits, thứ hạng và metric đạt.** Kết quả thực, không phải diagnostic nhãn.

20 ý hỏi × câu VI/EN × corpus VI/EN; chỉ có 20 cụm ý hỏi. H10 mới dùng hàng không-chênh-lệch của SOP; H13/H19 đã sửa trước inference. Bản draft lưu trong history/. Không sửa nhãn hoặc bản dịch theo kết quả.

## Kết quả tổng

| Phương pháp | P@10 | R@10 | MRR@10 | nDCG@10 | Đủ bằng chứng | Thành phần đạt | Latency TB / median / p95 (ms) |
|---|---:|---:|---:|---:|---:|---:|---:|
| Dense E5 | 0.0963 | 0.6562 | 0.5586 | 0.5594 | 52/80 (65.0%) | 156/244 | 546 / 488 / 941 |
| Dense + BGE | 0.1188 | 0.7875 | 0.8213 | 0.7731 | 62/80 (77.5%) | 189/244 | 1691 / 1549 / 2416 |
| Translated hybrid | 0.1188 | 0.7917 | 0.6590 | 0.6694 | 63/80 (78.8%) | 187/244 | 2437 / 2370 / 3165 |
| Translated hybrid + BGE | 0.1338 | 0.8823 | 0.9000 | 0.8635 | 69/80 (86.2%) | 208/244 | 3609 / 3578 / 4605 |

Trần P@10 trung bình theo nhãn: **15.5%**. Mỗi ca chỉ có vài gold chunk trong top10. Recall đếm cả gold chunk thay thế; Full evidence đo đã đủ mọi thành phần trả lời. Hai metric không đồng nghĩa.

## Theo hướng ngôn ngữ

| Nhóm | Dense | Dense + BGE | Translated hybrid | Translated hybrid + BGE |
|---|---:|---:|---:|---:|
| vi->vi | 16/20 | 16/20 | 16/20 | 17/20 |
| vi->en | 9/20 | 15/20 | 15/20 | 17/20 |
| en->vi | 12/20 | 15/20 | 16/20 | 17/20 |
| en->en | 15/20 | 16/20 | 16/20 | 18/20 |

Các ô là số ca đủ toàn bộ bằng chứng trong top10.

## Theo nhóm câu hỏi

| Nhóm | Dense | Dense + BGE | Translated hybrid | Translated hybrid + BGE |
|---|---:|---:|---:|---:|
| narrative | 17/20 | 20/20 | 19/20 | 19/20 |
| table_numeric | 14/20 | 16/20 | 16/20 | 18/20 |
| multi_chunk | 6/20 | 9/20 | 9/20 | 12/20 |
| paraphrase_terminology | 15/20 | 17/20 | 19/20 | 20/20 |

Các ô là số ca đủ toàn bộ bằng chứng trong top10.

## Điểm chính để trình bày

- Pipeline cuối đủ bằng chứng69/80, cao hơn dense52/80: **+17 ca, +21.25 điểm phần trăm**. Recall@10=0.8823, MRR@10=0.9000, nDCG@10=0.8635.
- So với dense+BGE: thắng8 ca, thua1 ca (H04 VI→EN), tăng ròng7 ca. CI95% của mức tăng đủ bằng chứng [+0.00,+20.00] điểm phần trăm vẫn chạm0; chưa nên khẳng định vượt trội chắc chắn ở mọi tập câu hỏi.
- Reranker cứu6 ca từ translated hybrid thô, không làm mất ca đủ bằng chứng nào so với nhánh thô. MRR tăng0.6590→0.9000; thứ hạng tốt hơn rõ hơn chỉ nhìn Recall.
- Câu ghép nhiều chunk vẫn yếu nhất:12/20 ca đủ bằng chứng. Nhóm văn bản19/20, paraphrase20/20, nhóm bảng/quy tắc18/20.
- Trung bình warm-stage latency tăng0.546s→3.609s so với dense. API dịch đo riêng0.560s trung bình; chưa phải end-to-end production latency.

## Ca nhánh cuối chưa đủ bằng chứng

- **H04-vi-to-en**: Mục Hồ sơ bắt buộc và lưu trữ của Manual yêu cầu giữ những nhóm hồ sơ nào?
  Thiếu: H04.purchase, H04.receiving, H04.count, H04.returns, H04.kpi. Tầng: candidate_pool_missing_evidence. Vị trí gold trong top30: {"LOCAL-EN-V1-01_Inventory_Management_Policy_Manual_EN.docx::chunk::16": null}.
- **H08-vi-to-vi**: Trong Inventory Control, Product ID 19 có Units Sold (Latest) và Avg Monthly Demand (3 snapshots) bao nhiêu?
  Thiếu: H08.sold, H08.average. Tầng: candidate_pool_missing_evidence. Vị trí gold trong top30: {"UPLOAD-53956dfa17064fd9b6f42e9e01570a20::chunk::15": null}.
- **H08-en-to-vi**: In Inventory Control, what Units Sold (Latest) and Avg Monthly Demand (3 snapshots) are recorded for Product ID 19?
  Thiếu: H08.sold, H08.average. Tầng: candidate_pool_missing_evidence. Vị trí gold trong top30: {"UPLOAD-53956dfa17064fd9b6f42e9e01570a20::chunk::15": null}.
- **H11-vi-to-vi**: So sánh hai dòng Inventory Control của Product ID 1 và Product ID 3: mỗi sản phẩm có size, màu và On-hand Units nào?
  Thiếu: H11.p1_size, H11.p1_color, H11.p1_on-hand_units, H11.p3_size, H11.p3_color, H11.p3_on-hand_units. Tầng: candidate_pool_missing_evidence. Vị trí gold trong top30: {"UPLOAD-53956dfa17064fd9b6f42e9e01570a20::chunk::10": null, "UPLOAD-53956dfa17064fd9b6f42e9e01570a20::chunk::9": null}.
- **H11-vi-to-en**: So sánh hai dòng Inventory Control của Product ID 1 và Product ID 3: mỗi sản phẩm có size, màu và On-hand Units nào?
  Thiếu: H11.p3_size, H11.p3_color, H11.p3_on-hand_units. Tầng: candidate_pool_missing_evidence. Vị trí gold trong top30: {"LOCAL-EN-V1-04_Inventory_Control_and_Reorder_Planner_EN.xlsx::chunk::10": null, "LOCAL-EN-V1-04_Inventory_Control_and_Reorder_Planner_EN.xlsx::chunk::9": 1}.
- **H11-en-to-vi**: Compare the Inventory Control rows for Product ID 1 and Product ID 3: what size, color, and On-hand Units does each product have?
  Thiếu: H11.p3_size, H11.p3_color, H11.p3_on-hand_units. Tầng: candidate_pool_missing_evidence. Vị trí gold trong top30: {"UPLOAD-53956dfa17064fd9b6f42e9e01570a20::chunk::10": null, "UPLOAD-53956dfa17064fd9b6f42e9e01570a20::chunk::9": 1}.
- **H11-en-to-en**: Compare the Inventory Control rows for Product ID 1 and Product ID 3: what size, color, and On-hand Units does each product have?
  Thiếu: H11.p3_size, H11.p3_color, H11.p3_on-hand_units. Tầng: candidate_pool_missing_evidence. Vị trí gold trong top30: {"LOCAL-EN-V1-04_Inventory_Control_and_Reorder_Planner_EN.xlsx::chunk::10": null, "LOCAL-EN-V1-04_Inventory_Control_and_Reorder_Planner_EN.xlsx::chunk::9": 1}.
- **H14-vi-to-vi**: Đối chiếu Product ID 8 và 9 trong Inventory Control: On-hand Units và Units Sold (Latest) của từng sản phẩm là bao nhiêu?
  Thiếu: H14.p8_onhand, H14.p8_sold, H14.p9_onhand, H14.p9_sold. Tầng: candidate_pool_missing_evidence. Vị trí gold trong top30: {"UPLOAD-53956dfa17064fd9b6f42e9e01570a20::chunk::11": null, "UPLOAD-53956dfa17064fd9b6f42e9e01570a20::chunk::12": null}.
- **H14-vi-to-en**: Đối chiếu Product ID 8 và 9 trong Inventory Control: On-hand Units và Units Sold (Latest) của từng sản phẩm là bao nhiêu?
  Thiếu: H14.p8_onhand, H14.p8_sold, H14.p9_onhand, H14.p9_sold. Tầng: candidate_pool_missing_evidence. Vị trí gold trong top30: {"LOCAL-EN-V1-04_Inventory_Control_and_Reorder_Planner_EN.xlsx::chunk::11": null, "LOCAL-EN-V1-04_Inventory_Control_and_Reorder_Planner_EN.xlsx::chunk::12": null}.
- **H14-en-to-vi**: Compare Product IDs 8 and 9 in Inventory Control: what are the On-hand Units and Units Sold (Latest) for each product?
  Thiếu: H14.p9_onhand, H14.p9_sold. Tầng: candidate_pool_missing_evidence. Vị trí gold trong top30: {"UPLOAD-53956dfa17064fd9b6f42e9e01570a20::chunk::11": 1, "UPLOAD-53956dfa17064fd9b6f42e9e01570a20::chunk::12": null}.
- **H14-en-to-en**: Compare Product IDs 8 and 9 in Inventory Control: what are the On-hand Units and Units Sold (Latest) for each product?
  Thiếu: H14.p9_onhand, H14.p9_sold. Tầng: candidate_pool_missing_evidence. Vị trí gold trong top30: {"LOCAL-EN-V1-04_Inventory_Control_and_Reorder_Planner_EN.xlsx::chunk::11": 4, "LOCAL-EN-V1-04_Inventory_Control_and_Reorder_Planner_EN.xlsx::chunk::12": null}.

Reranker cứu 6 ca so với translated hybrid thô và làm mất đủ bằng chứng ở 0 ca. ID cụ thể nằm trong analysis.json.

## Chênh lệch và độ chắc chắn

- Nhánh cuối so với Dense E5: +21.25 điểm phần trăm đủ bằng chứng; bootstrap95% CI [+10.00, +35.00] điểm phần trăm.
- Nhánh cuối so với Dense + BGE: +8.75 điểm phần trăm đủ bằng chứng; bootstrap95% CI [+0.00, +20.00] điểm phần trăm.
- Nhánh cuối so với Translated hybrid: +7.50 điểm phần trăm đủ bằng chứng; bootstrap95% CI [+2.50, +13.75] điểm phần trăm.

Bootstrap10.000 lần theo20 ý hỏi, seed20261022; các bản ngôn ngữ cùng một ý thuộc cùng cụm. Khoảng tin cậy không chứng minh tổng quát hóa sang miền mới.

## Điều kiện đo và hạn chế

- E5 multilingual-e5-base768 chiều + BGE reranker-v2-m3, revision cố định, FP32/CUDA, batch4,30 candidate,top10. Document vectors dùng lại. Xem config.json/protocol.json.
- SQL production chạy trên TEMP tables chứa corpus cố định1063 chunk/10 bản tài liệu; mỗi ca scope5 tài liệu ngôn ngữ đích, admin. Không đổi dữ liệu/vector public Supabase.
- Không cắt token: query E5 tối đa50 token; cận trên bảo thủ cho cặp BGE521/1024. Model đọc cache, không tải trọng số mới.
- Một lần chạy/ca/nhánh, thứ tự nhánh ngẫu nhiên cố định seed. Latency warm gồm encode+retrieve+rerank, không gồm tải model,API dịch,generation. Encode đo một lần cho mỗi40 văn bản rồi dùng chung hai corpus đích.
- Dịch40/40 câu không lỗi: API trung bình 0.560s, median 0.467s, p95 1.339s, đo riêng trong bước chuẩn bị. Không coi đây là end-to-end production latency. Bản dịch lưu cố định, không dùng bản EN đã soạn làm bản dịch oracle câu VI.
- 8 ý số liệu workbook giữ tên cột tiếng Anh và cùng dòng đáp án;6 ý có cả chunk giống hệt VI/EN. Cần xem riêng nhóm văn bản và từng hướng ngôn ngữ khi kết luận lợi ích dịch.
- Nhóm table_numeric có H10 là bảng quy tắc SOP; không phải cả nhóm đọc số. Một số câu số liệu ghép hai dòng nằm trong multi_chunk.
- Corpus mô phỏng đã biết, nhãn do trợ lý soạn/đối chiếu; người dùng duyệt hướng sửa. Chưa có kiểm định độc lập về người gán nhãn. Các chủ đề liên quan bộ cũ có trong overlap-audit.json.
- Chưa đo generation/faithfulness, từ chối khi thiếu đáp án, RBAC hoặc OCR. Phần generation/LLM cần An đánh giá riêng theo proposal/Review2.
- Bộ mới chưa có nhánh hybrid chỉ dùng query gốc: chênh lệch so với dense + BGE gộp tác động BM25/fusion và dịch, không tách riêng lợi ích dịch. Embedding giữ E5, không phải phép chọn lại model embedding.

## Tìm và chạy lại

Từ gốc project, kiểm artifact đã lưu bằng lệnh (không inference mới):

    .venv/bin/python artifacts/evaluation/heldout-review2-v1/run.py verify-run artifacts/evaluation/heldout-review2-v1/runs/review2-reviewed-r1-sql-20261022

Chạy inference lại, giữ nguyên bản dịch và toàn bộ đầu vào; dùng tên mới để không ghi đè:

    .venv/bin/python artifacts/evaluation/heldout-review2-v1/run.py run --name review2-reviewed-r1-sql-repeat-02

Giữ cả folder, đặc biệt inputs/,code/,prepared/,runs/ khi chuyển máy. Chi tiết lần chạy: metrics.csv,results.json,config.json,verification.json,analysis.json,query_vectors.npy và hai ma trận reranker logits.

## Giải thích các ca mất điểm bằng SQL thực

Đã kiểm lại11 ca bằng production SQL trên bảng tạm, dùng query vectors và bản dịch đã lưu. Toàn bộ11 danh sách top30 khớp lần chạy gốc. Chi tiết nằm trong candidate-diagnostics.json; không inference/gọi API mới, không sửa nhãn.

- **H04 VI→EN (1 ca):** dense đã đưa chunk đúng lên hạng19; dense+BGE lấy đủ câu trả lời. Bản dịch dùng “mandatory file categories and storage requirements” thay vì “required records and retention”. Nhánh lexical không trả chunk đó trong300 ứng viên, sau RRF nó xuống hạng33 và bị cắt trước reranker. Đây là một hồi quy thực của pipeline, có dấu hiệu dịch chưa sát cùng cơ chế fusion/cắt pool; không quy tất cả cho model rerank.
- **H08 trên corpusVI (2 ca):** Product ID19 đúng ở lexical hạng46/68, sau fusion hạng84/72, nên không vào top30.
- **H11 (4 ca):** thiếu Product ID3, hoặc thiếu cả1 và3. Chunk ID3 ở fusion hạng211–354; tìm theo bag-of-words/embedding chưa bảo đảm khóa đúng dòng có Product ID yêu cầu.
- **H14 (4 ca):** thiếu một hoặc cả hai dòng ID8/9; ví dụ ID9 ở fusion42/49 trong hai ca queryEN, và90/200 trong hai ca queryVI.

Cả11 ca đều thiếu đủ bằng chứng ngay trong pool30, không có ca pool đủ nhưng reranker làm mất trong top10. Vì vậy, đổi reranker đơn thuần chưa xử lý được các ca này. Tăng pool30→50 có thể đưa thêm một số dòng vào, nhưng không giải quyết các dòng xếp ngoài200. Hướng sau Review2: ưu tiên nhận dạng và tra đúng cột Product ID, tách truy vấn nhiều ID rồi ghép candidate, giữ nguyên ID/tên trường qua dịch; rà lại thuật ngữ hồ sơ/records. Chưa triển khai hoặc chỉnh benchmark theo các lỗi này.

## Lưu ý khi chạy ở Colab/offline

Kết quả chính ở đây dùng **backend sql**. Adapter offline chỉ là tùy chọn và không nên xem là thay thế tương đương để tái lập điểm: diagnostic11 ca cho thấy10 ca có top30 khác SQL. Adapter offline phá hòa BM25 theo chuỗi chunk ID, SQL theo numeric row ID; các hàng bảng gần giống nhau có thể đổi thứ tự khi bằng điểm. File offline-adapter-diagnostics.json ghi phép kiểm này, không phải một benchmark80 ca thứ hai. Dùng backend sql để tái lập kết quả báo cáo; giữ cùng corpus/order/bản dịch. Không trộn điểm/latency offline với SQL.
