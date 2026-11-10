# Sửa tiêu chí planner thay bộ lọc — 02/11/2026

## Phạm vi

Theo yêu cầu của Huy, đã gỡ `needs_search_planner()` và các test riêng của bộ lọc. `rag_service.py` và `test_knowledge_search_plan.py` trở về phiên bản đã commit trước thử gate. Các file đo latency và note đang sửa trước đó được giữ nguyên.

Thay đổi runtime của task này chỉ nằm ở `src/core/prompts/knowledge_search.py`. Không đổi model, quyền, corpus, top-k, thuật toán gộp context hay công tắc `KNOWLEDGE_MULTIQUERY_ENABLED`. Khi công tắc bật, mọi câu vẫn qua planner hiện có; không dùng dấu hỏi/từ khóa để bỏ planner.

## Tiêu chí mới

Số câu, số dấu hỏi hoặc chữ “và/why/what else” không quyết định số truy vấn. Planner chọn theo nhóm bằng chứng cần tìm:

- Mặc định một truy vấn, giữ nguyên câu gốc.
- So sánh số tiền, ngưỡng hoặc các model trong cùng bảng/chủ đề: một truy vấn.
- Các trường, điều kiện hợp lệ, ngoại lệ và giải thích của cùng biểu mẫu/quy trình: một truy vấn.
- Áp dụng công thức vào số liệu và giải thích kết quả: một truy vấn.
- “Còn phải kiểm tra gì?” trong cùng biểu mẫu: chưa phải lý do tách.
- Hai chính sách/quy trình độc lập: hai truy vấn, kể cả khi không có dấu hỏi.
- Phê duyệt/báo giá mua hàng và điều kiện phát hành PO vẫn là hai nhu cầu bằng chứng; không gom mọi thứ thành một để giảm latency.

Ví dụ không được hard-code tên CTL, VietStyle, ID chunk hay số tiền cụ thể. Ví dụ chung được dùng để mô tả quan hệ bằng chứng, không để trả lời câu hỏi.

## Kiểm tra chức năng

43 test liên quan đạt: planning, Knowledge outcomes, quyền, deadline, bounded orchestration, latency tracking và script đo. `git diff --check` đạt.

Không thêm schema/API mới; mọi giới hạn và fallback cũ giữ nguyên. Chưa commit/push/deploy task sửa prompt này.

## Thiết kế so sánh LLM thật

- So sánh prompt đang commit với prompt mới, cùng model và temperature=0.
- Xen kẽ thứ tự cũ/mới theo từng case, nghỉ giữa lần gọi để giảm quota burst.
- Chạy sáu câu hồi quy, 20 câu đã dùng phân tích gate và 10 câu mới cố định trước lượt so sánh.
- Bộ 20 câu là development set, không gọi là held-out sau khi đã dùng phân tích.
- Bộ 10 câu ở `data/evaluation/knowledge_planner_transfer_cases.json` chưa dùng để sửa prompt trong phép thử này.
- Nhãn thủ công là giả thuyết cần một hay hai nhóm tìm kiếm, KHÔNG phải gold chunk/đáp án thực tế; không chứng minh các chủ đề đều có trong kho.
- Trường `expected_planner` trong fixture cũ được tái sử dụng với nghĩa “kỳ vọng hai truy vấn”, không phải có gọi planner hay không. Cả hai phiên bản đều gọi planner cho mọi case.
- Lỗi API/JSON được ghi là lỗi, không tính thành ca một truy vấn thành công.
- Mỗi prompt/case chạy một lần: chưa đo tính ổn định qua nhiều lần.

Kết quả chi tiết local: `artifacts/local/planner-criteria-20261102/comparison.json`. Đã hoàn tất 72 lần gọi API cho 36 câu × 2 prompt, không có lỗi API/JSON; model `qwen/qwen3.8-27b`, temperature=0, output budget=256.

| Bộ câu | Prompt cũ khớp nhãn | Prompt mới khớp nhãn | Chênh lệch |
|---|---|---|---|
| Sáu câu hồi quy | 4/6 | 6/6 | Cũ tách thừa V3/V4, mới giữ một truy vấn |
| 20 câu đã phân tích | 19/20 | 20/20 | Cũ tách thừa H08, mới giữ một truy vấn |
| 10 câu mới cố định trước thử | 8/10 | 10/10 | Cũ tách thừa T02/T05, mới giữ một truy vấn |

Trong lượt này không có trường hợp cần hai truy vấn bị gom thành một theo nhãn thủ công. Prompt mới giữ các ca chủ đề độc lập H17/H18 (hai ca mà gate bỏ sót). Không sửa prompt tiếp sau khi xem bộ 10 câu mới.

V1–V5 mới ra một truy vấn; V6 ra hai. Kiểm tra thêm V3/V4/V6 hai lượt nữa: cả ba câu giữ cùng quyết định qua ba lượt (tổng 9/9 quyết định đạt), không có API/JSON error. Raw ở `critical-repeats.json` cùng thư mục local. Đây vẫn là mẫu nhỏ, chưa có đo đồng thời hay bảo đảm ổn định dài hạn.

Median planner cũ/mới tương ứng: hồi quy 506/499 ms; development 442/454 ms; fresh 449/456 ms. Không suy ra thời gian E2E từ các số này: chưa chạy lại BGE/DB/embedding trên VPS. Lợi ích dự kiến là bỏ lượt retrieval/rerank thừa ở V3/V4, không phải giảm thời gian planner.

Raw report lưu cả prompt cũ/mới và SHA-256 để tái hiện. `expected_planner` là nhãn giả thuyết thủ công về số nhóm tìm kiếm; các tỷ lệ trên không phải accuracy retrieval hoặc correctness của câu trả lời. Bộ thử nhỏ và do người phát triển soạn có thể thiên lệch; cần câu hỏi thực tế từ nhóm và kiểm tra độc lập trước khi khái quát.

## Cần kiểm chứng tiếp trên VPS

Kết quả chỉ đo quyết định planner. Không thể lấy tỷ lệ đúng nhãn tách để kết luận accuracy câu trả lời hoặc latency E2E.

Sau review và khi Huy yêu cầu commit/deploy: thử lại V3/V4/V6, xác nhận số retrieval/rerank lần lượt 1/1/2, kiểm tra nội dung và nguồn không mất điều kiện; sau đó lặp bài ON trên cùng sáu câu, cùng quyền và trạng thái tài liệu. Kỳ vọng giảm chi phí ở V3/V4 nhưng chưa có số giây mới để báo cáo. V6 phải giữ đủ bằng chứng, không chỉ giữ số truy vấn là hai.

Rủi ro còn lại: planner không nhìn tài liệu nên phải dự đoán phạm vi bằng chứng; prompt có thể tách sai hoặc gom sai. Vẫn phát sinh một lần gọi planner cho câu đơn, vẫn chịu quota/deadline của provider. Công tắc 0 quay về luồng không planner như trước. Không cần embedding lại.
