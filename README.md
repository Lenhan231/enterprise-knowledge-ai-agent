# Enterprise Knowledge AI Agent

Trợ lý phân tích dữ liệu doanh nghiệp bằng tiếng Việt, sử dụng schema `commerce` trên Supabase PostgreSQL.

## Cài đặt

```powershell
uv sync
```

Tạo `.env` và cấu hình một trong hai biến:

```text
SUPABASE_DB_URL=postgresql://...
DATABASE_URL=postgresql://...
```

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

Response tuân theo model `AgentResult`, bao gồm `answer`, `agent`, `evidence`, `data` và `metadata`.
`/api/chat` đi qua `AgentRouter`: câu hỏi số liệu dùng analytics; câu hỏi về nội dung tài liệu dùng knowledge/RAG. Knowledge cần `DATABASE_URL` trỏ tới kho `document_chunks` và `GROQ_API_KEY`. Yêu cầu kết hợp đồng thời tài liệu với SQL hoặc tạo dashboard hiện trả thông báo chưa hỗ trợ.

Với analytics, `data.table` chứa `columns` và `rows`; giao diện hiển thị bảng này. Chỉ số được chọn từ ontology, còn giá trị như `gross_profit = revenue - cogs` được tính trong code. Có thể hỏi cao nhất/thấp nhất, so sánh vùng hoặc các tháng trong năm, chọn vùng hoặc danh mục, và hỏi theo tháng hay năm. Kỳ hợp lệ nhưng không có hàng trả về thông báo “Không có dữ liệu”; yêu cầu thiếu thời gian hoặc tên nhóm không rõ sẽ được yêu cầu làm rõ.

Các truy vấn analytics hiện được hỗ trợ:

- Doanh thu và giá vốn theo tháng.
- Doanh thu theo khu vực theo tháng.
- Tồn kho theo danh mục tại một ngày snapshot.

## Smoke test Supabase

Script sau chạy ba truy vấn thật, kiểm tra `AgentResult`/`Evidence` và xác minh transaction chỉ đọc:

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
