# Sửa Dashboard thiếu driver và Knowledge không ghi được lịch sử — 02/11/2026

## Đọc log VPS

Có hai lỗi độc lập:

1. Dashboard HTTP 503: `create_repository_from_env()` ném `RuntimeError: Install asyncpg before connecting to Supabase PostgreSQL`. Dependency chính bị bỏ asyncpg trong thay đổi trước; code import driver theo kiểu optional nên kiểm tra import main cũ không phát hiện thiếu driver.
2. Knowledge HTTP 200 nhưng application failed, không có cited evidence. Lỗi phụ: insert lịch sử với `status='failed', error_type=NULL`, vi phạm CHECK của `agent_run_events`.

`claim_verification: null` chứng tỏ các request này không chạy audit. Có các HTTP 401 ở `/api/auth/me`, liên quan phiên xác thực chứ không phải thiếu asyncpg/constraint. Không thay auth hoặc tự đăng xuất user trong bản sửa này.

## Ràng buộc database vẫn giữ nguyên

Migration `supabase/migrations/20260926103153_agent_run_monitoring.sql` yêu cầu:

```sql
CHECK ((status = 'completed' AND error_type IS NULL)
    OR (status <> 'completed' AND error_type IS NOT NULL))
```

Code trước đã đặt failed khi `metadata.ok=false`, nhưng chỉ gán error_type từ các report status partial/failed/clarification_required. Knowledge thiếu bằng chứng hoặc audit chặn có thể không có status này, làm error_type còn NULL. Sửa tại handler tạo event; không xóa CHECK, không sửa dữ liệu hoặc migration.

## Giải thích từng dòng thay đổi runtime/config

### `pyproject.toml`

```python
"asyncpg>=0.32.0",
```

Khai báo driver là dependency chính vì API Dashboard/SQL thực sự dùng nó. Không thêm vào riêng optional OCR. `uv.lock` được tạo lại bằng uv 0.12.15, thêm package asyncpg 0.32.0 cùng hash/wheel và hai liên kết dependency/requirement của project. Các dòng URL/hash là dữ liệu lock tự sinh, không có logic thực thi hoặc key.

### `docker/Dockerfile.backend-api`

```dockerfile
RUN python -c "import asyncpg; from core.agents.main import create_app"
```

- `RUN`: bắt build thất bại nếu dependency cần cho API bị thiếu.
- `python -c`: chạy ngay trong venv của image, không gọi dịch vụ ngoài.
- `import asyncpg`: kiểm tra driver trực tiếp; không dựa vào import optional có thể nuốt ImportError trong commerce_repository.
- `from core.agents.main import create_app`: giữ kiểm tra chuỗi import agent/Report/python-docx từ bản sửa trước.

Không mở kết nối database lúc build. Chưa chứng minh biến `ANALYTICS_DATABASE_URL`, quyền reader hoặc query trên VPS hoạt động; cần thử Dashboard sau deploy. Không đổi least-privilege checks hoặc cơ chế query read-only.

### `src/app/agents.py`

```python
if status == "failed" and error_type is None:
    error_type = "InsufficientContext" if result.metadata.get("insufficient_context") else prefix + "Failed"
```

- `status == "failed"`: chỉ bổ sung loại lỗi cho application outcome thất bại; request thành công vẫn có error_type NULL.
- `and error_type is None`: giữ nguyên các mã đã được phân loại như AgentPartial/ReportFailed, không ghi đè chúng.
- `result.metadata.get("insufficient_context")`: đọc trạng thái nguồn do agent đã xác định, không suy từ citation_count bằng 0.
- `"InsufficientContext"`: ghi loại outcome thiếu bằng chứng thay vì NULL. Không đổi câu trả lời hay biến outcome này thành thành công.
- `else prefix + "Failed"`: fallback AgentFailed/ReportFailed cho các trường hợp ok=false khác, bao gồm audit unavailable/rejected nếu chưa có report status cụ thể.

Hai dòng này không sửa retrieval, prompt, reranker, API key, citation hoặc flag verifier. Lỗi ghi lịch sử cũ được bắt rồi ghi log nên không tự làm các request Knowledge trong log thành HTTP 503. Sửa telemetry không bảo đảm mọi câu Knowledge sẽ có đáp án.

## Test regression

`tests/test_agent_monitoring.py` thêm một test gồm sáu outcome:

| Metadata | status event | error_type |
|---|---|---|
| ok=false, insufficient_context=true | failed | InsufficientContext |
| ok=false, audit rejected | failed | AgentFailed |
| ok=false, audit unavailable | failed | AgentFailed |
| ok=false, không có report status | failed | AgentFailed |
| status=partial | failed | AgentPartial |
| ok=true | completed | NULL |

Mỗi ca dựng AgentResult/AsyncMock, gọi handler thật với identity admin giả và patch bước ghi database để không ghi production. Kiểm tra status, error_type, điều kiện tương đương CHECK và metadata câu trả lời không bị đổi. `subTest` giữ tên dữ liệu nếu một nhánh fail; patch được tự khôi phục sau từng ca. Không gọi Groq.

82 test liên quan đã đạt: monitoring, Inventory Dashboard, verifier/benchmark, Knowledge/planner/deadline, latency, orchestration và Report. Đã cài asyncpg 0.32.0 vào venv local, import main/driver thành công; export đúng lệnh prune của Docker vẫn có `asyncpg==0.32.0`. Không có Docker hoặc SSH VPS trong môi trường local; chưa build image/chạy DB analytics từ đây.

## Ghi nhận về Wacom và câu hello

Người dùng cho biết thử hello rồi hỏi thông tin Wacom. Hello trong chế độ Knowledge không phải câu có đáp án tài liệu; outcome thiếu bằng chứng không tự chứng minh lỗi hệ thống. Code hiện không có fallback trò chuyện chung trong Knowledge.

Đã kiểm tra database bằng kết nối chỉ đọc: `Wacom context test` (UPLOAD-7bf63a9a1e194c01bee05f3c7be47f5d) ready, active, 164 chunk; bản `Wacom Product Information` cũ ready nhưng inactive, 171 chunk. Nguồn active vẫn có bảng CTL-4100 ở chunk 38 với Weight 230 g và CTL-4100WL ở chunk 39 với Weight 250 g. Không thay trạng thái hai tài liệu. Chưa biết nguyên văn câu hỏi/answer Wacom và context top-k của request bị thiếu bằng chứng, nên chưa kết luận retrieval lỗi hoặc mất tài liệu.

## Deploy và xác nhận

Dừng benchmark trước khi recreate backend. Không cần migrate database hoặc đổi `.env`/API key.

```bash
git pull --ff-only origin main
docker compose build backend-api
docker compose up -d --no-deps backend-api

docker compose exec -T backend-api python - <<'PY'
import os
import asyncpg
from core.agents.main import create_app
print('asyncpg:', asyncpg.__version__)
print('Agent import: OK')
print('Analytics DB configured:', bool(os.getenv('ANALYTICS_DATABASE_URL')))
PY
```

Sau đó thử Dashboard. Nếu phát sinh thiếu URL/quyền reader thì lấy traceback mới; không thay bằng DATABASE_URL quyền owner để bỏ qua kiểm tra an toàn. Với Knowledge, hỏi câu tự đủ ngữ cảnh như “Wacom Intuos CTL-4100WL nặng bao nhiêu?” thay vì chỉ hello hoặc “nó nặng bao nhiêu?”. Quan sát câu trả lời và log, xác nhận không còn `CheckViolation`.

Nếu gặp HTTP 401 thì đăng nhập lại trên giao diện; nếu còn lặp lại sau đăng nhập, kiểm tra riêng session/auth. Không tự quy lỗi 401 cho verifier.

82 test không phải chứng minh E2E tất cả agent hoặc retrieval Wacom đều đúng. Benchmark verifier 28 ca vẫn chưa hoàn tất vì quota; giữ flag tắt cho tới khi có kết quả chất lượng.
