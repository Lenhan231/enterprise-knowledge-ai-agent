# Main, RBAC và report — 30/10/2026

## Phạm vi và trạng thái

- Đã fetch origin/main: `beac2f3c58426ddcaff3a3c95daf5b93154656aa`.
- Huy giữ `244803b`; không merge/rebase main vào nhánh lịch sử.
- Đọc/test main trong detached worktree `/tmp/enterprise-main-review-20261030`.
- Không sửa runtime code, chạy model, tải weights, ghi Supabase hoặc truy cập VPS.
- Người dùng giao thêm RBAC cho Huy và chọn soạn cả khung report nhóm, đánh dấu phần chờ Nhân/An.
- Google Doc đã cập nhật bằng tiếng Anh:
  https://docs.google.com/document/d/1dmKUA7Ahqr7Zu2pyjc9P2dONwtPMEC0v6XQcoAPTAVU/edit
- Bản nội dung lưu trong [group-report-draft-20261030.en.md](../report/group-report-draft-20261030.en.md).
  Đây là working draft, không phải báo cáo đã được các thành viên duyệt.
- Chưa commit/push các tài liệu mới của phiên này.

## Main mới khác checkpoint laptop thế nào?

Checkpoint laptop đã audit `169ea59`, biết remote `6fbfdf6` nhưng chưa review.
`6fbfdf6` thêm điều phối Knowledge/SQL có planning, giới hạn thực thi, truyền identity,
lịch sử hội thoại theo subject/conversation và fingerprint quyền; Report dùng nguồn
documents/analytics theo permission. Không coi finding “Knowledge không truyền role”
của audit cũ là hiện trạng: main mới đã truyền role cho Knowledge và report retrieval.

Các commit tiếp theo tập trung OCR:
- Heuristics VietOCR, lọc dòng lặp và nhiễu mép trang, sử dụng rendered page image
  để kiểm tra OCR đáng ngờ; giữ diagnostics thay vì khẳng định mọi lỗi đã sửa.
- Có reviewed layout pilot v3 trên 5 trang, IoU 0.50, so saved detector outputs,
  không post-processing. PP-DocLayout-L conf0.40 đạt macro-F1 ưu tiên 57.5%
  (table/text/title), dưới gate85%; chưa mở batch5 trang tiếp theo.
- Nguồn: `artifacts/evaluation/document-pipelines/results/shared-html/layout-5pilot-review-v3-20261030/report.md`.
  Không gọi đây là kết quả toàn bộ OCR hoặc chất lượng production.

Ingestion vẫn có hai đường:
- parser-handoff: lưu raw output + parsed; chunking worker: parsed → chunked.
- upload thường: inline chunking/embedding → ready.
- Không tìm thấy worker embedding riêng nối chunked → ready trong main đã đọc.

## RBAC đã có

1. `src/app/security.py`: role/permission matrix, JWT, route permission.
2. `src/app/agents.py::_agent_request`: server tạo VerifiedIdentity từ authenticated user;
   metadata request không được tự chèn identity/role/permission.
3. `src/core/agents/execution.py::authorize`: permission theo task; Knowledge cần document roles.
4. `src/core/agents/knowledge_agent.py`: truyền verified roles vào generate/retrieve;
   report document sources dùng đường retrieve này.
5. `src/core/retrieval/methods/common.py::eligible_cte`: role filter trước ranking/LIMIT
   cho dense/BM25/hybrid. Parent expansion lặp lại role/company filter.
6. `src/core/agents/conversation_context.py`: key theo subject + conversation;
   đổi fingerprint permissions/document_roles thì xóa history.
7. `src/core/reports/sources.py`: kiểm tra permission theo nguồn report.

Đây là nền có sẵn, không cần viết RBAC từ đầu. Chưa chứng minh đủ toàn bộ luồng.

## Gaps cần xử lý, theo ưu tiên

### 1. Tài liệu đã tắt vẫn có thể vào retrieval

Candidate SQL chỉ lọc ready, thiếu `knowledge_base_active`.
`expand_parent_contexts` cũng thiếu. Cần eligibility nhất quán trên hai đường.
Đây là finding đọc source, chưa dựng live exploit hoặc gọi production.

### 2. ACL rỗng và admin đang không theo policy đã chốt

SQL có `allowed_roles && roles OR 'admin' = ANY(roles)`: admin bypass cả ACL rỗng.
Nhóm trước đó chốt ACL rỗng là deny-all. Mặc định thực hiện policy đã chốt;
nếu muốn ngoại lệ admin thì phải ghi rõ ngoại lệ, không âm thầm coi đó là deny-all.
`DocumentAccessRequest` hiện min_length=1 nên API update không cho revoke về [].
Không nhầm [] ở role người dùng với [] ở ACL tài liệu.

### 3. Chốt phạm vi RBAC với schema thực tế

VerifiedIdentity hiện có subject, permissions, document_roles; chưa có company
hoặc danh sách document IDs được server xác định. Backend retrieval có tham số
company/document_ids nhưng Knowledge chưa truyền chúng. Nếu deployment chỉ một
company, đây là giới hạn scope, chưa đủ bằng chứng gọi là lỗi tenant thực tế.
Chỉ thêm company/doc scope theo nguồn dữ liệu server xác thực đã thống nhất;
không nhận quyền từ query, client metadata hoặc LLM.

### 4. Ba kết quả và phạm vi thông báo

- Có quyền và tìm thấy evidence: chỉ đưa evidence được phép sang reranker/LLM/citations.
- Không có evidence được phép cho query thông thường: “Không tìm thấy tài liệu phù hợp.”
- Yêu cầu tài liệu cụ thể có access-check được phép xác định mismatch: “Không đủ quyền.”
Không tìm trong corpus bị cấm để giải thích query chung thất bại; tránh lộ tồn tại tài liệu.
Empty ACL phải deny theo policy nhóm, không suy ra đây là không tìm thấy nội dung.

### 5. Kiểm thử RBAC sau khi sửa

Cases tối thiểu: allow/mismatch/empty ACL/disabled/not-ready/missing identity;
giả mạo client roles; dense/BM25/translated cùng scope; parent expansion;
Knowledge→Report evidence/citations; đổi ACL, role hoặc disable document trong hội thoại.
History fingerprint hiện chỉ theo quyền người dùng, không phải phiên bản ACL tài liệu:
cần kiểm tra revocation thực tế, chưa kết luận history tự xử lý được mọi revoke.
Định nghĩa expected outcome, task có được gọi không, evidence/prompt/citation chứa gì.
Không chỉ kiểm tra câu trả lời cuối.

## Test đã chạy trong phiên

Chọn 5 module trên main bằng venv desktop hiện có, offline:
`test_docling_ocr_postprocessing.py`, `test_bounded_execution.py`,
`test_orchestration_contracts.py`, `test_report_orchestration.py`,
`test_document_chunks_repository.py`.

unittest báo 36 records: 33 pass, 1 fail, 2 errors.
- Fail SQL expectation trong `test_query_uses_cosine_order_and_bound_parameters`:
  test đòi `d.fiscal_year = %s`, SQL hiện lấy year trong chunk metadata.
- Hai module không import vì venv thiếu `cv2` và `docx`.
  Đây là thiếu dependency môi trường local, không đủ chứng minh main/production hỏng.
- Không sync/install môi trường, không chạy full suite; không báo CI mới pass/fail.
- Log local: `/tmp/enterprise-main-review-tests.log` (không phải artifact bền).
- 28 tests của worker là kết quả lịch sử commit43cde90, không thay bằng kết quả main mới.
- CI YAML có build backend-api/embeddings/reranker/document-processing,
  chưa build chunking; không có bằng chứng tự deploy VPS.

## Report vừa làm

Đã thay template bằng working draft cả nhóm: Introduction, Management,
Literature framework, Methodology, Design, Results, Conclusion, evidence references,
appendix RBAC planned checks. Bỏ mẫu RL và heading Methodology trùng trong body.
TOC native còn nội dung template cũ: cần refresh trong Google Docs sau khi chốt layout.
Chưa kiểm tra PDF/rendered layout hoặc hoàn thiện bảng/ảnh/captions.

- Nhân: xác nhận parser/OCR/layout/table data, protocol, số liệu, artifacts và primary refs.
- An: xác nhận generation/Dashboard/SQL/Report protocol, chất lượng và latency thực đo.
- Huy: hoàn thiện RBAC rồi điền acceptance results; kiểm tra chunking/Knowledge baseline.
- Deployment owner chưa chốt: live commit, endpoint, runbook, health, RAM/load/cost thực tế.
- Research bibliography mới là danh sách cần bổ sung; không bịa papers/citations.
- Giữ frozen retrieval69/80 là full evidence, không answer accuracy; ghi10versions/1063chunks/
  20intentclusters/80directioncases riêng với shared5VI/532snapshot.
- Thêm pilot layout5pages57.5% đúng phạm vi; Nhân cần review diễn giải.
- Google Doc đã đọc lại nội dung; chưa certify typography/pagination.

## Đề xuất task code tiếp theo

Bắt đầu trên branch/worktree từ main mới:
1. Đồng bộ eligibility active/ready và deny-empty policy trong candidate + parent expansion.
2. Cho phép ACL revoke hợp lệ, giữ server-only identity; chốt admin exception nếu có yêu cầu mới.
3. Thêm integration tests meaningful cho ba outcomes và Knowledge/Report scope.
4. Sau đó hoàn thiện Knowledge baseline và handoff embedding, phối hợp An/Nhân theo contract.

