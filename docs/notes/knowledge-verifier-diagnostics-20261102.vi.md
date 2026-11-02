# Chẩn đoán ba ca verifier — không thay quyết định

## Baseline cần giữ

VPS đã hoàn tất 28 ca trong `artifacts/local/knowledge-latency/claim-verifier-full-01.jsonl`: 9/11 câu đúng được giữ, 16/17 câu sai bị chặn, R02 lọt qua, F10 bị chặn nhầm, P03 unavailable vì ValueError. Không ghi đè file, đổi nhãn hoặc chọn kết quả đẹp hơn để thay baseline này. Dữ liệu vẫn là bộ chẩn đoán phát triển tự soạn, chưa được review độc lập.

Đã đọc lại ba ca: F10 đúng với nguồn (lợi nhuận sau thuế hợp nhất 2024 = 20 tỷ); P03 là áp dụng đúng các ngưỡng và ngoại lệ trong bảng; R02 chứa phép tính sai `90 + 15 = 95`. Chưa biết ValueError của P03 thuộc coverage, citation hay quote vì bản cũ chỉ giữ tên exception.

## Phạm vi bản sửa

Chỉ đổi script benchmark và test/note. Không đổi prompt, validator production, câu hỏi, nhãn expected, fixture, model, temperature, timeout, số output token, quyền truy cập hoặc cách trả lời trên web. Không thêm lượt LLM để sinh lời giải thích sau kết quả.

Script dùng subclass nhỏ của GroqProvider để giữ nguyên chuỗi model trả về, rồi chuyển đúng chuỗi đó về verifier. Sau khi verifier đã quyết định, script chạy lại parser/validate_review thuần code để lấy mã lỗi cụ thể. Đây không phải lượt LLM thứ hai và không ghi đè quyết định đầu tiên.

JSONL bổ sung:

- `audit_raw`: JSON/fenced JSON nguyên văn của model, chỉ trong file output 0600, không in lên terminal mặc định. Có thể chứa claim sai đang được kiểm tra; không coi nó là đáp án cho user.
- `validation_error`: invalid_review_schema, incomplete_draft_coverage, invalid_claim_citations, missing_cited_source_quotes, fabricated_source_quote, hoặc null. Verdict contradicted/insufficient hợp lệ không phải lỗi parser nên trường này null.
- Manifest `case_ids`: những ca thực sự được chọn, cùng hash fixture/prompt như trước.

`--case-ids F10 P03 R02` chọn đúng ba ca theo thứ tự trong fixture. ID không tồn tại thì dừng trước khi khởi tạo provider. `--limit` nếu có vẫn áp dụng sau bước chọn ca.

Nếu model trả lại kết quả khác ở lượt mới, đó là độ biến động qua các lần gọi, không phải chứng cứ đã sửa được lỗi cũ. Raw của lượt cũ không thể khôi phục từ summary. Một verdict/quote không tự cho biết lý do nội bộ model; không suy đoán chain-of-thought.

## Giải thích từng dòng script mới/thay đổi

Số dòng dưới đây thuộc `scripts/agents/benchmark_knowledge_verifier.py` của bản chẩn đoán. Các dòng không liệt kê giữ nguyên logic cũ.

| Dòng | Giải thích |
|---:|---|
| 15 | Import ValidationError của Pydantic để phân biệt lỗi schema với lỗi liên kết bằng chứng. |
| 18 | Import schema AnswerReview và validate_review có sẵn, bên cạnh verify_answer; không tạo validator khác. |
| 22 | AuditRecorder kế thừa đúng GroqProvider, chỉ dùng trong công cụ benchmark. |
| 23 | Override generate và nhận nguyên prompt/keyword options. |
| 24 | Xóa raw cũ trước mỗi lần gọi để lỗi lần sau không dùng nhầm dữ liệu lần trước. |
| 25 | Gọi implementation gốc đúng một lần, giữ nguyên key selection/failover và ngân sách. |
| 26 | Lưu nguyên chuỗi response, chưa sửa fence hoặc JSON. |
| 27 | Trả chính chuỗi đó cho verifier, không sửa verdict hoặc draft. |
| 30 | Hàm replay thuần code nhận raw, draft và đúng nguồn của ca. |
| 31 | Nhận biết trường hợp không gọi được model hoặc không có raw. |
| 32 | Không tự tạo lỗi validator khi chưa có review để kiểm tra. |
| 33 | Bắt các lỗi schema/validation cục bộ. |
| 34 | Ghi rõ replay không có LLM call và không đổi outcome. |
| 35 | Dùng đúng regex fence của production hiện tại; không tìm JSON trong prose tùy ý. |
| 36 | Parse cùng AnswerReview, bóc đúng một fence nếu có. |
| 37 | Chạy cùng validate_review để kiểm tra coverage/citation/quote. |
| 38 | Nhận riêng lỗi schema JSON/kiểu dữ liệu. |
| 39 | Ghi mã invalid_review_schema, không dump exception chứa toàn bộ nội dung. |
| 40 | Nhận ValueError do validate_review ném với mã cố định. |
| 41 | Giữ mã cụ thể thay vì tên chung ValueError; hàm replay không gọi provider nên không lấy error message API. |
| 42 | Review hợp lệ thì không có lỗi validation; không đồng nghĩa verdict supported. |
| 49 | Thêm selector nhiều ID cho CLI; không ảnh hưởng API web. |
| 63 | Kiểm tra tất cả ID yêu cầu có trong fixture. |
| 64 | Báo ID sai trước khi gửi bất kỳ request nào. |
| 65 | Lọc các ca, không thay nội dung hoặc thứ tự gốc. |
| 66 | Áp dụng limit sau lọc, mặc định chạy tất cả ca đã chọn. |
| 69 | Dùng AuditRecorder với key đã chọn hoặc pool cũ; không đổi env backend. |
| 74 | Lưu danh sách ca trong manifest để phân biệt chạy subset với chạy đủ bộ. |
| 83 | Xóa audit_raw trước mỗi ca, cả khi verifier sẽ bỏ qua LLM do input/deadline. |
| 88 | Ghi usage và raw vào record của chính ca đó. |
| 89 | Ghi lỗi replay riêng; không thay outcome.status/reason đã nhận từ verifier. |
| 95 | Terminal bỏ trường audit_raw để tránh trộn raw dài với tiến độ; file vẫn giữ đủ. |

Replay cố ý nằm trong script để có thể copy chạy với image hiện tại, không bắt deploy lại API chỉ để chẩn đoán. Test kiểm tra fence/parse giống production; nếu parser production thay đổi sau này, cần cập nhật replay và test cùng lúc.

## Test trước push

90 test liên quan đạt, không gọi Groq thật. Test mới bảo đảm:

- AuditRecorder trả nguyên response, giữ raw, xóa raw khi lượt sau lỗi, không tự retry.
- Replay nhận đúng lỗi schema, coverage, thiếu quote và quote bịa; JSON/fenced JSON hợp lệ vẫn giữ kết quả.
- Selector chỉ chạy ca được chọn, raw được lưu trong file và không in ở tiến độ; ID lạ không tạo provider.
- Các regression cũ về quyền file, quota, key selection, chạy script từ /tmp và pipeline Knowledge/Report vẫn đạt.

Thêm bốn test `tests/test_groq_key_failover.py` đã chạy lúc kiểm tra giả thuyết fallback: mock key 1 trả 429 rồi key 2 thành công; ưu tiên key 2 ở lượt tiếp; không gọi HTTP khi cả hai cooldown; thử lại key 2 sau cooldown; key rỗng/trùng không tạo client mới. Đây là test logic, không kết luận nguyên nhân lỗi quota thực tế. Không đổi code provider.

Không build Docker, gọi LLM hay benchmark VPS ở local trong bản sửa chẩn đoán này.

## Cách chạy trên VPS — không build/restart

```bash
git pull --ff-only origin main
docker compose cp scripts/agents/benchmark_knowledge_verifier.py backend-api:/tmp/benchmark_knowledge_verifier.py

docker compose exec -T backend-api python -u /tmp/benchmark_knowledge_verifier.py \
  --cases /tmp/knowledge_claim_verification_cases.json \
  --api-key-env GROQ_API_KEY_2 \
  --case-ids F10 P03 R02 --pause 20 \
  --output /benchmarks/claim-verifier-three-cases-01.jsonl
```

Nếu fixture /tmp mất do đã recreate, copy lại từ `data/evaluation/knowledge_claim_verification_cases.json`. Giữ verifier web tắt. Dùng tên output mới nếu file đã tồn tại.

Đọc raw trên host sau khi chạy (bộ hiện tại là nguồn giả lập, không chứa API key):

```bash
python3 - <<'PY'
import json
from pathlib import Path
p = Path('artifacts/local/knowledge-latency/claim-verifier-three-cases-01.jsonl')
for line in p.read_text().splitlines():
    row = json.loads(line)
    if 'id' in row:
        print('\nCASE', row['id'], '|', row['status'], '|', row.get('validation_error'))
        print(row.get('audit_raw'))
PY
```

Với bộ tài liệu thật sau này, raw có thể chứa nội dung nguồn; giữ file 0600 và chỉ chia sẻ phần cần thiết. Không thêm raw vào API metadata, log production hoặc commit Git.
