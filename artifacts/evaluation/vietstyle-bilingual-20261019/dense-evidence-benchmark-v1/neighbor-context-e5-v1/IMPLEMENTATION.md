# Kiểm tra chunk lân cận — thay đổi và diễn giải

## Code cũ và mới

Trước: script benchmark lấy top 10 dense và chấm evidence v2. Chưa có bước chuẩn bị context lân cận.
Sau: thêm script thử nghiệm riêng `scripts/retrieval/evaluate_neighbor_context.py`; tái sử dụng vector, thứ hạng, metadata nguồn và scorer hiện có. Không sửa embedding_service.py, production retrieval, database/index hoặc cấu hình dịch. Không chạy encoder/GPU, không gọi API.

Các hàm mới:

- `context_candidates`: tạo danh sách seed → chunk trước → chunk sau cho từng seed top 10; bỏ trùng. Neighbor là final chunk_index ±1 trong cùng document/language và trong tập ACL cho phép. Nếu index kế tiếp không tồn tại hoặc không có quyền thì bỏ, không nhảy sang đoạn xa hơn/tài liệu khác. Đây là thứ tự parser trong snapshot, không bảo đảm thứ tự vật lý hàng/trang của PDF.
- `pack_context`: xét lần lượt và chỉ nhận nguyên chunk nếu toàn bộ context sau khi thêm vẫn vừa ngân sách; không cắt đuôi làm mất bằng chứng. Tính cả nhãn `[document_name#chunk_index]`, xuống dòng và dấu phân cách. Chunk không vừa bị bỏ và script vẫn xét các candidate tiếp theo.
- So sánh 3 policy ở cả 2.048/4.096 token được chọn trước khi xem kết quả: dense10, neighbors và dense30. Dense30 xét 30 ứng viên theo thứ hạng rồi đóng gói vừa ngân sách, không luôn đưa đủ 30 chunk vào context. Dense10 không giới hạn chỉ dùng để kiểm tra đúng baseline v2 đã lưu.

Ngân sách dùng tokenizer E5 đã ghim revision như một proxy. Đây là token context gồm nhiều chunk, có thể lớn hơn giới hạn 512 token của một input embedding. Không đổi cap encoder. Khi tích hợp generation phải dùng tokenizer của LLM thực và tính thêm system prompt, câu hỏi, output reserve. Các số này không phải hóa đơn token của cuộc trò chuyện Codex/ChatGPT.

## Kết quả Việt→Việt

| Ngân sách context | Dense top 10 | Thêm trước/sau top 10 | Xét dense top 30 |
|---|---:|---:|---:|
| 2.048 | 16/19 | 13/19 | 16/19 |
| 4.096 | 17/19 | 17/19 | 18/19 |

19 là số intent có nhãn đầy đủ; Q14 vẫn chưa đủ điều kiện. Đây là mức phủ toàn bộ evidence trong context, không phải Recall@10 hay chất lượng câu trả lời được sinh ra.

- Neighbor giúp Q13 đạt đủ ở cả hai mức ngân sách. Nó thêm đúng SOP parser index 1 (chuẩn bị/blind count) và index 4 (cập nhật không xóa lịch sử).
- Ở 2.048, cách xen kẽ neighbor làm rơi các phần cần thiết của Q07/Q12/Q16/Q17 so với dense10 cùng ngân sách. Lợi Q13 nhưng mất 4 câu khác nên tổng giảm 3 câu.
- Ở 4.096, neighbor giúp Q13 nhưng mất Q11.block_checks; context bị đầy trước khi giữ đủ checklist. Q20 vẫn thiếu luồng duyệt; thêm các đoạn kế bên seed hiện tại không bảo đảm chạm đúng bảng duyệt ở Manual index 13. Một số seed quan trọng của Q20 còn bị neighbor lấn chỗ.
- Dense30 ở 4.096 cải thiện Q20, không làm câu Việt→Việt nào giảm full-evidence so với dense10 cùng trần. Nhưng Q13 vẫn thiếu chuẩn bị/blind count. Chưa chứng minh khả năng tổng quát hóa.
- Dense10 ở trần4.096 thực dùng trung bình2.417 token; neighbor4.022; dense30 khoảng4.043. Nghĩa là neighbor tốn thêm khoảng66% context mà không tăng số câu đủ bằng chứng; dense30 thêm khoảng67% để tăng1 câu. Đây chỉ là proxy token, không phải giá API hoặc latency generation.

Chưa nên bật neighbor tự động đại trà theo policy xen kẽ này. Bước hợp lý tiếp theo: thử reranker trên candidate pool rộng với ngân sách context cố định; nếu tiếp tục thử neighbor thì cần ưu tiên seed và chỉ mở rộng khi có dấu hiệu câu hỏi đòi nhiều bước. Không hardcode Q13 hoặc dùng nhãn để điều khiển ranking. Cần đo lại toàn bộ bộ câu hỏi, kiểm tra hồi quy và tách tập phát triển/đánh giá mới trước quyết định production. Đây là tập nhỏ đã được phân tích lỗi và sửa nhãn, không phải held-out test.

## Token tiếng Việt và tiếng Anh

Đếm raw text của cùng20 ý hỏi ghép cặp, không thêm prefix/instruction/special token:

| Tokenizer | Việt | Anh | Việt/Anh |
|---|---:|---:|---:|
| multilingual-e5-base | 549 | 553 | 0,99× |
| BGE-M3 | 549 | 553 | 0,99× |
| Qwen3 embedding0.6B | 578 | 500 | 1,16× |

Không có quy luật rằng tiếng Việt luôn tốn gấp một số lần cố định. Tokenizer và cách diễn đạt bản dịch đều ảnh hưởng. Kết quả trên chỉ áp dụng cho bộ câu hỏi và các tokenizer này; không suy ra token count/chi phí của model hội thoại hiện tại. Nếu đo chi phí generation cần đếm toàn bộ prompt/answer bằng tokenizer thực của LLM đó.

## Kiểm tra và chạy lại

4 unit tests mới kiểm tra ACL/ngôn ngữ/document boundaries, không nhảy qua index trống, bỏ trùng, cách tính ngân sách có citation/separator, không cắt chunk và ghép hai nửa evidence. Cộng15 evidence tests hiện có:19 tests qua. Kiểm chứng80 thứ hạng gốc, baseline bằng kết quả v2,560 context variants được chấm và kiểm tra mức phủ ký tự độc lập. Một kiểm tra bổ sung đối chiếu560 context về identity/ACL/ngôn ngữ/neighbor relation và giới hạn token ghi nhận.

```bash
.venv/bin/python -m unittest discover -s tests -p test_neighbor_context.py -v
HF_HUB_OFFLINE=1 OMP_NUM_THREADS=4 MKL_NUM_THREADS=4 TOKENIZERS_PARALLELISM=false .venv/bin/python scripts/retrieval/evaluate_neighbor_context.py --output-dir artifacts/evaluation/neighbor-context-repeat
```

Kết quả mặc định hiện đã tồn tại, vì vậy dùng output-dir mới khi chạy lại. Tokenizer tải từ cache local; không tải encoder. Thời gian trong report chỉ là lập context + đếm token local, không phải end-to-end retrieval/generation latency. Mọi nhãn/đáp án chỉ dùng để chấm sau khi lựa chọn xong; không index hoặc dùng để chọn neighbor.
