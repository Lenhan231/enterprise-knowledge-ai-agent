# Bộ câu hỏi kiểm thử VietStyle EN/VI

Ngày soạn: 31/10/2026. Đây là bộ kiểm thử nhỏ tập trung vào bảng, chưa phải benchmark đại diện mọi chức năng.

Nguồn đã đọc trực tiếp từ database:
- EN: `UPLOAD-12f3d0901de9444fba9ad23005a0f54e`.
- VI: `UPLOAD-5f3724762c5e4146b9f85d3696a6f919`.

Chỉ bật một bản mỗi lượt; route Knowledge; New conversation trước mỗi câu. Hỏi cùng bộ câu tiếng Việt trên EN rồi trên VI. Chấm nội dung, điều kiện và nguồn riêng; câu đúng nhờ tài liệu khác không tính đạt kiểm thử bản mục tiêu. Các chunk ID dưới đây là số ghi trong DB, có thể đổi khi xử lý lại.

## Câu hỏi để copy

1. Theo Appendix B/Phụ lục B của VietStyle, khoản mua sắm 80 triệu đồng cần những bên nào phê duyệt và cần bao nhiêu báo giá?
2. Theo Appendix B/Phụ lục B, khoản mua sắm đúng 50 triệu và 50.000.001 đồng khác nhau thế nào về phê duyệt và yêu cầu báo giá?
3. Theo Appendix B/Phụ lục B, khoản mua sắm đúng 5 triệu và 5.000.001 đồng khác nhau thế nào về phê duyệt và điều kiện bổ sung?
4. Theo Appendix B/Phụ lục B, khoản mua sắm 250 triệu đồng cần ai phê duyệt và phải bổ sung hồ sơ gì?
5. Theo Appendix C/Phụ lục C, yêu cầu mua sắm cần những trường thông tin tối thiểu nào?
6. Theo Appendix C/Phụ lục C, số lượng bằng 0 có đạt điều kiện kiểm tra của yêu cầu mua sắm không? Còn phải kiểm tra điều kiện gì khác?
7. Theo Appendix C/Phụ lục C, biên bản nhận hàng có lượng giao 100, chấp nhận 90 và từ chối 15 có thỏa điều kiện số lượng không? Nêu thêm các điều kiện kiểm tra còn lại.
8. Theo Appendix C/Phụ lục C, biểu mẫu ngoại lệ chính sách cần thông tin gì và áp dụng điều kiện phê duyệt, pháp luật, hết hạn như thế nào?
9. Theo mục yêu cầu kiểm soát về nhật ký hệ thống, những loại dữ liệu nào không được ghi vào log?
10. Theo Appendix B và C/Phụ lục B và C, khoản mua sắm 80 triệu cần ai duyệt, điều kiện báo giá là gì, và đơn mua hàng chỉ được phát hành khi nào?
11. Tài liệu này cho biết chính xác doanh thu thực tế của VietStyle ngày 31/10/2026 là bao nhiêu không? Nếu có, nêu số và nguồn.
12. Tài liệu này cho biết mã PO và tên nhà cung cấp thực tế của khoản mua sắm 80 triệu đang được hỏi là gì không? Không suy đoán từ quy định chung.

## Đáp án và bằng chứng để người chấm đối chiếu

| Câu | Ý bắt buộc | Chunk EN | Chunk VI |
|---|---|---:|---:|
| 1 | 80 triệu thuộc mức 50.000.001–200.000.000; Trưởng bộ phận + Mua sắm + Tài chính; ít nhất 3 báo giá bằng văn bản hoặc lý do chỉ định nguồn **đã phê duyệt** | 781 | 730 |
| 2 | 50 triệu: Trưởng bộ phận, ít nhất 2 báo giá tương đương nếu thị trường cho phép. 50.000.001: ba bên như câu 1, ít nhất 3 báo giá văn bản hoặc lý do chỉ định nguồn đã duyệt | 781 | 730 |
| 3 | 5 triệu: Quản lý trực tiếp; một báo giá có hồ sơ, ngân sách xác nhận. 5.000.001: Trưởng bộ phận; ít nhất hai báo giá tương đương nếu thị trường cho phép | 781 | 730 |
| 4 | Hội đồng Điều hành Vận hành + Tài chính; đánh giá nguồn cung và rà soát rủi ro được lập hồ sơ | 781 | 730 |
| 5 | Người đề nghị, bộ phận, lý do, sản phẩm/đặc tả, số lượng, dự toán, tiền tệ, chủ ngân sách | 790 | 737 |
| 6 | Không: số lượng phải > 0. Không trùng yêu cầu đang mở; ghi nhận ngân sách và tuyến/phương án tìm nguồn | 790 | 737 |
| 7 | Không: 90 + 15 = 105 > 100; yêu cầu accepted + rejected <= delivered. PO phải hợp lệ; hàng không đạt phải được cách ly | 791 | 741 |
| 8 | Mã/tham chiếu chính sách, giải trình, rủi ro, kiểm soát bù, chủ/người phụ trách, người duyệt, thời hạn hết hiệu lực. Cần duyệt trước trừ khẩn cấp thực sự; không miễn tuân thủ pháp luật; thực thi hết hạn | 792 | 741 |
| 9 | Không ghi mật khẩu, access token/token, thông tin thanh toán đầy đủ và dữ liệu cá nhân không cần thiết | 627 | 587 |
| 10 | Đủ ý câu 1, cộng PO chỉ được phát hành sau phê duyệt; không được kết luận cần cả 3 báo giá và lý do chỉ định nguồn cùng lúc | 781 + 791 | 730 + 738 |
| 11 | Câu kiểm tra từ chối: không tự bịa doanh thu thực tế từ chính sách. Chỉ trả số nếu có bằng chứng cụ thể đúng ngày và tài liệu mục tiêu; nếu không thì nói không đủ thông tin | Kiểm tra bằng chứng nếu có | Kiểm tra bằng chứng nếu có |
| 12 | 80 triệu là tình huống giả định trong câu hỏi, không tự tạo giao dịch/PO/nhà cung cấp thực tế. Nếu không có bằng chứng cụ thể, nói không đủ thông tin | Kiểm tra bằng chứng nếu có | Kiểm tra bằng chứng nếu có |

Câu 11–12 là ca thiếu dữ liệu kỳ vọng, không phải kết luận đã rà mọi ký tự của hai PDF để chứng minh không tồn tại. Nếu hệ thống đưa bằng chứng thật, cần kiểm tra trước khi chấm sai.

## Phiếu ghi kết quả

| Câu | Bản EN/VI | Nội dung đúng/sai | Đủ điều kiện? | Nguồn đúng và đủ? | Ghi chú |
|---|---|---|---|---|---|

Câu 1–10: bỏ sót điều kiện quan trọng thì ghi thiếu, không tính hoàn toàn đúng. Câu 11–12: câu trả lời từ chối hợp lý không cần ép có trích dẫn; trích dẫn quy định chung không chứng minh một giao dịch thực tế. Nếu không trả lời được câu 1–10, xem context retrieval trước khi quy lỗi cho E5.
