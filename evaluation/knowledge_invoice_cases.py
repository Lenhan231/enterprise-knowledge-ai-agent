"""Author-reviewed v1 fixtures; freeze before calling either agent."""

# question, independent reference answer, approved enterprise policy pages.
KNOWLEDGE = [
    ('Theo chính sách VietStyle, trước khi dùng số tồn trong một báo cáo phải xác định thông tin thời gian nào?', 'Phải xác định ngày dữ liệu, chọn snapshot phù hợp mới nhất cho sản phẩm và kỳ được hỏi, và ghi rõ đó là dữ liệu lịch sử nếu nguồn cũ.', [25, 27]),
    ('Một sản phẩm không xuất hiện trong snapshot: có được kết luận tồn bằng không không?', 'Không được coi sản phẩm thiếu trong snapshot là tồn bằng không; phải nêu thiếu dữ liệu.', [25]),
    ('Có được cộng stock_on_hand của nhiều ngày để làm tổng tồn kỳ không?', 'Không. Mỗi hàng là trạng thái tại một ngày; không cộng số lượng tồn qua ngày.', [25]),
    ('Nếu inventory và products ghi tên hoặc category khác nhau, dùng nguồn nào làm danh mục chuẩn?', 'Dùng commerce.products làm metadata danh mục chuẩn, product_id làm khóa và đánh dấu sai lệch với inventory.', [26]),
    ('Hai biến thể trùng tên phải được phân giải như thế nào trước khi phân tích tồn?', 'Phân giải thành đúng một product_id, so kích thước, màu, phân khúc và thuộc tính khác; nếu chưa xác định thì yêu cầu làm rõ, không tạo ID giả.', [26]),
    ('Snapshot cuối năm 2022 có thể chứng minh hàng đang bán được trong năm 2026 không?', 'Không. Snapshot lịch sử không chứng minh khả dụng hiện tại. Phải nêu ngày lịch sử và giới hạn, rồi xác minh trong hệ thống trực tiếp.', [27]),
    ('Chính sách yêu cầu báo cáo xu hướng tồn công bố những gì về các kỳ dữ liệu?', 'So các kỳ tương đương, nêu ngày snapshot, kỳ thiếu và dữ liệu hàng ngày, tháng hay không đều. Không nội suy kỳ thiếu để cam kết hàng.', [27]),
    ('reorder_flag=true có tự cho phép phát hành PO không?', 'Không. reorder_flag, stockout_flag hoặc days_of_supply thấp chỉ kích hoạt rà bổ sung; không tự tạo PO hay cho phép mua.', [28]),
    ('Trước khi đề nghị bổ sung hàng, phải xác minh những yếu tố nào ngoài các chỉ số snapshot?', 'Xác minh tồn trực tiếp, hàng đã phân bổ, cam kết mua mở, lead time, số đặt tối thiểu và trạng thái nhà cung cấp trong hệ thống nghiệp vụ; dùng phương pháp kế hoạch đã duyệt.', [28]),
    ('Khi chỉ số bổ sung hàng mâu thuẫn nhau, phải gắn trạng thái nào và làm gì?', 'Gắn DATA_CONFLICT và điều tra trước khi cam kết; không tự tạo lead time hoặc số đặt tối thiểu còn thiếu.', [28]),
    ('Có thể hứa ngày giao cho khách chỉ từ fill_rate lịch sử không?', 'Không. Phải xác minh tồn có thể bán hiện tại; không hứa ngày giao chỉ theo fill_rate lịch sử.', [29]),
    ('Thiếu hàng ảnh hưởng lớn hoặc lặp lại phải chuyển đến những bộ phận nào?', 'Chuyển đến chủ Tồn kho và Kinh doanh; xác minh tồn, đơn bị ảnh hưởng, biện pháp giảm thiểu và ghi nguyên nhân.', [29]),
    ('overstock_flag=true có cho phép tự thanh lý hay giảm giá không?', 'Không. Cờ dư hàng hoặc days_of_supply cao chỉ kích hoạt rà; cần cấp Kinh doanh và Tài chính liên quan duyệt trước khi đổi giá hoặc xử lý hàng.', [30]),
    ('Khi rà hàng dư, chính sách cho phép cân nhắc những phương án xử lý nào?', 'Có thể đánh giá điều chuyển, trả nhà cung cấp, giảm giá đã duyệt, bán gói hoặc giữ nguyên; theo dõi kết quả sau kỳ xác định.', [30]),
    ('Trong cửa sổ kiểm kê chu kỳ, phải kiểm soát luân chuyển hàng ra sao?', 'Đóng băng hoặc ghi nhận luân chuyển trong cửa sổ đếm; đếm theo danh tính sản phẩm, vị trí và đơn vị đã duyệt.', [31]),
    ('Sai lệch kiểm kê trọng yếu cần ai đếm lại và phiếu đếm có tự điều chỉnh tồn không?', 'Người độc lập đếm lại sai lệch trọng yếu. Phiếu đếm không tự là giao dịch điều chỉnh; phải so với hệ thống trực tiếp và giải thích lệch.', [31]),
    ('Hồ sơ bằng chứng cho kiểm kê chu kỳ phải chứa những nội dung nào?', 'Kế hoạch đếm, danh tính người đếm, thời điểm, vị trí, lượng thực, lượng sổ, đếm lại và giải thích lệch.', [31]),
    ('Người tự phát hiện chênh lệch trọng yếu có được làm người duyệt duy nhất cho điều chỉnh không?', 'Không. Người đếm không được là người duyệt duy nhất cho điều chỉnh trọng yếu; cần bằng chứng và phê duyệt phù hợp.', [32]),
    ('Có được sửa commerce.inventory để ghi nhận điều chỉnh vật lý sau kiểm kê không?', 'Không sửa snapshot lịch sử để giả lập điều chỉnh. Sau duyệt, ghi trong hệ thống tồn trực tiếp, đối chiếu số dư và giữ mã giao dịch.', [32]),
    ('Mất hàng không giải thích lặp lại hoặc nghi gian lận phải được chuyển tới đâu?', 'Chuyển Bảo mật và Tài chính, giữ bằng chứng và phê duyệt liên quan.', [32]),
    ('Khi nhận hàng, lượng giao, lượng chấp nhận và lượng từ chối phải được ghi như thế nào?', 'Ghi riêng lượng giao thực, lượng chấp nhận và lượng từ chối. Chấp nhận cộng từ chối không vượt lượng giao; chỉ hàng chấp nhận được xếp kho để bán hoặc đối chiếu hóa đơn chuẩn.', [33]),
    ('Hàng nhận không đạt hoặc chưa rõ tình trạng phải được xử lý trước xếp kho ra sao?', 'Đưa vào khu giữ chất lượng có nhãn rõ, kiểm hư hỏng và thông báo Mua sắm cùng nhà cung cấp về thiếu, thừa hoặc hỏng.', [33]),
    ('Hàng giữ kiểm định hoặc thu hồi có được tính là hàng có thể bán không?', 'Không. Phải tách vật lý, dán nhãn hàng hạn chế; chỉ giải phóng giữ khi có quyết định chất lượng có thẩm quyền.', [34]),
    ('Bản ghi trả hàng và refund_amount có chứng minh sản phẩm đã nhập lại kho bán được không?', 'Không. Trả hàng không tự nghĩa đã nhập lại kho và tiền hoàn không chứng minh đủ bán lại. Hoàn tiền và xử lý tồn là hai quyết định riêng.', [35]),
    ('Trước khi hoàn tiền và xử lý hàng trả, cần giữ những bằng chứng định danh và kiểm tra nào?', 'Giữ ID trả, ID đơn, ID sản phẩm, lượng, lý do, kết quả kiểm, phương án xử lý và bằng chứng hoàn. Không suy tình trạng chỉ từ return_reason.', [35]),
    ('Theo duy nhất chính sách này, chính xác còn bao nhiêu chiếc SKU VS-UNKNOWN ở kho lúc này?', 'Không đủ thông tin để xác định số tồn hiện tại cho SKU này; chính sách không cung cấp giao dịch tồn trực tiếp.', [25, 27]),
    ('Theo duy nhất chính sách này, thời gian giao thực tế của nhà cung cấp SUP-UNKNOWN hôm nay là mấy ngày?', 'Không đủ thông tin. Không có lead time hoặc giao dịch thực tế cho nhà cung cấp này trong nguồn được cung cấp; cần xác minh hệ thống nghiệp vụ.', [28]),
    ('Chỉ từ chính sách này, hãy nêu số lượng mua tối ưu chính xác cho SKU VS-UNKNOWN vào ngày mai.', 'Không đủ thông tin để đưa số mua chính xác; cần tồn trực tiếp, cam kết mở, nhu cầu, lead time, số đặt tối thiểu và phương pháp đã duyệt.', [28]),
    ('Theo duy nhất chính sách này, ai là người đã duyệt điều chỉnh tồn ADJ-UNKNOWN sáng nay?', 'Không đủ thông tin để xác định người duyệt một giao dịch cụ thể. Chính sách không chứa sổ điều chỉnh hoặc giao dịch đó.', [31, 32]),
    ('Chỉ từ chính sách VietStyle, cho biết chính xác vị trí ô kho và số sê-ri của sản phẩm VS-UNKNOWN.', 'Không đủ thông tin để xác định ô kho và sê-ri cụ thể; cần hệ thống kho trực tiếp, không được suy diễn.', [34]),
]

# Independent SQL oracles. Strict named columns; question requests these aliases.
INVOICES = [
    ('How many approved invoices are available? Return invoice_count.', 'SELECT COUNT(DISTINCT inv.invoice_id) AS invoice_count FROM commerce.invoices AS inv LIMIT 1'),
    ('List the latest 20 approved invoices with invoice_id, invoice_no, invoice_date and source_filename; order by invoice_date descending, then invoice_id.', 'SELECT inv.invoice_id, inv.invoice_no, inv.invoice_date, inv.source_filename FROM commerce.invoices AS inv ORDER BY inv.invoice_date DESC NULLS FIRST, inv.invoice_id LIMIT 20'),
    ('Show total invoice amount by seller and currency. Return seller, currency, invoice_total; sort by seller and currency.', 'SELECT inv.seller, inv.currency, SUM(inv.total_amount) AS invoice_total FROM commerce.invoices AS inv GROUP BY inv.seller, inv.currency ORDER BY inv.seller, inv.currency LIMIT 200'),
    ('Show total invoice tax by currency. Return currency and invoice_tax.', 'SELECT inv.currency, SUM(inv.tax_amount) AS invoice_tax FROM commerce.invoices AS inv GROUP BY inv.currency ORDER BY inv.currency LIMIT 200'),
    ('Count approved invoices by buyer. Return buyer and invoice_count.', 'SELECT inv.buyer, COUNT(DISTINCT inv.invoice_id) AS invoice_count FROM commerce.invoices AS inv GROUP BY inv.buyer ORDER BY inv.buyer LIMIT 200'),
    ('Show invoice totals by calendar month and currency. Return month, currency and invoice_total.', "SELECT DATE_TRUNC('month', inv.invoice_date) AS month, inv.currency, SUM(inv.total_amount) AS invoice_total FROM commerce.invoices AS inv GROUP BY DATE_TRUNC('month', inv.invoice_date), inv.currency ORDER BY 1, 2 LIMIT 200"),
    ('List the first 20 invoice items with invoice_id, line_no, description, unit, quantity, unit_price and amount, ordered by invoice_id and line_no.', 'SELECT li.invoice_id, li.line_no, li.description, li.unit, li.quantity, li.unit_price, li.amount FROM commerce.invoice_items AS li ORDER BY li.invoice_id, li.line_no LIMIT 20'),
    ('Show the sum of invoice item amounts by seller and invoice currency. Return seller, currency and invoice_item_amount.', 'SELECT inv.seller, inv.currency, SUM(li.amount) AS invoice_item_amount FROM commerce.invoice_items AS li JOIN commerce.invoices AS inv ON li.invoice_id = inv.invoice_id GROUP BY inv.seller, inv.currency ORDER BY inv.seller, inv.currency LIMIT 200'),
    ('Count approved invoices with unknown currency. Return invoice_count.', 'SELECT COUNT(DISTINCT inv.invoice_id) AS invoice_count FROM commerce.invoices AS inv WHERE inv.currency IS NULL LIMIT 1'),
    ('Find approved invoices whose invoice_no is BENCHMARK-NOT-EXIST-20261110. Return invoice_id and source_filename.', "SELECT inv.invoice_id, inv.source_filename FROM commerce.invoices AS inv WHERE inv.invoice_no = 'BENCHMARK-NOT-EXIST-20261110' ORDER BY inv.invoice_id LIMIT 200"),
]
