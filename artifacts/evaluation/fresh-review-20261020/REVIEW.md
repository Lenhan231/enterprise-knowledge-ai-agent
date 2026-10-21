# Draft question and evidence review

Assistant-authored; every intent requires independent human review. Offsets below are Unicode characters in frozen indexed chunk content, not parser-source offsets.

## F01 receiving_exception (vi; narrative)

Khi nhận hàng phát hiện thiếu hoặc hư hỏng, phải ghi nhận lúc nào và cần những bằng chứng gì?

Source: `UPLOAD-a835b48cc18c4d1baea6c2e5c3cfc54e::chunk::11`

> Ghi nhận thiếu / thừa / hư hỏng trước khi xác nhận nhận hàng; ảnh chụp và biên bản bắt buộc cho ngoại lệ.

## F01 receiving_exception (en; narrative)

When an inbound delivery is short or damaged, when must the exception be recorded and what evidence is required?

Source: `LOCAL-EN-V1-01_Inventory_Management_Policy_Manual_EN.docx::chunk::12`

> Record shortages, overages, or damage before confirming receipt; photos and an incident report are required for exceptions.

## F02 post_campaign (vi; narrative)

Sau khi chiến dịch kết thúc, cần đối chiếu forecast với những chỉ số nào để cập nhật kế hoạch?

Source: `UPLOAD-a835b48cc18c4d1baea6c2e5c3cfc54e::chunk::12`

> Sau campaign, đối chiếu forecast với sell-through, tồn còn lại và return rate để cập nhật kế hoạch.

## F02 post_campaign (en; narrative)

After a campaign ends, which outcomes must be compared with the forecast to revise the plan?

Source: `LOCAL-EN-V1-01_Inventory_Management_Policy_Manual_EN.docx::chunk::13`

> After the campaign, compare the forecast with sell-through, remaining stock, and return rate to update the plan.

## F03 emergency_po_record (vi; narrative)

Một PO khẩn cấp phải ghi rõ ba thông tin gì?

Source: `UPLOAD-a835b48cc18c4d1baea6c2e5c3cfc54e::chunk::5`

> Mọi PO khẩn cấp phải ghi rõ nguyên nhân, ảnh hưởng dịch vụ và người phê duyệt.

## F03 emergency_po_record (en; narrative)

Which three details must be documented for an emergency purchase order?

Source: `LOCAL-EN-V1-01_Inventory_Management_Policy_Manual_EN.docx::chunk::6`

> Every emergency PO must document the reason, service impact, and approver.

## F04 stock_240_days (vi; narrative)

Nếu hàng tồn vượt 240 ngày, ai phải đánh giá và đánh giá những phương án kế toán nào?

Source: `UPLOAD-a835b48cc18c4d1baea6c2e5c3cfc54e::chunk::10`

> Trên 240 ngày: Inventory Manager và Finance đánh giá dự phòng giảm giá trị / loại bỏ theo quy định kế toán.

## F04 stock_240_days (en; narrative)

For stock exceeding 240 days, who evaluates it and which accounting actions are considered?

Source: `LOCAL-EN-V1-01_Inventory_Management_Policy_Manual_EN.docx::chunk::11`

> Over 240 days: the Inventory Manager and Finance assess inventory write-downs or disposal under accounting rules.

## F05 demand_snapshots (vi; narrative)

Nhu cầu bình quân trong workbook dùng tối đa bao nhiêu snapshot, và có bắt buộc là các tháng liên tiếp không?

Source: `UPLOAD-a835b48cc18c4d1baea6c2e5c3cfc54e::chunk::17`

> Nhu cầu bình quân trong workbook lấy từ tối đa 3 snapshot gần nhất có sẵn cho SKU; các snapshot không nhất thiết là 3 tháng liên tiếp.

## F05 demand_snapshots (en; narrative)

How many snapshots can the workbook use for average demand, and must they be consecutive months?

Source: `LOCAL-EN-V1-01_Inventory_Management_Policy_Manual_EN.docx::chunk::18`

> Average demand in the workbook uses up to the three most recent available snapshots for each SKU; the snapshots are not necessarily consecutive months.

## F06 rag_policy_fields (vi; narrative)

Theo phụ lục A, những trường nào nên được giữ cùng nhau trong một chunk chính sách dùng cho RAG?

Source: `UPLOAD-a835b48cc18c4d1baea6c2e5c3cfc54e::chunk::16`

> Mã INV-POL-001 đến INV-POL-012 được xuất riêng trong policy_rules.csv để phục vụ tra cứu, nhập vào knowledge base hoặc kiểm thử Enterprise Knowledge AI Agent. Khi triển khai RAG, mỗi chunk nên giữ policy_id, owner, trigger, action, SLA và approval cùng nhau.

## F06 rag_policy_fields (en; narrative)

According to Appendix A, which fields should stay together in a policy chunk used for RAG?

Source: `LOCAL-EN-V1-01_Inventory_Management_Policy_Manual_EN.docx::chunk::17`

> Policy IDs INV-POL-001 through INV-POL-012 are exported separately in policy_rules.csv for lookup, knowledge-base ingestion, or Enterprise Knowledge AI Agent testing. For RAG, each chunk should keep policy_id, owner, trigger, action, SLA, and approval together.

## F07 blind_count (vi; narrative)

Khi áp dụng blind count, ai phân công người đếm và người đếm có được xem số lượng hệ thống không?

Source: `UPLOAD-644eabbe7e354e76a133477b5f9f1eb2::chunk::1`

> VietStyle Commerce • SOP-INV-002 • Tài liệu mô phỏng Trang 2 1. Mục đích và phạm vi Áp dụng cho SKU thời trang và outdoor trong kho / điểm xử lý đơn của mô hình VietStyle Commerce. SOP bao gồm kiểm kê chu kỳ, kiểm kê theo sự kiện và điều chỉnh chênh lệch. Không dùng SOP này để thay thế quy trình nhận hàng hoặc QA hàng trả về. 2. Khi nào phải kiểm kê đột xuất? • SKU có fill rate dưới 95% hoặc phát sinh stockout nhưng hệ thống vẫn ghi nhận lượng tồn cao. • Cờ stockout_flag và overstock_flag cùng bật; days of supply tính lại >120 ngày nhưng vẫn có stockout signal. • SKU có sai lệch lặp lại, hàng giá trị cao, nghi ngờ mất mát, lỗi barcode hoặc sai size/màu. • Sau campaign lớn, thay đổi vị trí kho, đổi mã SKU, trả hàng số lượng lớn hoặc sự cố hệ thống. 3. Chuẩn bị trước khi đếm • Inventory Controller xuất danh sách SKU, vị trí, đơn vị tính, snapshot timestamp và số lượng hệ thống. • Warehouse Supervisor phân công người đếm; người đếm không được xem số lượng hệ thống nếu tổ chức áp dụng blind count.

## F07 blind_count (en; narrative)

During a blind count, who assigns the counters and may they see the system quantities?

Source: `LOCAL-EN-V1-02_SOP_Cycle_Count_and_Stock_Adjustment_EN.pdf::chunk::1`

> Purpose and Scope Applies to fashion and outdoor SKUs in warehouses / fulfillment locations in the VietStyle Commerce model. This SOP covers cycle counts, event-triggered counts, and variance adjustments. It does not replace receiving procedures or QA for returned goods. 2. When Is an Ad Hoc Count Required? • A SKU has a fill rate below 95% or experiences a stockout while the system still records high inventory. • Both stockout_flag and overstock_flag are enabled; recalculated days of supply exceeds 120 days while a stockout signal remains. • A SKU has recurring variances, high value, suspected loss, barcode errors, or size/color mismatches. • After a major campaign, warehouse-location change, SKU-code change, large return, or system incident. 3. Preparation Before Counting • The Inventory Controller exports the SKU list, location, unit of measure, snapshot timestamp, and system quantity. • The Warehouse Supervisor assigns counters; counters must not see system quantities when blind counting is used.

## F08 variant_count (vi; narrative)

Có được gộp các biến thể gần giống nhau khi kiểm kê không, và cần đếm theo các chiều nào?

Source: `UPLOAD-644eabbe7e354e76a133477b5f9f1eb2::chunk::2`

> • Đóng băng giao dịch tại vị trí cần đếm hoặc ghi lại mọi giao dịch phát sinh trong cửa sổ đếm. • Chuẩn bị thiết bị quét, nhãn cách ly, biểu mẫu ghi nhận, camera và phương án xử lý hàng đang pick / pack / chuyển kho. 4. Thực hiện đếm và đối chiếu • Đếm theo SKU + size + color + vị trí; không gộp các biến thể gần giống nhau. • Ghi số lượng thực tế, đơn vị tính, người đếm, thời điểm và tình trạng bao bì. • Nếu có chênh lệch, thực hiện recount bởi người thứ hai trước khi sửa số liệu. • Đối chiếu receipts, picks, shipments, returns, transfers, cancellations và các giao dịch chờ đồng bộ. • Tính chênh lệch tuyệt đối = |thực tế − hệ thống|; tỷ lệ chênh lệch = chênh lệch / max(hệ thống, 1). 5.

## F08 variant_count (en; narrative)

May similar variants be combined during a count, and which identifiers must distinguish counted stock?

Source: `LOCAL-EN-V1-02_SOP_Cycle_Count_and_Stock_Adjustment_EN.pdf::chunk::2`

> • Freeze transactions at the location being counted or record every transaction occurring during the count window. • Prepare scanners, quarantine labels, recording forms, cameras, and a plan for goods being picked, packed, or transferred. 4. Counting and Reconciliation • Count by SKU + size + color + location; do not combine similar variants. • Record actual quantity, unit of measure, counter, timestamp, and packaging

## F09 small_adjustment_deadline (vi; table)

Với điều chỉnh tồn nhỏ có đủ bằng chứng, ai phê duyệt và thời hạn xử lý là bao lâu?

Source: `UPLOAD-a835b48cc18c4d1baea6c2e5c3cfc54e::chunk::13`

> Row 3: Loại quyết định: Điều chỉnh tồn nhỏ, có đủ bằng chứng | Luồng phê duyệt: Người đếm ≠ người nhập → Warehouse Supervisor | Thời điểm: Trong 1 ngày làm việc

## F09 small_adjustment_deadline (en; table)

For a small inventory adjustment with sufficient evidence, who approves it and what is the processing deadline?

Source: `LOCAL-EN-V1-01_Inventory_Management_Policy_Manual_EN.docx::chunk::14`

> Row 3: Decision Type: Small inventory adjustment with sufficient evidence | Approval Flow: Counter ≠ data-entry person → Warehouse Supervisor | Timing: Within 1 business day

## F10 disposal_approval (vi; table)

Thanh lý, scrap hoặc ghi giảm giá trị cần những bên nào phê duyệt và theo thẩm quyền nào?

Source: `UPLOAD-a835b48cc18c4d1baea6c2e5c3cfc54e::chunk::13`

> Row 5: Loại quyết định: Thanh lý / scrap / ghi giảm giá trị | Luồng phê duyệt: QA + Inventory Manager + Finance | Thời điểm: Theo thẩm quyền tài chính

## F10 disposal_approval (en; table)

Which parties approve disposal, scrap, or a write-down, and which authority governs it?

Source: `LOCAL-EN-V1-01_Inventory_Management_Policy_Manual_EN.docx::chunk::14`

> Row 5: Decision Type: Disposal / scrap / write-down | Approval Flow: QA + Inventory Manager + Finance | Timing: According to financial authority

## F11 class_b_investigation (vi; table)

Nhóm B đóng góp khoảng bao nhiêu phần trăm giá trị tiêu thụ, được kiểm kê bao lâu một lần và có SLA điều tra bao lâu?

Source: `UPLOAD-a835b48cc18c4d1baea6c2e5c3cfc54e::chunk::6`

> Row 2: Nhóm: B | Tiêu chí tham chiếu: Nhóm tiếp theo đóng góp xấp xỉ 15% | Tần suất: Hằng tháng | SLA điều tra: Điều tra trong 2 ngày làm việc

## F11 class_b_investigation (en; table)

Approximately what consumption-value share defines class B, how often is it counted, and what is its variance-investigation SLA?

Source: `LOCAL-EN-V1-01_Inventory_Management_Policy_Manual_EN.docx::chunk::7`

> Row 2: Class: B | Reference Criteria: Next group contributing approximately 15% | Frequency: Monthly | Investigation SLA: Investigate within 2 business days

## F12 recurring_variance (vi; mixed_pdf)

Theo bảng ngưỡng xử lý trong SOP, chênh lệch lặp lại hoặc giá trị lớn cần hành động gì và ai duyệt?

Source: `UPLOAD-644eabbe7e354e76a133477b5f9f1eb2::chunk::3`

> Chênh lệch lặp lại, giá trị lớn hoặc vượt ngưỡng nội bộ Giữ giao dịch liên quan; điều tra nguyên nhân gốc Inventory Manager + Finance 

## F12 recurring_variance (en; mixed_pdf)

According to the SOP handling-threshold table, what action and approvers apply to recurring or high-value variances?

Source: `LOCAL-EN-V1-02_SOP_Cycle_Count_and_Stock_Adjustment_EN.pdf::chunk::3`

> Recurring, high-value variance or a variance above internal thresholds Hold related transactions; investigate the root cause Inventory Manager + Finance 
