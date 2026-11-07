# Bộ kiểm tra mới cho Review 2 — heldout-review2-v1

Trạng thái: **reviewed-r1**, đã áp dụng H10/H13/H19 theo yêu cầu người dùng trước lần inference đầu. Bản nháp và kết quả rà soát cũ được giữ trong `history/draft-before-approved-edits.zip`. Xem `CHANGELOG.vi.md`; kết quả lần chạy thực tế nằm trong `runs/`.
Bộ cũ giữ làm development/regression. Không sửa câu hỏi, nhãn hoặc bản dịch sau khi thấy kết quả bộ này; nếu nhãn sai, ghi errata và tạo phiên bản mới.

## Cấu trúc và phạm vi

- 20 ý câu hỏi H01–H20, mỗi ý có bản VI và EN: **40 văn bản câu hỏi, 80 ca chạy** theo VI→VI, VI→EN, EN→VI, EN→EN. Chỉ có 20 ý độc lập, không phải 80 câu độc lập.
- Mỗi nhóm có 5 ý: nội dung văn bản; bảng/số liệu; kết hợp hai chunk; diễn đạt lại/thuật ngữ.
- `REVIEW.md`: câu hỏi, đáp án tham chiếu, trích dẫn nguồn/offset để người đọc duyệt. `review.csv`: checklist có thể điền tay.
- `questions.json`, `cases.json`, `evidence.json`: đầu vào máy chấm. Nhãn bằng chứng là nhãn đáp án, không được gửi cho retriever hoặc translator.
- `inputs/`: bản chụp parser VI/EN, corpus 1.063 chunk (532 VI + 531 EN), E5 document vectors, PostgreSQL lexemes. Không lệ thuộc dữ liệu đang thay đổi trên Supabase.
- `code/` và `run.py`: bản chụp logic retrieval/chấm điểm; `protocol.json` và `manifest.json`: cấu hình và SHA-256 cố định.
- `prepared/`: bản dịch tự động + query lexemes, tạo một lần và dùng lại.
- `runs/<tên-lần-chạy>/`: toàn bộ kết quả của lần chạy đó. Không ghi đè lần chạy cũ.

Mỗi ca tìm trên cả 5 tài liệu thuộc ngôn ngữ đích, với quyền admin và document-language mapping đã biết. Đây là phép đo có kiểm soát, không phải cấu hình tìm trên toàn kho production.
Câu hỏi mới vẫn dùng corpus mô phỏng đã biết, do trợ lý soạn có biết bộ development. `overlap-audit.json` ghi chủ đề liên quan và so khớp chữ; không chứng minh độc lập về nghĩa hoặc tổng quát hóa sang doanh nghiệp khác.

## Model và phương pháp

E5 `intfloat/multilingual-e5-base`, 768 chiều, normalize, `query: `/`passage: `, encoder 512 token. Reranker `BAAI/bge-reranker-v2-m3`, FP32, batch 4, tối đa 1.024 token/cặp. Revision được khóa trong protocol. Candidate 30, kết quả cuối 10, RRF k=60, trọng số dense=1/BM25=2.

So sánh dense; dense + BGE; translated hybrid trước rerank; translated hybrid + BGE. Nhánh hybrid thô dùng cùng candidate pool với nhánh rerank để tách tác động reranker.
Bản EN do người soạn cung cấp dùng làm một câu hỏi đầu vào riêng, **không dùng làm bản dịch oracle** cho câu VI. Translator chỉ thấy câu hỏi gốc.

## Metric giữ như bộ trước

- Precision@10, Recall@10, MRR@10, nDCG@10.
- Full evidence@10: đủ tất cả thành phần bắt buộc; Component coverage@10: tỷ lệ thành phần đủ bằng chứng.
- Retrieval latency: trung bình, median, p95; tách theo 4 hướng ngôn ngữ và nhóm câu hỏi.

Gold chunk là chunk có giao ký tự nguồn không trắng với một đoạn bằng chứng bắt buộc, bao gồm các cách dẫn chứng thay thế và đoạn bằng chứng bị chia. Một chunk có giao chưa chắc đủ trả lời; full/component evidence đo thêm điều đó. Precision có trần tùy số gold chunk từng ca. Nhãn không bao phủ mọi cách diễn đạt đúng ngoài các đoạn đã gán.
Latency là các giai đoạn đã warm up: encode query + retrieve + rerank; dùng lại bản dịch nên **không bao gồm gọi API dịch, sinh câu trả lời hoặc tải model**. Thời gian API lần chuẩn bị lưu riêng trong translations.json. Encode đo một lần/văn bản câu hỏi và dùng chung hai corpus đích; không phải 80 phép đo encode độc lập. Không gộp latency SQL với offline. Không đo ROUGE/BLEU/faithfulness hay chất lượng câu trả lời LLM trong bộ retrieval này; phần generation cần An chạy riêng theo proposal/Review 2.

## Kiểm tra và chạy lại (WSL, từ gốc project)

Dùng `.venv` hiện tại; không cần cài lại hoặc tải lại model đã có cache. Không kèm `.env`, API key hoặc trọng số model trong thư mục này.

```bash
.venv/bin/python artifacts/evaluation/heldout-review2-v1/run.py verify
```

Lệnh trên chỉ kiểm tra hash, nhãn, corpus và khả năng ghép bằng chứng; không gọi model/API. Sau khi thực sự đọc duyệt REVIEW.md, có thể lưu tên người duyệt:

```bash
.venv/bin/python artifacts/evaluation/heldout-review2-v1/run.py review --reviewer Huy
```

**Chuẩn bị một lần**, khi đã đồng ý gửi 40 câu hỏi mô phỏng tới Groq. Cần `.env` có GROQ_API_KEY, GROQ_MODEL=openai/gpt-oss-20b và DATABASE_URL. Không gửi tài liệu, đáp án tham chiếu hay nhãn bằng chứng; PostgreSQL chỉ được dùng đọc để tạo query lexemes.

```bash
.venv/bin/python artifacts/evaluation/heldout-review2-v1/run.py prepare --allow-groq
```

Chạy benchmark với GPU, model cache và SQL production trên **bảng tạm** chứa corpus cố định, không sửa bảng public hoặc vector production:

```bash
.venv/bin/python artifacts/evaluation/heldout-review2-v1/run.py run --name review2-run-01
```

Sau đó xem `runs/review2-run-01/metrics.csv`, `results.json` (từng ca, thứ hạng, bằng chứng thiếu), `config.json`, `verification.json`. Query vectors và reranker logits được lưu để kiểm tra lại cách tính điểm.

```bash
.venv/bin/python artifacts/evaluation/heldout-review2-v1/run.py verify-run artifacts/evaluation/heldout-review2-v1/runs/review2-run-01
.venv/bin/python artifacts/evaluation/heldout-review2-v1/run.py run --name review2-run-02
```

`verify-run` kiểm lại artifact, logits, thứ hạng và metric, **không chạy inference mới**. Lệnh `run` với tên mới mới thực sự chạy lại model. Nếu dùng Colab không nối database, mang cả folder và dùng `--backend offline` sau khi prepared đã hoàn tất; điểm/latency phải ghi rõ backend. Nếu thiếu model cache thì chỉ tải khi chủ động thêm `--allow-download`. So sánh số đo giữa máy khác cần ghi GPU, phiên bản thư viện, backend; không kỳ vọng latency giống hệt.

Lệnh run lưu checkpoint kết quả sau mỗi ca. Run bị ngắt mang trạng thái chưa hoàn tất/failed, không đưa vào báo cáo tổng; hiện chưa hỗ trợ tiếp tục giữa chừng, hãy chạy tên mới. Phải giữ cả prepared/ lẫn runs/ khi chuyển máy để kiểm tra lại đầy đủ.
