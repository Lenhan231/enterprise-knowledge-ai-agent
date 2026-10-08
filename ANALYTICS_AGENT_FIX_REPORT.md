# Báo cáo hoàn thiện Analytics Agent

**Ngày kiểm tra:** 2026-10-08 (Asia/Saigon)  
**Phạm vi:** `SQLAnalyticsAgent`, `AnalyticsAgent`, `BaseAgent`, `AgentRouter`, metric ontology và luồng Supabase chỉ đọc.

## 1. Kết luận

Các vấn đề được nêu trong phản hồi review đã được xử lý:

| Vấn đề | Trạng thái | Cách xử lý |
|---|---|---|
| Không đọc `AgentRequest.question` | Hoàn tất | `_query_text()` ưu tiên field `question`. |
| Agent trả payload không đúng contract | Hoàn tất | Payload nội bộ vẫn là `dict`; biên public map sang `AgentResult` và `Evidence` dùng chung. |
| Router không await agent async | Hoàn tất | `AgentRouter.route()` là async, await kết quả khi cần và validate bằng `AgentResult`. |
| Metric ontology chưa được dùng | Hoàn tất | `_resolve_operation()` dùng `resolve_metric_names()` cho metric; keyword chỉ còn dùng nhận diện dimension như khu vực/danh mục. |
| Agent không theo `BaseAgent` | Hoàn tất | `SQLAnalyticsAgent`, `AnalyticsAgent` kế thừa `BaseAgent`; contract `run()` và `close()` đều async. |
| Thiếu test nghiệp vụ và lỗi DB | Hoàn tất | Đã thêm test cho ba query chính, thiếu ngày, metric không hỗ trợ, lỗi database, lifecycle và E2E router. |
| Output còn lẫn tiếng Anh | Hoàn tất trong luồng này | Câu trả lời, findings, recommendations và limitations của analytics đã được Việt hóa. Tên field API vẫn giữ tiếng Anh để tránh phá contract. |

## 2. Thiết kế sau thay đổi

```text
AgentRequest(question)
        |
        v
AgentRouter.route() [async]
        |
        v
AnalyticsAgent.run() -> AgentResult(agent="analytics")
        |
        v
SQLAnalyticsAgent.run_payload() -> dict nội bộ
        |
        v
CommerceRepository -> Supabase PostgreSQL [read-only]
        |
        v
payload_to_agent_result()
        |
        +-> AgentResult
        +-> Evidence(source_type="database")
```

Payload `dict` chỉ tồn tại trong quá trình ghép kết quả SQL và diễn giải. Model không bị định nghĩa trùng trong hai agent; cả hai đều dùng `src/core/models/agents.py` làm contract chuẩn.

## 3. Chi tiết thay đổi và lý do

### 3.1 Mapping payload vào model chung

`payload_to_agent_result()` thực hiện:

- map từng evidence thành `Evidence`;
- mặc định `source_type="database"`;
- sinh citation ID ổn định `S1`, `S2`, ... khi payload chưa có;
- chuyển `period` vào `Evidence.metadata`;
- giữ `rows`, `operation`, `metrics`, `findings`, `recommendations` và `limitations` trong `AgentResult.data`;
- giữ metadata nguồn, tiền tệ, trạng thái `ok` và loại lỗi;
- tạo câu trả lời tiếng Việt từ `answer` hoặc `findings`.

Kết quả SQL trực tiếp dùng `agent="sql_analytics"`. Kết quả đã qua lớp diễn giải dùng `agent="analytics"`.

### 3.2 Contract async thống nhất

- `BaseAgent.run()` và `BaseAgent.close()` đổi thành async.
- `KnowledgeAgent` dùng `asyncio.to_thread()` cho RAG sync để không chặn event loop.
- Router await agent async, đồng thời vẫn chấp nhận agent sync tạm thời để các adapter cũ không vỡ đột ngột.
- Script đánh giá route gọi `await router.route(...)` qua một entry point `asyncio.run()`.

### 3.3 Metric ontology

SQL agent không còn tự nhận diện metric bằng một danh sách từ khóa rời rạc. Nó dùng `resolve_metric_names()` để map alias về metric chuẩn.

Các ví dụ đã được kiểm thử:

| Câu hỏi | Metric chuẩn | Operation |
|---|---|---|
| `Giá vốn hàng bán tháng 12/2022` | `cogs` | `revenue_cogs_by_month` |
| `Doanh thu theo khu vực tháng 12/2022` | `regional_revenue` | `revenue_by_region` |
| `Số ngày đủ hàng theo danh mục tại ngày 2022-12-31` | `days_of_supply` | `inventory_by_category` |
| `Tỷ lệ bán hết theo danh mục tại ngày 2022-12-31` | `sell_through_rate` | `inventory_by_category` |

Alias `inventory` cũng được thêm vào metric `stock_on_hand` để câu hỏi tiếng Anh hiện có không bị mất tương thích.

### 3.4 Xử lý lỗi database

Lỗi repository không còn thoát thẳng ra ngoài. Agent trả `AgentResult` an toàn với:

- `metadata.ok = false`;
- `metadata.error_type` chỉ chứa tên loại exception;
- câu trả lời tiếng Việt yêu cầu thử lại;
- không đưa nội dung exception hoặc thông tin kết nối vào câu trả lời.

### 3.5 Lifecycle

- `SQLAnalyticsAgent.close()` đóng pool của `CommerceRepository`.
- `AnalyticsAgent.close()` ủy quyền cho SQL agent.
- `KnowledgeAgent.close()` đóng RAG service qua thread worker.

## 4. Kiểm thử

### 4.1 Test tập trung

Lệnh:

```powershell
.venv\Scripts\python.exe -m unittest tests.test_analytics_agents tests.test_agents tests.test_agent_route_evaluation
```

Kết quả:

```text
Ran 28 tests
OK
```

Các trường hợp chính:

1. Doanh thu/giá vốn tháng 12/2022.
2. Doanh thu theo khu vực tháng 12/2022.
3. Tồn kho theo danh mục tại ngày 2022-12-31.
4. Thiếu thời gian.
5. Metric chưa hỗ trợ.
6. Database phát sinh exception.
7. Mapping `dict` sang `AgentResult`/`Evidence`.
8. Đóng repository qua agent.
9. E2E `router -> analytics -> SQL -> repository giả -> AgentResult`.

### 4.2 Compile

```powershell
.venv\Scripts\python.exe -m compileall -q src tests scripts
```

Kết quả: thành công, không có lỗi syntax/import trong phạm vi compile.

### 4.3 Toàn bộ test suite

```powershell
.venv\Scripts\python.exe -m unittest discover -s tests -p 'test_*.py'
```

Kết quả:

```text
Ran 99 tests
98 passed, 1 failed
```

Failure còn lại không thuộc thay đổi analytics:

```text
test_retrieval_callers.RetrievalCallersTest.test_script_consumes_typed_results_and_closes_service
```

Đây là mismatch đã có giữa test Apple retrieval và `scripts/check_apple_retrieval.py`; test kỳ vọng dữ liệu/cấu trúc cũ và trả exit code `1`. Không sửa trong thay đổi này để tránh mở rộng phạm vi sang corpus Apple.

## 5. Smoke test Supabase thật

Luồng sau đã chạy với kết nối PostgreSQL từ `.env` và repository chỉ đọc:

```text
AgentRequest
  -> AgentRouter
  -> AnalyticsAgent
  -> SQLAnalyticsAgent
  -> CommerceRepository
  -> Supabase
  -> AgentResult
```

Output đã rút gọn:

```python
{
    "model_type": "AgentResult",
    "destination": "analytics",
    "agent": "analytics",
    "ok": True,
    "operation": "revenue_cogs_by_month",
    "row_count": 1,
    "evidence_count": 1,
    "answer": "2022-12-01: lợi nhuận gộp âm 1034737.24.",
}
```

Không có migration, insert, update hoặc delete nào được thực hiện.

## 6. Cách kiểm tra thủ công

### Kiểm tra SQL agent trực tiếp

```python
result = await sql_agent.run(
    AgentRequest(question="Doanh thu và giá vốn tháng 12/2022")
)

assert isinstance(result, AgentResult)
assert result.agent == "sql_analytics"
assert result.data["operation"] == "revenue_cogs_by_month"
assert result.evidence[0].source_type == "database"
```

### Kiểm tra analytics agent

```python
result = await analytics_agent.run(
    AgentRequest(question="Doanh thu và giá vốn tháng 12/2022")
)

assert result.agent == "analytics"
assert "gross_profit" in result.data["metrics"][0]
assert "lợi nhuận gộp" in result.answer
```

### Kiểm tra router

```python
result = await router.route(
    AgentRequest(question="Doanh thu theo khu vực tháng 12/2022")
)

assert router.last_destination == "analytics"
assert isinstance(result, AgentResult)
```

## 7. Phạm vi chưa có implementation

Các vấn đề trong review analytics đã được xử lý. Tuy nhiên repository hiện chưa có implementation riêng cho `HybridAgent`, `DashboardAgent` và `ReportAgent`; router chỉ có các điểm nối cho chúng. Vì vậy không nên diễn đạt rằng mọi loại agent của toàn sản phẩm đã hoàn thiện. Kết luận chính xác là:

> `KnowledgeAgent`, `SQLAnalyticsAgent`, `AnalyticsAgent` và luồng async router liên quan đã có contract hoạt động; các agent hybrid/dashboard/report vẫn cần implementation riêng nếu sản phẩm yêu cầu chạy thật.

## 8. Cập nhật API chat và smoke test Supabase — 2026-10-08

### Dọn test dataset cũ

- Loại test gọi script retrieval của corpus cũ.
- Thay các ID và expected facts trong test QA bằng số liệu `commerce` tháng 12/2022.
- Thay `data/evaluation/vinamilk_qa_cases.json` bằng `data/evaluation/commerce_analytics_cases.json`.
- Giữ các fixture retrieval tổng quát vì chúng không gắn với thương hiệu hoặc dataset cũ.
- Toàn bộ thư mục `tests/` không còn chuỗi nhận diện dataset Apple/Vinamilk.

### Smoke test Supabase tái lập

Script mới: `scripts/smoke_test_supabase_analytics.py`.

Script xác minh:

1. `commerce.sales` tháng 12/2022: revenue `52454936.20`, COGS `53489673.44`.
2. Doanh thu khu vực East tháng 12/2022: `14079268.92`.
3. Inventory category Casual tại `2022-12-31`: 40 SKU quan sát, 31 SKU hết hàng.
4. Mỗi case trả `AgentResult` cùng `Evidence(source_type="database")` hợp lệ.
5. Transaction báo `transaction_read_only=on` và chặn write probe với SQLSTATE `25006`.

Báo cáo live được ghi tại `artifacts/smoke/supabase_analytics_smoke.json`; kết quả `3/3` case pass.

### FastAPI `/api/chat`

- Xóa `/api/dashboard` chứa dữ liệu hard-code và endpoint upload placeholder.
- Thêm app factory để production dùng Supabase thật còn test inject agent giả.
- Thêm `POST /api/chat` với response model `AgentResult`.
- Chặn câu hỏi rỗng, câu hỏi quá 2.000 ký tự, field lạ và metadata quá 20 trường.
- Lỗi nội bộ trả HTTP 503 bằng thông báo tiếng Việt và không lộ exception.
- Lifespan đóng asyncpg pool khi ứng dụng dừng.
- Thay dashboard cũ bằng giao diện chat tiếng Việt gọi API thật; model output được render bằng `textContent`.

### Kết quả xác minh cuối

```text
Live Supabase smoke: 3/3 pass
Read-only write probe: blocked, SQLSTATE 25006
Live POST /api/chat: HTTP 200, analytics, commerce.sales evidence
Python compileall: pass
JavaScript syntax check: pass
Full unittest suite: 103/103 pass
```

