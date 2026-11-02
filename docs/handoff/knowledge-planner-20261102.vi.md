# Handoff cuối ngày — Knowledge planner — 02/11/2026

## Trạng thái trước bàn giao

- Runtime không còn bộ lọc regex trước planner. Khi `KNOWLEDGE_MULTIQUERY_ENABLED=1`, mọi câu qua planner như trước.
- Sửa tiêu chí planner trong `src/core/prompts/knowledge_search.py`: một nhóm bằng chứng thì một truy vấn; chỉ tách khi có hai nhóm độc lập. Không thay model/retrieval/RBAC/corpus.
- Sáu câu hồi quy: V1–V5 một truy vấn, V6 hai truy vấn. Lặp V3/V4/V6 ba lượt giữ đúng số truy vấn.
- So sánh LLM thật: prompt cũ/mới khớp nhãn thủ công 4/6→6/6; development 19/20→20/20; bộ 10 câu mới 8/10→10/10. Không dùng các tỷ lệ này làm accuracy câu trả lời.
- 43 test liên quan đã đạt trước bàn giao; code và dependency sản phẩm không thay ngoài prompt. Script đo latency sửa xác thực cookie Secure qua Bearer và xác minh /auth/me trước khi đo.
- Các note, fixture và script đo trước đó được đưa cùng đợt bàn giao để không còn phần dở dang trong working tree.

## Deploy chưa thực hiện

Assistant thử SSH BatchMode vào root@147.93.171.214: bị từ chối `Permission denied (publickey,password)`. Không có thông tin xác thực để deploy. Không yêu cầu người dùng cung cấp password/private key qua chat.

Chưa có kết quả retrieval/BGE/generation thật trên VPS sau sửa prompt. Không ghi là đã deploy hay đã chốt kiểm thử production.

## Lệnh cho người có SSH trên VPS

```bash
cd /opt/enterprise-knowledge-ai-agent
git status --short
# Nếu có local changes, dừng kiểm tra; không discard .env hoặc thay đổi server.
git pull --ff-only origin main
nano .env
# Đặt đúng một dòng: KNOWLEDGE_MULTIQUERY_ENABLED=1

docker compose up -d --build --no-deps --force-recreate --wait --wait-timeout 180 backend-api
```

Riêng thay đổi này chỉ cần backend-api. Không yêu cầu rebuild parser hoặc embedding lại. Nếu main chứa thay đổi parser khác, kiểm tra/deploy phần đó riêng.

Xác nhận prompt mới trong container:

```bash
docker compose exec -T backend-api python - <<'PY'
import os
from core.prompts.knowledge_search import SEARCH_PLAN_PROMPT
print('Multiquery:', os.getenv('KNOWLEDGE_MULTIQUERY_ENABLED', '0'))
print('Evidence-topic criteria:', 'Choose searches by EVIDENCE TOPIC' in SEARCH_PLAN_PROMPT)
PY
```

Hai kết quả phải là 1 và True.

## Kiểm tra sau deploy

Chỉ bật bản EN đang thử; không thay quyền/trạng thái trong phép so sánh. ID: UPLOAD-12f3d0901de9444fba9ad23005a0f54e. Route Knowledge, New conversation trước mỗi câu.

- V3: Khoản mua sắm đúng 5 triệu và 5.000.001 đồng khác nhau thế nào về phê duyệt và điều kiện bổ sung?
- V4: Theo Phụ lục C, số lượng bằng 0 có đạt điều kiện của yêu cầu mua sắm không? Còn phải kiểm tra gì khác?
- V6: Theo Phụ lục B và C, khoản mua sắm 80 triệu cần ai duyệt, điều kiện báo giá là gì và đơn mua hàng chỉ được phát hành khi nào?

Kỳ vọng retrieval_total/reranking event count là 1/1/2. V3 đúng hai mức duyệt; V4 số lượng >0, không trùng yêu cầu mở và ghi nhận ngân sách/tuyến tìm nguồn; V6 đủ ba bên duyệt, ba báo giá hoặc lý do chỉ định nguồn ĐÃ DUYỆT, PO phát hành sau duyệt. Xem citation thật, không chỉ application_ok.

Đo lại đầy đủ khi có thời gian:

```bash
docker compose cp scripts/operations/measure_pipeline_latency.py backend-api:/tmp/measure_pipeline_latency.py
docker compose exec -T backend-api python /tmp/measure_pipeline_latency.py \
  --cases vietstyle --passes 3 --pause 15 --no-resource-sampling \
  --output /tmp/vietstyle-latency-criteria-01.json
mkdir -p artifacts/local/knowledge-latency
docker compose cp backend-api:/tmp/vietstyle-latency-criteria-01.json \
  artifacts/local/knowledge-latency/criteria-01.json
```

Dùng output mới nếu đã có file. Script in đủ HTTP/application status và lưu nội dung để chấm; không coi lỗi 401/503 hoặc thiếu thông tin là mẫu trả lời thành công.

## Baseline đã đo (prompt cũ)

Median ba lần, giây:

| Câu | Multiquery OFF | ON prompt cũ |
|---|---:|---:|
| V1 | 21,78 | 23,37 |
| V2 | 21,52 | 22,30 |
| V3 | 19,47 | 40,33 |
| V4 | 23,74 | 43,33 |
| V5 | 20,27 | 20,64 |
| V6 | 21,85 | 39,63 |

ON server ok 18/18; OFF 15/18, V6 thiếu thông tin cả ba lần. Đây không phải điểm đúng nội dung đã chấm độc lập 36 câu. V3/V4/V6 ON cũ đều hai retrieval/rerank; BGE tổng khoảng 28–32 giây. Chưa có latency prompt mới để điền.

## Rollback

Đổi .env thành KNOWLEDGE_MULTIQUERY_ENABLED=0 rồi recreate backend-api; không cần sửa DB hoặc embedding. Rollback tắt cả planner/multiquery, không khôi phục prompt cũ khi giữ flag=1.

## Note đọc lại

- docs/notes/knowledge-planner-criteria-20261102.vi.md
- docs/notes/knowledge-query-gate-trial-20261102.vi.md (lịch sử gate đã gỡ)
- docs/notes/knowledge-latency-stability-check.vi.md
- docs/notes/huy-knowledge-multiquery-explained.vi.md

Còn cần làm sau khi VPS có code: ghi nhận version thực tế, số retrieval, đáp án và latency V3/V4/V6; nếu đạt mới mở rộng lượt đo. Không fine-tune E5 ở bước này.

## Cập nhật sau deploy do Huy xác minh trên VPS — 02/11/2026

Phần trạng thái “Deploy chưa thực hiện” ở trên là tại thời điểm assistant bàn giao; cập nhật này thay thế trạng thái đó. Huy đã build/recreate backend, chạy script mới và gửi kết quả. Assistant vẫn không có quyền SSH; không tự quan sát VPS hoặc xác minh hash image đang chạy.

Một vòng smoke sáu câu EN: HTTP 200 6/6, application_ok 6/6, không lỗi HTTP; median E2E 23,35 giây, min 22,76, max 44,48. Chưa chấm nội dung độc lập cả sáu đáp án mới. File VPS: /tmp/vietstyle-criteria-smoke-01.json.

Đã đọc output nội dung và số events Huy gửi cho ba ca chính:

| Câu | Retrieval / rerank | E2E | Đánh giá nội dung |
|---|---|---:|---|
| V3 | 1 / 1 | 23,53 giây | Đúng ngưỡng 5 triệu / 5.000.001; đúng cấp duyệt và báo giá, xác nhận ngân sách, điều kiện thị trường |
| V4 | 1 / 1 | 23,12 giây | Đúng số lượng >0, không trùng yêu cầu mở, ghi nhận ngân sách và tuyến tìm nguồn |
| V6 | 2 / 2 | 44,48 giây | Đúng ba bên duyệt, ba báo giá hoặc lý do một nguồn ĐÃ DUYỆT; PO sau duyệt và hoàn tất các kiểm tra; citation S1/S4/S2 |

So tham khảo với ON prompt cũ (median 3 lượt): V3 40,33→23,53 giây; V4 43,33→23,12; V6 39,63→44,48. Không báo đây là mức cải thiện ổn định hoặc quan hệ nhân quả đã kiểm soát: bên mới mới có một lượt, trạng thái cache/tải/provider khác nhau.

Kết luận chốt ngày: đã kiểm chứng mục tiêu bỏ lượt tìm/rerank thừa ở V3/V4 mà giữ đủ hai nhóm bằng chứng V6. Có thể giữ cấu hình đang thử, tiếp tục theo dõi; chưa chứng nhận production dưới tải hoặc ổn định dài hạn. Chưa có benchmark đầy đủ sau thay đổi trên VI và bộ câu hỏi rộng hơn.

Trước khi recreate container tiếp, copy report ra host:

```bash
mkdir -p artifacts/local/knowledge-latency
docker compose cp backend-api:/tmp/vietstyle-criteria-smoke-01.json \
  artifacts/local/knowledge-latency/criteria-smoke-01.json
```

Việc tiếp theo ngày sau: lặp ít nhất hai vòng cùng cấu hình mới, chấm đáp án và nguồn; xem median/max theo câu, lỗi 429/timeout, rồi mới cân nhắc đo nhiều người dùng. Chưa cần đổi E5 hay embedding lại.
