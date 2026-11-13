# Nhận xét sau bước 3

Ba model đã chạy local GPU, cùng 1.063 chunk, 80 lượt/model; phát lại độc lập xác nhận 240 thứ hạng và mức phủ bằng chứng. Không có input bị truncation. Kết quả đầy đủ nằm trong comparison.md và từng candidates/<model>/results.json.

## Với mục tiêu chính là tiếng Việt

E5 multilingual base tốt nhất ở Việt→Việt trên bộ nhãn này: phủ 55/62 ý bắt buộc (88,7%), đủ bằng chứng cho 15/19 câu (78,9%). BGE và Qwen đều đạt 13/19 câu, lần lượt phủ 53/62 và 51/62 ý. Đây là chênh lệch 2 câu trên tập nhỏ, chưa đủ để kết luận model thắng mọi loại tài liệu. Chưa có MiniLM theo metric mới nên không dùng bảng này để khẳng định mức cải thiện so với MiniLM.

## Với câu hỏi và tài liệu khác ngôn ngữ

BGE ổn định hơn E5 ở cả hai hướng: Việt→Anh 14/19 so với 8/19; Anh→Việt 13/19 so với 11/19. Qwen đạt 14/19 ở Việt→Anh (ngang BGE), phủ nhiều hơn BGE một component; Anh→Việt đạt 12/19. Không có model thắng tất cả các hướng. Bản Anh là tài liệu mô phỏng được chuẩn bị từ bản Việt, không đại diện cho mọi tài liệu tiếng Anh thực tế.

## Vì sao điểm mới thấp hơn điểm tìm file?

Ví dụ E5 Việt→Việt Q13 có source_recall_at_10=1.0: các file được gán đều xuất hiện. Tuy nhiên nhãn evidence báo thiếu Q13.prepare, Q13.independent và Q13.audit_update. Tìm đúng file không đảm bảo top 10 chứa mọi chi tiết cần trả lời. Đây là thiếu theo nhãn hiện tại; vẫn cần đọc các chunk để kiểm tra liệu có đoạn diễn đạt tương đương chưa được gán nhãn.

Q18.no_guess bị thiếu ở E5 và BGE Việt→Việt: câu này đòi bằng chứng rằng không thể suy ra số liệu PO/backorder từ bộ tài liệu mô phỏng. Nó không phải bài tìm một con số bằng zero. Q14 vẫn có vấn đề nhãn vai trò phê duyệt giữa Manual/SOP và không được tính full-intent đúng/sai.

## Việc nên làm tiếp

Đọc và xác nhận các ca mất điểm của E5 Việt→Việt (Q11, Q13, Q18, Q20) trước vì nhóm đang ưu tiên dữ liệu Việt. Phân loại: đoạn thật sự chưa lọt top 10; bằng chứng tương đương bị thiếu nhãn; hoặc câu hỏi cần nhiều đoạn nên top 10 chưa đủ. Sau khi nhãn rõ hơn mới thử thay đổi retrieval như ghép chunk lân cận/parent context, tăng candidate pool hoặc hybrid/reranker, và đo bằng cùng bộ chấm. Chưa cần thay model trong database từ kết quả này.
