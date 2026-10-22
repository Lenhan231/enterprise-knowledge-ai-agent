# Gợi ý nói phần Huy — khoảng 5 phút

Dùng kết quả80 ca làm chính. Cần tập bấm giờ cùng nhóm; bảng cấu hình/metric dài để backup. Đây là lời nói gợi ý, không phải deck slide hoàn chỉnh.

## 1. Bài toán và phần phụ trách

“Phần của em là chuẩn bị đầu vào embedding và tìm bằng chứng trước khi đưa cho LLM. Câu hỏi có thể Việt hoặc Anh, tài liệu có bảng, và đáp án có thể nằm ở nhiều đoạn. Em kiểm tra cả model có đọc đủ nội dung và retrieval có lấy đủ những đoạn cần thiết không.”

Hình: tài liệu → tokenization/embedding → index → retrieval/rerank → LLM. Phân biệt với parser/OCR và generation của nhóm.

## 2. Tokenization và embedding

“Tokenizer phải khớp embedding model. Trước đây ứng dụng có thể ghi512 nhưng encoder mặc định256, nên có nguy cơ cắt nội dung. Hiện giới hạn encoder được đặt rõ, tokenizer cùng revision và chunk quá dài được chia lại.

Với bảng, giữ header để đoạn sau biết giá trị thuộc cột nào. Overlap không bảo đảm tự lấy đủ hai dòng. Source offsets được lưu để kiểm tra bằng chứng.

Hiện dùng multilingual-e5-base768 chiều, query/passage prefixes và normalization. Bộ 1.063 chunk có chuỗi dài nhất476/512 token, không vượt cửa sổ. Đây là model khác e5-large-v2.”

Backup: schema,449.203 token đầu vào tính cả header/overlap; số liệu tokenizer thật và metadata snapshot cũ được phân biệt trong báo cáo.

## 3. Pipeline

“Dense dùng câu hỏi gốc tìm theo vector. Nhánh lexical dùng query tự động chuyển VI/EN để BM25 có thêm tín hiệu. RRF hợp nhất thứ hạng, BGE chấm từng cặp query gốc–chunk gốc, xếp 30 ứng viên thành 10 đoạn cuối.

BGE là model reranker riêng, không phải embedding model. Nó sửa thứ tự nhưng không tìm thêm đoạn đã bị loại.”

Hình: query → dense/BM25 sau dịch → fusion →30 →BGE →10. Benchmark đã biết scope/mapping ngôn ngữ; không nói production tự có language routing cho mọi tài liệu.

## 4. Thiết kế và kết quả

“Bộ cũ giữ để phát triển. Bộ mới20 ý, mỗi ý VI/EN và chạy trên hai corpus, tổng80 ca, không phải80 câu độc lập. Một ca đạt khi top 10 chứa đủ mọi thành phần bằng chứng bắt buộc; có chấp nhận nguồn thay thế.

Dense đạt 52/80; dense+BGE62; translated hybrid63; thêm BGE69/80, tức86,25%. So với dense thêm 17 ca,21,25 điểm phần trăm. MRR cuối0,9 và Recall@10=0,8823. Tỷ lệ đủ bằng chứng không phải tỷ lệ LLM trả lời đúng.”

Chỉ bảng4 nhánh, nếu cần rút thời gian chỉ nói52→69. Chưa có original-query hybrid arm trong bộ mới nên không tách riêng dịch với lexical/fusion.

## 5. Failure và hạn chế

“Còn 11 ca thiếu evidence. Em đã kiểm cả11; tất cả thiếu ngay từ30 ứng viên. Ví dụ cần ID1 và3 nhưng dòngID3 ở ngoài 200 sau fusion, BGE không được xem.

Một ca ‘hồ sơ lưu trữ’ dịch thành ‘file categories/storage’: dense+BGE lấy được, nhưng fusion đẩy chunk đúng xuống33. Đây là hồi quy, không phải thêm hybrid luôn thắng.

Nhóm nhiều chunk vẫn chỉ12/20. Hướng tiếp theo là lookup đúng Product ID và ghép candidate cho nhiều ID, không chỉ đổi reranker.”

Backup:6 ý có chunk bảng VI/EN giống hệt; corpus đã biết/nhãn chưa nhiều annotator độc lập;3 run/mean±std chưa làm.

## 6. Độ trễ và chuyển sang An

“Đổi lại, warm retrieval trung bình tăng0,55→3,61 giây. Chưa gồm live API dịch và generation, không phải tổng response time.

Kết quả chứng minh retrieval đủ bằng chứng tốt hơn dense trên bộ này, chưa chứng minh LLM đúng86,25%. Phần tiếp theo nhóm đo câu trả lời, citations, faithfulness và end-to-end trên đúng bộ câu hỏi.”

## Câu phản biện

| Câu hỏi | Ý trả lời |
|---|---|
| Vì sao E5? | Pilot Commerce source coverage tốt, quyết định theo miền; không nói tốt nhất mọi corpus. |
| Có train không? | Pretrained, chưa fine-tune; không có epoch/loss training. |
| Vì sao không100% như trước? |100% là development12 ý đã xem lỗi; bộ mới20 ý có ca bảng/ghép dòng khó hơn. |
| Có ý nghĩa thống kê không? | Vs dense+21,25pp, cluster-bootstrap CI[10,35]; vs dense+BGE CI chạm0 nên thận trọng. |
| Sao không tăng top 30? | Có gold ngoài 200; tăng50 chưa giải quyết hết và tăng chi phí rerank. |
| Retrieval đúng thì LLM đúng? | Còn packing/generation; phải chấm context thực và câu trả lời riêng. |
| Đã3seed chưa? | Chưa, một pass/ca/nhánh; seed cho thứ tự/bootstrap không phải training. |
| Chạy lại? | Bundle có input/hash/vector/bản dịch; run tên mới bằng SQL mặc định. |
