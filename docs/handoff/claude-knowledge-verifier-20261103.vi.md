# Handoff cho Claude — Knowledge / verifier / retrieval

Cập nhật: 03/11/2026, giờ Việt Nam. Đây là context bàn giao, không phải lệnh tự sửa code, bật feature hoặc deploy.

## Prompt khởi động có thể dán vào Claude

> Đọc `docs/handoff/claude-knowledge-verifier-20261103.vi.md` trước. Làm trực tiếp trên nhánh Huy đã đồng bộ main; user không muốn tạo nhánh/worktree mới. Kiểm tra status và main trước khi làm. Trong lượt đầu tóm tắt trạng thái, review F17 và phương án cùng test cần có; chưa sửa code, đổi env, commit/push hoặc deploy nếu user chưa giao việc đó. Phân biệt điều đã kiểm chứng với giả thuyết.

Nếu không truy cập filesystem/repo, cần gửi nội dung file này và các file source liên quan; không được giả vờ đã đọc code hoặc chạy test.

## 1. Trạng thái Git và nơi làm việc — đọc trước khi bắt đầu

Repo: `Lenhan231/enterprise-knowledge-ai-agent`.

Main mới nhất đã được bàn giao ở commit **`1241801` — fix: anchor verifier reviews to claim IDs and check exact arithmetic**. Hãy fetch để kiểm tra main có tiến thêm không, đừng coi hash này luôn là HEAD mới nhất.

Cập nhật sau yêu cầu đồng bộ nhánh của user:

- Workspace Desktop: `/home/eroz/projects/enterprise-knowledge-ai-agent`.
- **Làm trực tiếp trên Huy; user không muốn tạo nhánh hoặc worktree mới.**
- Các note/handoff dang dở đã được giữ trong commit `dd43de0` trước khi merge.
- Đã merge `origin/main` tại `1241801` vào Huy, giữ lịch sử và công cụ/ghi chú riêng của Huy. Code `src`, tests, Docker/config/dependency hiện khớp main ở thời điểm merge; Huy không nhất thiết có hash bằng main vì giữ lịch sử riêng.
- Có 7 conflict khi merge: giữ code/test mới từ main và giữ hai note xác minh VPS của Huy. Không reset Huy để làm nó giống hệt main.
- Checkout tạm `/tmp/backend-runtime-dependencies-20261102` là nơi assistant trước đã phát triển các commit trên main, chỉ là lịch sử; không tiếp tục sửa tại đó trong workflow mới.
- Handoff đã được track trong Git. Kiểm tra `git status` lại trước khi làm, đừng mặc định workspace luôn clean.

Kiểm tra trước:

```bash
git status --short
git branch --show-current
git log -3 --oneline
git fetch origin main
git log -5 --oneline origin/main
```

Có thể đối chiếu code main mà không rời nhánh Huy:

```bash
git show origin/main:src/core/rag/claim_verification.py
git show origin/main:src/core/rag/arithmetic.py
```

Nếu cần chạy/sửa, làm trên Huy theo yêu cầu user. Không reset, xóa hoặc tự stash thay đổi của user; không tạo thêm nhánh/worktree. Nếu main tiến thêm thì xem diff và merge main vào Huy có kiểm tra, không tự mang toàn bộ lịch sử/artifact riêng của Huy ngược lên main.

**VPS đã deploy v2 `1241801` hay chưa: chưa được user xác nhận.** Git đã pull không chứng minh image/container đã nạp code mới.

## 2. Mục tiêu và phạm vi

User là Huy, tập trung Knowledge, retrieval, chunking và quyền truy cập tài liệu. Nhóm có An làm SQL/router/report; các phần OCR có owner khác.

Thứ tự user đã chọn:

1. Làm verifier trước, đo cả chặn sai và chặn nhầm câu đúng.
2. Sau đó tối ưu reranker.
3. Tune embedding/model sau cùng khi có bằng chứng cần thiết.

**User đã yêu cầu dừng sửa Dashboard, làm phần của mình trước.** Dashboard có lỗi kết nối DB còn tồn tại, chỉ ghi nhận/bàn giao, không mở rộng công việc sang đó.

Cách làm user muốn:

- Sửa phần nào phải báo cáo và giải thích code từng dòng trong note.
- Phải chạy test trước khi đẩy code; kết quả LLM thật khác với test mock.
- Giữ giải pháp nhỏ, dùng thư viện chuẩn/helper sẵn có, không thêm framework không cần thiết.
- Báo tiến độ và nói rõ chưa kiểm tra gì; không khẳng định đã fix chỉ vì code compile.
- Không tự bật verifier cho cả nhóm. Cờ hiện là theo backend, chưa có cờ theo từng tài khoản.
- Không tự tạo task/nhắn cho An hoặc người khác. User chưa đưa bộ benchmark riêng của An.

## 3. Luồng hệ thống hiện tại

```text
UI → backend-api → KnowledgeAgent
  → RAGService.generate_answer
    → planner nếu bật multiquery
    → retrieve từng nhánh: dense / lexical / fusion / BGE rerank
    → gộp nguồn → sinh bản nháp → kiểm tra citation tồn tại
    → verifier nếu bật → trả AgentResult + evidence + metadata
```

Docker tách backend-api, embeddings, reranker, document-processing, chunking. Các địa chỉ nội bộ không mặc nhiên gọi được từ Desktop.

Model LLM đang dùng: `qwen/qwen3.8-27b`, provider OpenAI-compatible Groq Responses API. Generation và verifier dùng cùng provider/model; chưa có model judge độc lập. Không âm thầm đổi model giữa các lượt benchmark.

### Cờ hiện tại

- `KNOWLEDGE_MULTIQUERY_ENABLED=1`: Knowledge lập kế hoạch một/hai truy vấn theo topic bằng chứng.
- `KNOWLEDGE_CLAIM_VERIFICATION_ENABLED=0`: **verifier web mặc định tắt**. Chạy script benchmark trực tiếp không bật verifier trên web.
- Nếu đổi cờ verifier thành 1 và recreate backend thì ảnh hưởng mọi người dùng backend đó, không chỉ Huy.

Không gửi/in API key, DSN, cookie hoặc toàn bộ `.env`. Key/env local và VPS không nhất thiết giống nhau.

## 4. Bối cảnh retrieval/chunking đã xử lý

Chunking cũ làm mất quan hệ heading/model với bảng, gây không tìm được thông số Wacom hoặc hiểu bảng phê duyệt. Chunking mới giữ section/table/column/row context. Không được làm mất những thông tin đó khi tối ưu.

Một lỗi khác ở câu nhiều ý: hỏi phê duyệt + phát hành PO trong một query làm bảng phê duyệt EN chunk 781 rơi ngoài top 30 fusion trước BGE. BGE không thể cứu chunk không có trong ứng viên. Tăng top-k cuối không giải quyết được.

Đã thêm multiquery có giới hạn:

- Một hoặc hai truy vấn theo **topic bằng chứng**, không theo số dấu hỏi/từ “và”.
- So sánh hai ngưỡng trong cùng bảng hoặc nhiều điều kiện cùng biểu mẫu vẫn một query.
- Approval/quotation và release PO là hai topic, thường hai query.
- Mỗi nhánh lấy tối đa 5 context; merge round-robin, dedup, tối đa 10 context và 24.000 ký tự.
- Mọi nhánh giữ cùng scope quyền/company/document filters; không có cách lấy nguồn ngoài quyền để cứu câu trả lời.
- Thiếu bằng chứng một nhánh thì không sinh một câu trả lời đầy đủ giả tạo.

Planner không còn regex gate. Đừng thêm rule riêng chỉ để sáu câu test đẹp hơn.

## 5. Latency đã đo — không đoán lại từ đầu

Đợt trước sửa timeout: 30/60 request rồi dừng, 28 thành công; một V6 timeout 60 giây, một RemoteDisconnected sát lúc container được tạo lại. JSON /tmp mất nhưng log host còn. Không coi đó là đủ một đợt 60 request.

Sau sửa:

- Knowledge bật multiquery được chờ tối đa 90 giây; tắt giữ 60 giây. Deadline cha ngắn hơn vẫn có hiệu lực.
- Đã chạy đủ 60 request tuần tự trên VPS: 59/60 thành công (98,3%); V1–V5 50/50; V6 9/10.
- Median 59 request thành công 39,48 giây, P95 nội suy khoảng 81,10 giây.
- Median V6 thành công 78,53 giây; lỗi còn lại là TimeoutError, handler 90.006 ms, HTTP 92,82 giây.
- Reranking là phần chính, từng request lên khoảng 75,4 giây. Planner khoảng 0,4 giây, sinh đáp án thường dưới 1 giây.
- Telemetry thường 2,7 giây, một số lần khoảng 12,8 giây.

Mốc đo:

- `request_total_ms`: handler trước ghi lịch sử, không gồm auth.
- `telemetry_persistence`: chờ ghi lịch sử DB.
- `response_ready_ms`: handler đến sau telemetry, chưa gồm serialize/transport/auth.
- `http_elapsed_ms`: client đo toàn request HTTP; đây là mốc thực tế người dùng chờ.
- Stage lồng nhau/nhánh song song không được cộng mù thành E2E.

File VPS đã kiểm tra có **60 request và summary**:

```text
/opt/enterprise-knowledge-ai-agent/artifacts/local/knowledge-latency/stability-fix-repeat-01.json
/opt/enterprise-knowledge-ai-agent/artifacts/local/knowledge-latency/stability-fix-repeat-01.log
```

Đây là khoảng một giờ test tuần tự, không chứng minh tải nhiều người hoặc vận hành cả ngày. `application_ok`/HTTP 200 không tự chứng minh trả lời đúng.

## 6. Vì sao làm verifier

An chỉ ra validator cũ chấp nhận miễn có `[S1]` thuộc nguồn đã retrieve, không kiểm claim có được source hỗ trợ không. Đã tái hiện: nguồn revenue 100/profit 20 nhưng “profit 100”, “revenue 999”, “revenue sai năm” đều qua citation-only validator.

Numeric matcher của Report không đủ: số 100 có trong source vẫn có thể thuộc sai metric/year. Không áp nó mù quáng vì số giả định trong câu hỏi hoặc kết quả 90 + 15 = 105 có thể hợp lệ dù không in trong tài liệu.

Verifier thử nghiệm thêm tối đa một lượt LLM audit với đúng nguồn đã cite, không retrieve lại, không tự repair/regenerate, deadline tối đa 15 giây trong deadline cha. Code buộc schema/coverage/citation/quote. Nguồn được lấy theo quyền trước audit.

Nếu audit rejected/unavailable, không trả draft/evidence như đã được chứng nhận. Metadata có `ok=false`, trạng thái kiểm chứng; không gán nhầm thành “source không có dữ liệu”. Không đưa draft bị chặn vào API metadata.

## 7. Baseline verifier v1 trên VPS — giữ nguyên

Bộ 28 ca: `data/evaluation/knowledge_claim_verification_cases.json`, 11 expected supported và 17 expected rejected. Đây là nguồn/draft giả lập tự soạn, chưa phải bộ độc lập/benchmark của An.

Kết quả VPS trong `claim-verifier-full-01.jsonl`:

- Giữ 9/11 câu đúng.
- Chặn 16/17 câu sai.
- 1 câu sai lọt (R02).
- 1 unavailable (P03), một false reject khác (F10).

Ba ca:

- F10: source profit after tax 2024 = 20 tỷ; claim cũng 20 tỷ nhưng LLM nói contradicted. Không suy ra nguyên nhân nội bộ chỉ từ raw JSON.
- P03: model chép/tách draft rồi tự thêm citation, code báo `incomplete_draft_coverage`. Không nới check để bỏ qua chữ/citation tự chèn.
- R02: model chấp nhận “90 + 15 = 95”, quote quy tắc `Accepted + rejected <= delivered` có thật nhưng không chứng minh phép tính.

Không ghi đè baseline, đổi nhãn sau khi xem output hoặc gọi unavailable là chặn đúng.

## 8. Verifier v2 đã triển khai trên main 1241801

### A. ID bất biến cho claim block

`claim_blocks()` do code tách draft tại nhóm citation, gán C1/C2..., giữ text/source_ids. Một block có thể chứa nhiều phát biểu dùng chung citation. LLM chỉ trả claim_id/verdict/quotes, không chép text hoặc tự chọn lại citation.

Code yêu cầu đủ mọi ID, không thừa/trùng, kiểm quote thuộc đúng source_ids server giữ. Đuôi formatting Markdown được giữ, chữ/số uncited không được bỏ qua. `claim_count` là số block theo citation, không phải chứng minh đã tách mọi claim nguyên tử.

### B. Guard số học exact

`src/core/rag/arithmetic.py` dùng regex + `ast.parse` + whitelist + Fraction. Không dùng Python eval. Hỗ trợ literal +,-,*,/, dấu âm, ngoặc, ưu tiên toán tử, chuỗi đẳng thức và một số locale số. Tái dùng `numeric_value` từ `core.reports.grounding`.

- Sai đẳng thức → rejected/arithmetic_mismatch trước LLM.
- Chia 0 → invalid_arithmetic.
- Mơ hồ/ngoài phạm vi/làm tròn → unavailable, không tự chứng nhận.
- Giới hạn 200 ký tự/vế, 16 số, 64 AST node.
- Arithmetic đúng không được override semantic rejection.
- Không phải máy toán tổng quát; không bắt mọi phép tính/suy luận hoặc công thức trong lời văn. Không tự đổi scale/currency.

### C. Prompt groundedness

Phân biệt factual support với completeness: một claim đúng không thành sai chỉ vì question còn hỏi một metric khác. Nhắc rõ tỷ/billion, triệu/million, đúng metric/year/scope/currency. Không có code tự cho F10 qua vì thấy số 20.

### D. Công cụ

Script dùng parser chung `parse_review`, ghi `verification_protocol=claim-blocks-v2`, raw audit trong file 0600, metadata/mã lỗi và summary theo context. Terminal không in raw mặc định. Có `--api-key-env` và `--case-ids`. Không có lượt LLM thứ hai để giải thích hoặc sửa.

## 9. Kết quả v2 local — tách từng bộ

101 test code liên quan đạt trước push, có test 200 cặp phép tính đúng/sai sinh tự động bằng seed. Đây không phải 101 ca LLM/ngữ nghĩa.

LLM thật `qwen/qwen3.8-27b`, fixed draft/source, không chạy retrieval/E2E VPS:

| Bộ | Giữ đúng | Chặn sai | Sai lọt | Unavailable |
|---|---:|---:|---:|---:|
| Regression 28 ca cũ | 10/11 | 17/17 | 0 | 1 |
| 12 ca phát triển mới | 5/5 | 7/7 | 0 | 0 |
| 4 paired probes tài chính | 3/3 | 1/1 | 0 | 0 |

F10/P03/R02 đạt trong lượt riêng và lượt 28 ca. R02 do code chặn, không gọi LLM. Không gộp các bộ thành accuracy production; paired probes lặp dữ kiện F10 và các bộ mới được soạn sau khi xem lỗi v1, không held-out.

Median audit có LLM usage: 584,87 ms (28 ca), 632,18 ms (12 ca), 627,44 ms (4 probes). Không suy ra latency E2E tương ứng hoặc so như một A/B latency có kiểm soát với VPS.

Raw local (Git ignore, 0600):

```text
/home/eroz/projects/enterprise-knowledge-ai-agent/artifacts/local/claim-verifier-20261102/v2-three-cases-01.jsonl
/home/eroz/projects/enterprise-knowledge-ai-agent/artifacts/local/claim-verifier-20261102/v2-full-01.jsonl
/home/eroz/projects/enterprise-knowledge-ai-agent/artifacts/local/claim-verifier-20261102/v2-transfer-01.jsonl
/home/eroz/projects/enterprise-knowledge-ai-agent/artifacts/local/claim-verifier-20261102/v2-finance-probe-01.jsonl
```

Không mặc định Claude ở máy khác sẽ có các file local này; source/fixture/note có trên Git, raw không commit.

## 10. Việc còn lại quan trọng nhất: F17

F17 là câu đúng nhiều nguồn. Model v2 nói supported nhưng tự nối hai đoạn source không liền nhau thành một quote. Code chặn với `fabricated_source_quote`, nên đây là false block/unavailable, không phải có bằng chứng claim tài chính sai.

Source S2 nguyên văn:

```text
Separate financial results of the parent company. Unit: VND billion. Revenue: 2024 = 80; 2023 = 70. Profit after tax: 2024 = 12; 2023 = 10.
```

Quote model trả:

```text
Separate financial results of the parent company. Unit: VND billion. Profit after tax: 2024 = 12; 2023 = 10.
```

Nó bỏ đoạn Revenue ở giữa nhưng nối thành một chuỗi quote. Không nới validator thành fuzzy/subsequence matching: cách đó có thể bỏ mất phủ định/ngoại lệ và hợp thức hóa bằng chứng sai.

**Đề xuất ban đầu, chưa triển khai:** server cấp ID cho các đoạn bằng chứng, model chọn ID thay vì chép quote; hai đoạn rời nhau vẫn là hai bằng chứng riêng, code lấy nguyên văn từ nguồn. Cần review thiết kế, granularity/span/header/unit, quyền truy cập và test chống chọn sai bằng chứng. Đừng coi đề xuất này là code đã có hoặc bảo đảm semantic entailment.

Review Claude đã chỉ ra schema hiện cho phép nhiều quote cùng source_id, nên có lựa chọn nhỏ hơn: chỉ thêm một câu prompt yêu cầu mỗi quote là đoạn liền nhau, các đoạn rời phải là nhiều quote riêng cùng source_id. Assistant đã đề xuất thử lựa chọn prompt này trước, không gộp đổi thứ tự validation. Chưa có thay đổi code cho F17 sau review đó. Evidence ID chỉ nên cân nhắc nếu cách nhỏ hơn không đủ.

Claude cũng nêu việc validator dừng ở lỗi đầu có thể khiến unavailable xuất hiện trước một verdict contradicted ở block sau. Đây là lựa chọn ưu tiên phân loại, không mặc nhiên là đếm sai; cần đánh giá riêng, không đổi cùng lúc với prompt rồi mất khả năng phân biệt tác động.

Lượt đầu của Claude nên đối chiếu review hiện tại và lựa chọn nhỏ hơn. Chưa mặc định triển khai thêm trước khi user giao nhiệm vụ cụ thể. Dù dùng ID, LLM vẫn có thể chọn bằng chứng không hỗ trợ claim.

Sau xử lý/đánh giá F17: regression 28 ca + bộ mới, rồi sáu câu VietStyle E2E/latency; khi verifier đạt mức chấp nhận được mới sang reranker. Không tự bật flag cho web chung.

## 11. File cần đọc trên main, theo thứ tự

1. `src/core/rag/claim_verification.py` — block IDs, schema, quote/citation validation, outcome/deadline.
2. `src/core/rag/arithmetic.py` — guard literal arithmetic và giới hạn.
3. `src/core/prompts/knowledge_verification.py` — prompt v2.
4. `src/core/rag/rag_service.py` — điểm chèn audit sau kiểm citation và cách chặn draft.
5. `src/core/agents/knowledge_agent.py` — env flag, deadline, evidence/metadata.
6. `scripts/agents/benchmark_knowledge_verifier.py` — selector, recording, quota, counters.
7. `tests/test_claim_verification.py`, `tests/test_claim_verifier_benchmark.py`, `tests/test_arithmetic.py`, `tests/test_groq_key_failover.py`.
8. `docs/notes/knowledge-verifier-v2-20261103.vi.md` và `knowledge-verifier-v2-lines-20261103.vi.md` — báo cáo và giải thích từng dòng.

Lưu ý implementation: quote của block supported bị buộc đúng nguồn/nguyên văn; block contradicted/insufficient bị chặn sớm, không nhất thiết chạy hết kiểm tra quote. Đọc code thật trước khi đề xuất thay đổi thứ tự validation.

Các note v1 giữ lịch sử, schema `text` trong review của v1 không còn là protocol v2.

## 12. Test và benchmark

Chạy trên Huy đã đồng bộ main, kiểm tra status trước. Venv Desktop hiện có ở `/home/eroz/projects/enterprise-knowledge-ai-agent/.venv`; dùng interpreter đó hoặc dựng môi trường theo lock. Không tự nâng package ngoài scope.

```bash
PYTHONPATH=src:tests /home/eroz/projects/enterprise-knowledge-ai-agent/.venv/bin/python -m unittest \
  test_arithmetic test_claim_verification test_claim_verifier_benchmark test_groq_key_failover \
  test_knowledge_outcomes test_knowledge_search_plan test_knowledge_timeout \
  test_latency_tracking test_pipeline_latency_report test_orchestration_contracts \
  test_bounded_execution test_agent_monitoring test_inventory_dashboard \
  test_report_agent test_report_delivery test_report_provider -q
```

Đã đạt 101 test ở commit 1241801. Không tuyên bố toàn bộ test suite repo đạt; có test cũ ngoài nhóm liên quan cần review riêng.

Benchmark verifier dùng source/draft cố định, không gọi database hoặc embeddings. Output phải là tên mới, không ghi đè. Tham khảo lệnh chính xác trong note v2. Bộ 28 ca ở `data/evaluation/knowledge_claim_verification_cases.json`; hai bộ mới là `knowledge_verifier_transfer_v2.json` và `knowledge_verifier_finance_probe_v2.json`.

Giữ dữ liệu và prompt hash, model, status/errors/usage. Đo riêng unavailable; không retry tới khi được kết quả tốt rồi bỏ các lượt lỗi.

## 13. VPS / deploy / lưu kết quả

VPS repo `/opt/enterprise-knowledge-ai-agent`, backend service `backend-api`, container thường `enterprise-knowledge-ai-agent-backend-api-1`.

Assistant trước không có quyền SSH vào VPS; user tự chạy lệnh. Không khẳng định đã deploy/test VPS từ Desktop.

Compose dùng `env_file: .env`. Build image không tự thay env trên host; đổi env cần recreate container, restart đơn thuần không nạp env mới.

`./artifacts/local/knowledge-latency` trên host bind-mount vào `/benchmarks` trong backend. Lưu benchmark ở **/benchmarks**, không /tmp nếu cần tồn tại qua recreate. Script/fixture copy vào /tmp sẽ mất khi thay container.

Bản v2 thay src/schema/prompt nên cần build backend. Các bản chỉ sửa script có thể chỉ pull/copy script; đừng áp điều đó cho v2.

Chỉ deploy nếu user giao việc đó, không trong lúc benchmark:

```bash
cd /opt/enterprise-knowledge-ai-agent
git pull --ff-only origin main
docker compose build backend-api
docker compose up -d --no-deps backend-api
```

Sau recreate, copy script và fixture (image không copy scripts hoặc toàn bộ data/evaluation):

```bash
docker compose cp scripts/agents/benchmark_knowledge_verifier.py backend-api:/tmp/benchmark_knowledge_verifier.py
docker compose cp data/evaluation/knowledge_claim_verification_cases.json backend-api:/tmp/knowledge_claim_verification_cases.json

docker compose exec -T backend-api python -u /tmp/benchmark_knowledge_verifier.py \
  --cases /tmp/knowledge_claim_verification_cases.json --api-key-env GROQ_API_KEY_2 \
  --case-ids F10 P03 R02 --pause 20 --output /benchmarks/claude-v2-smoke-01.jsonl
```

Chọn output mới nếu tên đã có. Giữ verifier web tắt trong benchmark riêng. Đừng vừa benchmark vừa dùng web gọi LLM hoặc deploy. `docker compose logs -f --since 5m --tail 200 backend-api` xem log; Ctrl+C chỉ dừng xem log.

## 14. Quota và fallback key — chưa được kết luận quá mức

Có hai key khác nhau được nạp, API 2 thuộc tài khoản khác theo user. API 1 đã hết quota ở một số thời điểm. Các benchmark pool nhiều lần bị RateLimitError; chạy riêng API 2 sau đó hoàn tất 28 ca, nhưng **chưa xác định chính xác nguyên nhân các 429 trước**.

- Provider bắt OpenAI RateLimitError, thử key tiếp theo, ưu tiên key thành công và có cooldown per-key.
- Bốn test mock chuyển key/cooldown đã đạt; điều này không chứng minh trạng thái từng key trong request lỗi thật trước đó.
- Khi mọi key cooling, provider có thể ném lại lỗi rate limit đã giữ mà không có HTTP request mới.
- `--api-key-env GROQ_API_KEY_2` chỉ chọn key cho tiến trình benchmark, không đổi key của web.
- `rate_limit` ghi kind/limit/used/requested/retry_after nếu provider có; dùng pool thì đó là lỗi cuối cùng, không phải trace từng key.
- Một request OK với 16 output token không chứng minh request audit xin tối đa 3072 token sẽ được chấp nhận.
- Pause dài hơn không giải quyết quota ngày; hạn mức organization có thể còn bị workload khác dùng chung. Không tạo thêm key cùng org để coi là quota mới.

Không dump error body/key nguyên văn hoặc gọi lại cả bộ nhiều lần chỉ để đoán quota. Dừng khi quota cạn, giữ log và phân biệt lỗi provider với chất lượng verifier.

## 15. Các việc phụ đã ghi nhận, không mở lại trong task Knowledge

- Thiếu python-docx đã sửa bằng dependency chính + build import smoke (`d4ee6f2`).
- Thiếu asyncpg đã sửa (`29cd45c`); export/runtime có asyncpg 0.32.0.
- Telemetry từng failed + error_type NULL vi phạm CHECK; đã gán InsufficientContext/AgentFailed phù hợp, không sửa hoặc xóa constraint.
- Dashboard sau đó timeout khi mở thêm kết nối trong pool lúc chạy query song song. Nguyên nhân gốc chưa xác định. User yêu cầu không làm Dashboard tiếp.
- `/health` 200 không chứng minh analytics/LLM hoạt động. HTTP 401 là session/auth riêng; đừng quy cho verifier.

### Nguồn tài liệu đã biết — trạng thái chỉ là lần kiểm tra gần nhất

- EN VietStyle: `UPLOAD-12f3d0901de9444fba9ad23005a0f54e`, bảng phê duyệt chunk 781, PO rule chunk 300, Appendix C 790/791.
- VI VietStyle: `UPLOAD-5f3724762c5e4146b9f85d3696a6f919`, Appendix B 730, C 737/738/741. Trạng thái active EN/VI đã từng được bật/tắt khi test, kiểm tra lại nếu cần.
- Wacom mới: `UPLOAD-7bf63a9a1e194c01bee05f3c7be47f5d`, title Wacom context test, ready/active, 164 chunk. Chunk 38 CTL-4100 Weight 230 g; chunk 39 CTL-4100WL Weight 250 g.
- Wacom cũ `UPLOAD-3e9e70c708d5415c8e1cf23ab0cc9d41`, ready nhưng inactive, 171 chunk. Không tự bật lại hoặc xóa tài liệu.

“Hello” trong chế độ Knowledge không phải câu có đáp án tài liệu. Câu Wacom tự đủ ngữ cảnh nên ghi rõ model; chưa có tính năng trò chuyện chung/follow-up resolution được xác nhận trong phần này. Không suy từ câu trả lời thiếu bằng chứng rằng dữ liệu chắc chắn đã mất.

## Điều Claude nên trả sau lượt đọc đầu

1. Bạn đang đọc branch/commit nào; có khớp main/v2 không?
2. Tóm tắt verifier hiện tại, ranh giới code xác thực với phán đoán LLM.
3. Phân tích đúng F17: quote ghép so với claim sai, không nới matching tùy tiện.
4. Phương án sửa nhỏ nhất, các nguy cơ chọn sai span/đơn vị/header/nguồn ngoài quyền.
5. Test cần thêm và cách so sánh giữ baseline, false accept, false block, unavailable, latency/token.
6. Phần chưa đọc/chưa kiểm tra và câu hỏi thật sự cần user bổ sung.

Không nói đã test/deploy nếu chưa chạy. Không coi handoff là chứng minh mọi số liệu/proposal đều đúng mãi; đối chiếu code và giữ các quyết định/phạm vi đã được user chấp nhận.
