# Phần thuyết trình Huy — Review 2, bản ngày 26/10/2026

Lời nói bằng tiếng Việt; nội dung slide giữ tiếng Anh. Bản cập nhật thay cho dàn ý theo số slide cũ ngày 22/10.

## Lời thuyết trình tiếng Việt — dùng bản này khi tập nói

Nội dung trình chiếu vẫn bằng tiếng Anh. Phần này là lời nói tiếng Việt theo slide 10–14, khoảng 5 phút tùy tốc độ. Không cần đọc mọi con số; bấm giờ khi tập. Các phần kiểm chứng và nguồn chi tiết nằm bên dưới.

### Mở phần

“Tiếp theo, em trình bày cách nhóm chuẩn bị các đoạn tài liệu cho embedding, tổ chức tìm kiếm bằng chứng và đánh giá chất lượng retrieval. Phần này được đánh giá riêng với chất lượng câu trả lời của LLM.”

### Slide 10 — Tokenization, Chunking, and Provenance

**Ý cần nhớ: giữ cấu trúc → kiểm tra token → giữ thông tin nguồn.**

“Sau parsing, hệ thống nhận văn bản, bảng và thông tin nguồn mà parser trích xuất được. Ở bước chunking, văn bản được chia ưu tiên theo ranh giới câu; bảng được chia theo nhóm hàng và lặp lại header khi có, để các giá trị vẫn gắn với tên cột.

Sau đó, hệ thống dùng tokenizer của embedding model để kiểm tra độ dài đầu vào. Nếu đoạn quá dài thì chia thêm trước khi tạo vector. Kích thước ký tự và số token là hai đơn vị khác nhau, nên một đoạn đạt mục tiêu ký tự vẫn cần được kiểm tra bằng tokenizer.

Hệ thống cũng giữ định danh tài liệu, chỉ số chunk và vị trí trang, section hoặc bảng khi có, để các đoạn truy hồi có thể dẫn lại về nguồn.”

**Nếu hỏi sâu:** 1.100 ký tự là mục tiêu parser, không phải mọi chunk dài đúng hoặc tối đa 1.100. Một hàng dài có thể giữ nguyên ở parser nhưng bị chia ở bước token. Chưa có ablation chứng minh chunk size hoặc overlap tối ưu. Không nói main có đầy đủ source spans ký tự như nhánh Huy.

### Slide 11 — Embedding Model and Index Design

**Ý cần nhớ: E5 tạo vector tương thích cho query và tài liệu; lựa chọn có pilot hỗ trợ.**

“Nhóm dùng multilingual E5-base, tạo vector 768 chiều được chuẩn hóa, với giới hạn đầu vào 512 token. Câu hỏi có prefix query, còn đoạn tài liệu có prefix passage để đúng cách sử dụng model.

Các vector được lưu trong PostgreSQL với pgvector, tìm theo cosine similarity và có giới hạn phạm vi tài liệu, quyền truy cập. Đầu ra parser được lưu riêng với các đoạn đã có vector.

Về lựa chọn model, em đã so sánh năm embedding model trên cùng bộ tài liệu VietStyle. E5-base đạt expected-source recall cao nhất trong pilot, nên được chọn cho pipeline này. Tuy nhiên, đây là kết quả trên dữ liệu của nhóm, không phải khẳng định E5 tốt nhất ở mọi bài toán.”

**Nếu hỏi số pilot:** E5 93,33%; MiniLM 80%; BGE-M3 89,17%; Qwen 86,67%; e5-large-v2 78,33%. Pilot đo tìm đúng file nguồn, không phải đủ bằng chứng hoặc answer accuracy. BGE-M3 embedding khác BGE reranker-v2-m3.

### Slide 12 — Retrieval and Reranking Pipeline

**Ý cần nhớ: hai tín hiệu tìm ứng viên → RRF hợp nhất → BGE xếp lại.**

“Pipeline có hai nhánh. Query gốc được E5 mã hóa để tìm các đoạn gần về ngữ nghĩa. Nhánh lexical dùng các phiên bản query tiếng Việt và tiếng Anh với BM25 để bổ sung tín hiệu khớp từ khóa.

Hai nhánh không chia đôi kho tài liệu mà cùng tìm trong phạm vi được phép. RRF hợp nhất kết quả theo thứ hạng, thay vì cộng trực tiếp cosine score với BM25 score vì chúng khác thang đo.

Sau đó BGE đọc từng cặp câu hỏi gốc và chunk để xếp lại ứng viên. Trong benchmark của em, bước này nhận 30 ứng viên và đánh giá top 10. Trong ứng dụng, số đoạn cuối có thể cấu hình; các đoạn còn qua bước đóng gói context trước khi đưa vào LLM.”

**Nếu hỏi sâu:** RRF benchmark dùng k bằng 60, trọng số dense 1 và lexical 2; không phải quota lấy 15 dense và 15 BM25. Top 10 thuộc benchmark; main RAG mặc định top 5. Nếu evidence không có trong pool 30 thì BGE không thể lấy lại.

### Slide 13 — Retrieval Experimental Setup

**Ý cần nhớ: dataset chung khác corpus mở rộng; 20 ý hỏi tạo 80 ca.**

“Dataset chung của nhóm có năm tài liệu tiếng Việt. Riêng thí nghiệm retrieval, em bổ sung năm phiên bản tiếng Anh tương ứng để kiểm tra truy hồi song ngữ, tạo corpus gồm 1.063 chunk.

Bộ đánh giá có 20 ý hỏi, mỗi ý có câu tiếng Việt và tiếng Anh, rồi chạy trên tài liệu của cả hai ngôn ngữ. Như vậy có 80 ca theo bốn hướng, được nhóm theo 20 ý hỏi; không thể coi 80 ca là 80 câu hỏi độc lập.

Thí nghiệm chạy trên RTX 2060, FP32, reranker batch size 4. Dữ liệu, bản dịch, vector, cấu hình và kết quả được lưu để kiểm tra lại. Mỗi ca và mỗi phương pháp chạy một pass; không fine-tune model.”

**Nhắc khi bị hỏi:** Shared ready dataset theo kiểm đếm ngày 24/10 có 532 retrieval chunks. Các bản EN là mở rộng thử nghiệm riêng. Chưa có ba run độc lập, chưa có double annotation độc lập/Kappa; không gọi đây là kiểm thử tổng quát hóa sang doanh nghiệp mới.

### Slide 14 — Retrieval Results

**Ý cần nhớ: đủ bằng chứng tăng 52 lên 69 ca; không phải LLM accuracy.**

“Tiêu chí chính là top 10 có đủ mọi thành phần bằng chứng cần để trả lời câu hỏi hay không.

Dense E5 đạt 52 trên 80 ca. Thêm BGE đạt 62 ca. Translated hybrid đạt 63 ca, còn translated hybrid kết hợp BGE đạt 69 ca, tương đương 86,25 phần trăm.

So với dense, pipeline cuối tăng 17 ca đủ bằng chứng, tức 21,25 điểm phần trăm. Recall ở top 10 đạt khoảng 0,8823; MRR đạt 0,9, cho thấy đoạn liên quan đầu tiên thường được xếp sớm hơn.

Đây là kết quả retrieval, chưa phải độ chính xác câu trả lời LLM. Em đã phân tích cả 11 ca chưa đạt: tất cả đều thiếu evidence ngay trong top 30 trước reranking, chủ yếu liên quan tìm đúng hoặc ghép nhiều hàng bảng.”

**Nếu bị hỏi độ chắc chắn:** Có cluster bootstrap theo 20 ý hỏi; so dense khoảng tin cậy gain là 10–35 điểm phần trăm, còn so dense+BGE là 0–20 nên kết luận thận trọng. Không cần tự đưa phần bootstrap vào lời nói mở đầu.

### Chuyển người trình bày

“Kết quả này cho thấy pipeline lấy đủ bằng chứng tốt hơn dense trên bộ đánh giá. Phần tiếp theo sẽ trình bày cách thành phần generation sử dụng context và đánh giá câu trả lời.”

**Lưu ý:** Không nói generation được chấm trên cùng 80 ca nếu thực tế bộ hỏi khác nhau.

### Nếu được giao nói phần mình ở slide Completed Work and Next Steps

“Phần retrieval đã được tích hợp và có kết quả đánh giá lưu lại. Hướng tiếp theo của em là cải thiện truy hồi theo Product ID và ghép ứng viên cho câu hỏi cần nhiều hàng, sau đó phối hợp đánh giá chất lượng toàn pipeline trên một bộ câu hỏi chung.”

## Bản rút gọn tiếng Việt — khoảng một phút

“Em phụ trách chuẩn bị chunk, embedding và retrieval. Hệ thống ưu tiên cấu trúc câu và bảng, kiểm tra giới hạn token trước embedding và giữ thông tin nguồn để hỗ trợ citation. Pipeline sử dụng E5, BM25 với query Việt–Anh, RRF và BGE reranker.

Dataset chung có năm tài liệu tiếng Việt. Riêng benchmark, em bổ sung năm bản tiếng Anh tương ứng, tạo 80 ca từ 20 ý hỏi. Số ca lấy đủ bằng chứng tăng từ 52 lên 69 trên 80, tương đương tăng từ 65 lên 86,25 phần trăm.

Đây là chất lượng lấy bằng chứng, không phải độ chính xác LLM. Cả 11 ca còn thiếu đều thiếu evidence trước reranking, nên hướng tiếp theo là cải thiện tập ứng viên, đặc biệt với Product ID và câu hỏi nhiều hàng bảng.”

---


## Phạm vi nguồn và bằng chứng

- Bản lưu từ [Notion của Huy](https://app.notion.com/p/4033d666f9ee81bf9c9cd1251f4723f3?pvs=204), đối chiếu [Canva Review 2](https://canva.link/jp3t3fxx0rtidj0) revision 163, 28 trang gồm phần backup. Không có PPTX/PDF export mới trong repo.
- [Mục lục bằng chứng](README.md), [câu hỏi/checklist đầy đủ](checklist-evidence-assessment.vi.md), [audit chunking](chunking-and-slides-audit-20261025.vi.md).
- [Metrics gốc](../../artifacts/evaluation/heldout-review2-v1/runs/review2-reviewed-r1-sql-20261022/metrics.csv), [báo cáo benchmark](../../artifacts/evaluation/heldout-review2-v1/runs/review2-reviewed-r1-sql-20261022/REPORT.vi.md), [candidate diagnostics](../../artifacts/evaluation/heldout-review2-v1/runs/review2-reviewed-r1-sql-20261022/candidate-diagnostics.json).
- [Pilot chọn embedding](../../artifacts/evaluation/embedding-comparison-20261018/comparison.md), [thống kê E5](retrieval-report-stats.json), [kiểm đếm database ngày 24/10](dataset-count-verification-20261024.json).

**Phân biệt nhánh:** phần kiến trúc chung được kiểm tra trên main commit `1ffe05bbd5bcf477d2fe583d086db4f47b1f9497`. Main mặc định translated_hybrid_rerank, RAG top5 và cap 24.000 ký tự; không đồng nhất với Huy checkpoint 165727a hoặc benchmark top10. Main không có đầy đủ source_spans của Huy. HTTP/UI chưa cung cấp verified document-language mapping tương đương benchmark.

**Phân biệt phép đo:** 69/80 là retrieval evidence trên corpus VI+EN riêng, không phải production answer accuracy. Các số đo Docker mới của thành viên khác trong ảnh/Canva chưa được kiểm tra lại bằng raw logs tại đây; không dùng chúng thay latency RTX2060 đã lưu.

**Kiểm tra artifact gần nhất:** đã replay hashes, rankings, metric/evidence cho 80 ca và 4.800 reranker logit entries; kết quả đạt. Hàm save của verify_run được thay tạm trong bộ nhớ để không ghi đè verification.json. Không chạy inference mới, không sửa frozen code/inputs/results.

## Ba định nghĩa khi phản biện

- **Recall@10:** mỗi ca lấy số gold chunks trong top10 chia tổng gold chunks được gán nhãn; báo macro trung bình 80 ca, không phải tỷ lệ câu đã đủ đáp án. Gold chunks được ánh xạ từ evidence spans, không chỉ chứa từ khóa.
- **MRR@10:** mỗi ca lấy 1 chia hạng chunk liên quan đầu tiên; không có trong top10 thì 0; lấy trung bình qua các ca. MRR cao chưa bảo đảm đủ evidence.
- **Full evidence@10:** mỗi ca đạt khi đủ mọi thành phần bắt buộc, chấp nhận alternatives; 69/80=86,25%. Không phải LLM accuracy.

Các lời nói trong file này là gợi ý để tập, không phải bản ghi lời thầy hoặc kết quả rehearsal. Thời lượng cần bấm giờ thực tế.
