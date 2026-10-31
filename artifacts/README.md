# Mục lục artifacts

## Muốn tìm nhanh

| Bạn cần | Mở ở đâu |
|---|---|
| Kết quả và tài liệu chuẩn bị Review 2 | [review2/README.md](review2/README.md) |
| Benchmark mới đã chốt và chạy lại | [evaluation/heldout-review2-v1](evaluation/heldout-review2-v1/README.md) |
| Bộ development/regression cũ | [evaluation/fresh-reviewed-v1](evaluation/fresh-reviewed-v1/) |
| Metrics bổ sung trên bộ development | [evaluation/retrieval-metrics-20261022/REPORT.vi.md](evaluation/retrieval-metrics-20261022/REPORT.vi.md) |
| Đang làm gì / tiếp tục từ đâu | [HANDOFF.md](HANDOFF.md) — đọc mục mới nhất ở đầu |
| Phân loại các nhóm evaluation | [evaluation/README.md](evaluation/README.md) |
| Kết quả lịch sử đã gom | [archive/README.md](archive/README.md) |
| Tìm một đường dẫn cũ | [inventory-20261022.csv](inventory-20261022.csv) và [nhật ký di chuyển](cleanup-20261022.json) |

## Quy tắc lưu kết quả

- Mỗi đợt benchmark mới dùng một folder có README, đầu vào/cấu hình cố định và runs/<tên-lần-chạy>/; không ghi đè run đã công bố.
- Mục review2 chỉ trỏ tới nguồn gốc, tránh có nhiều bản kết quả không biết bản nào mới.
- Folder cũ vẫn được giữ ở evaluation nếu script, manifest hoặc package đang dùng đường dẫn đó. “Cũ” không đồng nghĩa “có thể xóa”.
- Chuyển file lịch sử vào archive sau khi kiểm tra tham chiếu; ghi old_path/new_path và hash. Không xóa corpus/vector/nhãn của một kết quả đã chốt.

Đợt dọn22/10/2026: gom79 JSON lịch sử và2 folder báo cáo đã được thay thế; không xóa file, không thay production code. Dung lượng không giảm đáng kể vì đây là sắp xếp để dễ tìm.
