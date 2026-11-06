# Hướng dẫn duyệt vietstyle-test-v2 (r2)

Chỉ cần duyệt **8 câu** dưới đây (đổi nội dung đáng kể). Các câu còn lại: Codex đã đối chiếu từng câu với chính sách (CODEX_REVIEW.md); câu tính toán đã được tính lại hai lần (mình + Codex). Với mỗi câu: đọc trích dẫn, xem đáp án có khớp không, ghi `ok` hoặc ghi chỗ sai.

## 1. Q09 — hai người duyệt khác nhau
**Câu hỏi:** Khoản 90 triệu; trưởng bộ phận kiêm phụ trách Mua sắm muốn tự mình hoàn tất toàn bộ phê duyệt. Có được không, vai trò nào phải duyệt?
**Đáp án:** Không. Cần trưởng bộ phận + Mua sắm + Tài chính; ít nhất hai người duyệt khác nhau; ≥3 báo giá văn bản hoặc lý do chỉ định nguồn.
**Trích (tr.19):** “Yêu cầu hai người duyệt khác nhau nếu ma trận chỉ định nhiều phê duyệt.” — **(PL-B):** “50.000.001–200.000.000 VND | Trưởng bộ phận + Mua sắm + Tài chính | Ít nhất ba báo giá văn bản hoặc lý do chỉ định nguồn đã duyệt.”
Duyệt: ____

## 2. Q24 — DATA_CONFLICT
**Câu hỏi:** Chủ dữ liệu xác nhận các chỉ số của cùng snapshot mâu thuẫn. Trước khi dùng để cam kết mua, gắn nhãn gì, xử lý thế nào?
**Đáp án:** Gắn DATA_CONFLICT, điều tra trước cam kết; dừng và yêu cầu xác minh tồn trực tiếp.
**Trích (tr.28):** “Nếu chỉ số mâu thuẫn, gắn DATA_CONFLICT và điều tra trước cam kết.” — **(tr.36):** “Nếu mâu thuẫn dữ liệu có thể gây mua hoặc cam kết khách, dừng và yêu cầu xác minh trực tiếp.”
Duyệt: ____

## 3. Q26 — ngoại lệ không miễn luật (câu bẫy, thay mới)
**Câu hỏi:** Ngoại lệ đã được duyệt, vậy được bỏ qua luôn yêu cầu pháp luật và nghĩa vụ hợp đồng, đúng không?
**Đáp án:** Không. Ngoại lệ không miễn luật, nghĩa vụ hợp đồng hoặc yêu cầu bảo mật không được miễn.
**Trích (tr.45):** “Ngoại lệ không miễn luật, nghĩa vụ hợp đồng hoặc yêu cầu bảo mật không được miễn.”
Duyệt: ____

## 4. Q27 — tố cáo chưa xác minh (câu bẫy, thay mới)
**Câu hỏi:** Nghe một lời tố cáo chưa xác minh về nhà cung cấp, muốn ghi ngay vào bảng điểm đánh giá. Có được không?
**Đáp án:** Không. Bảng điểm không chứa cáo buộc chưa xác minh hoặc dữ liệu cá nhân; điều tra trong bối cảnh, xu hướng và bằng chứng quyết định hành động.
**Trích (tr.24):** “Điều tra từng kết quả xấu trong bối cảnh; xu hướng và bằng chứng quyết định hành động.” “Bảng điểm không chứa cáo buộc chưa xác minh hoặc dữ liệu cá nhân.”
Duyệt: ____

## 5. Q37 — hỏi tiếp về mua khẩn
**Lượt trước:** “Nhóm tôi vừa hoàn tất rà soát sau một khoản mua khẩn.” → **Câu hỏi:** Nếu rà xong phát hiện vi phạm kiểm soát thì coi như đã khắc phục chưa? Nhóm cứ mua khẩn liên tục thì sao?
**Đáp án:** Rà sau không xóa vi phạm kiểm soát; mua khẩn lặp lại phải rà nguyên nhân gốc.
**Trích (tr.23):** “Rà sau không xóa vi phạm kiểm soát.” “Cùng nhóm dùng mua khẩn lặp lại phải rà nguyên nhân gốc.”
Duyệt: ____

## 6. Q39 — câu mơ hồ
**Câu hỏi:** “Phải rà soát bao lâu một lần?”
**Đáp án mong đợi:** Hỏi lại người dùng muốn hỏi rà soát cái gì; không tự chọn một loại. (Bỏ danh sách tần suất vì trùng câu dev X04/M05/E03.)
**Trích (tr.49):** “Nếu bằng chứng mâu thuẫn, hỏi mơ hồ hoặc thiếu trường bắt buộc, hỏi làm rõ hoặc chuyển cấp.”
Duyệt: ____

## 7. Q40 — tin nhắn dài về bàn giao (thay mới)
**Câu hỏi (tóm tắt):** Nghỉ 4 ngày; còn đơn gấp, hàng trả, cam kết nhà cung cấp, sự cố; định nhắn chung “ai rảnh thì xử lý”, không ghi người thay/hạn; định đăng hồ sơ khám thai lên lịch nhóm. Sửa thế nào?
**Đáp án:** Quản lý bố trí thay thế; xác định việc cần phân công lại, ghi rõ người thay và hạn; lịch chỉ hiển thị loại nghỉ và khả năng làm việc; không đưa hồ sơ y tế lên lịch nhóm.
**Trích (tr.8):** “Quản lý chịu trách nhiệm bố trí thay thế…” “Xác định đơn gấp, hàng trả đang mở, cam kết nhà cung cấp và sự cố được giao cần phân công lại.” “Ghi rõ người thay và hạn cho công việc trọng yếu.” “Lịch chỉ hiển thị loại nghỉ và khả năng làm việc…” “Không đưa hồ sơ y tế lên lịch nhóm.”
Duyệt: ____

## 8. Q10–Q16 — kiểm phép tính (đã thêm giả định rõ vào câu hỏi)
| Câu | Phép tính | Kết quả |
|---|---|---|
| Q10 | hạn kế hoạch 250.000 < 300.000 | 250.000/người |
| Q11 | 2.300.000 ≤ 2.500.000 | hoàn đủ |
| Q12 | 3 × 300.000; 1.050.000 − 900.000 | 900.000; vượt 150.000 cần ngoại lệ văn bản duyệt trước |
| Q13 | 2 × 1.600.000 + 2.500.000 | 5.700.000 |
| Q14 | 12 × 3.500.000 + 800.000 | 42.800.000 → trưởng bộ phận, 2 báo giá |
| Q15 | 3 × 24.000.000 | 72.000.000 → TBP + Mua sắm + Tài chính |
| Q16 | 45.000.000 × 1,1 | 49.500.000 → trưởng bộ phận |

**Trích (tr.12):** “ăn uống tại địa phương được hoàn tối đa 300.000 VND/người/bữa; lưu trú … 1.800.000 VND/phòng/đêm ở địa điểm nội địa thông thường và 2.500.000 VND tại thành phố lớn được chỉ định.” **(tr.19):** “Tính tổng cam kết dự kiến gồm vận chuyển, thuế, tùy chọn và gia hạn đã biết.”
Duyệt: ____
