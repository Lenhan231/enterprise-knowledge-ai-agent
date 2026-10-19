# Bước 3: nối evidence vào benchmark dense

## Đã thay đổi gì so với code cũ?

1. `scripts/retrieval/evaluate_embedding_candidates.py`: trước đây `score_case` chỉ chấm tìm đúng file (hoặc trang ở bộ tài liệu cũ). Giờ nhận thêm evidence_context tùy chọn: sau khi dense lấy top 10, chuyển đúng 10 chunk đó sang scorer bước 2. Không dùng nhãn để tìm/chọn chunk. Snapshot cũ không có evidence vẫn dùng cách chấm cũ.
2. `load_evidence_context` kiểm tra hash nhãn, nguồn, câu hỏi và mapping trước khi tải encoder. Candidate revision được ghim theo snapshot. `summarize_evidence` báo riêng 4 hướng, số component bắt buộc được phủ và số câu có đủ bằng chứng. Q14 loại khỏi mẫu số full-intent, vẫn chấm các component đã rõ. Vector câu hỏi có SHA256 để phát lại kiểm tra.
3. Thêm `scripts/retrieval/prepare_vietstyle_evidence_benchmark.py`: đóng băng 5 tài liệu Việt + 5 bản Anh. Dùng shared chunker của bước 1 với tokenizer Qwen đã ghim để tạo cùng một tập chunk cho cả 3 encoder. Có 532 chunk Việt + 531 chunk Anh; ở cap 512 không parent nào phải chia thêm. Token preflight kiểm tra lại input đầy đủ của từng encoder, gồm prefix/instruction/special tokens: E5 tối đa 476, BGE 474, Qwen 425 token. Không bị truncation. Metadata embedding_model trong frozen chunks ghi tokenizer dùng cho bước chuẩn bị; model tạo vector thực tế được ghi riêng chính xác trong candidate config.json.
4. Thêm `scripts/retrieval/compare_vietstyle_evidence.py`: không tải encoder; đọc vector đã lưu, tự tính lại top 10 bằng phép nhân vector và stable sort, rồi dùng tập vị trí ký tự để đối chiếu mức phủ evidence. Đây là cách kiểm tra khác với phép gộp interval của scorer. Script sinh comparison.md và replay-verification.json.
5. Thêm 4 test trong `tests/test_evidence_benchmark.py`: scope ngôn ngữ và đúng top 10; ACL và tie order; chế độ benchmark cũ không cần mapping; Q14/pending không làm sai mẫu số. 11 test evidence/scorer đã qua, cùng 4 test mapping trước đó.

## Cách đọc kết quả

- **required_component_coverage_at_10**: có bao nhiêu ý bằng chứng bắt buộc đã đủ / 62 ý ready. Không phải phần trăm ký tự.
- **full_evidence_success_rate_at_10**: bao nhiêu câu có đủ mọi ý bắt buộc / 19 câu có nhãn hoàn chỉnh. Q14 được báo riêng.
- Một câu có 3 ý, lấy đủ 2 ý: component score = 2/3, full evidence = chưa đạt.
- A+B cùng phủ một ý thì được gộp; overlap không đếm trùng. Lấy đúng file nhưng sai đoạn vẫn có thể thiếu bằng chứng.
- Điểm file cũ vẫn lưu để chẩn đoán. Không so sánh trực tiếp phần trăm file cũ với phần trăm evidence mới.

Có 20 ý hỏi, mỗi ý có câu Việt và câu Anh. Mỗi câu được tìm trong corpus Việt và corpus Anh: 80 lượt/model. Đây là 20 ý tái sử dụng, không phải 80 câu độc lập.

Mỗi lượt chỉ tìm trong cả 5 tài liệu của ngôn ngữ đích, không lọc theo đáp án/gold document. language trong snapshot là metadata thí nghiệm; chưa thêm cột language vào database và chưa kiểm tra chọn ngôn ngữ tự động trong production.

## Chạy lại

Trong terminal WSL tại thư mục repo:

```bash
export HF_HUB_OFFLINE=1 OMP_NUM_THREADS=4 MKL_NUM_THREADS=4
# Snapshot hiện tại đã có, không chạy prepare đè lên nó.
# Muốn tạo snapshot mới: thêm --output-dir artifacts/evaluation/<tên-mới>
.venv/bin/python scripts/retrieval/prepare_vietstyle_evidence_benchmark.py --output-dir artifacts/evaluation/vietstyle-evidence-repeat

.venv/bin/python scripts/retrieval/evaluate_embedding_candidates.py --snapshot artifacts/evaluation/vietstyle-evidence-repeat --model multilingual-e5-base --device cuda --batch-size 2
.venv/bin/python scripts/retrieval/evaluate_embedding_candidates.py --snapshot artifacts/evaluation/vietstyle-evidence-repeat --model bge-m3 --device cuda --batch-size 2
.venv/bin/python scripts/retrieval/evaluate_embedding_candidates.py --snapshot artifacts/evaluation/vietstyle-evidence-repeat --model qwen3-embedding-0.6b --device cuda --batch-size 1
.venv/bin/python scripts/retrieval/compare_vietstyle_evidence.py --snapshot artifacts/evaluation/vietstyle-evidence-repeat
```

Chỉ phát lại kiểm tra kết quả hiện tại, không dùng GPU:

```bash
.venv/bin/python scripts/retrieval/compare_vietstyle_evidence.py
.venv/bin/python -m unittest discover -s tests -p 'test_evidence*.py' -v
```

Model weights dùng cache local và GPU RTX 2060, float32, cap 512. Không đổi embedding_service.py, live database/vector index, production retrieval hoặc translation. Không gọi API dịch/generation. Thời gian local retrieval không gồm evidence scoring, không phải latency database thực tế. Kết quả và code hiện chưa commit.

## Giới hạn cần nhớ

Nhãn và bản Anh do assistant chuẩn bị, chưa được người phụ trách xác nhận độc lập; có thể còn bằng chứng tương đương chưa gán nhãn. Trước khi quyết định model cuối cùng, nên đọc các câu mất điểm để tách lỗi retrieval thật khỏi thiếu alternative evidence. Chấm evidence không chấm câu trả lời được LLM sinh ra. Bước này chưa thêm tự mở rộng chunk lân cận, chưa sửa cách chia dòng bảng. Kết quả chỉ so sánh ba candidate hiện tại, chưa chạy MiniLM theo metric evidence mới.
