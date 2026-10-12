# Enterprise Knowledge AI Agent

Trợ lý phân tích dữ liệu doanh nghiệp bằng tiếng Việt, sử dụng schema `commerce` trên Supabase PostgreSQL.

## Cài đặt

```powershell
uv sync
```

Tạo `.env` và cấu hình hai kết nối tách biệt:

```text
DATABASE_URL=postgresql://...            # kho tài liệu/RAG
ANALYTICS_DATABASE_URL=postgresql://...  # commerce reader chỉ đọc
```

`ANALYTICS_DATABASE_URL` phải dùng login không phải superuser, không có quyền ghi,
chỉ có `USAGE` trên schema `commerce` và `SELECT` trên các cột được phê duyệt.
Chạy [scripts/provision_commerce_analytics_reader.sql](scripts/provision_commerce_analytics_reader.sql)
bằng tài khoản quản trị để tạo role nhóm, sau đó tạo login/password trong secret
manager của môi trường và grant login đó vào role. Ứng dụng tự kiểm tra quyền và từ
chối khởi động analytics nếu nhận kết nối `postgres`/service role hoặc role có quyền ghi.
Không đưa chuỗi kết nối vào frontend hoặc commit vào Git.

## Chạy ứng dụng

```powershell
uvicorn src.app.main:app --reload --port 8000
```

Mở `http://localhost:8000` để sử dụng giao diện chat tiếng Việt.

### API chat

```http
POST /api/chat
Content-Type: application/json

{
  "question": "Doanh thu và giá vốn tháng 12/2022"
}
```

Analytics chỉ chạy khi middleware xác thực đã gắn một `VerifiedIdentity` phía server
với permission `analytics:read` vào `request.state.verified_identity`. `user_id` do
client gửi bị từ chối; cài đặt mặc định không xác thực trả HTTP 403 cho analytics.
Câu hỏi chính sách/tài liệu vẫn đi qua knowledge/RAG và không chạy SQL.

Response tuân theo model `AgentResult`, bao gồm `answer`, `agent`, `evidence`, `data` và `metadata`.
`/api/chat` đi qua `AgentRouter`: câu hỏi số liệu dùng analytics; câu hỏi về nội dung tài liệu dùng knowledge/RAG. Knowledge cần `DATABASE_URL` trỏ tới kho `document_chunks` và `GROQ_API_KEY`. Yêu cầu kết hợp đồng thời tài liệu với SQL hoặc tạo dashboard hiện trả thông báo chưa hỗ trợ.

Với analytics, `data.table` chứa `columns` và `rows`; giao diện hiển thị bảng này. Chỉ số được chọn từ ontology, còn giá trị như `gross_profit = revenue - cogs` được tính trong code. Có thể hỏi cao nhất/thấp nhất, so sánh vùng hoặc các tháng trong năm, chọn vùng hoặc danh mục, và hỏi theo tháng hay năm. Kỳ hợp lệ nhưng không có hàng trả về thông báo “Không có dữ liệu”; yêu cầu thiếu thời gian hoặc tên nhóm không rõ sẽ được yêu cầu làm rõ.

Các câu hỏi analytics hiện được hỗ trợ:

- Doanh thu, giá vốn và lợi nhuận gộp theo tháng/năm; cực trị doanh thu theo ngày
  hoặc tháng khi người dùng nêu rõ grain.
- Doanh thu theo khu vực cho bất kỳ tập con khu vực nào có trong kết quả. Đây là
  doanh thu tái dựng từ đơn đã giao, không phải `commerce.sales`.
- Tồn kho theo danh mục tại đúng một ngày snapshot; không cộng số dư qua snapshot.
- Lượt truy cập và tỷ lệ thoát, có thể nhóm theo nguồn truy cập.
- Số đơn theo trạng thái, thiết bị, nguồn đơn hoặc khu vực; AOV theo khu vực;
  điểm đánh giá theo danh mục/sản phẩm; thời gian giao hàng theo khu vực.
- Tra cứu sản phẩm theo `product_id`.

Các nghĩa chưa hỗ trợ được trả lời rõ ràng, hiện gồm tỷ lệ hoàn hàng, phân tích mức
giảm theo promotion, tra cứu tự do theo tên và câu hỏi cần nhiều metric linh hoạt
trong cùng một truy vấn. Không suy ra rằng mọi câu hỏi đều trả lời được chỉ vì bảng
có tồn tại.

Luồng text-to-SQL chỉ biên dịch kế hoạch semantic đã kiểm soát. Trước khi chạy,
SQL được parse thành AST và bắt buộc là đúng một `SELECT`, chỉ dùng bảng/cột/join/hàm
trong allowlist, có `LIMIT <= 200`, transaction read-only và statement timeout 5 giây.
SQL sinh ra không xuất hiện trong response `/api/chat`.

## Smoke test Supabase

Script sau chạy ba truy vấn thật bằng `ANALYTICS_DATABASE_URL`, kiểm tra
`AgentResult`/`Evidence` và xác minh transaction chỉ đọc:

```powershell
$env:PYTHONIOENCODING='utf-8'
.venv\Scripts\python.exe scripts/smoke_test_supabase_analytics.py
```

Ghi báo cáo JSON tái lập:

```powershell
.venv\Scripts\python.exe scripts/smoke_test_supabase_analytics.py `
  --output artifacts/smoke/supabase_analytics_smoke.json
```

Write probe sử dụng `UPDATE ... WHERE FALSE` bên trong transaction `readonly=True`. Câu lệnh không thể sửa hàng nào và smoke test chỉ pass khi PostgreSQL chặn nó với SQLSTATE `25006`.

## Chạy test

```powershell
.venv\Scripts\python.exe -m unittest discover -s tests -p 'test_*.py'
```

Các test mặc định không gọi dịch vụ bên ngoài. Kiểm tra Supabase thật chỉ chạy khi chủ động gọi smoke-test script.
