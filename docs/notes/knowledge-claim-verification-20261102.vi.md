# Knowledge claim verification — bản thử nghiệm 02/11/2026

## Mục tiêu và giới hạn

Góp ý của An đúng: validator cũ chỉ buộc có citation và citation thuộc tập nguồn được cấp. Thử nghiệm cố định nguồn doanh thu 100, lợi nhuận 20 cho thấy cả số 999, nhầm lợi nhuận thành 100 và nhầm năm đều được chấp nhận nếu có `[S1]`. Kiểm tra số xuất hiện trong nguồn của Report cũng không đủ kiểm chứng chỉ tiêu/năm/phạm vi.

Bản này thêm bước LLM audit sau generation, mặc định TẮT (`KNOWLEDGE_CLAIM_VERIFICATION_ENABLED=0`). Không thay retrieval, top-k, reranker, embedding, quyền truy cập hay raw evidence cho Report. Chưa được coi là verifier đã đạt chất lượng production; chưa tối ưu reranker/tune model.

## Luồng xử lý

```text
Truy xuất theo quyền → Sinh bản nháp → Kiểm tra citation hiện có
  → [flag=0] Trả bản nháp như trước
  → [flag=1] Lọc nguồn được bản nháp trích dẫn → một lượt LLM audit
       → kiểm tra JSON + phủ đủ bản nháp + citation + quote thật
       → supported: trả nguyên bản nháp và evidence
       → rejected/unavailable: chặn toàn bộ bản nháp, không trả evidence như đã xác nhận
```

Verifier dùng cùng provider/model của generation. Nó được yêu cầu kiểm tra từng claim theo chỉ tiêu, giá trị, đơn vị, năm, phạm vi hợp nhất/riêng, phủ định, điều kiện và ngoại lệ. Nó cũng phải phân biệt số giả định trong câu hỏi với số công bố, kiểm tra phép tính và ngưỡng bao gồm/không bao gồm.

Không gọi LLM riêng cho từng claim, không tự sửa câu trả lời, không truy xuất lại và không thử generation lần hai. Provider có thể thử key khác khi gặp 429 như cơ chế sẵn có; đó không phải vòng tự sửa verifier.

## Những gì code thực sự bảo đảm

- JSON phải đúng schema, không có field thừa, 1–16 đoạn claim. Mỗi text không trống và tối đa 6.000 ký tự.
- Ghép các đoạn claim đúng thứ tự phải bằng toàn bộ bản nháp khi bỏ whitespace. Nếu model bỏ đoạn, đổi số, đổi chữ hoặc đổi thứ tự, kết quả không được chấp nhận.
- Mỗi đoạn có citation hợp lệ. Mọi nguồn trích trong đoạn được đánh dấu supported phải có quote đi kèm; quote phải nằm trong chính nguồn đó khi chuẩn hóa whitespace.
- Chỉ nguồn vừa được retrieval theo quyền và được bản nháp trích dẫn được gửi sang audit. Không cho verifier tự lấy nguồn khác hoặc gọi database.
- Chỉ cần một verdict contradicted/insufficient thì chặn cả bản nháp. JSON lỗi, quote bịa, coverage lỗi, provider lỗi hoặc timeout cũng không cho bản nháp đi qua.
- Đầu ra khi chặn: “Chưa thể kiểm chứng đầy đủ câu trả lời với các nguồn được trích dẫn. Vui lòng thử lại hoặc hỏi rõ hơn.” Không gán nhầm thành “nguồn không có dữ liệu”. `metadata.ok=false`, `claim_verification.status` là `rejected` hoặc `unavailable`; `insufficient_context` giữ nghĩa cũ.
- Metadata chỉ có trạng thái, mã lý do và số đoạn claim; không trả bản nháp bị chặn hoặc lập luận nội bộ của verifier.
- Câu trả lời thiếu nguồn/không đủ thông tin sẵn có không gọi verifier. Flag tắt không thêm lượt LLM nào.

**Code không chứng minh entailment/ngữ nghĩa.** Quote thật có thể vẫn bị LLM diễn giải sai; coverage không chứng minh các đoạn thực sự là claim nguyên tử. Số liệu, đơn vị và arithmetic được LLM phán đoán, không phải một bộ máy tính tài chính xác định. Không tái sử dụng mù quáng numeric matcher của Report vì nó có thể chặn nhầm 80 triệu do người dùng đặt giả định hoặc kết quả 90 + 15 = 105 không in trong nguồn.

Cùng một model sinh và kiểm chứng có thể lặp lại cùng lỗi. Prompt chống injection là biện pháp giảm rủi ro, không là bảo đảm chống injection. Không kiểm chứng toàn văn PDF, extraction, nguồn chưa retrieve hoặc tính đúng của chính tài liệu.

## Ngân sách và latency

- Tối đa một lượt audit logical, `max_output_tokens=3072`, timeout tối đa 15 giây và luôn bị chặn bởi deadline cha.
- Không tự tăng trần Knowledge 90 giây. Khi V6 đã dùng gần hết thời gian, audit có thể không hoàn tất. Chưa bật mặc định trước khi tối ưu reranking.
- Giới hạn draft 6.000 ký tự và payload JSON 40.000 ký tự. Vượt giới hạn thì unavailable, không âm thầm cắt bằng chứng để rồi chứng nhận phần còn lại.
- Stage mới `claim_verification` ghi thời gian kiểm chứng. Benchmark HTTP lưu cả flag và metadata kiểm chứng để phân biệt bị chặn với exception HTTP.
- JSON được model bọc duy nhất trong một code fence `json` được bỏ lớp bọc. Không bóc JSON từ văn bản tùy ý, không repair JSON, không làm lượt LLM thứ hai.

## Kiểm thử đã chạy

Đã cập nhật trên main `b1b075a` (bao gồm thay đổi OCR mới), không có conflict. 75 test local đạt: schema/citation/quote/coverage, đảo thứ tự hoặc bỏ claim, mixed true/false, lỗi provider/timeout/JSON, fence JSON, giới hạn input, deadline khôi phục, chỉ nguồn đã cite được audit, flag chỉ do server quyết định, không lộ bản nháp bị chặn, cả hai đường retrieval, benchmark checkpoint/quyền file, Knowledge/planner/runtime/telemetry/orchestration/Report regression.

Lệnh:

```bash
PYTHONPATH=src:tests .venv/bin/python -m unittest \
  test_claim_verification test_claim_verifier_benchmark \
  test_knowledge_outcomes test_knowledge_search_plan test_knowledge_timeout \
  test_latency_tracking test_pipeline_latency_report test_orchestration_contracts \
  test_bounded_execution test_agent_monitoring test_report_agent \
  test_report_delivery test_report_provider -q
```

Mock verdict chỉ kiểm tra code có chặn/cho qua theo hợp đồng; **không tính là độ chính xác ngữ nghĩa**. Đây là nhóm test liên quan, không tuyên bố toàn bộ test suite của repo đạt.

Đã thử LLM thật với model đang cấu hình: lần đầu F01 bị chặn do model trả fenced JSON, F02 bị nhận ra sai số (contradicted). Đã bổ sung parser chỉ gỡ một lớp fence và test tương ứng. Lần chạy toàn bộ bộ chẩn đoán sau sửa dừng ngay ở F01 vì `RateLimitError` của key local. Không gọi tiếp, không đổi model để lấy số đẹp. Chưa có số đo chất lượng sau sửa hoặc kết quả 28/28.

Raw kết quả local (Git ignore): `artifacts/local/claim-verifier-20261102/live-smoke-01.jsonl` và `live-diagnostic-01.jsonl`. Không đưa API key vào repo/log. Môi trường local không có Docker/SSH VPS; chưa chạy E2E sáu câu trên VPS với flag bật.

## Bộ chẩn đoán và bàn giao cho An

`data/evaluation/knowledge_claim_verification_cases.json`: 28 ca, 11 expected supported và 17 expected rejected, nguồn tài chính/chính sách tổng hợp giả lập. Có lỗi số, chỉ tiêu, năm, đơn vị tiền, scale, scope hợp nhất/riêng, cite sai, thiếu ngoại lệ, phủ định, arithmetic, ngưỡng, suy rộng và prompt injection. Câu đúng có phép tính, input do người dùng đưa, nhiều nguồn và chuyển ngôn ngữ.

Đây là dữ liệu phát triển tự soạn, chưa được An/nhóm review độc lập, chưa phải held-out hoặc benchmark của An. Không dùng “28 ca” để khẳng định độ chính xác thực tế. Sau khi biết bộ của An, thêm vào đánh giá riêng, không sửa nhãn sau khi xem output rồi gọi đó là test độc lập.

`scripts/agents/benchmark_knowledge_verifier.py` giữ cố định question/draft/source, chỉ gọi audit để tách lỗi verifier khỏi retrieval/generation. Ghi JSONL sau mỗi ca, model, hash dữ liệu/prompt, token usage và thời gian. Unavailable không được đếm là chặn đúng. Gặp hết quota/auth thì dừng sớm. File output mới, quyền 0600. Đây không phải kết quả E2E.

Phân biệt các chỉ số:

- `supported_kept / expected_supported`: giữ được câu đúng.
- `unsupported_rejected / expected_rejected`: phát hiện câu sai bằng verdict, không gộp lỗi hệ thống.
- `unsupported_passed`: câu sai lọt qua, cần đọc lại từng ca.
- `unavailable`: lỗi định dạng, coverage, quote, input budget hoặc provider; phân tích `reason` riêng. Đối chiếu label để tìm chặn nhầm câu đúng.
- Latency/token audit được đo riêng. E2E phải đo thêm toàn bộ pipeline.

## Deploy code nhưng chưa bật web

Không deploy trong lúc benchmark khác đang chạy.

```bash
cd /opt/enterprise-knowledge-ai-agent
git pull --ff-only origin main
docker compose build backend-api
docker compose up -d --no-deps backend-api
```

Giữ `KNOWLEDGE_CLAIM_VERIFICATION_ENABLED=0` (hoặc chưa khai báo). Chạy benchmark độc lập bằng key trong container; không gửi key qua chat. Image API chỉ copy `src` và `data/semantic`, nên cần copy script và fixture:

```bash
docker compose cp scripts/agents/benchmark_knowledge_verifier.py backend-api:/tmp/benchmark_knowledge_verifier.py
docker compose cp data/evaluation/knowledge_claim_verification_cases.json backend-api:/tmp/knowledge_claim_verification_cases.json

docker compose exec -T backend-api python -u /tmp/benchmark_knowledge_verifier.py \
  --cases /tmp/knowledge_claim_verification_cases.json \
  --limit 2 --pause 15 --output /benchmarks/claim-verifier-smoke-01.jsonl
```

Nếu smoke có quota và format hợp lệ, chạy đủ 28 ca, tên output mới:

```bash
docker compose exec -T backend-api python -u /tmp/benchmark_knowledge_verifier.py \
  --cases /tmp/knowledge_claim_verification_cases.json \
  --pause 15 --output /benchmarks/claim-verifier-diagnostic-01.jsonl
```

Kết quả tự có trên host ở `artifacts/local/knowledge-latency/`. Không chạy test 60 request đồng thời để tránh tranh CPU/quota. Benchmark chỉ trên fixed sources không cần bật flag web.

Chỉ sau khi review kết quả, lên lịch cửa sổ thử nghiệm chung, mới đổi `.env`:

```dotenv
KNOWLEDGE_CLAIM_VERIFICATION_ENABLED=1
```

Tạo lại backend để nạp env, copy lại script latency nếu cần, chạy sáu câu VietStyle trước. Kiểm tra cả câu trả lời, status kiểm chứng, số nhánh và stage; không gọi “HTTP 200” là thành công nếu `metadata.ok=false`.

Rollback flag về 0 rồi recreate backend, không cần build lại; giữ kết quả host. Không tăng timeout hoặc đổi model âm thầm giữa hai nhánh benchmark. Reranker được xử lý sau khi verifier có kết quả chất lượng đủ để quyết định, tune embedding/model sau cùng.

## Giải thích code từng dòng

Xem `docs/notes/knowledge-claim-verification-lines-20261102.vi.md`: liệt kê từng dòng runtime và script thay đổi, giải thích schema, prompt, nhánh chặn và phép đo; test/fixture có bảng mô tả mục đích từng ca.

## Sửa lỗi đường dẫn script copy vào /tmp

Bản đầu dùng `Path(__file__).resolve().parents[2]`. Khi file nằm trực tiếp `/tmp/benchmark_knowledge_verifier.py`, chỉ có hai parent là `/tmp` và `/`; index 2 vượt giới hạn và gây `IndexError` trước khi gọi provider hoặc ghi output. Vì vậy hai lần chạy lỗi này không tiêu token.

Đã sửa thành `.parent.parent.parent`: đi lên từng cấp sẽ dừng tại `/` thay vì ném lỗi. Khi chạy trong repo vẫn xác định đúng root. Trong container dùng `PYTHONPATH=/app/src` có sẵn và tham số `--cases /tmp/...` rõ ràng; không phụ thuộc root giả định để tìm fixture.

Test regression copy file thật trực tiếp vào `/tmp`, chạy subprocess từ `/tmp` với `--help`, mô phỏng PYTHONPATH container. Test đã tái hiện lỗi trước sửa và đạt sau sửa. Chỉ cập nhật script, test và note, không cần build/recreate backend: pull main, copy đè script vào `/tmp`, chạy lại lệnh benchmark cũ. File output cũ chưa được tạo bởi lỗi này nên có thể giữ tên `claim-verifier-smoke-01.jsonl` nếu chưa chạy thành công lần nào.
