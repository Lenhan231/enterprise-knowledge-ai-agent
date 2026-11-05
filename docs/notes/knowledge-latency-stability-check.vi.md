# Kiểm tra latency và tính ổn định Knowledge trên VPS

## Mục tiêu

Dùng đúng sáu câu VietStyle, cùng role admin và trạng thái tài liệu, lặp 3 vòng tuần tự (18 lượt). Mỗi câu có conversation_id mới. Nghỉ 15 giây giữa request. Không gọi API upload/remove hay cập nhật quyền. Chat vẫn tạo bản ghi monitoring như bình thường; provider có thể tính phí/quota.

Đây là kiểm tra phản hồi và chất lượng lặp lại với concurrency=1, không phải kiểm tra chịu tải. Median/min/max là thống kê mô tả trên mẫu nhỏ, chưa phải SLA hay bằng chứng ổn định production.

## Trước khi đo

- Chỉ bật EN, tắt VI cho lượt đo EN; không thay trạng thái trong lúc chạy.
- Tránh upload/OCR hoặc test khác cùng VPS trong thời gian đo. Ghi lại nếu có người khác đang dùng.
- Xác nhận container dùng code mới và `KNOWLEDGE_MULTIQUERY_ENABLED=1`.
- Ghi lại `git rev-parse HEAD`, cấu hình VPS và việc model đã warm hay vừa khởi động.
- Không coi mọi câu ở first_pass là cold. Các vòng sau hưởng cache bản dịch; đó là điều kiện phải ghi trong report.

## Đưa script mới lên VPS (không cần build backend)

Script đang nằm trên máy Huy, chưa commit/push trong task đo này. Từ terminal laptop, tại thư mục repo:

```bash
scp scripts/operations/measure_pipeline_latency.py root@147.93.171.214:/tmp/measure_pipeline_latency.py
```

Trên VPS:

```bash
cd /opt/enterprise-knowledge-ai-agent
docker compose cp /tmp/measure_pipeline_latency.py backend-api:/tmp/measure_pipeline_latency.py
docker compose exec -T backend-api python /tmp/measure_pipeline_latency.py \
  --cases vietstyle --passes 3 --pause 15 --no-resource-sampling \
  --output /tmp/vietstyle-latency-on-01.json
```

Script dùng tài khoản demo admin đã có trong môi trường container để đăng nhập API nội bộ, không in password/token. Không cần đi qua Vercel/ngrok. HTTP timing đo đường vào API tại localhost, không bao gồm internet/browser/tunnel.

Chạy khoảng 10–20 phút tùy latency/quota. Script in một dòng sau mỗi câu và ghi JSON sau mỗi lượt. Exit code 1 nghĩa có request lỗi, thiếu latency hoặc server báo `ok != true`; report vẫn được lưu. Đó là kết quả kiểm thử, không tự retry để che lỗi.

Đổi tên output cho mỗi lần chạy, script từ chối ghi đè file cũ. Ctrl+C dừng chạy; report vẫn được hoàn thiện qua finally nếu tiến trình không bị kill cưỡng bức.

Lấy report về thư mục VPS:

```bash
mkdir -p artifacts/local/knowledge-latency
docker compose cp backend-api:/tmp/vietstyle-latency-on-01.json \
  artifacts/local/knowledge-latency/vietstyle-latency-on-01.json
```

Lưu ý file trong /tmp container mất khi container bị recreate; copy report ra trước khi thay env.

## Đọc kết quả

JSON có:
- `summary`: từng vòng, số request, HTTP 200, application_ok, lỗi và latency median/min/max.
- `by_case`: cùng thống kê cho từng câu V1–V6 qua các vòng.
- `results`: câu hỏi, câu trả lời đầy đủ, bằng chứng, thời gian HTTP, timing từng stage.
- `resource_samples`: để trống khi `--no-resource-sampling`; lượt chạy này không thu CPU/RAM.

Chấm thủ công câu trả lời và nguồn bằng `vietstyle-en-vi-test-questions.vi.md`. HTTP 200 hay application_ok=true không tự chứng minh đáp án đúng.

Cần ghi ít nhất:
1. Bao nhiêu lượt HTTP thành công / 18, bao nhiêu timeout/503 hoặc application_ok=false.
2. Mỗi câu đúng và đủ bao nhiêu lần / 3; giữ các câu sai/thiếu, không bỏ khỏi mẫu.
3. Median và max từng câu; tách câu 6 khỏi câu đơn.
4. Thời gian planner và tổng rerank từng request. Stage rerank cộng hai lượt; stage retrieval_total bao hàm các bước con, không cộng chồng để suy ra E2E.
5. Nếu planner null trong lượt bật, kiểm tra version/flag. Planner có thời gian chưa chứng minh đã tách; một câu giữ nguyên vẫn gọi planner. Kiểm tra log `Knowledge search plan fallback` khi cần tìm lỗi 429/JSON.
6. Lưu log server cùng khung giờ, nhưng không chia sẻ file chứa secrets.

## So sánh ON/OFF sau lượt đầu

Nếu lượt ON không có lỗi hạ tầng/quota nghiêm trọng, có thể đo cùng script khi đặt flag=0, recreate backend rồi chạy output `vietstyle-latency-off-01.json`. Không chạy hai cấu hình đồng thời và không thay dữ liệu. Recreate làm mất cache trong backend, nên phải ghi nhận hiệu ứng cache/warm-up khi so sánh; tốt hơn dùng các vòng warm và lặp đổi thứ tự ON/OFF trong lần đo sau.

Công tắc rollback chỉ bỏ planner và multiquery; không sửa quota đã cạn. Nếu có nhiều lỗi 429 hoặc timeout, dừng và phân tích trước khi thử concurrency=2.

## Trạng thái tại lúc chuẩn bị

Đã kiểm tra script bằng HTTP giả lập: chạy đủ vòng/câu, fresh sessions, ghi đúng response/latency và phân biệt HTTP 200 với application_ok=false. Chưa chạy bài đo 18 request trên VPS do assistant không có kết nối SSH dùng được. Chưa có kết quả latency mới hoặc kết luận chất lượng từ bài đo này.

## Sửa xác thực sau lượt chạy đầu

Lượt đầu trả toàn HTTP 401 nên không dùng làm latency Knowledge. Script ban đầu chỉ dựa vào cookie; cookie Secure không được HTTP client gửi qua localhost HTTP. Script mới lấy session do login cấp để dùng Bearer (backend đã hỗ trợ), xác minh `/api/auth/me` là admin trước khi đo và dừng ngay nếu gặp 401/403. Không tắt AUTH_COOKIE_SECURE, không in/lưu token. Chép lại script vào container và dùng output mới, ví dụ `/tmp/vietstyle-latency-on-02.json`. Ba test gồm cookie Secure và đăng nhập thất bại đạt. Nguyên nhân cookie Secure cần xác nhận với cấu hình thực tế nếu 401 vẫn còn sau sửa.
