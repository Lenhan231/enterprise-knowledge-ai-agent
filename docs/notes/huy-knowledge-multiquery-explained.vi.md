# Ghi chú cho Huy: Knowledge tìm bằng chứng theo nhiều ý

Ngày 31/10/2026, cập nhật 01/11/2026. Đã triển khai trên máy; chưa commit/deploy.

**Công tắc mới:** `KNOWLEDGE_MULTIQUERY_ENABLED=1` mới bật cơ chế. Không khai báo, đặt `0` hoặc giá trị khác thì dùng luồng một câu gốc. Bảng mô tả `decompose=True` bên dưới áp dụng khi đã bật công tắc. Đây là phần bổ sung sau bản sửa context bảng, không thay E5 hay thay dữ liệu Supabase.

## Đọc nhanh

Câu hỏi nhiều ý có thể làm một nhóm bằng chứng lấn át nhóm khác. Mình tách tối đa hai câu tìm kiếm, tìm riêng, gộp bằng chứng rồi trả lời câu gốc một lần.

```text
Câu gốc: ai duyệt khoản 80 triệu, cần báo giá gì, PO phát hành khi nào?
  → planner: câu về duyệt/báo giá + câu về phát hành PO
  → retrieval câu 1: bảng phê duyệt 781
  → retrieval câu 2: điều kiện PO 300/791
  → gộp, bỏ trùng, đánh lại S1/S2...
  → LLM trả lời câu gốc, có nguồn cho từng ý
```

Không tách bằng cách đếm chữ “và”. “So sánh hai mức tiền về phê duyệt” có thể vẫn chỉ cần một nhóm bằng chứng.

## Vì sao cần làm?

Trên câu thử EN tìm toàn kho:
- Bảng phê duyệt 781: dense hạng 31, BM25 EN hạng 126, BM25 VI hạng 86.
- Bảng 781 không lọt 30 ứng viên sau fusion, nên BGE không được chấm nó.
- Bảng điều kiện PO 791 lọt fusion hạng 11 rồi được BGE đưa lên hạng 1.
- Tăng kết quả cuối từ 5 lên 10 vẫn thiếu 781, do vẫn dùng 30 ứng viên fusion.
- Tách thủ công: 781 lên hạng 1 cho câu duyệt/báo giá; 300 và 791 đứng đầu cho câu PO.

Đây là lỗi thiếu bao phủ các ý trong lượt retrieval, không phải bằng chứng E5 cần fine-tune hoặc bảng chưa được đọc.

## File nào làm gì?

| File | Nhiệm vụ |
|---|---|
| `src/core/prompts/knowledge_search.py` | Chỉ dẫn LLM tạo JSON với 1 hoặc 2 câu tìm kiếm |
| `src/core/rag/rag_service.py` | Kiểm tra kế hoạch, gọi retrieval, gộp context, gọi generation |
| `src/core/agents/knowledge_agent.py` | Bật cơ chế này cho Knowledge trả lời bằng `decompose=True` |
| `src/core/latency.py` | Thêm thời gian `knowledge_search_planning` vào monitoring |
| `tests/test_knowledge_search_plan.py` | Kiểm tra các nhánh logic mới |
| `tests/test_knowledge_outcomes.py` | Cập nhật kiểm tra lời gọi từ KnowledgeAgent |

Không sửa routing của An. `KnowledgeAgent.retrieve()` lấy bằng chứng thô cho Report vẫn giữ hành vi cũ. `generate_answer()` mặc định `decompose=False`, nên caller khác không tự đổi hành vi; luồng Knowledge trả lời chủ động bật True. Auto nếu gọi chính KnowledgeAgent.run cũng đi qua bước này, nhưng không sửa bộ lập kế hoạch Auto.

## 1. Planner chỉ lập câu tìm kiếm

```python
questions = self._search_questions(question)
```

- Gửi câu hỏi gốc, không gửi nội dung tài liệu cho planner.
- Prompt yêu cầu giữ ngôn ngữ, đối tượng, tiền, đơn vị và phạm vi tài liệu/section; không bịa dữ kiện hoặc quyền.
- Đầu ra phải là JSON có đúng trường `questions`, từ 1 tới 2 chuỗi không rỗng, mỗi chuỗi tối đa 4.000 ký tự, không trùng nhau.
- Nếu chỉ có 1 câu, code dùng lại câu gốc, không dùng bản viết lại của LLM.
- Sai JSON/schema hoặc API lỗi: quay về câu gốc và ghi loại lỗi trong log.
- Planner tối đa 256 output token, timeout tối đa 15 giây hoặc deadline còn lại nếu ngắn hơn.
- Timeout/quyền truy cập không bị biến thành fallback bỏ qua giới hạn.

Việc giữ đúng nghĩa và mọi chi tiết của hai câu nhỏ vẫn phụ thuộc LLM; JSON hợp lệ không chứng minh tách đúng nghĩa. Đây là giới hạn cần kiểm thử.

## 2. Hai câu vẫn đi qua retrieval cũ

```python
for query in questions:
    groups.append(self.retrieve_contexts(query, ...))
```

Mỗi câu có tối đa 5 kết quả (hoặc `limit` nhỏ hơn do caller yêu cầu). Chạy tuần tự, không tạo thread song song mới. Giữ nguyên company, roles, document_ids, metadata_filter, ngôn ngữ và phương pháp retrieval từ caller cho mọi câu.

Không để planner chọn hoặc mở rộng quyền. DB vẫn lọc trạng thái ready/active và ACL như trước. Không bắt lỗi PermissionError để truy xuất lại bằng quyền rộng hơn.

`remaining()` kiểm tra deadline trước mỗi lượt tìm kiếm và trước generation; không tự cấp thêm thời gian cho request.

## 3. Gộp context

```python
contexts = _merge_contexts(groups)
```

Ví dụ:

```text
Nhánh A: 781, 780, 286
Nhánh B: 300, 791, 781
Gộp:    781, 300, 780, 791, 286
```

- Lấy xen kẽ theo hạng để giữ chỗ cho cả hai nhánh.
- Nhận diện trùng bằng chunk_id; nếu thiếu thì document_id + chunk_index.
- Tối đa 10 chunk và 24.000 ký tự context đã format (gồm nhãn nguồn).
- Chunk quá dài không vừa ngân sách bị bỏ qua nguyên chunk; không cắt giữa bảng.
- Đánh lại source_id S1, S2... vì mỗi lượt retrieval trước đó đều có S1 riêng.
- Không rerank lại toàn bộ theo câu gốc, tránh một ý lại chiếm ưu thế.
- Không sửa các dictionary context gốc.

Kiểm tra thêm: nếu một trong hai nhánh không có chunk nào còn lại trong context cuối, không gọi LLM để tạo đáp án đầy đủ. Trả thông báo thiếu thông tin. Nếu cả hai lượt đều không tìm thấy gì, giữ thông báo không có tài liệu phù hợp.

Có chunk từ mỗi nhánh chỉ là điều kiện tối thiểu; chưa chứng minh chúng thật sự đủ bằng chứng. Prompt trả lời vẫn yêu cầu từ chối khi thiếu.

## 4. Trả lời câu gốc một lần

```python
self.generate_from_contexts(question, contexts)
```

Vẫn dùng prompt Knowledge hiện có và kiểm tra citation hiện có. Các mã nguồn trong đáp án phải thuộc tập context. Không thay đổi kiểu response, không thêm context_status.

Lưu ý kiểm tra citation mới bảo đảm mã nguồn tồn tại; không tự chứng minh mọi phát biểu đều được nguồn hỗ trợ. Người chấm vẫn cần xem nội dung, đặc biệt chữ “đã duyệt” trong ngoại lệ.

## 5. Kết quả đã kiểm tra

40 test đạt trong hai lượt:
- 21 test: search plan, knowledge outcomes, latency tracking, pipeline latency report.
- 19 test: orchestration contracts, bounded execution.

Bao gồm: đúng scope ở cả hai câu, không sửa input, bỏ trùng và đánh lại nguồn, không cắt context, giới hạn 10 chunk, thiếu một nhánh, cả hai nhánh rỗng, planner lỗi, câu đơn, PermissionError, hết deadline, caller mặc định không tự bật planner.

API thật:
- Planner đã tạo đúng hai câu nhỏ cho ca EN nhiều ý.
- Có lần thử liên tiếp gặp Groq 429 (rate limit); planner có fallback. Không coi các lần fallback đó là planner tự nhận diện câu đơn thành công.
- Sau giới hạn planner 256 output token, một lượt hoàn chỉnh với LLM thật + retrieval replay đã thành công: đáp án đủ phê duyệt, báo giá/ngoại lệ đã duyệt và điều kiện PO; citation S1/S2/S4 đúng tập bằng chứng.
- Planner khoảng 904 ms; generation khoảng 807 ms trong lượt replay. KHÔNG phải latency toàn hệ thống: không có embedding, translation, database search hay BGE thật trong lượt này.

Replay là gì? Dùng lại danh sách chunk retrieval do Huy đã chạy trên VPS, chỉ phát lại theo nhánh tương ứng. Nó kiểm tra luồng planner/gộp/generation, KHÔNG xác nhận rằng câu nhỏ do planner tự viết sẽ lấy ra đúng cùng kết quả trên VPS.

Kết quả local: `artifacts/local/knowledge-multiquery-20261031/automatic-plan-replay.json` và `live-plan.json`. Không đưa nội dung nguồn này vào Git.

Giới hạn kiểm tra:
- `test_retrieval_callers` và `test_rag` còn import `_RESPONSE_CACHE` đã không tồn tại trước bản sửa.
- Một assertion cũ trong `test_translated_hybrid` yêu cầu `d.company`, trong khi SQL hiện dùng company trong chunk metadata. Không sửa kiểm tra này trong task hiện tại.
- Chưa chạy pipeline mới với embedding/reranker thật của VPS, chưa đo latency VPS, chưa chạy lại đủ 6 câu EN/VI sau thay đổi.

## 6. Cần kiểm tra trước khi deploy rộng

1. Review code và commit/push khi Huy yêu cầu.
2. Trên VPS thử đúng câu 6 EN bằng cơ chế mới và giữ toàn bộ scope cũ.
3. Kiểm tra các câu nhỏ thực tế, context đủ 781/791 hoặc bằng chứng tương đương, đáp án đủ và có nguồn.
4. Chạy lại 6 câu EN/VI, cộng câu không có đáp án và kiểm tra thu hồi quyền.
5. Đo tổng latency và từng stage, đặc biệt planner + hai lượt BGE; so với bản cũ.

Chưa cần embedding lại vì không thay nội dung chỉ mục.

## 7. Chi phí và rủi ro cần nhớ

Mọi lượt Knowledge trả lời thêm một lần planner, kể cả câu đơn. Câu tách hai ý có hai lượt retrieval, nên tăng thời gian embedding/dịch/rerank. Nếu VPS không còn đủ deadline, request có thể hết thời gian.

Planner và generation dùng cùng GroqProvider, nên dùng chung quota/cooldown. Planner API lỗi có thể fallback, nhưng nếu quota của cả tài khoản hết thì bước tạo câu trả lời cũng có thể thất bại; fallback không tạo thêm quota. Chưa thay cơ chế retry/model/key hay hạ ngân sách câu trả lời để né lỗi này.

Chỉ hỗ trợ tối đa hai ý tìm kiếm. Không bảo đảm đúng mọi câu nhiều ý. Đây là bản thay đổi local để review và kiểm tra tiếp, chưa phải xác nhận sẵn sàng production.

## Kiểm tra sẵn sàng tích hợp ngày 01/11/2026

Main mới nhất lúc kiểm tra: `d77e634`, thêm ba commit sau `906902e` (layout/chart, dependency parser, cache PaddleX). Huy chưa tự merge ba commit mới trong lượt đánh giá này.

Đã tạo checkout tạm từ main `d77e634` rồi áp đúng patch multiquery và hai file runtime/test mới, không tạo commit. Patch áp sạch. Tổng 133 test đạt: 115 Knowledge/orchestration/deadline/latency/API services/SQL/metrics/table-context, 10 API chat/Report, 8 Docling table sections/Word semantics/chart recognition. `uv lock --check` và whitespace check đạt. Cài bổ sung python-docx (dependency có sẵn trong project) vào môi trường kiểm thử local để chạy test API/Report; không sửa dependency dự án.

Kết luận: có thể đưa phần sửa vào main để deploy kiểm thử có kiểm soát; chưa coi là được kiểm chứng production. Chỉ phần multiquery yêu cầu rebuild backend-api; nếu triển khai cả parser/layout mới của main thì parser là phạm vi cập nhật riêng cần kiểm tra riêng.

Chưa build Docker (máy không có docker), chưa chạy embedding/reranker thực tế trên VPS hoặc kiểm chứng quota/latency dưới tải; chưa chạy full suite và UI Streamlit. Không cần migration hoặc embedding lại cho riêng multiquery. Sau deploy phải thử ca 6 EN, một câu đơn, một ca không đủ bằng chứng và quyền bị thu hồi; nếu latency/quota không đạt thì tắt `decompose=True` ở KnowledgeAgent và rebuild backend.

## Công tắc thử nghiệm và rollback

Thêm vào `.env` trên VPS sau khi deploy code:

```dotenv
KNOWLEDGE_MULTIQUERY_ENABLED=1
```

Nếu không ổn, đổi thành `0`. Với code đã có trong image, áp dụng thay đổi môi trường bằng:

```bash
docker compose up -d --no-deps --force-recreate --wait --wait-timeout 180 backend-api
```

`docker compose restart` không nạp lại `.env` vào container hiện có. Lần đầu deploy code vẫn cần `--build`. Backend đọc công tắc từ môi trường server, không nhận quyền bật/tắt từ nội dung câu hỏi hoặc metadata người dùng. Không cần cập nhật DB hay embedding khi bật/tắt.

Fallback planner tự động và rollback khác nhau: fallback chỉ xử lý lỗi lập kế hoạch; công tắc 0 bỏ hẳn bước planner và quay về luồng cũ. Công tắc không giải quyết lỗi quota chung của Groq hoặc lỗi vốn có của retrieval.
