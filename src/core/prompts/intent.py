INTENT_CLASSIFIER_PROMPT = """
Phân loại yêu cầu của người dùng trong bối cảnh doanh nghiệp Việt Nam.

Khả năng hiện có:

knowledge:
Tra cứu thông tin thực tế trong tài liệu doanh nghiệp.

analytics:
Truy vấn dữ liệu thương mại có cấu trúc trong schema `commerce` bằng SQL và
tính toán chỉ số. Dữ liệu gồm doanh thu, giá vốn, đơn hàng, khách hàng, sản
phẩm, khuyến mãi, thanh toán, giao hàng, trả hàng, đánh giá, tồn kho và lưu
lượng web. Nhóm này cũng bao gồm việc đếm hoặc so sánh metadata tài liệu.

hybrid:
Cần kết hợp nội dung tài liệu với dữ liệu có cấu trúc.

dashboard:
Người dùng yêu cầu rõ biểu đồ, bảng điều khiển hoặc giao diện KPI.

report:
Người dùng yêu cầu tóm tắt hoặc soạn báo cáo. Không chọn nhóm này chỉ vì câu
hỏi nhắc đến một báo cáo làm nguồn hoặc yêu cầu đếm báo cáo.

Chỉ trả về JSON hợp lệ, không thêm giải thích. Giá trị chuỗi mô tả nếu có phải
dùng tiếng Việt:

{{
  "intent": "knowledge | analytics | dashboard | hybrid | report",
  "needs_knowledge": true,
  "needs_sql": false,
  "output_mode": "answer | dashboard",
  "confidence": 0.0
}}

Yêu cầu của người dùng:
{question}
"""
