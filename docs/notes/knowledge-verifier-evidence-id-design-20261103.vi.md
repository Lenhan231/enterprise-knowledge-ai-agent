# Thiết kế đề xuất: evidence ID cho verifier (chưa triển khai)

Ngày 03/11/2026. Trạng thái: **đã code cách B (tách dòng + câu, không tự gắn header)**, 104 test liên quan đạt; chưa chạy LLM thật. Nền: main `1241801`, Huy `58b7226`.

## Vấn đề

F17 là câu đúng nhưng bị chặn `fabricated_source_quote`: model nối hai đoạn rời của S2 thành một quote. Thử quy tắc prompt "mỗi quote liền nhau" đã thất bại 2/2 lượt (xem `knowledge-verifier-v2-20261103.vi.md`). Không nới matching quote.

Hai sự thật từ code hiện tại quyết định phạm vi:

1. Quote **không** đến tay user: `VerificationOutcome` chỉ có status/reason/count (`claim_verification.py:41-45`, `knowledge_agent.py:81-82`). Quote chỉ là bằng chứng chống bịa, không phải bằng chứng hiển thị.
2. Quote nguyên văn chỉ chứng minh chuỗi có trong nguồn, không chứng minh nó hỗ trợ claim. Entailment vẫn là phán đoán của LLM.

Vì vậy evidence ID giữ đúng chức năng hiện tại của quote (model phải chỉ ra nó dựa vào đâu trong nguồn đã cite) nhưng bỏ hẳn bước model chép chữ.

## Thiết kế nhỏ nhất

### Cắt nguồn thành đơn vị bằng chứng (server)

- Chỉ cắt các `cited_contexts` mà `rag_service.py:274` đã lọc theo citation, trên nền nguồn đã lọc quyền. Không retrieve, không thêm nguồn.
- Tách theo dòng (`\n`). Chunk bảng đã có dạng `Section: …` / `Table: …` / `Columns: …` / `Row N: cột: giá trị | …` (`chunking/table/chunker.py:33-40`), nên mỗi dòng bảng đã tự mang tên cột.
- Mỗi dòng tách thêm tại ranh giới câu: dấu `.`/`!`/`?` + khoảng trắng. Không tách ở `;` vì sẽ cắt `Revenue: 2024 = 80; 2023 = 70.` làm mất nhãn của số 2023. `1.5` hoặc `50.000.001` không có khoảng trắng sau dấu chấm nên không bị cắt.
- ID dạng `S2.1`, `S2.2`… theo thứ tự trong nguồn. Ghép các đơn vị theo thứ tự phải tái tạo lại nội dung nguồn (sau khi chuẩn hóa khoảng trắng); có assert/test cho bất biến này.
- Cắt quá nhỏ (ví dụ sau "e.g.") chỉ làm model phải chọn nhiều ID hơn, không làm lọt sai, vì chữ hiển thị vẫn nguyên văn.

F17 S2 sẽ thành `S2.1` "Separate financial results of the parent company." · `S2.2` "Unit: VND billion." · `S2.3` "Revenue: 2024 = 80; 2023 = 70." · `S2.4` "Profit after tax: 2024 = 12; 2023 = 10." Model chọn `S2.1, S2.2, S2.4`, không cần chép chữ.

### Payload và schema

- Payload gửi `units: [{"id": "S2.1", "text": "…"}]` **thay cho** `content`, không gửi cả hai, để không nhân đôi token input.
- `SupportingQuote(source_id, text)` → `evidence: list[str]`, mỗi phần tử khớp `^S\d+\.\d+$`, tối đa 10 (giữ cùng giới hạn hiện tại).
- Validation giữ nguyên thứ tự hiện tại; chỉ thay hai dòng kiểm quote:
  - mọi ID phải tồn tại trong các đơn vị server đã cấp → nếu không: `unknown_evidence_id` (thay `fabricated_source_quote`);
  - tập nguồn của các ID phải đúng bằng `source_ids` của block (giữ ý nghĩa `missing_cited_source_quotes`, đổi tên `missing_cited_source_evidence`).
- Prompt: thay các dòng hướng dẫn chép quote bằng "chọn ID của mọi đơn vị cần thiết, gồm cả dòng tiêu đề/đơn vị/cột để hiểu ô bảng". Các dòng về groundedness giữ nguyên.
- Manifest benchmark: `verification_protocol=claim-evidence-v3`; `validation_error` trong script dùng chung `validate_review`, nên tự theo.

Ước lượng: khoảng 15–20 dòng ở `claim_verification.py`, khoảng 5 dòng prompt, 1 dòng script, và cập nhật các test đang dùng `quotes` (16 chỗ trong `test_claim_verification.py`, 6 chỗ trong `test_claim_verifier_benchmark.py`).

## Rủi ro và giới hạn — không được nói là đã giải quyết

- **Chọn sai bằng chứng vẫn có thể xảy ra**: model có thể chọn `S2.3` (Revenue) cho claim profit mà vẫn qua kiểm ID. Quote nguyên văn hiện tại cũng có lỗ hổng y hệt; chặn việc này là phần của LLM verdict, không phải code.
- **Bỏ qua phủ định/ngoại lệ nằm ở đơn vị khác**: tương đương quote hiện tại. LLM vẫn thấy toàn bộ đơn vị của nguồn, nhưng code không chứng minh được nó đã đọc.
- **Header/đơn vị**: không tự gắn header vào đơn vị (thêm logic, dễ sai với văn xuôi). Đơn vị/tiền tệ nằm ở dòng Section/Table hoặc câu đầu; prompt yêu cầu chọn chúng nhưng code không ép.
- **Dòng bảng rất dài**: một dòng là một đơn vị dù dài; đã được giới hạn bởi chunk size.
- **Chunk thật khác fixture**: fixture tổng hợp là một dòng văn xuôi; tài liệu thật đa số là dòng bảng/đoạn. Cần một ca dựng từ chunk bảng thật (dạng VietStyle bảng phê duyệt) trước khi tin vào kết quả.
- **So sánh baseline**: prompt/schema đổi nên hash đổi; 28 ca + 12 + 4 chỉ là regression, không phải held-out.

## Test cần có

Unit (không gọi LLM):

1. Cắt đơn vị: dòng bảng, văn xuôi nhiều câu, số `1.5`/`50.000.001` không bị cắt, ghép lại bằng nội dung nguồn.
2. F17 dạng ID rời `S2.1,S2.2,S2.4` → supported.
3. ID không tồn tại (`S2.9`), ID của nguồn không được cite (`S3.1`), thiếu ID cho một nguồn đã cite → bị chặn đúng mã lỗi.
4. Giữ các test hiện có: coverage claim ID, verdict âm chặn cả draft, arithmetic trước LLM, deadline, chỉ nguồn đã cite và đã lọc quyền vào verifier.

LLM thật (mỗi bộ một lượt, output mới, không retry, có trần token như lần trước):

1. F17 riêng → 28 ca → 12 ca → 4 probe.
2. **Trước khi chạy**, soạn vài ca held-out: bằng chứng rời trong cùng nguồn; bẫy phủ định/ngoại lệ ở đơn vị giữa; claim đúng số nhưng chọn được dòng sai metric; một ca từ chunk bảng thật.
3. So với v2 theo từng bộ: giữ câu đúng, câu sai lọt, chặn nhầm, unavailable (theo mã lỗi), token input/output, median audit.

## Cần user quyết định

1. Đồng ý thiết kế (tách theo dòng + câu, không tự gắn header)?
2. Ai soạn/duyệt ca held-out? Có dùng bộ của An nếu có?
3. Ngân sách token cho lượt LLM thật sau khi code xong.

## Kết quả LLM thật lượt đầu (03/11/2026)

`qwen/qwen3.8-27b`, pause 15 giây, mỗi lượt một lần, không retry. Prompt hash v3 `02ab5bae…`, protocol `claim-evidence-v3`.

- F17 riêng (`v3-f17-01`, `GROQ_API_KEY` cũ): supported, C2 chọn `S2.1, S2.2, S2.4` (header, đơn vị, dòng profit; bỏ dòng revenue). 957 input + 69 output token.
- 28 ca bằng `GROQ_API_KEY` cũ (`v3-full-01`, `-02`) và key mới thay thế (`v3-full-03`) dừng vì RateLimitError OTPM (limit 1000; requested 1536, 1211, rồi 3072 đúng bằng `max_output_tokens`). `-03` có F01/F02/F03 đúng trước khi dừng. Giữ cả ba file; không tính vào kết quả.
- 28 ca bằng `GROQ_API_KEY_2` (`v3-full-04`) hoàn tất, không lỗi provider. **Khác key với baseline v2.**

| | v2 (`v2-full-01`) | v3 (`v3-full-04`) |
|---|---:|---:|
| Giữ câu đúng | 10/11 | 11/11 |
| Câu sai lọt | 0 | 0 |
| Chặn đúng câu sai | 17/17 | 17/17 |
| Unavailable | 1 (F17) | 0 |
| Lỗi bằng chứng (`fabricated_source_quote` / `unknown_evidence_id` / `missing_cited_source_evidence`) | 1 | 0 |
| Token input / output / tổng (27 audit) | 18.144 / 1.725 / 19.869 | 20.644 / 1.293 / 21.937 |
| Median audit | 584,87 ms | 556,06 ms |

Chỉ F17 đổi kết quả. Đã đọc evidence của mọi ca supported: đều chọn đúng dòng metric/năm và kèm dòng phạm vi + đơn vị (hoặc header bảng với ca phê duyệt). Đây vẫn là regression bộ đã biết, chưa held-out.

Rủi ro mở: Groq dường như tính trước `max_output_tokens=3072` vào OTPM (suy luận từ trường quota, chưa kiểm chứng). Output thực của v3 chỉ ~36–69 token/ca; hạ trần (ví dụ 768) là việc riêng cần user duyệt vì ảnh hưởng cả web khi bật verifier.

## Bộ 12 ca phát triển — dừng vì OTPM (03/11/2026, 02:07)

`v3-transfer-01` bằng `GROQ_API_KEY_2`: N01 supported, N02/N03 rejected (đều đúng nhãn), N04 RateLimitError OTPM (limit 1000, requested 1432). Dừng, không retry; chưa chạy 4 probe. Token dùng 2.269.

Quan sát lặp lại ở hai key khác nhau (`v3-full-03`, `v3-transfer-01`): ba request đầu qua, request thứ tư bị OTPM với pause 15 giây. Phù hợp giả thuyết provider giữ chỗ `max_output_tokens=3072` theo phút (chưa kiểm chứng với tài liệu Groq). `v3-full-04` chạy đủ 28 ca bằng key 2 trước đó, nên hạn mức có thể còn phụ thuộc workload chung của org.

## Việc còn lại cho verifier

1. ~~Hạ `max_output_tokens`~~ — đã làm, xem mục dưới.
2. ~~Chạy lại 12 ca và 4 probe~~ — đã làm, xem mục dưới.
3. Soạn ca held-out trước khi chạy: bằng chứng rời trong cùng nguồn, phủ định/ngoại lệ ở đơn vị giữa, đúng số nhưng sai dòng metric, một ca từ chunk bảng thật.
4. Sáu câu VietStyle E2E/latency trên VPS (cần build backend; user tự chạy).
5. Verifier web vẫn tắt. Kế hoạch user: ngày tiếp theo chuyển sang reranker.

## Hạ trần output audit xuống 768 (03/11/2026, 02:10)

`claim_verification.py`: hằng `AUDIT_MAX_OUTPUT_TOKENS = 768` thay cho số 3072 viết cứng; script benchmark ghi đúng hằng này vào manifest; test payload khóa giá trị 768. Nếu model nói dài hơn 768 token, JSON bị cắt → `unavailable`, không chứng nhận sai.

Chạy bằng `GROQ_API_KEY_2`, pause 15 giây, mỗi bộ một lượt, **không RateLimitError**:

| Bộ | Giữ đúng | Chặn sai | Sai lọt | Unavailable | Input / output token | Output lớn nhất/ca | Median audit |
|---|---:|---:|---:|---:|---:|---:|---:|
| 12 ca v2 (`v2-transfer-01`) | 5/5 | 7/7 | 0 | 0 | 6.301 / 501 | 99 | 632,18 ms |
| 12 ca v3 (`v3-transfer-02`) | 5/5 | 7/7 | 0 | 0 | 7.094 / 398 | 72 | 540,28 ms |
| 4 probe v2 (`v2-finance-probe-01`) | 3/3 | 1/1 | 0 | 0 | 2.630 / 220 | 102 | 627,44 ms |
| 4 probe v3 (`v3-finance-probe-01`) | 3/3 | 1/1 | 0 | 0 | 3.026 / 186 | 72 | 597,00 ms |

Không ca nào đổi kết quả so với v2. Tổng 10.704 token. Hai lượt trước với 3072 bị OTPM ở request thứ tư; lượt này 16 request liên tiếp qua — phù hợp giả thuyết giữ chỗ theo `max_output_tokens`, nhưng chưa có đối chứng chạy cùng lúc nên chưa kết luận chắc. 28 ca chưa chạy lại với 768.
