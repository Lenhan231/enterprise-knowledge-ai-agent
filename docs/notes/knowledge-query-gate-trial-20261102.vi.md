# Thử bộ lọc trước planner — 02/11/2026

Trạng thái: thử nghiệm local, chưa commit/push/deploy. **Cập nhật sau thử nghiệm: đã gỡ bộ lọc khỏi runtime theo yêu cầu của Huy; tài liệu này chỉ giữ lịch sử phép thử.** Không sửa prompt planner để tách riêng tác dụng của gate. Những file đo latency đang sửa trước đó được giữ nguyên.

## Code và luồng

`needs_search_planner()` trong `src/core/rag/rag_service.py` dùng quy tắc cấu trúc VI/EN, không gọi model:
- Nhiều dấu hỏi hoặc dấu chấm phẩy.
- Danh sách có ít nhất hai mục đánh số.
- Từ nối rõ như đồng thời/ngoài ra/sau đó/also/then.
- Có ít nhất hai cụm hỏi, hoặc hai động từ yêu cầu thuộc nhóm tóm tắt/so sánh/liệt kê/giải thích.

Chữ “và/and” đơn lẻ không đủ. Nếu gate trả false, `_search_questions()` trả câu gốc trước khi gọi planner. Nếu true, planner hiện có vẫn chọn một hoặc hai truy vấn. Kiểm tra deadline trước gate; quyền, scope, giới hạn context và citation giữ nguyên. Công tắc multiquery hiện có vẫn chi phối toàn luồng. Gate không có công tắc riêng và chưa có trên VPS.

Gate chỉ nhìn cách viết, không biết tài liệu. Nó không phải bộ phân loại ngữ nghĩa được huấn luyện. Câu có hai ý nhưng viết như một tiêu đề có thể bị bỏ sót; câu đơn có thêm “Vì sao?” có thể bị chuyển thừa. Phạm vi VI/EN không bảo đảm xử lý ngôn ngữ khác.

## Kết quả local

45 test liên quan đạt: gate/planning/outcomes/authorization/deadline/orchestration/latency/report. Bộ test xác nhận hành vi code; không đồng nghĩa gate suy luận đúng mọi câu.

Sáu câu hồi quy, kiểm tra bước planner bằng LLM thật:

| Câu | Gate | Kế hoạch thực tế |
|---|---|---|
| V1 | Bỏ planner | 1 truy vấn gốc |
| V2 | Bỏ planner | 1 truy vấn gốc |
| V3 | Bỏ planner | 1 truy vấn gốc; trước đó VPS chạy 2 retrieval |
| V4 | Gọi planner | 2 truy vấn; vẫn tách thừa theo nhu cầu bằng chứng đã xem |
| V5 | Gọi planner | Planner giữ 1 truy vấn; gate chuyển thừa nhưng không tạo thêm retrieval |
| V6 | Gọi planner | 2 truy vấn; giữ hai nhu cầu bằng chứng |

Gate loại được 3/6 lời gọi planner. Đây không phải mức giảm 50% tổng latency. Planner thường khoảng 0,4 giây, trong khi một lượt BGE mất khoảng 13–17 giây trên VPS. Tiết kiệm đáng kể có khả năng nằm ở V3 do tránh retrieval thứ hai, chưa đo lại VPS.

Bộ 20 cách diễn đạt/chủ đề mới được viết và gán nhãn mong muốn trước lượt đánh giá đầu tiên: `data/evaluation/knowledge_query_gate_cases.json`.
- 11/20 bỏ qua planner, 9/20 chuyển sang planner.
- 3 ca chuyển thừa: H07, H08, H09.
- 2 ca bỏ sót: H17 và H18 (nhiều chủ đề nhưng không có dấu hỏi/cụm hỏi rõ).
- 15/20 khớp giả thuyết routing thủ công; không gọi đây là accuracy retrieval, không xác nhận các chủ đề có trong corpus, không có chấm đáp án end-to-end.
- Không sửa thêm regex theo các lỗi mới rồi báo lại như một bộ held-out độc lập.

## Hai ca bỏ sót đáng chú ý

“Mô tả quy trình nghỉ phép và xử lý sự cố bảo mật.”
“Mức lương tối thiểu và lịch sao lưu dữ liệu.”

Hai câu chứa các nhóm bằng chứng khác nhau, nhưng gate xếp đơn giản. Đây là lý do chưa đề xuất deploy rộng bản thử.

## Kết quả chi tiết

Local, không commit nội dung chạy model:
- `artifacts/local/knowledge-query-gate-20261102/evaluation.json`.
- `artifacts/local/knowledge-query-gate-20261102/live-plans.json`.

Không chạy E5, BM25, BGE hoặc generation trong lượt live planner này. Không cập nhật DB, không có số đo E2E VPS mới.

## Các phương án khác

1. Giữ planner hiện có và sửa tiêu chí theo nhóm bằng chứng, nhất là so sánh trong cùng bảng, kiểm tra hợp lệ + giải thích, trường thông tin + điều kiện của cùng biểu mẫu. Ít thay đổi kiến trúc nhất; vẫn trả phí planner mỗi câu và cần bộ đánh giá mới trước khi chốt.
2. Retrieve một lần trước, chỉ gọi planner để tìm bổ sung nếu bằng chứng thiếu. Dựa vào context thực tế hơn nhưng phát hiện thiếu không dễ; ca khó có thể phải chạy ba lượt retrieval, tăng latency và đụng deadline. Câu trả lời sai nhưng tự tin cũng không tự được sửa.
3. Bộ phân loại ngữ nghĩa nhỏ thay regex: cần dữ liệu nhiều cách diễn đạt và đánh giá riêng, thêm công vận hành. Chưa phù hợp nếu chỉ có sáu câu làm bằng chứng.

Nguồn tham khảo cho các kiểu biến đổi/tách query (không phải bằng chứng gate của mình tốt):
- https://learn.microsoft.com/en-us/azure/architecture/ai-ml/guide/rag/rag-information-retrieval
- https://developers.llamaindex.ai/python/examples/query_transformations/query_transform_cookbook/

Khuyến nghị: giữ bản thử để review, chưa deploy. Ưu tiên giảm tách thừa trong planner trước, vì bottleneck đo được là lượt BGE bổ sung, không phải 0,4 giây planner. Nếu thử tiếp gate, cần chấp nhận và đo rõ tổn thất do bỏ sót, không chỉ tính số lời gọi giảm.
