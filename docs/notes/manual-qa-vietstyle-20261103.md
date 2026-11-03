# Bộ câu hỏi thử tay — VietStyle Enterprise Operating Policy v1.0

Ngày soạn: 03/11/2026. Tài liệu nguồn: `artifacts/datasets/vietstyle-operations-vi-v1/VietStyle_Enterprise_Operating_Policy_v1.0_VN.md`. Đây là tài liệu đang chạy trên production.

**Phạm vi.** 15 câu này **không trùng** với V1–V6 trong benchmark. Các câu trải đều 6 phần của chính sách: nhân sự, mua sắm, tồn kho, bảo mật, ngoại lệ, AI. Đáp án tóm tắt lấy trực tiếp từ tài liệu; số "Trang" là số *TRANG CHÍNH SÁCH* in trong tài liệu.

**Cách chấm từng câu:**
- **Đúng:** đủ ý trong đáp án, có trích dẫn [S…].
- **Thiếu:** đúng nhưng thiếu ý.
- **Sai:** sai nội dung, hoặc bịa ra điều tài liệu không có.
- **Chặn:** bị verifier chặn, ra câu "Chưa thể kiểm chứng…".

Ghi thêm thời gian trả lời, xem ở `metadata.latency` hoặc đếm tay.

| # | Loại | Câu hỏi | Đáp án mong đợi (tóm tắt) | Nguồn |
|---|---|---|---|---|
| 1 | Tra cứu | Nghỉ phép theo kế hoạch phải xin trước bao lâu? Nghỉ ốm đột xuất thì sao? | Ít nhất **5 ngày làm việc** trước ngày đầu nghỉ. Nghỉ khẩn, nghỉ bệnh hoặc nghỉ được pháp luật bảo vệ báo sớm nhất có thể và **không mất hiệu lực** vì báo muộn. | Trang 06 |
| 2 | Tính toán | Nhân viên mới làm đủ 6 tháng thì tích lũy được bao nhiêu ngày phép năm? | Quyền phép năm là 12 ngày, tích lũy 1/12 mỗi tháng làm việc hoàn tất. **12 × 6/12 = 6 ngày**, trừ khi luật quy định cách tính có lợi hơn. | Trang 05 |
| 3 | Tính toán | Đi công tác 2 đêm ở thành phố lớn được chỉ định thì tiền phòng được hoàn tối đa bao nhiêu? | Tối đa 2.500.000 VND/phòng/đêm, nên **2 × 2.500.000 = 5.000.000 VND**. Mức này áp dụng trừ khi hợp đồng hoặc kế hoạch công tác đặt hạn thấp hơn. | Trang 12 |
| 4 | Loại trừ | Tiền rượu bia khi đi công tác có được hoàn không? | **Không**: đồ uống có cồn bị loại trừ, trừ khoản được quy tắc tiếp khách riêng cho phép. Giải trí cá nhân, chi cho người đi cùng và tiền phạt cũng bị loại. | Trang 12 |
| 5 | Bẫy chính sách | Một nhu cầu mua 60 triệu, tách thành 2 đơn 30 triệu để chỉ cần trưởng bộ phận duyệt có được không? | **Không**: cấm chia nhỏ mua sắm để tránh ngưỡng; duyệt theo **tổng cam kết**. 60 triệu cần **trưởng bộ phận + Mua sắm + Tài chính** và ít nhất 3 báo giá văn bản (hoặc lý do chỉ định nguồn đã duyệt). | Trang 15, 19; Phụ lục B |
| 6 | Ngưỡng | Cam kết mua 250 triệu đồng cần ai phê duyệt? | **Hội đồng Điều hành Vận hành + Tài chính**; cần đánh giá nguồn cung và rà soát rủi ro có lập hồ sơ. | Phụ lục B |
| 7 | Quy trình | Muốn thanh toán hóa đơn nhà cung cấp thì cần đối chiếu những gì? Nếu là dịch vụ thì sao? | **Đối chiếu ba bên**: PO đã phát hành, biên bản nhận hàng được chấp nhận và hóa đơn. Với dịch vụ, dùng **xác nhận nghiệm thu dịch vụ** thay phiếu nhận hàng. | Trang 22 |
| 8 | Điều kiện chặn | Nhà cung cấp chưa được xác minh có được phát hành PO không? | **Không**. Chỉ dùng nhà cung cấp sau khi kiểm tra danh tính, chỉ dẫn thanh toán, tư cách pháp lý và rủi ro. | Trang 17; Phụ lục B |
| 9 | Tồn kho | Bảng commerce.inventory trên Supabase có được dùng làm số tồn kho hiện tại không? | **Không**: đó là dữ liệu phân tích lịch sử. Số chính thức là số dư trực tiếp trong hệ thống quản lý kho. Câu trả lời về tồn phải nêu ngày dữ liệu. | Trang 25, 27 |
| 10 | Tồn kho | Sản phẩm có reorder_flag=true thì hệ thống có được tự tạo PO không? | **Không**: cờ này chỉ kích hoạt rà soát bổ sung, không cho phép mua tự động và không chứng minh lead time. | Trang 28 |
| 11 | Suy luận | Đơn trả hàng đã hoàn tiền cho khách thì hàng đó đã được nhập lại kho để bán chưa? | **Không suy ra được**: bản ghi trả không có nghĩa là đã nhập lại kho, và hoàn tiền không chứng minh hàng đủ điều kiện bán lại. | Trang 35 |
| 12 | Bảo mật | API key phải được lưu ở đâu? Nếu nghi bị lộ thì làm gì? | Lưu trong **kho bí mật được duyệt** hoặc cấu hình môi trường được bảo vệ, với quyền tối thiểu; **thay ngay khi nghi lộ**. Lộ bí mật phải báo ngay qua kênh sự cố. | Trang 39, 42 |
| 13 | Ngoại lệ | Ngoại lệ đã được duyệt khi hết hạn thì sao? | **Tự hết hiệu lực**, trừ khi cấp cùng hoặc cao hơn gia hạn trước ngày hết hạn. Mỗi ngoại lệ phải có chủ, phạm vi, ngày bắt đầu và ngày hết hạn. | Trang 46 |
| 14 | Tiếng Anh | Can the AI agent issue a purchase order or adjust inventory on its own? | **No.** The agent may retrieve approved policies, query permitted data and draft proposals. It must not approve spending, issue POs, pay invoices, adjust inventory or grant access, unless a separately approved and audited flow explicitly allows that action. | Trang 44 |
| 15 | Ngoài phạm vi | Mức lương tối thiểu của nhân viên kho VietStyle là bao nhiêu? | Tài liệu **không có** thông tin này. Đáp án đúng là nói không tìm thấy hoặc từ chối, **không** được bịa ra một con số. | — |

**Gợi ý thêm:**
- Câu 16, nhiều phần: *"Mua laptop 45 triệu cho nhân viên mới: cần ai duyệt, mấy báo giá, và cấp quyền hệ thống cho nhân viên đó theo nguyên tắc nào?"* Đáp án: trưởng bộ phận; ít nhất 2 báo giá tương đương nếu thị trường cho phép; quyền tối thiểu theo vai trò, tập dữ liệu và thời hạn, gắn danh tính cá nhân, không dùng tài khoản chung. Câu này kiểm tra khả năng tách thành nhiều nhánh tìm kiếm.
- Hỏi lại câu 5 hoặc câu 6 bằng tài khoản có vai trò khác (nếu có). Mục đích là kiểm tra RBAC: người không có quyền đọc tài liệu phải nhận câu trả lời "không có bằng chứng", không lộ nội dung.

**Lưu ý:**
- Số trang ở cột "Nguồn" đã được đối chiếu với nhãn *TRANG CHÍNH SÁCH* trong file Markdown.
- Các câu 2, 3 và 5 có phép tính. Verifier sẽ kiểm tra phép tính đó, nên đây cũng là bài thử cho bản sửa lỗi dấu ngoặc.
