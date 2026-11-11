# Knowledge: timeout, phép đo latency và lưu benchmark — 02/11/2026

## Vấn đề đã quan sát

Đợt kiểm thử dự kiến 60 request dừng sau 30 request: 28 thành công, 2 HTTP 503, đều ở V6 (câu tổng hợp Phụ lục B và C). Log trên host còn, JSON trong `/tmp` của container cũ không còn.

Lịch sử database ghi nhận:

- 11:44:19 UTC: `TimeoutError`, handler 60.017 ms. Luồng Knowledge chờ `run_sync()` tối đa 60 giây; V6 thường cần hai lượt retrieval/reranking và đã mất khoảng 48–59 giây ở các request thành công.
- 12:00:29 UTC: `RemoteDisconnected`, handler 42.648 ms. Container backend mới được tạo lúc 12:00:31 UTC. Thời điểm sát nhau gợi ý ảnh hưởng deploy, nhưng không còn traceback cũ để xác định bên nào đóng kết nối.
- Các `RateLimitError` trước đó thuộc đợt hết quota Groq, không phải hai lỗi này.

Một request V2 trước đó mất 93,02 giây HTTP trong khi handler chỉ 27,87 giây. Bản cũ đo handler trước khi chờ ghi lịch sử database; chưa đủ bằng chứng quy toàn bộ phần chênh lệch cho database.

## Thay đổi và lý do

### Giới hạn chờ Knowledge

`src/core/agents/knowledge_agent.py` đặt deadline cho phần sinh câu trả lời: 90 giây khi `KNOWLEDGE_MULTIQUERY_ENABLED=1`, 60 giây khi tắt. Đây là giới hạn theo chế độ multiquery, không phải chỉ những câu được planner tách thành hai nhánh. Deadline ngắn hơn từ luồng cha vẫn được giữ.

`src/core/agents/runtime.py` thêm tham số nội bộ `_timeout` vào `run_sync()`, mặc định 60 giây. Tham số này điều khiển thời gian chờ, không truyền xuống hàm RAG. Các caller khác giữ mặc định cũ. Deadline được truyền vào worker và khôi phục ở caller cả khi lỗi.

Tăng trần chờ tránh cắt ngang request V6 chỉ vì hơi vượt 60 giây; không làm retrieval hoặc reranker nhanh hơn. Planner, số candidate, top-k, thứ tự hai nhánh, quyền truy cập và cách chọn nguồn giữ nguyên.

### Đo phần chờ ghi lịch sử

`src/app/agents.py` và `src/core/latency.py` thêm:

- `telemetry_persistence`: thời gian chờ ghi lịch sử, gồm hàng đợi thread, kết nối database, ghi và đóng kết nối.
- `request_total_ms`: giữ nghĩa cũ, handler trước ghi lịch sử, không gồm xác thực.
- `response_ready_ms`: từ lúc vào handler đến sau ghi lịch sử; chưa gồm xác thực, serialize và truyền HTTP.
- `http_elapsed_ms`: script đo từ client, gồm toàn bộ request HTTP, vẫn là mốc đánh giá trải nghiệm thực tế.

Log `agent_latency` được ghi sau bước telemetry, cả khi agent thành công hoặc lỗi. `_record_agent_run` vẫn bắt lỗi database như trước, dữ liệu monitoring vẫn lưu thời gian handler để không thay nghĩa thống kê cũ. Chưa chuyển ghi lịch sử sang background hoặc đặt timeout database mới.

### Giữ kết quả khi thay container

`docker-compose.yml` bind-mount riêng `./artifacts/local/knowledge-latency` trên host vào `/benchmarks` trong backend. Benchmark phải dùng `--output /benchmarks/...json`; đường dẫn `/tmp` vẫn mất khi thay container.

`scripts/operations/measure_pipeline_latency.py` ghi checkpoint sau mỗi request bằng file tạm quyền `0600`, rồi thay file JSON bằng thao tác rename trên cùng filesystem. Nếu tiến trình bị ngắt lúc ghi file tạm, checkpoint trước đó vẫn đọc được. Lần ghi cuối cập nhật summary; nếu container bị dừng đột ngột có thể chỉ có checkpoint chưa có summary. Đây không phải resume tự động và không bảo đảm chịu lỗi mất điện/storage.

Thư mục kết quả vẫn được Git ignore; không đưa câu trả lời hoặc API key vào commit. Không cần đổi `.env` cho bản sửa này; giữ `KNOWLEDGE_MULTIQUERY_ENABLED=1` để đo multiquery.

## Kiểm tra local

56 test liên quan timeout, Knowledge, planner, orchestration, telemetry, benchmark và Report đã đạt. Test mới kiểm tra giới hạn 90/60, không vượt deadline cha, khôi phục context sau lỗi, giữ quyền truyền xuống RAG, đo telemetry cả khi agent lỗi, và checkpoint riêng tư không làm hỏng báo cáo cũ khi ghi thất bại.

Chưa build image hoặc benchmark E2E trên VPS từ máy local; không có Docker/SSH VPS tại môi trường này. Phải xác nhận mount, import và smoke sau deploy.

## Deploy trên VPS

Thống nhất không deploy trong lúc benchmark. Không chạy `docker compose down` hoặc build lại các dịch vụ OCR/reranker cho bản sửa này.

```bash
cd /opt/enterprise-knowledge-ai-agent
mkdir -p artifacts/local/knowledge-latency
git pull --ff-only origin main
docker compose build backend-api
docker compose up -d --no-deps backend-api

docker compose exec -T backend-api python - <<'PY'
import os
from pathlib import Path
from core.agents.main import create_app
assert Path('/benchmarks').is_dir(), 'Missing host benchmark mount'
print('Agent import: OK')
print('Multiquery:', os.getenv('KNOWLEDGE_MULTIQUERY_ENABLED', '0'))
PY

docker compose cp scripts/operations/measure_pipeline_latency.py backend-api:/tmp/measure_pipeline_latency.py
```

Smoke trước; nếu tên file đã có, chọn tên mới, không xóa kết quả cũ:

```bash
set -o pipefail
docker compose exec -T backend-api python -u /tmp/measure_pipeline_latency.py \
  --cases vietstyle --passes 1 --pause 15 --no-resource-sampling \
  --output /benchmarks/stability-fix-smoke-01.json \
  | tee artifacts/local/knowledge-latency/stability-fix-smoke-01.log
```

Xác nhận JSON đã ở host, các phép đo mới có dữ liệu:

```bash
python3 - <<'PY'
import json
from pathlib import Path
p = Path('artifacts/local/knowledge-latency/stability-fix-smoke-01.json')
r = json.loads(p.read_text())
for row in r['results']:
    t = row.get('latency') or {}
    stages = t.get('stages_ms') or {}
    print(row['case_id'], 'HTTP', row.get('status'),
          'http_ms', row['http_elapsed_ms'],
          'handler_ms', t.get('request_total_ms'),
          'telemetry_ms', stages.get('telemetry_persistence'),
          'response_ready_ms', t.get('response_ready_ms'))
PY
```

Sau khi smoke đạt, chạy 10 lượt tuần tự (không chạy đồng thời với smoke):

```bash
docker compose exec -T backend-api python -u /tmp/measure_pipeline_latency.py \
  --cases vietstyle --passes 10 --pause 15 --no-resource-sampling \
  --output /benchmarks/stability-fix-repeat-01.json \
  | tee artifacts/local/knowledge-latency/stability-fix-repeat-01.log
```

Giữ terminal SSH mở. Nếu có 503, lưu log ngay ở terminal khác trước khi thay container:

```bash
docker compose logs --since 2h backend-api > artifacts/local/knowledge-latency/stability-fix-backend.log
```

Nếu hết quota Groq thì dừng kiểm thử, giữ kết quả và đánh dấu nguyên nhân bên ngoài; không dùng request lỗi như mẫu latency thành công. 60 request có thể tiêu thụ đáng kể quota ngày. Không tự retry cả benchmark hoặc đổi model giữa đợt.

## Cách đánh giá sau deploy

Kiểm tra đủ 60 request, HTTP và application status, nội dung/citation V6, số nhánh qua events, latency từng câu qua các lượt, stage telemetry và HTTP ngoài handler. Không cộng các stage lồng nhau thành tổng. `application_ok` và số citation không tự chứng minh trả lời đúng.

Bản sửa xử lý giới hạn chờ và khả năng quan sát, chưa tối ưu CPU/reranking, chưa chứng minh chịu tải nhiều người dùng hoặc vận hành cả ngày. Nếu vẫn chậm, dùng dữ liệu mới để chọn tối ưu reranker, không giảm candidate tùy tiện vì có thể mất bằng chứng.

## Rollback

Tắt `KNOWLEDGE_MULTIQUERY_ENABLED=0` rồi tạo lại backend sẽ quay về truy vấn gốc và giới hạn Knowledge 60 giây, nhưng có thể tái hiện thiếu bằng chứng ở V6. Không tắt mount để tránh mất cách lưu kết quả. Nếu cần rollback code, dùng revert commit bản sửa sau khi kết thúc benchmark; không reset/xóa thay đổi của nhóm hoặc `.env`.
