# Kết quả lịch sử đã lưu trữ

Đợt dọn 22/10/2026 chỉ di chuyển, không xóa dữ liệu. Các file được kiểm SHA-256 trước/sau; đường dẫn cũ–mới ở [cleanup-20261022.json](../cleanup-20261022.json).

| Thư mục | Nội dung |
|---|---|
| [legacy-reports-20261022](legacy-reports-20261022/) | 79 JSON kết quả/diagnostic lịch sử không có tham chiếu bên ngoài trong lần rà 1.048 file mã, notebook, dữ liệu và tài liệu. Ngày trong tên là ngày gom, không phải ngày mọi thí nghiệm. |
| [main-review-20261021](main-review-20261021/REVIEW.md) | Bản rà main trước khi tích hợp parser/production. |
| [retrieval-metrics-20261022-initial](retrieval-metrics-20261022-initial/) | Bản metrics đầu, đã được bản evaluation/retrieval-metrics-20261022 thay thế. Có giữ evaluator-at-run.py để truy vết. |

Không sửa dữ liệu lưu trữ để khớp kết quả mới. Nếu cần phục hồi vị trí cũ, xem old_path/new_path trong nhật ký, bảo đảm vị trí cũ chưa có file mới rồi di chuyển ngược. Không ghi đè kết quả được sinh sau ngày dọn.
