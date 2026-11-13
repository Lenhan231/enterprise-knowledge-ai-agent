# Handoff — Chunking, Knowledge AI và VPS — 29/10/2026

## Đọc trước khi làm tiếp

Checkpoint này nằm trên **Huy**, chỉ gồm tài liệu và bằng chứng audit gọn.
Code tích hợp hiện nằm trên **main**. Không merge toàn bộ Huy vào main chỉ để
lấy handoff: Huy còn giữ implementation/benchmark lịch sử khác main.

- Worker đã commit và push main: **43cde905598c5553dbaab592f9ef4933adbf00bd**.
- Lần fetch cuối: `origin/main` ở **b495167**. Có thêm thay đổi của nhóm sau
  commit worker; chưa chạy lại toàn bộ main mới hoặc deploy nó trên VPS.
- Khi tiếp tục: đọc handoff này, kiểm tra `git status`, fetch remote, rồi chuyển
  main và cập nhật bằng fast-forward nếu có thể. Không force-push/reset dữ liệu local.

## Phân công và phạm vi đã chốt

- Huy: nhận parser output, chunking, token budget, embedding/retrieval và Knowledge AI.
- Nhân: parsing/OCR/layout; đang xử lý diagram có context. Theo Nhân, figure hiện
  tại là dấu nên tạm chưa đưa vào retrieval. Vẫn giữ nguồn/metadata figure.
- An: Router, Dashboard/SQL/Analytics/Report và phối hợp contract quyền truy cập.
- Trước mắt giữ kỹ thuật chunking hiện tại để test; chưa tuning nhiều cấu hình.
  Text/bảng là phạm vi đang triển khai. Chưa tạo worker embedding trong phiên này.

## Worker đã làm và đã push main

Các file ở main: `src/core/chunking/worker.py`, `processing_output.py`,
`processor.py`, `docker/Dockerfile.chunking`, `docker-compose.yml`,
`scripts/chunking/preview_processing_output.py`, tests và hướng dẫn chunking/deployment.

```text
documents.processing_status = parsed + có document_processing_outputs
→ lock document và parser-output bằng FOR UPDATE SKIP LOCKED
→ đọc elements/tables/document_metadata từ Supabase
→ map_output → ChunkingProcessor
→ replace document_parser_chunks + status chunked trong cùng transaction
```

Claim là khóa transaction; không có lease hay trạng thái `chunking` đã commit
riêng. Hai worker không nhận cùng tài liệu. Trạng thái nhìn từ session khác vẫn
là `parsed` trong khi khóa đang giữ. Source output cũng bị khóa để tránh bị thay
giữa lúc chunking. Xử lý thuần CPU, không gọi inference/API trong transaction.

- Thành công: `chunked`, chưa phải `ready`.
- Lỗi xử lý/ghi: rollback replacement, giữ chunks cũ, chuyển `failed`, log document ID.
- Gián đoạn trước commit: rollback; có thể nhận lại tài liệu khi connection/lock được giải phóng.
- Poll 5 giây mặc định; có `--once`. `failed` không tự retry; retry cần chủ động đưa về `parsed`.
- Không tạo vector, không bật knowledge base, không thay company/roles, không ghi analytics store.
- Metadata giữ tham chiếu nguồn theo nhóm parser, không phải exact character spans của từng token fragment.

Worker dùng schema canonical **elements/tables**, giữ thứ tự elements và table_ref.
Mapper còn hỗ trợ split-array snapshot cũ cho dry-run; thứ tự bbox của snapshot cũ
chỉ là ước lượng. Các dòng cũ do migration ghép lại không tự khôi phục được thứ tự gốc.

Hai migration từ main cần có trước khi bật worker:

1. `supabase/migrations/20261028090548_add_chunking_document_statuses.sql`
2. `supabase/migrations/20261028091543_align_processing_outputs_with_parser.sql`

Worker kiểm tra schema/status trước khi claim. Không dùng migration tạm
`20261028160000_add_chunked_document_status.sql`: file đó đã bỏ khi main có migration tương ứng.
Hai bảng phụ `document_processing_text_elements`/`document_processing_figures` đã
được bỏ; không dựa vào chúng. Source nằm trong JSON canonical.

## Kiểm chứng đã thực hiện

Ở commit worker 43cde90: **28 tests pass**, gồm PostgreSQL local thật cho concurrent
claims, khóa source, rollback lỗi INSERT sau DELETE, interruption/retry,
schema guard, CLI --once, mapping canonical/legacy, provenance và token splitting.
Test PostgreSQL dùng database tạm riêng, đã xóa; server tạm đã dừng. Không test ghi lên Supabase.

Trước khi schema đổi canonical: snapshot tài liệu Nhân được dry-run và ghi thử
**298 parser chunks** vào PostgreSQL local, content khớp dry-run; poll lại không nhận nữa.
Đó không phải số chunk được ghi trên production. Main mới sau 43cde90 chưa được kiểm chứng lại trong phiên này.
Không có Docker CLI tại workspace; chỉ kiểm tra YAML và import/entry point theo layout image,
chưa build/chạy Docker image thật ở đây. Main mới đã bổ sung dependency cho image chunking.

## Parser và chunking còn dính nhau ở đâu?

Lúc đầu kiểm tra: API lưu raw output trước nhưng chạy chunking bằng biến `parsed`
trong bộ nhớ; parser-handoff chỉ đặt `parsed` sau khi chunking xong.

**Cập nhật quan trọng lúc viết handoff:** main đã có **c7cd012**, tách `/parser-handoff`:

```text
/parser-handoff: parse → lưu raw output → parsed → trả response (không chunk/embed)
chunking worker: đọc Supabase → parser chunks → chunked
```

Upload thường `/api/documents/upload` vẫn giữ đường synchronous:
parse → lưu raw output → inline chunking → inline embedding → ready.
Công cụ Streamlit của Nhân lưu parser output + parsed rồi dừng; không chunking.
Embedding worker đọc `chunked` chưa được làm. Đừng coi toàn bộ ingestion đã async.

## Tài liệu đã audit và những lỗi còn lại

- Document ID: `PARSER-04180dffbff040b4978182be2208b9e3`.
- Title: `2.BCTC da kiem toan 2008 (V)`; PDF gốc 22 trang trên main:
  `data/raw/processing_data/2.BCTC da kiem toan 2008 (V).pdf`.
- SHA-256: `73147462f2b39db5efa971136a6d3468f248393bce500cc6568639a7b53b6fa4`.
- Snapshot cũ: 564 text, 24 bảng, 16 figures; 298 parser chunks → 302 token passages;
  input dài nhất 510/512 tokens. 189 chunks là lần thử ban đầu ghép bảng ở cuối,
  không phải kết quả đã khôi phục thứ tự bbox và cũng không chứng minh chất lượng tốt hơn.
- Đủ tham chiếu 588 text/table sources; đối chiếu 265 dòng bảng không rỗng và text
  sau chuẩn hóa khoảng trắng không phát hiện mất so với parser output.
- Đối chiếu trực quan 6 trang PDF: 3, 7, 14, 17, 18, 19. Không phải OCR CER/WER benchmark.

Các vấn đề xác nhận:

1. PDF trang 7: tổng nguồn vốn **577.753.465**, parser lưu **52793465**.
   Lỗi OCR có trước chunking, không tự sửa/đoán số trong mapper.
2. PDF trang 17: bảng xoay, parser gộp sai cấu trúc thành 6 dòng/4 cột generic.
3. Trang 14/18: các bảng/mục khác nhau bị gom chung; cần Nhân xử lý lại layout.
4. Token splitting cắt giữa hàng/ô số ở parser chunks 109, 110, 251, 252.
   Header và ký tự vẫn giữ nhờ overlap nhưng token child có thể thiếu tên khoản mục;
   metadata phạm vi hàng vẫn là phạm vi parent. Đây là việc chunking/tokenization cần cải thiện.
5. 24 bảng context rỗng; 41 table chunks không có section_title.
6. 154 text elements không có chữ/số; 40 chunk bodies không có chữ/số sau khi bỏ
   context headers. Mép gáy PDF tạo nhiễu và làm geometric order phân mảnh văn bản.

Bản audit gọn đã track trên Huy:
`artifacts/evaluation/chunking/long-hau-2008-parser-output-audit-20261028.json`.
Đây là audit snapshot split-array trước migration; không khẳng định dữ liệu live vẫn giữ nguyên.
Full JSON/Markdown preview và ảnh render ở `artifacts/local/chunking-preview/` chỉ
có trên máy này, được gitignore, không push. Không phụ thuộc chúng khi đổi máy.

## Quy tắc RBAC đã thống nhất

Server xác định roles/scope từ identity đã xác thực, không tin roles từ query/frontend.
Dense và BM25 phải lọc trước candidate selection/rerank; LLM chỉ nhận bằng chứng được phép.

1. Không có bằng chứng trong phạm vi được phép: “Không tìm thấy tài liệu phù hợp.”
2. `allowed_roles: []`: mặc định không cấp quyền, không đưa vào retrieval.
3. Yêu cầu tài liệu cụ thể nhưng role không khớp: “Bạn không đủ quyền truy cập tài liệu này.”

Không tìm thêm tài liệu bị cấm cho câu hỏi chung chỉ để phân biệt hai message.
Chưa kiểm chứng enforcement toàn bộ main mới. Snapshot preview thiếu company,
roles rỗng và inactive; worker không được tự cấp quyền hoặc kích hoạt nó.

## Hosting: người dùng đã thuê Contabo 12 GB RAM

Mục tiêu: cả nhóm truy cập và test mà không phụ thuộc người giữ máy cá nhân.
Người dùng xác nhận đang dùng Contabo 12 GB; để VPS/backend chạy 24/7.
Đóng SSH hoặc tắt laptop không dừng container đã chạy bằng `docker compose up -d`.
Compose có restart unless-stopped; cần kiểm tra Docker được bật cùng hệ điều hành.
Stop VPS/container không hủy phí thuê; cancellation/gia hạn phụ thuộc hợp đồng trong panel.

Chưa SSH, deploy hoặc đo RAM trên VPS này; chưa có IP/domain/credentials được cấp
trong phiên. Không ghi credentials vào handoff. Chưa thiết lập CI/CD tự deploy.
Ước lượng 12 GB là mức có thể thử với tải hạn chế, 16 GB ưu tiên, 24 GB có dư địa hơn;
không phải benchmark. BGE probe lịch sử 2.31 GiB RSS chỉ gồm cặp ngắn, không phải peak cả stack.
LLM dùng API và PostgreSQL ở Supabase nên không cộng model LLM/database vào RAM VPS.

Main mới b495167 đã đổi runtime default sang `qwen/qwen3.8-27b` và giữ OSS-120B
làm baseline; `.env` của server có thể override. Không mô tả mọi runtime vẫn dùng OSS-120B.

## Thứ tự làm tiếp ngày mai

1. Fetch/read main mới trước khi sửa; đặc biệt parser-handoff, worker, schema và config model.
2. Kiểm tra deployment Contabo 12 GB: service nào đã chạy, migration nào đã áp dụng,
   logs/health, URL HTTPS và frontend Vercel đang trỏ đâu. Không kết luận worker đã live chỉ vì code đã push.
3. Chạy một tài liệu test qua parser-handoff/Streamlit → parsed → worker → parser chunks → chunked.
   Hiện chưa thực hiện bước này trên Supabase/VPS thật; không nhầm với test local đã qua.
4. Chốt contract embedding nhận `chunked`, kiểm tra token, ghi vectors, rồi ready;
   không gộp lại vào parser. Worker embedding chưa có. Thống nhất với An trước khi đổi API response/luồng upload thường.
5. Sửa giữ nguyên hàng qua token split nếu hàng vừa budget; xử lý context/nhiễu có kiểm tra,
   giữ baseline trước đổi. Gửi ví dụ OCR/layout ở trên cho Nhân qua người dùng;
   chưa gửi tin nhắn trực tiếp cho thành viên nào.
6. Test Knowledge AI từ source → retrieval → answer/citation và scope RBAC.
7. Đo RAM thực tế lúc idle, chat, OCR và đồng thời trước khi nâng VPS. Thiết lập CI/CD
   main → build/test → deploy để nhóm không phụ thuộc một người cập nhật thủ công.

Các benchmark Review2 cũ và evidence guide vẫn nằm trên Huy, không bị sửa số liệu
hoặc chạy lại. Không lấy kết quả 80-case cũ để khẳng định chất lượng tài liệu Nhân mới.
