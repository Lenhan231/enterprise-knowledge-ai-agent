# Đồng bộ main vào Huy — 30/10/2026

Người dùng yêu cầu tiếp tục trên Huy, không tạo nhánh task mới.

- Huy trước merge: `68960dd` (đã checkpoint report và audit local).
- Main được merge: `beac2f3c58426ddcaff3a3c95daf5b93154656aa`.
- Merge có 65 đường dẫn conflict do hai nhánh đã lệch kiến trúc/parser/retrieval.
- Runtime `src/`, test hiện hành `tests/`, `pyproject.toml`, `uv.lock` và
  `.env.example` lấy nguyên trạng main, không ghép parser/agent lịch sử vào runtime mới.
- Giữ dữ liệu, artifacts, report và công cụ riêng của Huy; các script trùng tên
  bị conflict lấy phiên bản main. Công cụ thí nghiệm cũ không mặc định tương thích
  runtime mới; frozen Review 2 có source snapshot riêng để kiểm tra lịch sử.
- Source/test lịch sử vẫn có đầy đủ trong commit Huy `68960dd`, không rewrite history.
- Gộp ignore/attribute rules của hai nhánh, giữ quy tắc bảo toàn byte benchmark.
- Ghi chú embedding cũ được giữ tại
  `docs/review2/embeddings-tokenization-historical-huy-20261030.md`.

## Kiểm tra trước merge commit

- Không còn unmerged entries.
- Runtime/dependency/test tree không khác main trước khi làm RBAC.
- Frozen `artifacts/evaluation/heldout-review2-v1`, `artifacts/datasets` và
  `data/evaluation/embedding_benchmark_20261001` không đổi so với Huy trước merge.
- Parse cú pháp toàn bộ Python trong src thành công.
- 23 test chọn lọc: 22 pass, 1 fail sẵn trong main do E5 test đòi
  `d.year_or_version`/`d.company` trong khi SQL hiện dùng chunk metadata.
  Test repository khác cũng có expectation fiscal_year cũ, đã thấy ở phiên audit.
  Sửa expectation đúng theo SQL hiện tại khi bổ sung test RBAC liên quan.
- Chưa build Docker, kiểm tra Supabase/VPS hoặc chạy full suite.

Tiếp theo: thực hiện bộ lọc active + ready + nonempty document ACL, giữ scope
role hiện có và kiểm tra lại context expansion không đưa anchor bị từ chối vào output.
