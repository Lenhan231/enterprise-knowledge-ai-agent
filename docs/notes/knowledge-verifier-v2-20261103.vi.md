# Knowledge verifier v2 — 03/11/2026

## Phạm vi đã thống nhất

Sửa ba vấn đề quan sát được trong lượt VPS `claim-verifier-full-01.jsonl`, giữ nguyên file đó và bộ 28 ca làm baseline:

| Ca | v1 | Bằng chứng |
|---|---|---|
| F10 | Chặn nhầm câu đúng | Source và claim cùng nêu profit after tax 2024 = 20 tỷ, nhưng model nói contradicted. Không suy ra được nguyên nhân nội bộ từ JSON. |
| P03 | unavailable | Model tự chèn `[S1].` khi chép/tách câu; code báo incomplete_draft_coverage đúng. |
| R02 | Câu sai lọt qua | Model chấp nhận `90 + 15 = 95` dựa vào quote quy tắc có thật. |

v1 đã giữ 9/11 câu đúng, chặn 16/17 câu sai, có 1 unavailable. Không sửa nhãn hoặc ghi đè kết quả để thay baseline đó.

Bản v2 vẫn mặc định tắt qua `KNOWLEDGE_CLAIM_VERIFICATION_ENABLED=0`. Không sửa Dashboard, SQL, retrieval, embedding, reranker, quyền tài liệu, API key hay deadline 90 giây. Chưa chuyển sang tune model.

## 1. P03: server cấp ID, model không chép lại bản nháp

Code chia draft thành các đoạn kết thúc ở nhóm citation, gán C1/C2... và giữ nguyên text/source_ids. Model chỉ trả:

```json
{"claims":[{"claim_id":"C1","verdict":"supported","quotes":[{"source_id":"S1","text":"exact source quote"}]}]}
```

Một nhóm citation có thể hỗ trợ nhiều phát biểu, ví dụ hai mức mua sắm trong P03 đều gắn S1 ở cuối. Code giữ cả hai vế trong một block C1 thay vì yêu cầu model chép thành hai câu rồi tự thêm citation. Prompt yêu cầu kiểm tra tất cả phát biểu trong block; nếu một phát biểu không có bằng chứng, không cho toàn block supported.

Code buộc tập ID trả về bằng đúng tập ID gửi đi, không thiếu/thừa/trùng. Thứ tự review có thể khác vì đối chiếu theo ID. Field text từ model bị schema cấm. Citation và quote được đối chiếu với source_ids của block do server giữ, không lấy citation do model mới viết ra.

Nếu sau citation còn nội dung không có citation thì unavailable. Whitespace và ký tự đóng Markdown/table/ngoặc được giữ như formatting, không coi là claim mới. Không bỏ qua chữ/số ở đuôi. `claim_count` là số block theo citation, không phải số claim nguyên tử được chứng minh bằng code.

## 2. R02: kiểm tra phép tính tường minh bằng code

`src/core/rag/arithmetic.py` chạy trước lượt LLM audit:

- Dò chuỗi có đẳng thức và phép tính số literal; hỗ trợ +, -, *, /, ×, ÷, dấu âm và ngoặc, thứ tự ưu tiên và chuỗi đẳng thức.
- Dùng `numeric_value` đã có để đọc số theo locale một cách bảo thủ; không đoán `1,000` là 1 hay 1000.
- Chuyển số thành Fraction chính xác trước khi tính. Không dùng float nên 0.1 + 0.2 = 0.3 không bị lỗi biểu diễn nhị phân.
- Dùng `ast.parse` chỉ để đọc cấu trúc, tự duyệt whitelist phép toán. Không gọi Python eval, không chạy hàm hoặc lũy thừa do người dùng đưa.
- Giới hạn mỗi biểu thức 200 ký tự, 16 số và 64 AST node. Vượt phạm vi/mơ hồ thì unavailable, không tự cho qua.
- Đẳng thức sai như 90 + 15 = 95 trả rejected/arithmetic_mismatch trước khi gọi LLM. Chia cho 0 là invalid_arithmetic. Phép tính đúng vẫn phải qua LLM kiểm chứng claim và nguồn.
- `arithmetic_checked` đếm số đẳng thức code đã đối chiếu, không phải số phép suy luận toàn câu.

Giới hạn quan trọng: không phải bộ máy toán tổng quát, không chứng minh ngữ nghĩa của ký hiệu nằm trong lời văn. Không kiểm mọi hàm, toán khoa học, số viết bằng chữ, phép tính đơn vị, xấp xỉ hoặc arithmetic không có đẳng thức. Dòng có chỉ dẫn làm tròn/xấp xỉ trong phạm vi parser trả unavailable thay vì gán sai thành đúng/sai chính xác. Ví dụ `1 / 3 = 0.33` không phải đẳng thức chính xác; `1 / 3 = 2 / 6` là đúng. Inequality, assignment đơn lẻ và ngưỡng tiền không tự bị coi là phép tính.

Đây là guard cho lỗi rõ ràng, không bảo đảm mọi phép toán sai sẽ được bắt. LLM vẫn phải kiểm các suy luận ngoài phạm vi đó.

## 3. F10: groundedness khác answer completeness

Prompt yêu cầu đối chiếu đúng entity, chỉ tiêu, giá trị, currency/scale, năm/kỳ và scope hợp nhất/riêng. Nêu rõ:

- Claim đúng vẫn được supported dù câu trả lời chưa đáp ứng hết các ý của câu hỏi.
- VND billion tương ứng tỷ đồng, VND million tương ứng triệu đồng; không đánh đồng hai scale hoặc đổi currency.
- Số giống nhau không đủ; phải gắn đúng metric/year/scope. Không kết luận contradicted khi không có dữ kiện xung đột cụ thể.
- Quote phải nguyên văn, không chèn `...` như raw F10 cũ.

Không có code tự cho qua vì thấy số 20. Kiểm tra completeness của đáp án là bài toán khác; `supported` không đồng nghĩa câu trả lời đầy đủ. Việc prompt nhấn mạnh hai khái niệm trên là một giả thuyết cải thiện, không phải bằng chứng về nguyên nhân ẩn của lỗi F10 cũ.

## Thay đổi công cụ và dữ liệu

Benchmark dùng chung `parse_review` với production thay vì duy trì parser riêng. Manifest ghi `verification_protocol=claim-blocks-v2`. Record giữ context, raw review, verdict, arithmetic_checked và validation_error. Summary thêm `by_context` để đọc riêng finance/approval/receiving và các nhóm mới. Không có lượt LLM thứ hai, không tự sửa hoặc tự retry câu trả lời.

Giữ nguyên `knowledge_claim_verification_cases.json` (28 ca). Thêm hai bộ riêng:

- `knowledge_verifier_transfer_v2.json`: 12 ca phát triển mới (5 supported, 7 rejected), số/năm/scale/công ty khác, có nhân/chia số thập phân. Nhãn tự soạn, chưa review độc lập, không gọi là held-out.
- `knowledge_verifier_finance_probe_v2.json`: 4 ca đối chứng dựa trên F10: hỏi cả revenue/profit, chỉ profit, tiếng Anh, và control nhầm metric. Đây là paired diagnostic để xem biến động theo cách hỏi/ngôn ngữ, không phải mẫu độc lập để chứng minh accuracy.

Prompt và protocol đã đổi sau khi xem v1, nên kết quả mới trên 28 ca là regression của bộ đã biết. Không cộng các bộ rồi gọi là độ chính xác production. Cần An/nhóm review và bộ dữ liệu độc lập trước khi kết luận tổng quát.

## Kiểm thử và kết quả thực nghiệm

**101 test code liên quan đạt**, gồm ID coverage/citation/quote/Markdown, quyền truy cập, flag, deadline, benchmark và regression Knowledge/Report. Riêng guard số học có test 200 cặp phép tính đúng/sai sinh bằng seed cố định, ngoài các ca precedence/ngoặc/locale/chia 0/làm tròn. Test mock không được tính thành độ chính xác ngữ nghĩa.

Đã chạy LLM thật bằng model `qwen/qwen3.8-27b`, temperature hiện có 0, key được cấu hình local, pause 15 giây; source/draft cố định, không chạy retrieval hoặc E2E VPS:

| Bộ | Giữ câu đúng | Chặn câu sai | Sai lọt | Unavailable |
|---|---:|---:|---:|---:|
| Baseline v1 do user chạy trên VPS, 28 ca | 9/11 | 16/17 | 1 | 1 |
| Regression v2 local, cùng 28 ca không đổi | 10/11 | 17/17 | 0 | 1 |
| 12 ca phát triển mới | 5/5 | 7/7 | 0 | 0 |
| 4 paired probe tài chính | 3/3 | 1/1 | 0 | 0 |

Trong 17 câu sai v2, R02 do code chặn; 16 còn lại do audit. Không gộp các bộ để công bố một accuracy: paired probes lặp dữ kiện F10 và các bộ đều chưa được review độc lập. Bản v2 được phát triển sau khi xem v1, không gọi 28 ca là held-out.

Lượt ba ca riêng và lượt 28 ca đều giữ F10/P03, chặn R02. Kết quả mới không thay thế baseline hoặc chứng minh tính ổn định lâu dài.

**Vấn đề còn lại F17:** model đánh dấu supported nhưng quote S2 nối phần heading/unit với phần profit, bỏ qua câu revenue nằm giữa. Các thông tin có thể đúng nhưng chuỗi quote không liền nhau, nên code trả unavailable/fabricated_source_quote. Giữ nguyên kết quả này; không sửa prompt/validator thêm để ép ca vừa thấy đi qua, không nới matching quote thành subsequence. Cần review bước tiếp theo trước khi bật mặc định.

Thông số riêng lượt v2 local (không phải E2E và không phải so sánh latency có kiểm soát với VPS):

| Bộ | Lượt audit có usage | Median lượt có usage | Token thực dùng |
|---|---:|---:|---:|
| 28 ca | 27 | 584,87 ms | 19.869 |
| 12 ca mới | 10 | 632,18 ms | 6.802 |
| 4 paired probes | 4 | 627,44 ms | 2.850 |

R02 bị chặn bằng code khoảng 0,21 ms ở lượt 28 ca, không phát sinh token audit; generation của pipeline thật vẫn có chi phí riêng. Ba nhóm trên không có RateLimitError. Không đo hoặc khẳng định toàn pipeline nhanh tương ứng.

Các file local: `v2-three-cases-01.jsonl`, `v2-full-01.jsonl`, `v2-transfer-01.jsonl`, `v2-finance-probe-01.jsonl` trong thư mục artifact nêu bên dưới. Không chạy lại để thay kết quả F17. Chưa build Docker hoặc đo E2E trên VPS tại local; verifier vẫn phải tắt mặc định.

Raw local được giữ trong `artifacts/local/claim-verifier-20261102/` (Git ignore, output 0600). Không đưa raw tài liệu/API key vào commit.

## Deploy và chạy VPS

Bản này đổi schema và prompt trong src, **phải build/recreate backend**, không chỉ copy script. Dừng benchmark trước khi deploy, giữ các file /benchmarks trên host. Không bật verifier web ngay.

```bash
git pull --ff-only origin main
docker compose build backend-api
docker compose up -d --no-deps backend-api

docker compose cp scripts/agents/benchmark_knowledge_verifier.py backend-api:/tmp/benchmark_knowledge_verifier.py
docker compose cp data/evaluation/knowledge_claim_verification_cases.json backend-api:/tmp/knowledge_claim_verification_cases.json

docker compose exec -T backend-api python -u /tmp/benchmark_knowledge_verifier.py \
  --cases /tmp/knowledge_claim_verification_cases.json \
  --api-key-env GROQ_API_KEY_2 --case-ids F10 P03 R02 --pause 20 \
  --output /benchmarks/claim-verifier-v2-three-cases-01.jsonl
```

Sau khi ba ca chạy được, chạy đủ 28 ca với file mới để so với v1:

```bash
docker compose exec -T backend-api python -u /tmp/benchmark_knowledge_verifier.py \
  --cases /tmp/knowledge_claim_verification_cases.json \
  --api-key-env GROQ_API_KEY_2 --pause 20 \
  --output /benchmarks/claim-verifier-v2-full-01.jsonl
```

Hai bộ mới, chạy riêng từng bộ, không chạy đồng thời:

```bash
docker compose cp data/evaluation/knowledge_verifier_transfer_v2.json backend-api:/tmp/knowledge_verifier_transfer_v2.json
docker compose exec -T backend-api python -u /tmp/benchmark_knowledge_verifier.py \
  --cases /tmp/knowledge_verifier_transfer_v2.json --api-key-env GROQ_API_KEY_2 --pause 20 \
  --output /benchmarks/claim-verifier-v2-transfer-01.jsonl

docker compose cp data/evaluation/knowledge_verifier_finance_probe_v2.json backend-api:/tmp/knowledge_verifier_finance_probe_v2.json
docker compose exec -T backend-api python -u /tmp/benchmark_knowledge_verifier.py \
  --cases /tmp/knowledge_verifier_finance_probe_v2.json --api-key-env GROQ_API_KEY_2 --pause 20 \
  --output /benchmarks/claim-verifier-v2-finance-01.jsonl
```

Giữ raw và summary tất cả lượt; nếu 429 thì dừng và đọc trường quota. Không đổi key/model/pause âm thầm giữa các lượt so sánh. Chưa tăng deadline để che chi phí audit. Chỉ cân nhắc thử flag web trong cửa sổ riêng sau khi review kết quả; sau đó còn phải đo sáu câu VietStyle E2E và latency, rồi mới sang reranker, tune sau cùng.

## Giải thích code từng dòng

Xem `knowledge-verifier-v2-lines-20261103.vi.md` cùng thư mục. Các note v1 giữ làm lịch sử; schema text-span v1 không còn là protocol hiện tại.
