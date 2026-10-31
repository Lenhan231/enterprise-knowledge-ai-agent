# Phân tích 4 câu E5 Việt→Việt mất điểm

Phạm vi: kết quả E5 multilingual base, direction vi->vi, top 10, bộ nhãn evidence-v1 hiện tại. Đã đọc toàn bộ 10 chunk trả về của từng câu, đối chiếu từng component/alternative và tính thứ hạng ngoài top 10 từ vector lưu. Không chạy lại encoder, không sửa nhãn, không thay kết quả benchmark.

## Kết luận chính

Không nên xem cả bốn câu là model hoàn toàn không tìm thấy câu trả lời. Q11 có bằng chứng thay thế mạnh chưa được nhãn chấp nhận; Q18 có tiêu chí retrieval quá chặt đối với câu hỏi thiếu dữ liệu; Q13 và Q20 thực sự thiếu một số chi tiết cần trả lời đầy đủ, đồng thời cũng có phần nhãn nên rà soát.

| Câu | Ý đủ theo nhãn v1 | Phần bị trừ | Đánh giá sau khi đọc nội dung |
|---|---:|---|---|
| Q11 | 2/3 | Checklist khóa PO/kiểm tra dữ liệu | Có nội dung tương đương rải ở SOP và slide; cần bổ sung/duyệt alternative bundle |
| Q13 | 6/9 | Chuẩn bị, blind count, cập nhật không xóa lịch sử | Thiếu thật chi tiết chuẩn bị/blind count; audit trail đã có nhưng điều kiện không xóa lịch sử chưa có |
| Q18 | 1/2 | Câu hướng dẫn không suy đoán PO | Đã có bằng chứng thiếu dữ liệu rất rõ ở hạng 1; nên xem lại tiêu chí bắt buộc riêng này |
| Q20 | 3/5 | Luồng duyệt cụ thể và xử lý conflict | Thiếu thật luồng Planner→Procurement Manager; conflict có ứng viên alternative ngay trong top 10 |

Các con số 15/19 và bảng benchmark cũ được giữ nguyên. Đây là review nhãn/chất lượng retrieval, chưa phải kết quả chấm bằng bộ nhãn mới.

## Q11 — stockout nhưng days of supply = 145

Câu hỏi: “Một SKU có stockout signal nhưng calculated days of supply là 145 ngày. AI Agent nên làm gì trước khi đề xuất mua thêm?”

Đã lấy được:

- Hạng 1: Manual, parser index 14: “Khi tín hiệu mâu thuẫn, chuyển sang trạng thái DATA CONFLICT; chặn PO tự động và yêu cầu Inventory Controller xác minh.”
- Hạng 3: SOP, parser index 3: “Tạm khóa đề xuất PO tự động, kiểm tra tồn khả dụng, hàng giữ, đơn chưa xuất, snapshot timestamp và công thức days of supply.” Đồng thời có điều kiện hơn 120 ngày + stockout và chỉ mở lại khi Controller ghi nhận kết luận.
- Hạng 9: Training Deck, parser index 3: “Khóa đề xuất PO tự động, xác minh giao dịch và nhu cầu trước khi mua.”

Vì sao vẫn bị trừ? Q11.block_checks chỉ có một alternative, trong đó bắt buộc AND hai span: câu SOP và câu CSV “Tạm khóa PO tự động; kiểm tra giao dịch, snapshot, đơn hàng treo và cách tính nhu cầu”. CSV parser index 2 ở hạng 17 nên component bị đánh trượt. Tuy nhiên SOP hạng 3 + slide hạng 9 đã bao phủ phần lớn, có thể đầy đủ checklist về tồn/giữ/đơn chưa xuất/snapshot/công thức/giao dịch/nhu cầu bằng cách diễn đạt khác.

Đánh giá: đây là ứng viên bằng chứng thay thế mạnh, không nên coi là thiếu toàn bộ nội dung kiểm tra. Cần duyệt mức tương đương của “đơn chưa xuất” và “đơn hàng treo” trong yêu cầu nghiệp vụ, rồi bổ sung alternative AND(SOP, slide) nếu chấp nhận. Không thay AND thành OR bừa bãi: chỉ một đoạn có thể vẫn thiếu một số bước.

## Q13 — mô tả quy trình kiểm kê từ đầu đến đóng phiếu

Đây là câu nhiều bước, không phải tìm một thông tin đơn lẻ.

Đã lấy được:

- SOP parser index 2, hạng 2: freeze giao dịch, recount bởi người thứ hai, đối chiếu receipts/picks/shipments/returns/transfers/cancellations/chờ đồng bộ.
- SOP parser index 6, hạng 3: bảng tổng quan 6 bước; điều tra có nguyên nhân/chứng từ; người duyệt độc lập; cập nhật có audit trail.
- SOP parser index 5, hạng 4: chỉ đóng phiếu sau phê duyệt, đồng bộ thành công và cập nhật báo cáo ngoại lệ.

Thiếu theo nhãn:

1. Q13.prepare: chi tiết danh sách SKU/vị trí/đơn vị/snapshot/số lượng hệ thống. Nằm trong SOP parser index 1, hạng 17. Bảng tổng quan hạng 3 chỉ có danh sách SKU/vị trí/phạm vi/thời điểm freeze nên chưa đầy đủ điều kiện này.
2. Q13.independent: phân công người đếm và không cho xem số hệ thống nếu blind count. Cũng ở SOP index 1, hạng 17. Cụm “Đếm độc lập” trong bảng tổng quan không tự chứng minh đủ quy tắc blind count.
3. Q13.audit_update: câu “Không xóa giao dịch cũ hoặc sửa trực tiếp file nguồn; dùng giao dịch điều chỉnh có thể truy vết.” ở SOP index 4, hạng 27. Top 10 đã có “Điều chỉnh có audit trail” nhưng không có đầy đủ điều kiện không xóa/sửa nguồn. Nếu chỉ yêu cầu audit trail như reference answer thì có ứng viên alternative; nếu giữ yêu cầu mạnh hơn này thì đây vẫn là thiếu thật.

Đánh giá: có thiếu bằng chứng thật, dù tìm đúng SOP. Nội dung quy trình rải ở nhiều parser chunk. Dense ưu tiên bảng/tổng quan nhưng bỏ sót phần chuẩn bị và một đoạn guard ngắn. Không phải encoder cắt mất nội dung: các đoạn thiếu còn nguyên trong index và đều dưới cap 512. Có dấu hiệu parser gán heading chưa sát nội dung: index 2 mang nhãn “5. Ngưỡng xử lý và phê duyệt” nhưng chứa freeze/count/reconcile của phần trước. Đây là yếu tố nên kiểm tra riêng, chưa có phép đo chứng minh nó gây tụt hạng.

Thử nghiệm phù hợp sau khi nhãn được duyệt: lấy candidate rộng hơn rồi rerank, hoặc mở rộng chunk lân cận trong cùng tài liệu và cùng ACL. Ví dụ SOP index 2 và 5 đã có sẵn; neighbor index 1 và 4 chứa đúng phần đang thiếu. Đây mới là giả thuyết cần đo với ngân sách context rõ ràng, không phải kết quả đã cải thiện.

## Q18 — yêu cầu con số PO inbound/backorder chính xác của SKU X

Hạng 1 là workbook parser index 1, nói trực tiếp:

“Dataset không có Open PO / Backorder; workbook mặc định 0 và yêu cầu nhập số thực tế.”

Cùng chunk còn yêu cầu điền dữ liệu thực tế. Hạng 4 Manual index 3 nói dataset không cung cấp đầy đủ PO inbound/backorder và các trường này phải được bổ sung trước triển khai thật.

Nhãn Q18.missing_inputs đã chấp nhận đúng bằng chứng này. Tuy nhiên Q18.no_guess bắt buộc thêm đúng câu “3. Không suy đoán lead time / currency / PO.” trên Training Deck index 7, hạng 15. Vì thiếu slide này nên full evidence bị đánh trượt.

Đánh giá: top 10 đã có bằng chứng đủ mạnh để kết luận không thể cung cấp số chính xác từ corpus. Bắt retrieval phải tìm thêm một câu hướng dẫn hành vi của AI là tiêu chí nên rà soát: hành vi không bịa số cần được kiểm tra ở generation, không thể suy từ retrieval score. Có thể chuyển câu hướng dẫn này thành optional context hoặc duyệt một alternative dựa trên bằng chứng thiếu dữ liệu + yêu cầu nhập số thực tế. Không vì có số 0 mặc định mà trả lời PO/backorder thực bằng 0. Chưa chạy generation nên chưa biết LLM sẽ từ chối đúng hay không.

## Q20 — yêu cầu Agent tự tạo và phát hành PO ngay khi đạt ROP

Đã lấy được:

- Hạng 2, CSV index 11: không tự ghi PO/điều chỉnh tồn, trích dẫn nguồn và snapshot, “Human approval bắt buộc”, mâu thuẫn chuyển người duyệt.
- Hạng 3, Deck index 2: AI chỉ đọc dữ liệu phân quyền/đề xuất, không tự phát hành PO/sửa tồn.
- Hạng 7, Manual index 5: kiểm tra tồn khả dụng/PO mở/hàng giữ/backorder/MOQ/ngân sách/lịch giao.
- Hạng 9, SOP index 3: DATA CONFLICT, khóa PO tự động, kiểm tra dữ liệu, chỉ mở lại sau khi Inventory Controller ghi kết luận.
- Hạng 10, CSV index 2: khóa PO và kiểm tra, owner Inventory Controller.

Hai component bị trừ:

1. Q20.human_approval: Manual index 13 ở hạng 12, chứa rõ Planner→Procurement Manager và ngoại lệ lên Operations+Finance. Top 10 biết cần human approval và có owner Planner+Procurement ở registry, nhưng chưa nêu rõ luồng duyệt cụ thể này. Đây là thiếu thật đối với câu trả lời đầy đủ. Cần rà soát việc yêu cầu cả dòng ngoại lệ vì câu hỏi/reference không nhất thiết đòi toàn bộ mọi nhánh ngoại lệ.
2. Q20.conflict: nhãn chỉ chấp nhận đúng câu Manual index 14 (hạng 27), dù SOP hạng 9 và CSV hạng 10 đã có các hành động tương ứng. Đây là ứng viên alternative cần duyệt. Dù sửa component conflict, câu vẫn thiếu luồng duyệt cụ thể nên chưa tự trở thành đạt toàn bộ.

## Chẩn đoán nếu chỉ tăng k (không phải cấu hình đề xuất)

Từ vector đã lưu, k nhỏ nhất để phủ đủ mọi span bắt buộc của nhãn v1: Q11=17, Q13=27, Q18=15, Q20=27. Con số này chỉ cho biết dữ liệu có trong index nhưng nằm ngoài top 10, không chứng minh tăng k như vậy là giải pháp tốt. Tăng k còn tăng context/latency/nhiễu; không chọn k dựa riêng vào bốn ca test để đẩy điểm.

## Ưu tiên xử lý

1. Review evidence v2 độc lập với việc model nào thắng: Q11.block_checks, Q18.no_guess, Q20.conflict, và độ chi tiết Q13.audit_update/Q20.human_approval. Thêm alternative phải có đủ sự kiện, không hạ điều kiện chỉ để tăng điểm và không chỉ thêm những đoạn một model đã lấy được. Kiểm tra tương ứng cả VI/EN rồi chấm lại cả 3 model.
2. Với phần thiếu thật, dùng Q13/Q20 để hình dung loại lỗi: truy hồi được tổng quan nhưng bỏ sót bước/luồng duyệt ở đoạn khác. Thử candidate pool rộng + rerank hoặc neighbor/parent expansion; đo với cùng ngân sách và bộ nhãn đã chốt.
3. Chỉ sau đó mới quyết định model/index production. Không có bằng chứng ở bốn ca này rằng cần tăng encoder max_seq_length hoặc đổi vector database.

Nguồn: evidence-v1/evidence.json; dense-evidence-benchmark-v1/indexed-corpus.jsonl, cases.json, candidates/multilingual-e5-base/{results.json,vectors.npy,query-vectors.npy}. Source parser index là số bắt đầu từ 0; thứ hạng retrieval bắt đầu từ 1.
