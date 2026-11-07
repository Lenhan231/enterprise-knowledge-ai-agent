> Báo cáo dưới đây dành cho **draft trước sửa**. H10 đã được thay và H13/H19 đã được chỉnh theo yêu cầu. Xem [CHANGELOG.vi.md](CHANGELOG.vi.md).

# Rà soát câu hỏi trước benchmark — 22/10/2026

**Kết luận:** đã đối chiếu 20 câu VI/EN, đáp án và nhãn với ngữ cảnh nguồn. Chưa nên dùng bản hiện tại để công bố kết quả mới: H10 có một alternative nhãn không đủ căn cứ; H19 cần làm rõ cách hỏi. Các số liệu được hỏi khớp bản parser đã chụp. Đây là rà soát của trợ lý, không phải xác nhận đã có người duyệt độc lập.

Không chạy retrieval/model inference, không gọi dịch/API. Chỉ thêm báo cáo và diagnostic nhãn; không thay câu hỏi, nhãn, manifest, metric hoặc production. Chưa có điểm benchmark mới.

## Nếu bạn chỉ có 3 phút

| Ưu tiên | Cần xem | Đề xuất của mình |
|---|---|---|
| 1 | **H10 — nhãn và độ mới** | Bỏ bằng chứng thời điểm lấy từ Manual VI parser 5. Nếu muốn câu mới về kiến thức, nên thay H10 vì nhánh PO ngoại lệ đã xuất hiện trong nhãn Q20 cũ. |
| 2 | **H19 — “mã hóa ra sao”** | Hỏi có cần gắn mã lý do hay không; không yêu cầu mã cụ thể vì nguồn không cung cấp bảng mã. Có câu chữ VI/EN đề xuất bên dưới. |
| 3 | **H13 — câu dài và ghép hai việc** | Có thể giữ để thử ghép nguồn; luồng PO là kiến thức cũ, phần chỉ tiêu nhà cung cấp/lịch cập nhật mới. Viết gọn theo tình huống mua hàng. |
| 4 | **8 câu bảng số liệu** | Giữ để đo tìm đúng dòng/ghép dòng; khi trình bày, tách khỏi nhóm văn bản để tránh gọi toàn bộ là thử nghiệm dịch chéo thuần túy. |
| 5 | **Phạm vi đánh giá** | Không có nhãn nào yêu cầu bằng chứng từ SOP PDF. Bộ mới chưa đo đầy đủ mọi định dạng, OCR, phân quyền hoặc từ chối câu không có đáp án. |

Bạn có thể đọc H10, H19, H13 trong [REVIEW.md](REVIEW.md) trước; không cần rà lại toàn bộ 141 đoạn trích ngay.

## Hai chỗ nên sửa trước khi chạy

### H10: alternative thời điểm chưa chứng minh điều được hỏi

Câu hỏi yêu cầu luồng phê duyệt PO vượt ngân sách/SKU mới/campaign bất thường và thời điểm phải được duyệt.

Bằng chứng đúng nằm trong bảng phê duyệt:

- VI Manual, parser 13, hàng 2: `Procurement Manager → Operations + Finance` và `Trước khi phát hành PO`.
- EN Manual, parser 14, hàng 2: cùng luồng và `Before PO issuance`.

Nhưng `H10.timing.vi.a0` còn trỏ vào VI Manual parser 5, [547,569): `Trước khi phát hành PO`. Ngữ cảnh đầy đủ là:

> Trước khi phát hành PO, kiểm tra tồn kho khả dụng, PO đang mở, hàng đang giữ, backorder, MOQ, ngân sách và lịch giao.

Đoạn này yêu cầu **kiểm tra**, không khẳng định mốc phê duyệt của trường hợp ngoại lệ. Không đủ làm alternative cho yêu cầu đang hỏi.

Diagnostic chỉ dùng chunk bảng đúng, không chạy model:

| Ngôn ngữ tài liệu | Recall@10 | nDCG@10 | Đủ toàn bộ bằng chứng |
|---|---:|---:|---:|
| VI | 50% | 0.6131 | 100% |
| EN | 100% | 1.0000 | 100% |

Chênh lệch do nhãn tạo thêm một gold chunk ở VI. Cần bỏ alternative và span trên nếu giữ H10, rồi tạo lại gold map/manifest trước inference. Giữ bằng chứng bảng VI [420,442) và EN [398,416).

**Độ mới:** Q20 cũ đã có `Q20.exception_approval` (optional context) đúng hàng ngoại lệ này; hàng đó còn nằm trong một bundle cũ của `Q20.human_approval`. H10 có cách hỏi riêng, nhưng không phải kiến thức hoàn toàn chưa từng dùng. Khuyến nghị thay bằng một câu bảng SOP hỏi thông tin chưa có trong bộ cũ nếu cần bảo vệ tuyên bố “bộ mới”. Chưa tự thay để tránh quyết định lại phạm vi thay bạn.

### H19: nguồn không có mã lý do cụ thể

Cách hỏi hiện tại “nguyên nhân đó phải được mã hóa ra sao” có thể được hiểu là cần trả lời mã `R01/R02/...`. Nguồn chỉ nói `Gắn mã nguyên nhân trả hàng`, ví dụ sai size/lỗi sản phẩm/giao trễ, rồi phản hồi Merchandising, QA, Logistics; không cung cấp mã cụ thể hoặc schema mã.

Câu chữ đề xuất:

**VI:** “Khách trả hàng vì sai cỡ hoặc giao chậm. Theo tài liệu, có cần gắn mã lý do trả hàng không, và thông tin này phải phản hồi tới những bộ phận nào?”

**EN:** “A customer returns an item because it did not fit or arrived late. Under the policy, must a return-reason code be assigned, and which departments should receive that feedback?”

Đáp án giữ: có gắn return-reason code; phản hồi Merchandising, QA, Logistics. Không bịa mã. Hai bản câu hỏi và cả phần question trong evidence/cases cần đồng bộ nếu áp dụng; không chỉ sửa file hiển thị.

## Các điểm đáng chú ý nhưng không phải đáp án sai

### H13: ghép hai nguồn đúng, tình huống có thể tự nhiên hơn

Bản hiện tại ghép luồng phê duyệt PO và việc duy trì hồ sơ nhà cung cấp. Nguồn hỗ trợ đầy đủ, và oracle đã xác nhận cần hơn một chunk; hai chunk phù hợp đủ trả lời. Tuy nhiên, câu hơi giống bài kiểm tra gom hai ý hơn một nhu cầu người dùng tự nhiên.

Gợi ý giữ cùng nội dung, viết gọn:

**VI:** “Khi chuẩn bị PO trong ngân sách và đúng tham số đã duyệt, Planner chuyển cho ai duyệt? Đồng thời, hồ sơ nhà cung cấp phải duy trì những thông tin nào và cập nhật theo tần suất nào?”

**EN:** “When preparing a PO within budget and approved parameters, whom does the Planner submit it to for approval? Which supplier information must also be maintained, and how often must it be updated?”

Luồng `Planner → Procurement Manager` đã là phần bắt buộc trong Q20 cũ; phần mới là lead time thực tế, MOQ, lịch giao, tỷ lệ giao đủ/đúng hạn, mỗi lần nhận/hằng tháng. Không gọi toàn bộ H13 là kiến thức mới. Lịch “mỗi lần nhận/hằng tháng” là đúng nguyên văn nguồn, không tự quy thành một deadline số ngày.

### Bảng số liệu: đúng nguồn, nhưng ngôn ngữ chưa được tách hoàn toàn

H06–H09, H11, H12, H14, H15 là 8 ý chủ yếu tra số liệu workbook (40% bộ câu hỏi). Tên cột Product ID, On-hand Units, Units Sold… giữ tiếng Anh trong cả hai corpus. Câu VI cũng dùng trực tiếp một số tên cột này.

- **6 ý H06/H07/H08/H11/H12/H14:** có chunk bằng chứng VI/EN giống hệt toàn bộ nội dung.
- **H09/H15:** chunk KPI Summary có phần khác nhau do nội dung ghi chú được dịch, nhưng các dòng số liệu GenZ/Streetwear cần trả lời vẫn giống nhau về tên trường và giá trị.
- Điều này phản ánh dữ liệu thực của nhóm và phù hợp bài tra bảng; chưa phải bằng chứng mạnh rằng model xử lý được hoàn toàn văn bản tiếng Việt đối chiếu hoàn toàn văn bản tiếng Anh.
- Khi có điểm, xem riêng nhóm narrative/paraphrase và từng hướng VI→EN, EN→VI. Không kết luận translation giúp chỉ dựa vào điểm tổng.

Không đề xuất dịch lại header/corpus hiện tại ngay: như vậy đổi cả dữ liệu và vector, tạo thêm một thí nghiệm khác. Ghi rõ hạn chế là đủ cho lần đo này.

### Nhãn theo chunk khác với “đã đủ câu trả lời”

Định nghĩa Recall hiện tại đếm tất cả gold chunk được gán, kể cả các nguồn thay thế. Do đó, tìm đủ một cách trả lời không luôn đạt Recall 100%:

- H02: Manual **hoặc** Deck đều đủ; lấy một nguồn có thể đủ bằng chứng nhưng Recall chỉ 1/2.
- H13: Manual + Registry **hoặc** Manual + Policy Matrix đủ; có tổng 3 gold chunk, một cặp đúng đạt Recall 2/3.
- H15: KPI Summary + một trong ba nguồn product-master đủ; tổng 4 gold chunk, một cặp đúng đạt Recall 2/4.
- H18: Manual đủ ba yếu tố; Deck chỉ cung cấp hai yếu tố. Chỉ lấy Manual đã đủ câu trả lời, Recall vẫn 1/2.

Đây là hệ quả của metric đang giữ như bộ trước, không tự động là lỗi retrieval. Đọc **Full evidence@10** cùng Recall@10. Riêng alternative H10 khác các ví dụ này: nó không chứng minh đúng quan hệ phê duyệt, nên cần sửa.

Component coverage cũng không phải tỷ lệ các từ khóa giống đáp án: H17 gộp cả 7 thông tin đối chiếu thành một thành phần, trong khi H11 chia 6 thành phần. Báo cả macro theo câu và số thành phần đạt/tổng; không diễn giải một thành phần của mọi câu là cùng độ khó. Chưa cần đổi cách chấm chỉ vì việc gộp này, miễn công khai định nghĩa.

### Phạm vi nguồn và độ mới

Số ý có ít nhất một nhãn từ mỗi nguồn VI (không cộng thành 20 vì một ý có nhiều nguồn):

| Nguồn | Số ý | Ghi chú |
|---|---:|---|
| Manual DOCX | 13 | Phần lớn câu văn bản/chính sách |
| Planner XLSX | 9 | Bảng, ghép dòng, có alternative Supplier Control |
| Training Deck PPTX | 3 | Đều là nguồn thay thế/đóng góp từng phần |
| Registry CSV | 1 | H13; workbook có alternative cùng quy tắc |
| SOP PDF | 0 | Có trong corpus tìm kiếm nhưng chưa là bằng chứng bắt buộc |

Không bắt buộc cân đều định dạng nếu mục tiêu là retrieval ngôn ngữ. Nếu báo cáo hiệu quả mọi loại tài liệu, cần bổ sung/thay câu để PDF/SOP được kiểm tra, và không suy ra chất lượng OCR từ điểm hiện tại. Tương tự, 20 câu đều có đáp án và dùng admin: không kiểm tra từ chối, hallucination khi thiếu nguồn hoặc giới hạn quyền truy cập.

## Kết quả rà từng câu

“Giữ” nghĩa là chưa thấy lỗi nội dung trong snapshot đã đối chiếu; không có nghĩa đã biết model sẽ tìm đúng.

| Câu | Kết luận | Điểm cần nhớ |
|---|---|---|
| H01 | Giữ | Đủ 4 mục tiêu: sẵn hàng, chi phí lưu kho, vốn bị chiếm dụng, chính xác dữ liệu. |
| H02 | Giữ | Streetwear/Outdoor/Casual/GenZ; Manual hoặc Deck đều là nguồn hợp lệ. |
| H03 | Giữ | Nhóm tạm, rà sau 3 chu kỳ; nguồn không nói đó là 3 tháng. Chủ đề ABC cùng Q03, yêu cầu tạm phân nhóm mới. |
| H04 | Giữ | 5 nhóm hồ sơ đúng; câu không hỏi thời hạn lưu bao nhiêu năm. Đáp án tham chiếu viết tắt; khi generation cần giữ các mục con trong nhãn như ảnh ngoại lệ, chứng từ nhà cung cấp, disposition. |
| H05 | Giữ | Không mặc định giảm giá trong ba nguyên nhân nêu; không phải cấm mọi hình thức giảm giá. |
| H06 | Giữ | ID17: M, silver, 28. Là snapshot 2022-12-31, không phải tồn hiện tại. |
| H07 | Giữ | ID18: 2 ngày, 0.9333 = 93.33%; không đọc thành 0.9333%. |
| H08 | Giữ | ID19: 3 và 2.333333333333333; được làm tròn hợp lý khi generation, không suy ra ba tháng liên tiếp. |
| H09 | Giữ | GenZ: 44 SKU, 5126 tồn, 199 bán; không nhầm số lượng đơn vị với số SKU. |
| H10 | Cần xử lý | Alternative VI sai quan hệ; kiến thức ngoại lệ đã có trong Q20 cũ. |
| H11 | Giữ | ID1 M/black/3; ID3 XL/blue/151. Hai dòng/chunk khác nhau, cần giữ đúng cặp ID–giá trị. |
| H12 | Giữ kèm lưu ý | ID2212 DOS25440; ID927 DOS6323.333333333334; cả hai CONFLICT - VERIFY BEFORE PO. Số rất lớn nhưng khớp nguồn, không tự sửa và không biến thành khuyến nghị mua hàng. |
| H13 | Nên viết gọn | Hai nguồn đủ; nhánh luồng duyệt là kiến thức cũ, chỉ tiêu nhà cung cấp mới. |
| H14 | Giữ | ID8 tồn101/bán1; ID9 tồn83/bán6. Là so sánh hai dòng, không cần tính xu hướng hay hiệu quả kinh doanh. |
| H15 | Giữ | Streetwear196 SKU/45085 đơn vị; toàn master2412 SKU. Toàn snapshot424 SKU, khác toàn master; không dùng tổng master làm tổng snapshot. |
| H16 | Giữ | Các log hỗ trợ phân tích nguyên nhân, không thay inventory ledger. Không suy thành mọi dữ liệu khác đều vô dụng. |
| H17 | Giữ | Phải đối chiếu PO, SKU, size, màu, số lượng, bao bì, chứng từ. “Đủ thùng” là tình huống giả định, không bỏ đối chiếu số lượng. Cùng đoạn nguồn F01 cũ nhưng hỏi thông tin khác. |
| H18 | Giữ | Service level, margin, chiến lược tồn kho. Manual đủ cả ba; Deck chỉ có hai. |
| H19 | Nên sửa câu chữ | Có gắn mã lý do; Merchandising/QA/Logistics. Không có mã cụ thể được cung cấp. |
| H20 | Giữ | System / Data Owner, khác Inventory Manager ở Q02. EN có riêng một parser row; VI chung bảng 7 vai trò, nên độ dài/ngữ cảnh chunk khác nhau. |

## Đề xuất chốt trước lần chạy đầu

1. Ưu tiên xử lý H10: nếu giữ câu thì sửa alternative; nếu muốn độ mới tốt hơn và phủ PDF thì thay bằng câu SOP chưa được bộ cũ hỏi.
2. Sửa cách hỏi H19, cân nhắc viết gọn H13; không đổi đáp án hoặc metric để làm điểm đẹp hơn.
3. Sau khi chốt, đồng bộ questions/cases/evidence/REVIEW/authoring specs, tạo lại manifest và gold map, chạy verify + tests. Giữ lại bản draft và báo cáo này làm lịch sử rà nhãn trước inference.
4. Chạy benchmark một lần với cấu hình đã cố định, rồi phân tích cả điểm tổng và nhóm câu. Không chỉnh bộ này theo các ca model bị mất điểm.

Chi tiết kiểm chứng máy nằm ở [assistant-review-audit.json](assistant-review-audit.json): SHA-256 của draft, diagnostic H10, số nguồn và so sánh nội dung chunk VI/EN. Diagnostic H10 chỉ kiểm bộ chấm với một chunk đúng được chọn sẵn; không phải kết quả benchmark.
