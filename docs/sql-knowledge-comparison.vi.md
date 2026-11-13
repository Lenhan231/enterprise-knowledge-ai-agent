# Báo cáo tóm tắt: SQL Agent và Knowledge Agent


## 1. Kết quả chính

SQL Agent cải tiến cho thấy khả năng trả về kết quả đúng tốt hơn rõ rệt so với baseline ngày 02/11: Execution Accuracy tăng từ **21,4% lên 89,3%**, tương đương **67,9 điểm phần trăm**. Số yêu cầu thực thi được SQL tăng từ **11/30 lên 27/30**. Tuy nhiên, SQL Semantic Equivalence chỉ đạt **32,1%**; kết quả khớp dữ liệu tham chiếu chưa chứng minh truy vấn luôn đúng trên mọi dữ liệu có thể có.

Knowledge Agent phục vụ truy xuất và giải thích tài liệu, bổ sung ngữ cảnh chính sách cho dữ liệu định lượng của SQL Agent. Đợt đánh giá v3 ngày 10/11 đã chạy đủ **30/30 câu**, đạt Faithfulness **95,00%**, Answer Relevancy **75,24%** và Context Precision **88,25%**. Đây là baseline tích hợp mới; bộ câu hỏi và thước đo khác SQL nên không dùng để xếp hạng trực tiếp hai agent.

## 2. Phạm vi và cách so sánh

Trong báo cáo này, **baseline** là kết quả SQL ngày 02/11/2026; **bản cải tiến** là đợt chạy đầy đủ ngày 04/11 và bản cập nhật từng phần công bố ngày 06/11. Đây là các mốc phát triển tích lũy, không phải phép thử chỉ thay đổi một thành phần.

Bộ SQL có 30 câu hỏi cố định: 28 câu có tham chiếu SQL hợp lệ và hai câu thiếu dữ liệu hỗ trợ. Agent dùng `qwen/qwen3.8-27b`, temperature 0; bộ chấm sử dụng Ragas và `CodexCLIJudge(gpt-5.6-luna, medium)`. Truy vấn và kết quả tham chiếu được lưu riêng với đầu ra agent. Các tham chiếu do người xây dựng bộ đánh giá rà soát, chưa được chứng nhận độc lập.

Kết quả ngày 06/11 chỉ chạy lại **S13, S15, S17**; 27 câu còn lại giữ kết quả ở phiên bản trước. Do đó, cột này là **tổng hợp từ hai phiên bản**, không phải một lần chạy mới toàn bộ hệ thống hiện tại. [Nguồn phương pháp](../artifacts/evaluation/agent-benchmarks-2026-11-02/README.md), [nguồn cập nhật](../artifacts/evaluation/sql-three-case-followup-2026-11-06/README.md).

## 3. So sánh vai trò và cơ chế

| Tiêu chí | SQL Agent baseline | SQL Agent cải tiến | Knowledge Agent |
|---|---|---|---|
| Mục tiêu | Trả lời câu hỏi định lượng từ cơ sở dữ liệu | Tăng khả năng trả lời đúng, kiểm soát ý nghĩa nghiệp vụ | Trả lời câu hỏi từ tài liệu và cung cấp bằng chứng |
| Nguồn chính | Dữ liệu có cấu trúc trong schema `commerce` | Cùng nguồn dữ liệu, với xử lý chỉ số và phạm vi truy vấn được hoàn thiện | Các đoạn tài liệu trong phạm vi quyền người dùng |
| Đặc điểm quan sát | Nhiều yêu cầu làm rõ hoặc bị chặn kiểm tra | Củng cố diễn giải chỉ số, biên dịch tồn kho và kiểm tra SQL | Truy xuất RAG, mặc định dùng `translated_hybrid_rerank`, trả nguồn trích dẫn |
| Đầu ra phù hợp | Bảng kết quả, số liệu | Bảng kết quả, số liệu, nguồn và giới hạn dữ liệu | Giải thích, chính sách, quy trình, nội dung tài liệu |
| Hạn chế chính | Khả năng hoàn thành thấp trên bộ tồn kho | Còn khác biệt về thời gian, mức chi tiết, thứ tự và cách diễn giải yêu cầu | Phụ thuộc chất lượng tài liệu, truy xuất và khả năng bám bằng chứng |


## 4. Kết quả SQL Agent

| Chỉ số | Baseline 02/11 | Chạy đầy đủ 04/11 | Cập nhật từng phần 06/11 |
|---|---:|---:|---:|
| Execution Accuracy — khớp kết quả tham chiếu | 21,4% (6/28) | 82,1% (23/28) | **89,3% (25/28)** |
| SQL Semantic Equivalence — tương đương ngữ nghĩa theo bộ chấm | 14,3% (4/28) | 32,1% (9/28) | **32,1% (9/28)** |
| Numerical Accuracy — độ chính xác giá trị số | 22,3% (27 câu có điểm) | 79,2% (24 câu có điểm) | **87,5% (24 câu có điểm)** |
| Yêu cầu thực thi SQL, kể cả kết quả rỗng | 11/30 | 25/30 | **27/30** |
| Lỗi bộ chấm / điểm đang chờ | 0 / 0 | 0 / 0 | 0 / 0 |

Nguồn: [baseline](../artifacts/evaluation/agent-benchmarks-2026-11-02/sql_analytics/RESULTS.md), [đợt 04/11](../artifacts/evaluation/sql-semantic-correctness-2026-11-04/RESULTS.md), [tổng hợp 06/11](../artifacts/evaluation/sql-three-case-followup-2026-11-06/merged/paired-summary.json).

Baseline có 14 yêu cầu làm rõ và năm lỗi kiểm tra chỉ số/SQL. Sau cải tiến, nhiều yêu cầu đã được xử lý thành công. Hai sửa đổi nổi bật trong bản cập nhật cuối là:

- **S13 — biến động tồn kho giữa hai ngày:** lấy các sản phẩm được quan sát ở cả hai ngày, tính tồn kho ngày sau trừ ngày trước; phân biệt thiếu quan sát với giá trị NULL.
- **S15 — các chỉ số tồn kho đã lưu:** diễn giải yêu cầu thành bộ mười chỉ số được duyệt, kèm định danh sản phẩm và ngày ghi nhận.

Cả S13 và S15 chuyển từ 0 sang 1 ở Execution Accuracy và Numerical Accuracy, nhưng điểm tương đương ngữ nghĩa vẫn là 0. Hồ sơ kiểm tra ghi nhận một số lập luận của bộ chấm không phù hợp với khóa chính/khóa ngoại đã xác minh; các điểm gốc vẫn được giữ nguyên. Những khác biệt về phạm vi thời gian và mức chi tiết ở các câu khác vẫn cần xử lý.

Numerical Accuracy là trung bình điểm theo câu và có thể nhận giá trị một phần. Mẫu số thay đổi từ 27 xuống 24 do quy tắc áp dụng, nên không thể diễn giải mức tăng từ 22,3% lên 87,5% như một phép so sánh hoàn toàn đồng nhất. Riêng bước 04/11 → 06/11 giữ cùng 24 câu áp dụng, tăng **8,3 điểm phần trăm**. Execution Accuracy và Semantic Equivalence giữ mẫu số 28.

Một phép so sánh cặp được lưu riêng giữa bản `153e5d5` và `f53c56f` ghi nhận Execution Accuracy **71,4% → 82,1%**, Semantic Equivalence **21,4% → 32,1%**, và Numerical Accuracy trên cùng 24 câu **75,0% → 79,2%**. Kết quả này củng cố bằng chứng cải thiện trong một giai đoạn cụ thể; không nên gộp các mốc baseline khác nhau thành cùng một thí nghiệm. [Nguồn so sánh cặp](../artifacts/evaluation/sql-semantic-correctness-2026-11-04/RESULTS.md).

## 5. Kết quả Knowledge Agent

Kết luận trước đây rằng “bộ 30 câu mới chưa chạy” dựa trên README cũ ngày 02/11 trong checkout local và đã bỏ sót kết quả được công bố trên GitHub main. Cần phân biệt ba hồ sơ:

- Bộ lịch sử tháng 10: 25 câu Knowledge; không phải kết quả mới dùng ở mục này.
- `knowledge-invoice-2026-11-10-v2`: dự kiến 30 câu Knowledge, chỉ thử K01 và timeout sau 60,014 giây khi khởi tạo mô hình; chưa gọi mô hình trả lời, không có điểm Ragas. Phần hóa đơn riêng đã hoàn thành 10 câu. [README v2](https://github.com/Lenhan231/enterprise-knowledge-ai-agent/blob/main/artifacts/evaluation/knowledge-invoice-2026-11-10-v2/README.md).
- `knowledge-invoice-2026-11-10-v3`: đã chạy đủ 30 câu Knowledge, lưu 30 generation và 90 bản ghi metric, không thiếu điểm hay lỗi bộ chấm. Đây là kết quả sử dụng trong báo cáo cập nhật. [Tổng hợp v3](https://github.com/Lenhan231/enterprise-knowledge-ai-agent/blob/main/artifacts/evaluation/knowledge-invoice-2026-11-10-v3/summary.json).

V3 đo revision `6bf2f73f2eb32940571dcfb424f20a6d336b56f2`, tích hợp main `cae083c`. Theo hồ sơ, mã production Knowledge/retrieval khớp main đã tích hợp; cấu hình gồm employee role, top-k 5, translated hybrid retrieval, E5 base và BGE reranker v2-m3 CPU int8, Qwen3.8-27B temperature 0. Multiquery và claim verification vẫn tắt theo mặc định. Như vậy đây là đánh giá pipeline đã tích hợp các thay đổi trên main, không phải pipeline cũ tháng 10; cũng không có nghĩa mọi tùy chọn RAG đều được bật. [Cấu hình và phiên bản](https://github.com/Lenhan231/enterprise-knowledge-ai-agent/blob/main/artifacts/evaluation/knowledge-invoice-2026-11-10-v3/README.md).

Bộ v3 gồm 25 câu có bằng chứng chính sách và năm yêu cầu tra cứu vận hành không được tài liệu hỗ trợ, dựa trên VSC-OPS-POL-001 v1.0. Không mặc nhiên coi đây là bộ có nội dung giống hệt 30 câu đã lưu ngày 02/11.

| Chỉ số | Kết quả | Phạm vi |
|---|---:|---|
| Faithfulness — bám sát bằng chứng | **95,00%** | 24 câu có trả lời; sáu câu từ chối là N/A |
| Answer Relevancy — mức liên quan đến câu hỏi | **75,24%** | Cả 30 câu, gồm các câu từ chối |
| Context Precision — độ chính xác ngữ cảnh truy xuất | **88,25%** | Cả 30 câu |
| Từ chối đúng yêu cầu không được hỗ trợ | **5/5** | Năm tra cứu vận hành |
| Từ chối dù câu hỏi được hỗ trợ | **1/25** | K17: truy xuất thiếu trang bằng chứng |
| Citation ID hợp lệ | **24/24** | Kiểm tra cấu trúc, không chứng minh nguồn hỗ trợ từng phát biểu |
| Độ trễ yêu cầu p50 / p95 | **13,487 / 19,257 giây** | Đã nạp mô hình; không bao gồm cold start |

Nguồn: [báo cáo so sánh v3](https://github.com/Lenhan231/enterprise-knowledge-ai-agent/blob/main/artifacts/evaluation/knowledge-invoice-2026-11-10-v3/COMPARISON.md). Có sáu câu từ chối: năm câu đúng phạm vi và một câu K17 bỏ sót bằng chứng. Đây là baseline tích hợp mới, chưa có phép đo trước/sau tương thích để quy mức cải thiện riêng cho thay đổi của Huy. Các phát biểu “chưa merge/push main” trong hồ sơ thí nghiệm mô tả thời điểm đo; [ghi chú công bố sau đó](https://github.com/Lenhan231/enterprise-knowledge-ai-agent/blob/main/artifacts/evaluation/KNOWLEDGE_INVOICE_PUBLICATION.md) xác nhận việc đưa kết quả lên main mà không thay đổi điểm hay đầu ra.

## 6. Nhận định và hướng tiếp theo

**SQL Agent cải tiến phù hợp cho tính toán và tổng hợp dữ liệu có cấu trúc; Knowledge Agent phù hợp cho giải thích và tra cứu tài liệu.** Ví dụ, câu hỏi “tỷ lệ hết hàng tại ngày ghi nhận X là bao nhiêu?” cần SQL; câu hỏi “chính sách quy định cách xử lý hết hàng thế nào?” cần Knowledge. Yêu cầu kết hợp cần đối chiếu cả số liệu và tài liệu, giữ rõ ngày dữ liệu, phạm vi áp dụng và nguồn của từng kết luận.

Ưu tiên tiếp theo là chạy lại toàn bộ 30 câu SQL trên cùng một phiên bản. SQL cần tiếp tục giải quyết khác biệt về thời gian, mức chi tiết, kết quả rỗng và tham chiếu; Knowledge cần cải thiện truy xuất cho K17 và có phép so sánh trước/sau trên cùng bộ câu hỏi nếu muốn đo tác động riêng của các thay đổi retrieval/RAG. Chưa có phép đo đồng nhất để kết luận agent nào nhanh hơn hoặc rẻ hơn.

Không nên đồng nhất “cải tiến” với mọi biến thể thử nghiệm. Biến thể single-pass từng giảm Execution Accuracy từ **85,7% xuống 53,6%** trên phép thử riêng và không được khuyến nghị áp dụng. Biến thể hybrid đạt **6/6** trên sáu yêu cầu trường dữ liệu tường minh, nhưng phạm vi mẫu quá hẹp để suy rộng. [Single-pass](../artifacts/evaluation/sql-single-pass-2026-11-04/RESULTS.md), [hybrid](../artifacts/evaluation/sql-hybrid-2026-11-04/RESULTS.md).

Giới hạn: báo cáo chưa chạy lại mô hình, kiểm tra chi phí hoặc xác nhận toàn bộ mã local hiện tại tương ứng với phiên bản đã đo. Kết quả SQL cập nhật là tổng hợp nhiều phiên bản; Knowledge v3 dùng bộ câu hỏi và thước đo khác SQL nên không dùng để xếp hạng trực tiếp. Kết quả Knowledge mới đã được đối chiếu từ hồ sơ trên GitHub main, không suy từ README cũ trong checkout local.
