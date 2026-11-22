# Review: vietstyle-dev-v3 (60 items)

For each item, check: is the question natural? Does the expected answer match the gold passage? Is anything missing or wrong? Mark **OK** or write the change next to the id.

## lookup

### D001 · role `employee` · vi · expected **answer**
**Q:** Nhân viên làm đủ một năm được bao nhiêu ngày nghỉ phép năm có lương?

**Expected:** VietStyle cấp 12 ngày làm việc nghỉ phép năm có lương cho một năm làm việc đầy đủ, tính theo tỷ lệ nếu chưa đủ năm; quyền lợi theo luật hoặc hợp đồng có lợi hơn được ưu tiên.
- must include: `12`
- gold VN#82: _Điều kiện và quyền nghỉ phép Quy tắc bắt buộc. Quyền theo luật và loại nghỉ được pháp luật bảo vệ là mức tối thiểu. VietStyle cấp 12 ngày làm việc nghỉ phép năm có lương cho một năm làm việc đầy đủ trong điều kiện thông thường, tính theo tỷ lệ nếu chưa đủ năm; quyền lợi theo luật hoặc hợp đồng có lợi hơn được ưu tiên._

Review: 

### D002 · role `employee` · vi · expected **answer**
**Q:** Đề nghị hoàn chi phí công việc phải nộp trong thời hạn bao lâu?

**Expected:** Nộp trong 30 ngày lịch kể từ ngày giao dịch hoặc ngày trở về từ chuyến công tác đã duyệt, lấy mốc muộn hơn.
- must include: `30 ngày`
- gold VN#166: _Quy trình bắt buộc Nộp trong 30 ngày lịch từ giao dịch hoặc ngày trở về chuyến công tác đã duyệt, lấy mốc muộn hơn._

Review: 

### D003 · role `employee` · vi · expected **answer**
**Q:** Nếu phải mua khẩn mà không kịp xin duyệt trước, chậm nhất khi nào phải báo cho Tài chính?

**Expected:** Báo lãnh đạo được chỉ định và Tài chính sớm nhất có thể, không muộn hơn một ngày làm việc sau khi cam kết.
- must include: `một ngày làm việc|1 ngày làm việc`
- gold VN#332: _Quy trình bắt buộc Nếu thực sự không thể duyệt trước, báo lãnh đạo chỉ định và Tài chính sớm nhất có thể, không muộn hơn một ngày làm việc sau cam kết._

Review: 

### D004 · role `employee` · vi · expected **answer**
**Q:** Quyền truy cập vào hệ thống nhạy cảm phải được rà soát định kỳ bao lâu một lần?

**Expected:** Rà quyền khi đổi vai trò và ít nhất mỗi quý đối với hệ thống nhạy cảm.
- must include: `quý`
- gold VN#528: _Quy trình bắt buộc Rà quyền khi đổi vai trò, ít nhất mỗi quý với hệ thống nhạy cảm._

Review: 

### D005 · role `employee` · vi · expected **answer**
**Q:** Khi muốn tăng giá trị hoặc số lượng trên một PO đã phát hành thì phải làm gì trước?

**Expected:** Thay đổi làm tăng giá trị, số lượng, phạm vi, rủi ro hoặc nghĩa vụ giao phải được rà soát trước khi chỉ đạo nhà cung cấp; so với PO và phê duyệt ban đầu, tính lại tổng cam kết và cấp duyệt.
- must include: `rà|duyệt` · `tổng cam kết|cấp duyệt`
- gold VN#301: _Thay đổi, hủy và cam kết đang mở Quy tắc bắt buộc. Thay đổi tăng giá trị, số lượng, phạm vi, rủi ro hoặc nghĩa vụ giao phải rà trước khi chỉ đạo nhà cung cấp thực hiện._
- gold VN#302: _Quy trình bắt buộc So thay đổi với PO đã phát hành và duyệt ban đầu.  Tính lại tổng cam kết và cấp duyệt._

Review: 

## amount

### D006 · role `employee` · vi · expected **answer**
**Q:** Mua máy lọc nước 4tr5 thì ai duyệt?

**Expected:** 4.500.000 VND thuộc mức đến 5.000.000 VND nên do quản lý trực tiếp phê duyệt; cần một báo giá có hồ sơ và ngân sách xác nhận.
- must include: `Quản lý trực tiếp|quản lý trực tiếp`
- must not include: `Trưởng bộ phận`
- gold VN#274: _Ma trận phê duyệt và ngưỡng tiền Quy tắc bắt buộc. Thẩm quyền mặc định cho một cam kết: đến 5.000.000 VND-quản lý trực tiếp; 5.000.001-50.000.000 VND-trưởng bộ phận; 50.000.001-200.000.000 VND-trưởng bộ phận cùng Mua sắm và Tài chính; trên 200.000.000 VND-Hội đồng Điều hành Vận hành cùng Tài chính._
- gold VN#730: _Phụ lục B - Hạn mức phê duyệt và bảng quyết định vận hành Columns: Tổng cam kết | Phê duyệt bắt buộc | Điều kiện bổ sung Row 1: Tổng cam kết: Đến 5.000.000 VND | Phê duyệt bắt buộc: Quản lý trực tiếp | Điều kiện bổ sung: Một báo giá có hồ sơ; ngân sách xác nhận. Row 2: Tổng cam kết: 5.000.001-50.000.000 VND | Phê duyệt bắt buộc: Trưởng bộ phận | Điều kiện bổ sung: Ít nhất hai báo giá tương đương nếu thị trường cho ph_

Review: 

### D007 · role `employee` · vi · expected **answer**
**Q:** Đặt in áo cho team 12 củ thì cần mấy báo giá?

**Expected:** 12.000.000 VND nằm trong khoảng 5.000.001–50.000.000 VND nên cần ít nhất hai báo giá tương đương nếu thị trường cho phép.
- must include: `hai|2`
- gold VN#261: _Tìm nguồn cạnh tranh và đánh giá báo giá Quy tắc bắt buộc. Cam kết dự toán đến 5.000.000 VND có thể dùng một báo giá được lập hồ sơ. Từ 5.000.001 đến 50.000.000 VND cần tìm ít nhất hai báo giá tương đương nếu thị trường cho phép. Trên 50.000.000 VND cần ít nhất ba báo giá bằng văn bản hoặc giải trình chỉ định nguồn được lập hồ sơ._
- gold VN#730: _Phụ lục B - Hạn mức phê duyệt và bảng quyết định vận hành Columns: Tổng cam kết | Phê duyệt bắt buộc | Điều kiện bổ sung Row 1: Tổng cam kết: Đến 5.000.000 VND | Phê duyệt bắt buộc: Quản lý trực tiếp | Điều kiện bổ sung: Một báo giá có hồ sơ; ngân sách xác nhận. Row 2: Tổng cam kết: 5.000.001-50.000.000 VND | Phê duyệt bắt buộc: Trưởng bộ phận | Điều kiện bổ sung: Ít nhất hai báo giá tương đương nếu thị trường cho ph_

Review: 

### D008 · role `employee` · vi · expected **answer**
**Q:** Mua văn phòng phẩm 500k có cần ai duyệt không?

**Expected:** 500.000 VND thuộc mức đến 5.000.000 VND: quản lý trực tiếp phê duyệt, kèm một báo giá có hồ sơ và ngân sách xác nhận.
- must include: `Quản lý trực tiếp|quản lý trực tiếp`
- gold VN#274: _Ma trận phê duyệt và ngưỡng tiền Quy tắc bắt buộc. Thẩm quyền mặc định cho một cam kết: đến 5.000.000 VND-quản lý trực tiếp; 5.000.001-50.000.000 VND-trưởng bộ phận; 50.000.001-200.000.000 VND-trưởng bộ phận cùng Mua sắm và Tài chính; trên 200.000.000 VND-Hội đồng Điều hành Vận hành cùng Tài chính._
- gold VN#730: _Phụ lục B - Hạn mức phê duyệt và bảng quyết định vận hành Columns: Tổng cam kết | Phê duyệt bắt buộc | Điều kiện bổ sung Row 1: Tổng cam kết: Đến 5.000.000 VND | Phê duyệt bắt buộc: Quản lý trực tiếp | Điều kiện bổ sung: Một báo giá có hồ sơ; ngân sách xác nhận. Row 2: Tổng cam kết: 5.000.001-50.000.000 VND | Phê duyệt bắt buộc: Trưởng bộ phận | Điều kiện bổ sung: Ít nhất hai báo giá tương đương nếu thị trường cho ph_

Review: 

### D009 · role `employee` · vi · expected **answer**
**Q:** Hợp đồng dịch vụ đúng 50.000.000 VND thì cấp nào phê duyệt?

**Expected:** 50.000.000 VND vẫn thuộc khoảng 5.000.001–50.000.000 VND nên trưởng bộ phận phê duyệt (chưa cần Mua sắm và Tài chính).
- must include: `Trưởng bộ phận|trưởng bộ phận`
- must not include: `Mua sắm và Tài chính` · `Mua sắm + Tài chính`
- gold VN#274: _Ma trận phê duyệt và ngưỡng tiền Quy tắc bắt buộc. Thẩm quyền mặc định cho một cam kết: đến 5.000.000 VND-quản lý trực tiếp; 5.000.001-50.000.000 VND-trưởng bộ phận; 50.000.001-200.000.000 VND-trưởng bộ phận cùng Mua sắm và Tài chính; trên 200.000.000 VND-Hội đồng Điều hành Vận hành cùng Tài chính._
- gold VN#730: _Phụ lục B - Hạn mức phê duyệt và bảng quyết định vận hành Columns: Tổng cam kết | Phê duyệt bắt buộc | Điều kiện bổ sung Row 1: Tổng cam kết: Đến 5.000.000 VND | Phê duyệt bắt buộc: Quản lý trực tiếp | Điều kiện bổ sung: Một báo giá có hồ sơ; ngân sách xác nhận. Row 2: Tổng cam kết: 5.000.001-50.000.000 VND | Phê duyệt bắt buộc: Trưởng bộ phận | Điều kiện bổ sung: Ít nhất hai báo giá tương đương nếu thị trường cho ph_

Review: 

### D010 · role `employee` · vi · expected **answer**
**Q:** Mua thiết bị 5 triệu thì quản lý trực tiếp tự duyệt được không?

**Expected:** Được: cam kết đến 5.000.000 VND (bao gồm đúng 5.000.000 VND) thuộc thẩm quyền quản lý trực tiếp.
- must include: `Quản lý trực tiếp|quản lý trực tiếp`
- must not include: `Trưởng bộ phận phê duyệt`
- gold VN#274: _Ma trận phê duyệt và ngưỡng tiền Quy tắc bắt buộc. Thẩm quyền mặc định cho một cam kết: đến 5.000.000 VND-quản lý trực tiếp; 5.000.001-50.000.000 VND-trưởng bộ phận; 50.000.001-200.000.000 VND-trưởng bộ phận cùng Mua sắm và Tài chính; trên 200.000.000 VND-Hội đồng Điều hành Vận hành cùng Tài chính._
- gold VN#730: _Phụ lục B - Hạn mức phê duyệt và bảng quyết định vận hành Columns: Tổng cam kết | Phê duyệt bắt buộc | Điều kiện bổ sung Row 1: Tổng cam kết: Đến 5.000.000 VND | Phê duyệt bắt buộc: Quản lý trực tiếp | Điều kiện bổ sung: Một báo giá có hồ sơ; ngân sách xác nhận. Row 2: Tổng cam kết: 5.000.001-50.000.000 VND | Phê duyệt bắt buộc: Trưởng bộ phận | Điều kiện bổ sung: Ít nhất hai báo giá tương đương nếu thị trường cho ph_

Review: 

## calculation

### D011 · role `employee` · vi · expected **answer**
**Q:** Nếu mua 3 lần, mỗi lần 2 triệu cho cùng một nhu cầu thì ai duyệt?

**Expected:** Duyệt theo tổng cam kết và không được chia nhỏ để tránh ngưỡng: 3 × 2.000.000 = 6.000.000 VND, thuộc 5.000.001–50.000.000 VND nên trưởng bộ phận phê duyệt.
- must include: `6.000.000|6 triệu` · `Trưởng bộ phận|trưởng bộ phận`
- must not include: `Quản lý trực tiếp phê duyệt`
- gold VN#274: _Ma trận phê duyệt và ngưỡng tiền Quy tắc bắt buộc. Thẩm quyền mặc định cho một cam kết: đến 5.000.000 VND-quản lý trực tiếp; 5.000.001-50.000.000 VND-trưởng bộ phận; 50.000.001-200.000.000 VND-trưởng bộ phận cùng Mua sắm và Tài chính; trên 200.000.000 VND-Hội đồng Điều hành Vận hành cùng Tài chính._
- gold VN#730: _Phụ lục B - Hạn mức phê duyệt và bảng quyết định vận hành Columns: Tổng cam kết | Phê duyệt bắt buộc | Điều kiện bổ sung Row 1: Tổng cam kết: Đến 5.000.000 VND | Phê duyệt bắt buộc: Quản lý trực tiếp | Điều kiện bổ sung: Một báo giá có hồ sơ; ngân sách xác nhận. Row 2: Tổng cam kết: 5.000.001-50.000.000 VND | Phê duyệt bắt buộc: Trưởng bộ phận | Điều kiện bổ sung: Ít nhất hai báo giá tương đương nếu thị trường cho ph_
- gold VN#224: _Yêu cầu kiểm soát Không chia nhỏ mua sắm để tránh ngưỡng.  Khẩn không miễn ghi nhận; mua khẩn phải lập hồ sơ và rà soát._

Review: 

### D012 · role `employee` · vi · expected **answer**
**Q:** Tôi đã làm đủ 7 tháng thì đã tích lũy được bao nhiêu ngày phép năm?

**Expected:** Phép năm tích lũy 1/12 quyền phép năm cho mỗi tháng làm việc hoàn tất; với 12 ngày/năm, 7 tháng tích lũy 7 ngày.
- must include: `7`
- gold VN#84: _Quy trình bắt buộc Phép năm tích lũy bằng một phần mười hai quyền phép năm áp dụng cho mỗi tháng làm việc hoàn tất, trừ khi quy định hợp pháp yêu cầu cách tính có lợi hơn._
- gold VN#82: _Điều kiện và quyền nghỉ phép Quy tắc bắt buộc. Quyền theo luật và loại nghỉ được pháp luật bảo vệ là mức tối thiểu. VietStyle cấp 12 ngày làm việc nghỉ phép năm có lương cho một năm làm việc đầy đủ trong điều kiện thông thường, tính theo tỷ lệ nếu chưa đủ năm; quyền lợi theo luật hoặc hợp đồng có lợi hơn được ưu tiên._

Review: 

### D013 · role `employee` · vi · expected **answer**
**Q:** Tôi có hóa đơn ngày 2/3, đi công tác về ngày 10/3. Hạn chót nộp đề nghị hoàn chi là ngày nào?

**Expected:** Hạn là 30 ngày lịch kể từ mốc muộn hơn giữa ngày giao dịch và ngày trở về, tức 10/3 + 30 ngày = 9/4.
- must include: `9/4|09/04|9 tháng 4`
- gold VN#166: _Quy trình bắt buộc Nộp trong 30 ngày lịch từ giao dịch hoặc ngày trở về chuyến công tác đã duyệt, lấy mốc muộn hơn._

Review: 

### D014 · role `employee` · vi · expected **answer**
**Q:** Mua 2 laptop, mỗi cái 20 củ thì cần mấy báo giá và ai duyệt?

**Expected:** Tổng cam kết 2 × 20.000.000 = 40.000.000 VND, thuộc 5.000.001–50.000.000 VND: cần ít nhất hai báo giá tương đương và trưởng bộ phận phê duyệt.
- must include: `40.000.000|40 triệu` · `hai|2` · `Trưởng bộ phận|trưởng bộ phận`
- gold VN#261: _Tìm nguồn cạnh tranh và đánh giá báo giá Quy tắc bắt buộc. Cam kết dự toán đến 5.000.000 VND có thể dùng một báo giá được lập hồ sơ. Từ 5.000.001 đến 50.000.000 VND cần tìm ít nhất hai báo giá tương đương nếu thị trường cho phép. Trên 50.000.000 VND cần ít nhất ba báo giá bằng văn bản hoặc giải trình chỉ định nguồn được lập hồ sơ._
- gold VN#274: _Ma trận phê duyệt và ngưỡng tiền Quy tắc bắt buộc. Thẩm quyền mặc định cho một cam kết: đến 5.000.000 VND-quản lý trực tiếp; 5.000.001-50.000.000 VND-trưởng bộ phận; 50.000.001-200.000.000 VND-trưởng bộ phận cùng Mua sắm và Tài chính; trên 200.000.000 VND-Hội đồng Điều hành Vận hành cùng Tài chính._
- gold VN#730: _Phụ lục B - Hạn mức phê duyệt và bảng quyết định vận hành Columns: Tổng cam kết | Phê duyệt bắt buộc | Điều kiện bổ sung Row 1: Tổng cam kết: Đến 5.000.000 VND | Phê duyệt bắt buộc: Quản lý trực tiếp | Điều kiện bổ sung: Một báo giá có hồ sơ; ngân sách xác nhận. Row 2: Tổng cam kết: 5.000.001-50.000.000 VND | Phê duyệt bắt buộc: Trưởng bộ phận | Điều kiện bổ sung: Ít nhất hai báo giá tương đương nếu thị trường cho ph_

Review: 

### D015 · role `employee` · vi · expected **answer**
**Q:** Mua khẩn được cam kết vào thứ Hai mà chưa kịp xin duyệt. Hạn báo Tài chính và hạn hoàn tất rà soát sau mua là khi nào?

**Expected:** Phải báo lãnh đạo chỉ định và Tài chính không muộn hơn một ngày làm việc sau cam kết (thứ Ba), và hoàn tất rà soát nguồn cung, bằng chứng, phê duyệt trong năm ngày làm việc (đến thứ Hai tuần sau).
- must include: `thứ Ba` · `năm ngày làm việc|5 ngày làm việc`
- gold VN#332: _Quy trình bắt buộc Nếu thực sự không thể duyệt trước, báo lãnh đạo chỉ định và Tài chính sớm nhất có thể, không muộn hơn một ngày làm việc sau cam kết._
- gold VN#333: _Quy trình bắt buộc Hoàn tất rà soát nguồn cung, bằng chứng và phê duyệt trong năm ngày làm việc._

Review: 

## multi_part

### D016 · role `employee` · vi · expected **answer**
**Q:** Nghỉ phép năm được bao nhiêu ngày và ai là người có quyền duyệt đơn nghỉ?

**Expected:** 12 ngày làm việc có lương cho một năm làm việc đầy đủ; quyết định nghỉ do quản lý hoặc người được Nhân sự ủy quyền hợp lệ thực hiện.
- must include: `12` · `quản lý|Nhân sự ủy quyền`
- gold VN#82: _Điều kiện và quyền nghỉ phép Quy tắc bắt buộc. Quyền theo luật và loại nghỉ được pháp luật bảo vệ là mức tối thiểu. VietStyle cấp 12 ngày làm việc nghỉ phép năm có lương cho một năm làm việc đầy đủ trong điều kiện thông thường, tính theo tỷ lệ nếu chưa đủ năm; quyền lợi theo luật hoặc hợp đồng có lợi hơn được ưu tiên._
- gold VN#109: _Phê duyệt, từ chối và thay đổi nghỉ phép Quyết định nghỉ phải do quản lý hoặc người được Nhân sự ủy quyền hợp lệ thực hiện và thông báo rõ cho nhân viên._

Review: 

### D017 · role `employee` · vi · expected **answer**
**Q:** Đề nghị hoàn chi phí cần những thông tin chứng từ gì, và nếu mất hóa đơn thì xử lý sao?

**Expected:** Cần đơn vị bán, ngày, loại chi, số tiền, tiền tệ, mục đích và hóa đơn/biên nhận; nếu mất chứng từ phải giải trình và được Tài chính duyệt trước khi hoàn trả.
- must include: `biên nhận|hóa đơn` · `Tài chính`
- gold VN#167: _Quy trình bắt buộc Cung cấp đơn vị bán, ngày, loại chi, số tiền, tiền tệ, mục đích và hóa đơn/biên nhận._
- gold VN#169: _Quy trình bắt buộc Nếu mất chứng từ, giải trình và được Tài chính duyệt trước khi hoàn trả._

Review: 

### D018 · role `employee` · vi · expected **answer**
**Q:** Tiếp nhận nhà cung cấp mới cần thu thập thông tin gì, và khi nhà cung cấp đổi tài khoản ngân hàng thì làm sao?

**Expected:** Thu tên pháp nhân, đăng ký/thuế, địa chỉ kinh doanh, liên hệ và đại diện có thẩm quyền; thay đổi ngân hàng phải xác minh qua kênh liên hệ lấy độc lập (gọi lại xác minh).
- must include: `pháp nhân|đăng ký` · `độc lập`
- gold VN#248: _Quy trình bắt buộc Thu tên pháp nhân, đăng ký/thuế, địa chỉ kinh doanh, liên hệ và đại diện có thẩm quyền._
- gold VN#249: _Quy trình bắt buộc Xác minh thay đổi ngân hàng qua kênh liên hệ lấy độc lập._
- gold VN#253: _Yêu cầu kiểm soát Thay đổi thanh toán cần gọi lại xác minh độc lập.  Nhà cung cấp rủi ro cao cần Mua sắm cùng Tài chính hoặc Bảo mật rà tùy trường hợp._

Review: 

### D019 · role `employee` · vi · expected **answer**
**Q:** Khóa bí mật và thông tin đăng nhập phải lưu ở đâu, và khi nào phải thay khóa?

**Expected:** Lưu trong kho bí mật được duyệt hoặc cấu hình môi trường được bảo vệ với quyền tối thiểu; thay khóa sau thay nhân sự, lộ vô ý hoặc nghi xâm phạm.
- must include: `kho bí mật` · `nghi|lộ|thay nhân sự`
- gold VN#553: _Bí mật, thông tin đăng nhập và cấu hình an toàn Quy tắc bắt buộc. Lưu thông tin đăng nhập trong kho bí mật được duyệt hoặc cấu hình môi trường được bảo vệ, với quyền tối thiểu; thay khi nghi lộ._
- gold VN#557: _Quy trình bắt buộc Thay khóa sau thay nhân sự, lộ vô ý hoặc nghi xâm phạm._

Review: 

### D020 · role `employee` · vi · expected **answer**
**Q:** Khi nhận hàng cần ghi những số lượng nào, và hàng chưa rõ chất lượng thì để ở đâu?

**Expected:** Ghi riêng lượng giao thực, lượng chấp nhận và lượng từ chối; chỉ lượng chấp nhận được xếp kho. Hàng chưa rõ hoặc không đạt đưa vào khu giữ chất lượng có nhãn rõ.
- must include: `chấp nhận` · `từ chối` · `khu giữ chất lượng|giữ chất lượng`
- gold VN#468: _Nhận hàng, kiểm số lượng và giữ kiểm định Quy tắc bắt buộc. Lượng nhận, chấp nhận và từ chối là riêng biệt. Chỉ lượng chấp nhận được xếp kho để bán hoặc đối chiếu hóa đơn chuẩn._
- gold VN#470: _Quy trình bắt buộc Ghi lượng giao thực riêng lượng chấp nhận và từ chối._
- gold VN#471: _Quy trình bắt buộc Kiểm hư, bao bì, lô/sê-ri và hạn dùng nếu áp dụng.  Đưa hàng chưa rõ hoặc không đạt vào khu giữ chất lượng có nhãn rõ._

Review: 

## multi_passage

### D021 · role `employee` · vi · expected **answer**
**Q:** Người kiểm kê có được tự duyệt chênh lệch lớn mà chính mình phát hiện không, và sai lệch trọng yếu khi kiểm kê thì xử lý thế nào?

**Expected:** Không: người nhận hàng hoặc kiểm kê không được độc lập duyệt chênh lệch trọng yếu do mình phát hiện; sai lệch trọng yếu phải được người độc lập đếm lại và so với hệ thống tồn trực tiếp, ghi nguyên nhân trước khi điều chỉnh.
- must include: `không` · `độc lập`
- gold VN#49: _Vai trò, trách nhiệm giải trình và phân tách nhiệm vụ Quy tắc bắt buộc. Người đề nghị quyền lợi hoặc cam kết không được là người duy nhất cho phép thực hiện. Người nhận hàng thực tế hoặc kiểm kê không được độc lập duyệt chênh lệch trọng yếu do chính mình phát hiện._
- gold VN#443: _Quy trình bắt buộc Người độc lập đếm lại sai lệch trọng yếu.  So số thực với hệ thống tồn trực tiếp và ghi nguyên nhân trước điều chỉnh._

Review: 

### D022 · role `employee` · vi · expected **answer**
**Q:** Khi hai cách hiểu chính sách xung đột thì làm gì, và nếu ma trận phê duyệt không có hàng nào khớp thì sao?

**Expected:** Chuyển cấp xử lý xung đột trước khi cam kết, không chọn cách hiểu dễ dãi hơn; nếu không hàng nào của ma trận khớp thì dừng và chuyển cấp thay vì chọn hàng thuận tiện.
- must include: `chuyển cấp`
- gold VN#20: _Quy trình bắt buộc Chuyển cấp xử lý xung đột trước khi cam kết; không chọn cách hiểu dễ dãi hơn._
- gold VN#673: _Duy trì và diễn giải ma trận phê duyệt Quy tắc bắt buộc. Áp hàng khớp lĩnh vực, tổng cam kết, tiền tệ, rủi ro và thẩm quyền tổ chức. Nếu không hàng nào khớp, dừng và chuyển cấp thay vì chọn hàng thuận tiện._

Review: 

### D023 · role `employee` · vi · expected **answer**
**Q:** Dữ liệu tồn kho trong Supabase kéo dài đến năm nào, và khi trả lời câu hỏi về tồn kho phải nêu điều gì?

**Expected:** Snapshot tồn kho lịch sử từ 2012-07-31 đến 2022-12-31, không phải số dư trực tiếp; mọi câu trả lời tồn phải nêu ngày dữ liệu và không trình bày snapshot lịch sử như hàng đang khả dụng.
- must include: `2022` · `ngày dữ liệu|snapshot`
- gold VN#392: _Sự phù hợp hệ thống và dữ liệu Nguồn tồn có snapshot lịch sử từ 2012-07-31 đến 2022-12-31; không được mô tả thành số dư trực tiếp năm 2026._
- gold VN#385: _Độ mới snapshot và báo cáo lịch sử Quy tắc bắt buộc. Mọi câu trả lời tồn phải nêu ngày dữ liệu. Với câu hỏi "tồn hiện tại", tác tử không được trình bày snapshot lịch sử như hàng đang khả dụng._

Review: 

### D024 · role `employee` · vi · expected **answer**
**Q:** Tôi có thể xin ngoại lệ để dán khóa API vào prompt cho AI dùng tạm không?

**Expected:** Không: không dán thông tin đăng nhập vào prompt AI, và ngoại lệ không miễn yêu cầu bảo mật không được miễn.
- must include: `không`
- gold VN#650: _Yêu cầu kiểm soát Ngoại lệ không miễn luật, nghĩa vụ hợp đồng hoặc yêu cầu bảo mật không được miễn._
- gold VN#559: _Yêu cầu kiểm soát Không dán thông tin đăng nhập vào prompt AI, phiếu hỗ trợ hoặc chính sách._

Review: 

### D025 · role `employee` · vi · expected **answer**
**Q:** Câu trả lời của trợ lý AI có được tính là phê duyệt nghỉ phép không, và AI được làm gì với phê duyệt?

**Expected:** Không: yêu cầu nghỉ vẫn chờ đến khi quyết định được ghi nhận, câu trả lời do AI tạo không phải phê duyệt; đề xuất của trợ lý AI không phải phê duyệt hay giao dịch, và tác tử không được tạo phê duyệt.
- must include: `không`
- gold VN#110: _Phê duyệt, từ chối và thay đổi nghỉ phép Quy tắc bắt buộc. Yêu cầu vẫn chờ đến khi quyết định được ghi nhận. Im lặng, mục lịch hoặc câu trả lời do AI tạo không phải phê duyệt._
- gold VN#23: _Yêu cầu kiểm soát Đề xuất của trợ lý AI không phải phê duyệt hay giao dịch._

Review: 

## table

### D026 · role `employee` · vi · expected **answer**
**Q:** Theo Phụ lục A, khóa chính của bảng commerce.order_items là gì?

**Expected:** commerce.order_items có khóa chính order_item_id (cùng các trường order_id, product_id, quantity, unit_price, discount_amount, promo_id, promo_id_2).
- must include: `order_item_id`
- gold VN#726: _Phụ lục A - Tham chiếu lược đồ Supabase và quan hệ Columns: Bảng | Trường khóa | Cách diễn giải được phép Row 4: Bảng: commerce.order_items | Trường khóa: order_item_id (PK); order_id, product_id, quantity, unit_price, discount_amount, promo_id, promo_id_2 | Cách diễn giải được phép: Cấp dòng bán hàng; không nối giá trị cấp đơn mà thiếu kiểm soát trùng. Row 5: Bảng: commerce.payments | Trường khóa: order_id (PK/FK); _

Review: 

### D027 · role `employee` · vi · expected **answer**
**Q:** SKU nhóm A phải kiểm kê bao lâu một lần và chênh lệch phải điều tra trong thời hạn nào?

**Expected:** Nhóm A (khoảng 80% giá trị tiêu thụ năm) kiểm kê hằng tuần và điều tra chênh lệch ngay trong ngày.
- must include: `hằng tuần|Hằng tuần` · `trong ngày`
- gold 01_Inventory_Management_#6: _5. Phân loại ABC và lịch kiểm kê Columns: Nhóm | Tiêu chí tham chiếu | Tần suất | SLA điều tra Row 1: Nhóm: A | Tiêu chí tham chiếu: Nhóm SKU đóng góp xấp xỉ 80% giá trị tiêu thụ năm | Tần suất: Hằng tuần | SLA điều tra: Điều tra chênh lệch ngay trong ngày Row 2: Nhóm: B | Tiêu chí tham chiếu: Nhóm tiếp theo đóng góp xấp xỉ 15% | Tần suất: Hằng tháng | SLA điều tra: Điều tra trong 2 ngày làm việc Row 3: Nhóm: C | Tiê_

Review: 

### D028 · role `employee` · vi · expected **answer**
**Q:** Fill rate xuống dưới bao nhiêu thì phải phát cảnh báo P1?

**Expected:** Mục tiêu mô phỏng fill rate ≥ 98%; dưới 95% thì cảnh báo P1 và phân tích nguyên nhân.
- must include: `95%`
- gold 01_Inventory_Management_#8: _6. Ngưỡng vận hành và KPI Columns: KPI | Mục tiêu / ngưỡng giả lập | Hành động Row 1: KPI: Fill rate | Mục tiêu / ngưỡng giả lập: Mục tiêu mô phỏng ≥ 98% | Hành động: Dưới 95%: cảnh báo P1 và phân tích nguyên nhân Row 2: KPI: Days of supply | Mục tiêu / ngưỡng giả lập: Tham chiếu 28–60 ngày tùy nhóm hàng | Hành động: >120 ngày: overstock review; >180 ngày: kế hoạch xử lý bắt buộc Row 3: KPI: Inventory record accuracy_

Review: 

### D029 · role `employee` · vi · expected **answer**
**Q:** PO vượt ngân sách hoặc cho SKU mới thì đi qua luồng phê duyệt nào?

**Expected:** PO vượt ngân sách, SKU mới hoặc campaign bất thường: Procurement Manager → Operations + Finance.
- must include: `Procurement Manager` · `Finance`
- gold 01_Inventory_Management_#13: _10. Phê duyệt và xử lý ngoại lệ Columns: Loại quyết định | Luồng phê duyệt | Thời điểm Row 1: Loại quyết định: Đề xuất PO trong ngân sách và trong tham số đã duyệt | Luồng phê duyệt: Planner → Procurement Manager | Thời điểm: Theo quy trình mua hàng hiện hành Row 2: Loại quyết định: PO vượt ngân sách, SKU mới hoặc campaign bất thường | Luồng phê duyệt: Procurement Manager → Operations + Finance | Thời điểm: Trước khi_

Review: 

### D030 · role `employee` · vi · expected **answer**
**Q:** Chính sách vận hành phiên bản 1.0 có hiệu lực từ ngày nào và do ai phê duyệt?

**Expected:** Phiên bản 1.0 có hiệu lực từ 23 tháng 10 năm 2026; chủ sở hữu/cấp phê duyệt là Bộ phận Quản trị Vận hành / Hội đồng Điều hành Vận hành.
- must include: `23` · `Hội đồng Điều hành Vận hành`
- gold VN#742: _Phụ lục D - Hồ sơ quản trị và sửa đổi Columns: Phiên bản | Ngày hiệu lực | Chủ sở hữu / cấp phê duyệt | Tóm tắt thay đổi Row 1: Phiên bản: 1.0 | Ngày hiệu lực: 23 tháng 10 năm 2026 | Chủ sở hữu / cấp phê duyệt: Bộ phận Quản trị Vận hành / Hội đồng Điều hành Vận hành | Tóm tắt thay đổi: Ban hành kiểm soát lần đầu, bao phủ nhân sự, mua sắm, tồn kho, bảo mật, ngoại lệ và sự phù hợp lược đồ._

Review: 

## not_covered

### D031 · role `employee` · vi · expected **not_covered**
**Q:** Công ty có hỗ trợ tiền gửi xe cho nhân viên không?

**Expected:** Tài liệu được phép truy cập không đề cập hỗ trợ tiền gửi xe.

Review: 

### D032 · role `employee` · vi · expected **not_covered**
**Q:** Nhân viên có được thưởng tháng 13 không, tính thế nào?

**Expected:** Tài liệu không đề cập lương hoặc thưởng tháng 13.

Review: 

### D033 · role `employee` · vi · expected **not_covered**
**Q:** Chính sách làm việc từ xa cho phép tối đa mấy ngày một tuần?

**Expected:** Tài liệu không có chính sách làm việc từ xa.

Review: 

### D034 · role `employee` · vi · expected **not_covered**
**Q:** Quy định về đồng phục khi đi làm là gì?

**Expected:** Tài liệu không quy định về đồng phục hoặc trang phục.

Review: 

### D035 · role `employee` · vi · expected **not_covered**
**Q:** Công ty có mua bảo hiểm sức khỏe cho người thân của nhân viên không?

**Expected:** Tài liệu không đề cập bảo hiểm sức khỏe.

Review: 

## false_premise

### D036 · role `employee` · vi · expected **answer**
**Q:** Vì phép năm là 15 ngày, tôi làm 6 tháng thì được bao nhiêu ngày?

**Expected:** Tiền đề chưa đúng: VietStyle cấp 12 ngày phép năm (không phải 15); tích lũy 1/12 mỗi tháng nên 6 tháng là 6 ngày.
- must include: `12` · `6`
- must not include: `7,5|7.5`
- gold VN#82: _Điều kiện và quyền nghỉ phép Quy tắc bắt buộc. Quyền theo luật và loại nghỉ được pháp luật bảo vệ là mức tối thiểu. VietStyle cấp 12 ngày làm việc nghỉ phép năm có lương cho một năm làm việc đầy đủ trong điều kiện thông thường, tính theo tỷ lệ nếu chưa đủ năm; quyền lợi theo luật hoặc hợp đồng có lợi hơn được ưu tiên._
- gold VN#84: _Quy trình bắt buộc Phép năm tích lũy bằng một phần mười hai quyền phép năm áp dụng cho mỗi tháng làm việc hoàn tất, trừ khi quy định hợp pháp yêu cầu cách tính có lợi hơn._

Review: 

### D037 · role `employee` · vi · expected **answer**
**Q:** Đơn mua dưới 5 triệu thì tôi tự duyệt cho mình được đúng không?

**Expected:** Không: không nhân viên nào được tự duyệt yêu cầu của mình; khoản đến 5.000.000 VND do quản lý trực tiếp duyệt.
- must include: `không`
- gold VN#21: _Yêu cầu kiểm soát Không nhân viên nào được tự duyệt yêu cầu của mình hoặc bỏ qua phê duyệt bắt buộc._
- gold VN#49: _Vai trò, trách nhiệm giải trình và phân tách nhiệm vụ Quy tắc bắt buộc. Người đề nghị quyền lợi hoặc cam kết không được là người duy nhất cho phép thực hiện. Người nhận hàng thực tế hoặc kiểm kê không được độc lập duyệt chênh lệch trọng yếu do chính mình phát hiện._
- gold VN#274: _Ma trận phê duyệt và ngưỡng tiền Quy tắc bắt buộc. Thẩm quyền mặc định cho một cam kết: đến 5.000.000 VND-quản lý trực tiếp; 5.000.001-50.000.000 VND-trưởng bộ phận; 50.000.001-200.000.000 VND-trưởng bộ phận cùng Mua sắm và Tài chính; trên 200.000.000 VND-Hội đồng Điều hành Vận hành cùng Tài chính._

Review: 

### D038 · role `employee` · vi · expected **answer**
**Q:** Số tồn trong bảng commerce.inventory là số tồn kho hiện tại đúng không?

**Expected:** Không: commerce.inventory là dữ liệu phân tích lịch sử (đến 2022-12-31), không phải sổ tồn trực tiếp; số hiện tại chính thức nằm ở hệ thống quản lý kho được duyệt.
- must include: `không` · `lịch sử`
- gold VN#357: _Hồ sơ tồn kho, phạm vi và thứ bậc nguồn Quy tắc bắt buộc. Số hiện tại chính thức là số dư trực tiếp trong hệ thống quản lý kho/tồn được duyệt. Supabase commerce.inventory là dữ liệu phân tích lịch sử, không phải sổ tồn trực tiếp._
- gold VN#392: _Sự phù hợp hệ thống và dữ liệu Nguồn tồn có snapshot lịch sử từ 2012-07-31 đến 2022-12-31; không được mô tả thành số dư trực tiếp năm 2026._

Review: 

### D039 · role `employee` · vi · expected **answer**
**Q:** Nhà cung cấp báo giá miệng rồi nên tôi chốt mua luôn được phải không?

**Expected:** Chưa: báo giá miệng phải được tóm tắt trong bản ghi có ngày và xác nhận trước khi cam kết.
- must include: `bản ghi|ghi lại` · `xác nhận`
- gold VN#225: _Yêu cầu kiểm soát Báo giá miệng phải tóm tắt trong bản ghi có ngày và xác nhận trước cam kết._

Review: 

### D040 · role `employee` · vi · expected **answer**
**Q:** Dựa vào snapshot tồn kho, hôm nay sản phẩm 1001 còn hàng để hứa giao cho khách không?

**Expected:** Không thể kết luận: snapshot chỉ là lịch sử; nếu hỏi 'bây giờ' chỉ được trả ngày lịch sử mới nhất kèm giới hạn và phải xác minh tồn trực tiếp, không hứa ngày giao theo dữ liệu lịch sử.
- must include: `không|chưa` · `lịch sử|xác minh`
- gold VN#390: _Yêu cầu kiểm soát Nếu hỏi "bây giờ" nhưng chỉ có lịch sử, trả ngày lịch sử mới nhất và giới hạn._
- gold VN#417: _Yêu cầu kiểm soát Không hứa ngày giao chỉ theo fill_rate lịch sử.  Không đổi hàng không khả dụng thành có thể bán để cải thiện chỉ số._
- gold VN#385: _Độ mới snapshot và báo cáo lịch sử Quy tắc bắt buộc. Mọi câu trả lời tồn phải nêu ngày dữ liệu. Với câu hỏi "tồn hiện tại", tác tử không được trình bày snapshot lịch sử như hàng đang khả dụng._

Review: 

## language

### D041 · role `employee` · en · expected **answer**
**Q:** How many days of paid annual leave does an employee get for a full year?

**Expected:** VietStyle grants 12 working days of paid annual leave for a full year of service, pro-rated for partial years.
- must include: `12`
- gold EN#79: _Leave eligibility and entitlement Mandatory rule. Statutory entitlements and protected leave under applicable law are the minimum. VietStyle provides annual paid leave of 12 working days for a full year of ordinary-condition service, prorated for partial years; a more favorable legal or contractual entitlement prevails._

Review: 

### D042 · role `employee` · en · expected **answer**
**Q:** What is the deadline to submit an expense claim?

**Expected:** Within 30 calendar days of the transaction or the return from approved travel, whichever is later.
- must include: `30`
- gold EN#168: _Required procedure  Submit within 30 calendar days of the transaction or return from approved travel, whichever is later._

Review: 

### D043 · role `employee` · mixed · expected **answer**
**Q:** Vendor đổi bank account thì phải verify thế nào?

**Expected:** Xác minh thay đổi ngân hàng qua kênh liên hệ lấy độc lập (gọi lại xác minh độc lập) trước khi chấp nhận.
- must include: `độc lập|independent`
- gold VN#249: _Quy trình bắt buộc Xác minh thay đổi ngân hàng qua kênh liên hệ lấy độc lập._
- gold VN#253: _Yêu cầu kiểm soát Thay đổi thanh toán cần gọi lại xác minh độc lập.  Nhà cung cấp rủi ro cao cần Mua sắm cùng Tài chính hoặc Bảo mật rà tùy trường hợp._

Review: 

### D044 · role `employee` · mixed · expected **answer**
**Q:** Service-role key có được để trong client code không?

**Expected:** Không: không lộ service-role hoặc khóa bí mật trong mã phía khách, notebook, ảnh chụp hay prompt; giữ service-role ở máy chủ.
- must include: `không|Không`
- gold VN#529: _Yêu cầu kiểm soát Không dùng chung tài khoản cá nhân.  Không lộ service-role hoặc khóa bí mật trong mã phía khách, notebook, ảnh chụp hay prompt._
- gold VN#556: _Quy trình bắt buộc Giữ service-role và thông tin cơ sở dữ liệu ở máy chủ._

Review: 

### D045 · role `employee` · en · expected **answer**
**Q:** Can I approve my own leave request?

**Expected:** No. The requester cannot approve their own request; leave decisions are made by the manager or an HR-authorised delegate.
- must include: `no|cannot|not`
- gold EN#113: _Control requirements  The requester cannot approve their own request.   A rejection must state a job-related reason and must not contravene protected-leave rights._

Review: 

## noisy

### D046 · role `employee` · vi · expected **answer**
**Q:** cham cong bi sai thi xin sua nhu the nao

**Expected:** Nộp yêu cầu sửa gồm ngày, bản ghi gốc, giá trị đề nghị và lý do; quản lý xác minh với lịch hoặc bằng chứng hợp pháp khác.
- must include: `lý do|ly do` · `quản lý|quan ly`
- gold VN#139: _Quy trình bắt buộc Nộp yêu cầu sửa gồm ngày, bản ghi gốc, giá trị đề nghị và lý do._
- gold VN#140: _Quy trình bắt buộc Quản lý xác minh với lịch hoặc bằng chứng hợp pháp khác._

Review: 

### D047 · role `employee` · vi · expected **answer**
**Q:** ê ku m coi giùm t, hàng khách trả về là đem bán lại liền đc ko?

**Expected:** Không: bản ghi trả không tự nghĩa đã nhập lại kho; phải kiểm tình trạng rồi quyết định nhập lại, tân trang, cách ly, trả nhà cung cấp hoặc thanh lý.
- must include: `không|chưa`
- gold VN#496: _Trả hàng, điều kiện hoàn tiền và xử lý vật phẩm Quy tắc bắt buộc. Bản ghi trả không tự nghĩa đã nhập lại kho; số tiền hoàn không chứng minh hàng đủ bán lại._
- gold VN#498: _Quy trình bắt buộc Kiểm tình trạng và quyết định nhập lại, tân trang, cách ly, trả nhà cung cấp hoặc thanh lý._

Review: 

### D048 · role `employee` · vi · expected **answer**
**Q:** sếp t im lặng ko rep đơn nghỉ, vậy coi như dc duyệt hả

**Expected:** Không: yêu cầu vẫn chờ đến khi quyết định được ghi nhận; im lặng, mục lịch hoặc câu trả lời AI không phải phê duyệt.
- must include: `không`
- gold VN#110: _Phê duyệt, từ chối và thay đổi nghỉ phép Quy tắc bắt buộc. Yêu cầu vẫn chờ đến khi quyết định được ghi nhận. Im lặng, mục lịch hoặc câu trả lời do AI tạo không phải phê duyệt._

Review: 

### D049 · role `employee` · vi · expected **answer**
**Q:** nhà cc báo giá mịêng thì có cần lưu lại j ko ạ

**Expected:** Có: báo giá miệng phải được tóm tắt trong bản ghi có ngày và xác nhận trước khi cam kết.
- must include: `bản ghi|ghi` · `ngày`
- gold VN#225: _Yêu cầu kiểm soát Báo giá miệng phải tóm tắt trong bản ghi có ngày và xác nhận trước cam kết._

Review: 

### D050 · role `employee` · vi · expected **answer**
**Q:** truoc campaign bao lau thi phai chot forecast ton kho

**Expected:** Tối thiểu 4 tuần trước campaign, Merchandising và Planner thống nhất forecast theo SKU/size/màu.
- must include: `4 tuần|4 tuan`
- gold 01_Inventory_Management_#12: _9. Khuyến mãi và mùa vụ Tối thiểu 4 tuần trước campaign, Merchandising và Planner thống nhất forecast theo SKU / size / màu. Kiểm tra promotions.csv hoặc hệ thống campaign: ngày bắt đầu/kết thúc, kênh, mức giảm, điều kiện đơn tối thiểu và stackable_flag. Chỉ tăng target stock khi có forecast hoặc phê duyệt; không đặt hàng chỉ dựa vào traffic hoặc doanh thu tổng. Sau campaign, đối chiếu forecast với sell-through, tồn _

Review: 

## rbac

### D051 · role `legal_compliance` · vi · expected **not_covered**
**Q:** Hàng tồn trên 240 ngày thì ai đánh giá dự phòng giảm giá trị?

**Expected:** Vai trò legal_compliance không được xem Bộ chính sách quản lý tồn kho (01); câu trả lời phải là không có trong tài liệu được phép, không lộ nội dung 01.
- must not use: 01_Inventory_Management_Policy_Manual.docx

Review: 

### D052 · role `finance_analyst` · vi · expected **answer**
**Q:** Theo bộ chính sách tồn kho, hàng tồn trên 240 ngày thì ai đánh giá dự phòng giảm giá trị?

**Expected:** Trên 240 ngày tồn: Inventory Manager và Finance đánh giá dự phòng giảm giá trị / loại bỏ theo quy định kế toán.
- must include: `Inventory Manager` · `Finance`
- gold 01_Inventory_Management_#10: _7. Hàng dư thừa và chậm luân chuyển Trên 120 ngày tồn: tạm dừng bổ sung, kiểm tra forecast, tồn kho theo size/màu, hàng đang chuyển và kế hoạch campaign. Trên 180 ngày: Merchandising lập phương án chuyển kho, bundle, markdown có kiểm soát hoặc thanh lý. Trên 240 ngày: Inventory Manager và Finance đánh giá dự phòng giảm giá trị / loại bỏ theo quy định kế toán. Không dùng giảm giá làm biện pháp mặc định nếu nguyên nhân_

Review: 

### D053 · role `executive` · vi · expected **not_covered**
**Q:** Theo KPI Summary của Inventory Planner, nhóm Outdoor có bao nhiêu SKU?

**Expected:** Vai trò executive không được xem Inventory Planner (04); câu trả lời phải là không có trong tài liệu được phép.
- must not use: 04_Inventory_Control_and_Reorder_Planner.xlsx

Review: 

### D054 · role `procurement` · vi · expected **answer**
**Q:** Trong KPI Summary của Inventory Planner, Outdoor có bao nhiêu SKU?

**Expected:** Theo KPI Summary, nhóm Outdoor có 144 SKU.
- must include: `144`
- gold 04_Inventory_Control_and#433: _KPI Summary Columns: Category | SKU Count | On-hand Units | Units Sold (Latest) | Mean Fill Rate Row 1: Category: Casual | SKU Count: 40 | On-hand Units: 4095 | Units Sold (Latest): 190 | Mean Fill Rate: 0.9608325000000001 Row 2: Category: GenZ | SKU Count: 44 | On-hand Units: 5126 | Units Sold (Latest): 199 | Mean Fill Rate: 0.9719704545454545 Row 3: Category: Outdoor | SKU Count: 144 | On-hand Units: 49929 | Units _

Review: 

### D055 · role `admin` · vi · expected **answer**
**Q:** Khi chưa đủ lịch sử nhu cầu thì nhóm ABC tạm được rà soát lại sau bao lâu?

**Expected:** ABC tính từ annual consumption value; khi chưa có lịch sử đủ tin cậy thì dùng nhóm tạm và rà soát sau 3 chu kỳ.
- must include: `3 chu kỳ|ba chu kỳ`
- gold 01_Inventory_Management_#7: _5. Phân loại ABC và lịch kiểm kê ABC phải được tính từ annual consumption value (nhu cầu năm × cost), không phân loại chỉ theo số lượng bán. Khi chưa có lịch sử nhu cầu đủ tin cậy, dùng nhóm tạm và rà soát sau 3 chu kỳ._

Review: 

## follow_up

### D056 · role `employee` · vi · expected **answer**
> (previous turn) **Q:** Mua máy in 4 triệu thì ai duyệt?  
> **A:** 4.000.000 VND thuộc mức đến 5.000.000 VND nên quản lý trực tiếp phê duyệt.
**Q:** còn nếu 30 triệu thì sao?

**Expected:** 30.000.000 VND thuộc 5.000.001–50.000.000 VND: trưởng bộ phận phê duyệt và cần ít nhất hai báo giá tương đương.
- must include: `Trưởng bộ phận|trưởng bộ phận` · `hai|2`
- gold VN#274: _Ma trận phê duyệt và ngưỡng tiền Quy tắc bắt buộc. Thẩm quyền mặc định cho một cam kết: đến 5.000.000 VND-quản lý trực tiếp; 5.000.001-50.000.000 VND-trưởng bộ phận; 50.000.001-200.000.000 VND-trưởng bộ phận cùng Mua sắm và Tài chính; trên 200.000.000 VND-Hội đồng Điều hành Vận hành cùng Tài chính._
- gold VN#261: _Tìm nguồn cạnh tranh và đánh giá báo giá Quy tắc bắt buộc. Cam kết dự toán đến 5.000.000 VND có thể dùng một báo giá được lập hồ sơ. Từ 5.000.001 đến 50.000.000 VND cần tìm ít nhất hai báo giá tương đương nếu thị trường cho phép. Trên 50.000.000 VND cần ít nhất ba báo giá bằng văn bản hoặc giải trình chỉ định nguồn được lập hồ sơ._
- gold VN#730: _Phụ lục B - Hạn mức phê duyệt và bảng quyết định vận hành Columns: Tổng cam kết | Phê duyệt bắt buộc | Điều kiện bổ sung Row 1: Tổng cam kết: Đến 5.000.000 VND | Phê duyệt bắt buộc: Quản lý trực tiếp | Điều kiện bổ sung: Một báo giá có hồ sơ; ngân sách xác nhận. Row 2: Tổng cam kết: 5.000.001-50.000.000 VND | Phê duyệt bắt buộc: Trưởng bộ phận | Điều kiện bổ sung: Ít nhất hai báo giá tương đương nếu thị trường cho ph_

Review: 

### D057 · role `employee` · vi · expected **answer**
> (previous turn) **Q:** Phép năm được bao nhiêu ngày?  
> **A:** VietStyle cấp 12 ngày làm việc nghỉ phép năm có lương cho một năm làm việc đầy đủ.
**Q:** nếu tôi mới làm được 3 tháng thì sao?

**Expected:** Tích lũy 1/12 quyền phép năm mỗi tháng làm việc hoàn tất: 3 tháng tương ứng 3 ngày.
- must include: `3`
- gold VN#84: _Quy trình bắt buộc Phép năm tích lũy bằng một phần mười hai quyền phép năm áp dụng cho mỗi tháng làm việc hoàn tất, trừ khi quy định hợp pháp yêu cầu cách tính có lợi hơn._
- gold VN#82: _Điều kiện và quyền nghỉ phép Quy tắc bắt buộc. Quyền theo luật và loại nghỉ được pháp luật bảo vệ là mức tối thiểu. VietStyle cấp 12 ngày làm việc nghỉ phép năm có lương cho một năm làm việc đầy đủ trong điều kiện thông thường, tính theo tỷ lệ nếu chưa đủ năm; quyền lợi theo luật hoặc hợp đồng có lợi hơn được ưu tiên._

Review: 

### D058 · role `employee` · vi · expected **answer**
> (previous turn) **Q:** Hoàn chi phí phải nộp trong bao lâu?  
> **A:** Trong 30 ngày lịch kể từ giao dịch hoặc ngày trở về chuyến công tác, lấy mốc muộn hơn.
**Q:** lỡ làm mất hóa đơn thì sao?

**Expected:** Nếu mất chứng từ phải giải trình và được Tài chính duyệt trước khi hoàn trả.
- must include: `Tài chính` · `giải trình`
- gold VN#169: _Quy trình bắt buộc Nếu mất chứng từ, giải trình và được Tài chính duyệt trước khi hoàn trả._

Review: 

### D059 · role `employee` · vi · expected **answer**
> (previous turn) **Q:** Khi nào được mua khẩn?  
> **A:** Mua khẩn giới hạn cho tình huống an toàn tức thời, liên tục dịch vụ hoặc tổn thất kinh doanh trọng yếu khi không thể theo thời gian thông thường.
**Q:** vậy nếu không kịp xin duyệt trước thì phải làm gì?

**Expected:** Báo lãnh đạo chỉ định và Tài chính không muộn hơn một ngày làm việc sau cam kết, và hoàn tất rà soát trong năm ngày làm việc.
- must include: `một ngày làm việc|1 ngày làm việc` · `năm ngày làm việc|5 ngày làm việc`
- gold VN#332: _Quy trình bắt buộc Nếu thực sự không thể duyệt trước, báo lãnh đạo chỉ định và Tài chính sớm nhất có thể, không muộn hơn một ngày làm việc sau cam kết._
- gold VN#333: _Quy trình bắt buộc Hoàn tất rà soát nguồn cung, bằng chứng và phê duyệt trong năm ngày làm việc._

Review: 

### D060 · role `employee` · vi · expected **answer**
> (previous turn) **Q:** Muốn xin quyền truy cập hệ thống thì làm sao?  
> **A:** Gửi yêu cầu qua bàn hỗ trợ hoặc luồng quản lý danh tính, nêu mục đích, tài nguyên, mức quyền và ngày kết thúc nếu tạm.
**Q:** thế ai duyệt và ai thực hiện cấp quyền?

**Expected:** Chủ dữ liệu duyệt và chủ hệ thống thực hiện cấp quyền, dùng tài khoản cá nhân và xác thực đa yếu tố.
- must include: `Chủ dữ liệu|chủ dữ liệu` · `chủ hệ thống`
- gold VN#527: _Quy trình bắt buộc Chủ dữ liệu duyệt và chủ hệ thống thực hiện.  Dùng tài khoản cá nhân và xác thực đa yếu tố được duyệt._

Review: 
