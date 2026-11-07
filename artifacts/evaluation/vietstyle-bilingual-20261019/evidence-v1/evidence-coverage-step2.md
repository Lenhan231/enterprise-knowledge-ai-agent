# Bước 2: chấm mức phủ bằng chứng

## Thay đổi so với trước

Trước: chunk có mapping về nguồn nhưng chưa có hàm dùng mapping để chấm bằng chứng.
Sau: `src/core/evaluation/evidence_metrics.py::score_evidence` nhận top-k chunk, nguồn parser đóng băng, bộ nhãn, mã câu hỏi và ngôn ngữ tài liệu. Hàm chỉ đánh giá kết quả đã được retrieval trả về; không thay đổi thứ hạng.

Ví dụ: một bằng chứng nằm ở cả chunk A và B. A riêng lẻ thiếu; B riêng lẻ thiếu; A+B đạt nếu gộp lại phủ đủ phần bằng chứng. Overlap không đếm hai lần. Header lặp không thể thay thế dòng dữ liệu bị thiếu.

## Quy tắc chấm

- Chỉ lấy k chunk đầu tiên; chunk trùng vẫn tốn một vị trí nhưng không tăng mức phủ.
- Khớp document_id + source_parser_index + SHA256 của nguyên đoạn parser. Kiểm tra từng source_spans bằng chuỗi thực tế; thiếu mapping, sai hash hoặc nội dung không khớp thì báo lỗi, không giả thành retrieval miss.
- Gộp những khoảng nguồn thực sự có trong kết quả. Không lấy khoảng từ vị trí nhỏ nhất đến lớn nhất vì như vậy sẽ tính cả phần bị bỏ qua.
- Mỗi span phải được phủ đủ mọi ký tự không phải khoảng trắng. Bỏ qua khác biệt xuống dòng/khoảng trắng; vẫn bắt buộc chữ, số, dấu câu và toán tử. Fraction ký tự chỉ là thông tin chẩn đoán, không phải độ chính xác câu trả lời.
- Một component đạt khi có ít nhất một phương án evidence hoàn chỉnh (OR). Mọi span bên trong phương án đó đều phải đủ (AND). Không ghép các nửa thiếu thuộc hai phương án khác nhau để tuyên bố đạt.
- `required_coverage`: số component bắt buộc đã đủ / số component bắt buộc có nhãn ready. Đây là tỷ lệ component, không phải Recall@10 cũ.
- `full_evidence_success`: tất cả component bắt buộc đủ. Khi còn component bắt buộc pending, giá trị là null và full_intent_eligible=false. Q14 vẫn được báo riêng. Optional không nằm trong mẫu số.
- sources chỉ gồm parser corpus của ngôn ngữ đích. Phải chạy validator nhãn trước khi chấm; scorer kiểm tra thêm các span thực sự sử dụng. Không đưa câu hỏi/đáp án/nhãn vào corpus hay dùng nhãn để chọn chunk.

## Kiểm tra

7 unit tests mới: A/B/A+B; overlap và duplicate; header/sai document/sai parent; mapping thiếu hoặc bị sửa; AND/OR; pending/optional; khoảng trắng so với số bị mất. Cộng 8 targeted tests của bước trước: tổng 15 tests qua. Không tuyên bố toàn bộ test suite của repo đã qua.

Kiểm tra tích hợp trên nguồn thật: 532 đoạn parser Việt và 531 đoạn Anh, qua chunker bước 1 bằng character tokenizer giả để buộc chia nhỏ (3,513 và 3,517 child chunks). Cap kiểm tra theo parent: max(256, độ dài header đã chuẩn hóa + 128), không phải cap model. Cấp tất cả child chunks cho scorer để kiểm tra mapping: cả hai ngôn ngữ đều phủ đủ 62 component bắt buộc ready, 19 intent đủ điều kiện đạt; Q14 giữ null. Cấp danh sách rỗng: không component bắt buộc nào đạt.

Đây là kiểm tra oracle: chủ động cấp toàn bộ chunk, không phải benchmark model và không được báo thành retrieval accuracy. JSON lưu kết quả chi tiết và ví dụ cắt đôi một span thật: A đạt 17/32 ký tự, B đạt 15/32, A+B đạt 32/32.

Chạy lại unit tests từ repo WSL:

```bash
.venv/bin/python -m unittest discover -s tests -p test_evidence_metrics.py -v
```

## Việc tiếp theo

Nối scorer vào benchmark dense offline: tạo chunk có provenance, giữ chúng cạnh vector, lấy đúng top-k của từng model rồi chấm bốn hướng ngôn ngữ. Kết quả sẽ phân biệt tìm đúng tài liệu với lấy đủ bằng chứng. Bước 2 chưa chạy encoder, GPU, translation API, database hay thay đổi retrieval production. Mapping giúp biết A+B có đủ bằng chứng; nó chưa tự khiến retrieval lấy cả A+B. Context expansion/ghép dòng bảng là thay đổi retrieval riêng, cần đo sau.
