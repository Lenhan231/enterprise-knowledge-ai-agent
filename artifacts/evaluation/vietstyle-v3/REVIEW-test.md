# Review: vietstyle-test-v3 (60 items)

For each item, check: is the question natural? Does the expected answer match the gold passage? Is anything missing or wrong? Mark **OK** or write the change next to the id.

## lookup

### T001 · role `employee` · vi · expected **answer**
**Q:** Nghỉ phép theo kế hoạch phải gửi đề nghị trước ít nhất bao lâu?

**Expected:** Nghỉ theo kế hoạch nên được đề nghị ít nhất năm ngày làm việc trước ngày đầu nghỉ.
- must include: `năm ngày làm việc|5 ngày làm việc`
- gold VN#97: _Nộp yêu cầu nghỉ và thời hạn báo trước Quy tắc bắt buộc. Nghỉ theo kế hoạch nên được đề nghị ít nhất năm ngày làm việc trước ngày đầu nghỉ. Nghỉ khẩn, do bệnh hoặc được pháp luật bảo vệ phải báo sớm nhất có thể một cách hợp lý và không mất hiệu lực vì thiếu thời gian báo trước._

Review: 

### T002 · role `employee` · vi · expected **answer**
**Q:** Sự cố bảo mật mức Cao phải báo cho Bảo mật trong bao lâu?

**Expected:** Mức Cao (khả năng truy cập trái phép hoặc suy giảm dịch vụ đáng kể): báo Bảo mật và chủ hệ thống trong một giờ.
- must include: `một giờ|1 giờ`
- gold VN#599: _Quy trình bắt buộc Cao: khả năng truy cập trái phép hoặc suy giảm dịch vụ đáng kể; báo Bảo mật và chủ hệ thống trong một giờ._

Review: 

### T003 · role `employee` · vi · expected **answer**
**Q:** Nhà cung cấp trọng yếu phải được rà soát hiệu quả bao lâu một lần?

**Expected:** Rà nhà cung cấp trọng yếu ít nhất hằng năm và sau lỗi lặp về chất lượng, giao hàng, bảo mật hoặc hóa đơn.
- must include: `hằng năm`
- gold VN#343: _Hiệu quả mua sắm và rà soát nhà cung cấp Quy tắc bắt buộc. Rà nhà cung cấp trọng yếu ít nhất hằng năm và sau lỗi lặp về chất lượng, giao hàng, bảo mật hoặc hóa đơn._

Review: 

### T004 · role `employee` · vi · expected **answer**
**Q:** Dữ liệu trong công ty được chia thành những mức phân loại nào?

**Expected:** Bốn mức: Công khai, Nội bộ, Mật và Hạn chế; xử lý theo mức phân loại cao nhất áp dụng.
- must include: `Công khai` · `Nội bộ` · `Mật` · `Hạn chế`
- gold VN#568: _Phân loại, xử lý và chia sẻ dữ liệu Quy tắc bắt buộc. Dữ liệu Công khai, Nội bộ, Mật và Hạn chế phải được xử lý theo mức phân loại cao nhất áp dụng._
- gold VN#569: _Quy trình bắt buộc Công khai: đã được duyệt xuất bản không hạn chế.  Nội bộ: dùng cho công việc bởi nhân sự được phép._
- gold VN#570: _Quy trình bắt buộc Mật: thông tin nhạy cảm thương mại hoặc liên quan khách/nhân viên, chỉ truy cập theo nhu cầu cần biết._
- gold VN#571: _Quy trình bắt buộc Hạn chế: thông tin đăng nhập, thanh toán, giấy tờ định danh, y tế và nội dung nhạy cảm bảo mật._

Review: 

### T005 · role `employee` · vi · expected **answer**
**Q:** Chủ lĩnh vực phải rà soát chính sách vận hành bao lâu một lần?

**Expected:** Ít nhất hằng năm và sau thay đổi trọng yếu về luật, mô hình dữ liệu, quy trình nhà cung cấp, kiểm soát tồn, kiến trúc bảo mật hoặc ứng phó sự cố.
- must include: `hằng năm`
- gold VN#712: _Rà quản trị, kiểm toán và cải tiến liên tục Quy tắc bắt buộc. Chủ lĩnh vực rà ít nhất hằng năm và sau thay đổi trọng yếu về luật, mô hình dữ liệu, quy trình nhà cung cấp, kiểm soát tồn, kiến trúc bảo mật hoặc ứng phó sự cố._

Review: 

## amount

### T006 · role `employee` · vi · expected **answer**
**Q:** Mua hệ thống camera 80 củ thì ai duyệt?

**Expected:** 80.000.000 VND thuộc 50.000.001–200.000.000 VND: trưởng bộ phận cùng Mua sắm và Tài chính phê duyệt; cần ít nhất ba báo giá văn bản hoặc lý do chỉ định nguồn đã duyệt.
- must include: `Mua sắm` · `Tài chính`
- must not include: `Hội đồng Điều hành`
- gold VN#274: _Ma trận phê duyệt và ngưỡng tiền Quy tắc bắt buộc. Thẩm quyền mặc định cho một cam kết: đến 5.000.000 VND-quản lý trực tiếp; 5.000.001-50.000.000 VND-trưởng bộ phận; 50.000.001-200.000.000 VND-trưởng bộ phận cùng Mua sắm và Tài chính; trên 200.000.000 VND-Hội đồng Điều hành Vận hành cùng Tài chính._
- gold VN#730: _Phụ lục B - Hạn mức phê duyệt và bảng quyết định vận hành Columns: Tổng cam kết | Phê duyệt bắt buộc | Điều kiện bổ sung Row 1: Tổng cam kết: Đến 5.000.000 VND | Phê duyệt bắt buộc: Quản lý trực tiếp | Điều kiện bổ sung: Một báo giá có hồ sơ; ngân sách xác nhận. Row 2: Tổng cam kết: 5.000.001-50.000.000 VND | Phê duyệt bắt buộc: Trưởng bộ phận | Điều kiện bổ sung: Ít nhất hai báo giá tương đương nếu thị trường cho ph_

Review: 

### T007 · role `employee` · vi · expected **answer**
**Q:** Hợp đồng 1,2 tỷ thì cấp nào phê duyệt?

**Expected:** 1.200.000.000 VND trên 200.000.000 VND: Hội đồng Điều hành Vận hành cùng Tài chính phê duyệt; cần đánh giá nguồn cung và rà rủi ro được lập hồ sơ.
- must include: `Hội đồng Điều hành Vận hành` · `Tài chính`
- gold VN#274: _Ma trận phê duyệt và ngưỡng tiền Quy tắc bắt buộc. Thẩm quyền mặc định cho một cam kết: đến 5.000.000 VND-quản lý trực tiếp; 5.000.001-50.000.000 VND-trưởng bộ phận; 50.000.001-200.000.000 VND-trưởng bộ phận cùng Mua sắm và Tài chính; trên 200.000.000 VND-Hội đồng Điều hành Vận hành cùng Tài chính._
- gold VN#730: _Phụ lục B - Hạn mức phê duyệt và bảng quyết định vận hành Columns: Tổng cam kết | Phê duyệt bắt buộc | Điều kiện bổ sung Row 1: Tổng cam kết: Đến 5.000.000 VND | Phê duyệt bắt buộc: Quản lý trực tiếp | Điều kiện bổ sung: Một báo giá có hồ sơ; ngân sách xác nhận. Row 2: Tổng cam kết: 5.000.001-50.000.000 VND | Phê duyệt bắt buộc: Trưởng bộ phận | Điều kiện bổ sung: Ít nhất hai báo giá tương đương nếu thị trường cho ph_

Review: 

### T008 · role `employee` · vi · expected **answer**
**Q:** Gói mua 60tr thì cần bao nhiêu báo giá?

**Expected:** Trên 50.000.000 VND cần ít nhất ba báo giá bằng văn bản hoặc giải trình chỉ định nguồn được lập hồ sơ.
- must include: `ba|3`
- gold VN#261: _Tìm nguồn cạnh tranh và đánh giá báo giá Quy tắc bắt buộc. Cam kết dự toán đến 5.000.000 VND có thể dùng một báo giá được lập hồ sơ. Từ 5.000.001 đến 50.000.000 VND cần tìm ít nhất hai báo giá tương đương nếu thị trường cho phép. Trên 50.000.000 VND cần ít nhất ba báo giá bằng văn bản hoặc giải trình chỉ định nguồn được lập hồ sơ._
- gold VN#730: _Phụ lục B - Hạn mức phê duyệt và bảng quyết định vận hành Columns: Tổng cam kết | Phê duyệt bắt buộc | Điều kiện bổ sung Row 1: Tổng cam kết: Đến 5.000.000 VND | Phê duyệt bắt buộc: Quản lý trực tiếp | Điều kiện bổ sung: Một báo giá có hồ sơ; ngân sách xác nhận. Row 2: Tổng cam kết: 5.000.001-50.000.000 VND | Phê duyệt bắt buộc: Trưởng bộ phận | Điều kiện bổ sung: Ít nhất hai báo giá tương đương nếu thị trường cho ph_

Review: 

### T009 · role `employee` · vi · expected **answer**
**Q:** Bữa trưa khi đi công tác hết 350k thì được hoàn bao nhiêu?

**Expected:** Ăn uống tại địa phương được hoàn tối đa 300.000 VND/người/bữa; phần vượt cần ngoại lệ bằng văn bản được duyệt trước.
- must include: `300.000`
- gold VN#179: _Hạn mức chi phí, ăn uống và công tác Quy tắc bắt buộc. Trừ khi hợp đồng hoặc kế hoạch công tác đã duyệt đặt hạn thấp hơn, ăn uống tại địa phương được hoàn tối đa 300.000 VND/người/bữa; lưu trú công tác qua đêm tối đa 1.800.000 VND/phòng/đêm ở địa điểm nội địa thông thường và 2.500.000 VND tại thành phố lớn được chỉ định._
- gold VN#182: _Quy trình bắt buộc Vượt hạn cần ngoại lệ bằng văn bản được duyệt trước; cấm chia nhỏ đề nghị._

Review: 

### T010 · role `employee` · vi · expected **answer**
**Q:** Cam kết đúng 200 triệu thì ai duyệt?

**Expected:** 200.000.000 VND vẫn thuộc 50.000.001–200.000.000 VND: trưởng bộ phận cùng Mua sắm và Tài chính (chưa đến Hội đồng Điều hành Vận hành).
- must include: `Mua sắm` · `Tài chính`
- must not include: `Hội đồng Điều hành Vận hành phê duyệt`
- gold VN#274: _Ma trận phê duyệt và ngưỡng tiền Quy tắc bắt buộc. Thẩm quyền mặc định cho một cam kết: đến 5.000.000 VND-quản lý trực tiếp; 5.000.001-50.000.000 VND-trưởng bộ phận; 50.000.001-200.000.000 VND-trưởng bộ phận cùng Mua sắm và Tài chính; trên 200.000.000 VND-Hội đồng Điều hành Vận hành cùng Tài chính._
- gold VN#730: _Phụ lục B - Hạn mức phê duyệt và bảng quyết định vận hành Columns: Tổng cam kết | Phê duyệt bắt buộc | Điều kiện bổ sung Row 1: Tổng cam kết: Đến 5.000.000 VND | Phê duyệt bắt buộc: Quản lý trực tiếp | Điều kiện bổ sung: Một báo giá có hồ sơ; ngân sách xác nhận. Row 2: Tổng cam kết: 5.000.001-50.000.000 VND | Phê duyệt bắt buộc: Trưởng bộ phận | Điều kiện bổ sung: Ít nhất hai báo giá tương đương nếu thị trường cho ph_

Review: 

## calculation

### T011 · role `employee` · vi · expected **answer**
**Q:** Ở khách sạn 3 đêm tại thành phố lớn được chỉ định thì tối đa được hoàn bao nhiêu tiền phòng?

**Expected:** Hạn 2.500.000 VND/phòng/đêm tại thành phố lớn được chỉ định: 3 × 2.500.000 = 7.500.000 VND.
- must include: `7.500.000|7,5 triệu`
- gold VN#179: _Hạn mức chi phí, ăn uống và công tác Quy tắc bắt buộc. Trừ khi hợp đồng hoặc kế hoạch công tác đã duyệt đặt hạn thấp hơn, ăn uống tại địa phương được hoàn tối đa 300.000 VND/người/bữa; lưu trú công tác qua đêm tối đa 1.800.000 VND/phòng/đêm ở địa điểm nội địa thông thường và 2.500.000 VND tại thành phố lớn được chỉ định._

Review: 

### T012 · role `employee` · vi · expected **answer**
**Q:** Mua 4 máy chủ, mỗi máy 60 triệu thì ai duyệt?

**Expected:** Duyệt theo tổng cam kết: 4 × 60.000.000 = 240.000.000 VND, trên 200.000.000 VND nên Hội đồng Điều hành Vận hành cùng Tài chính phê duyệt.
- must include: `240.000.000|240 triệu` · `Hội đồng Điều hành Vận hành`
- gold VN#274: _Ma trận phê duyệt và ngưỡng tiền Quy tắc bắt buộc. Thẩm quyền mặc định cho một cam kết: đến 5.000.000 VND-quản lý trực tiếp; 5.000.001-50.000.000 VND-trưởng bộ phận; 50.000.001-200.000.000 VND-trưởng bộ phận cùng Mua sắm và Tài chính; trên 200.000.000 VND-Hội đồng Điều hành Vận hành cùng Tài chính._
- gold VN#730: _Phụ lục B - Hạn mức phê duyệt và bảng quyết định vận hành Columns: Tổng cam kết | Phê duyệt bắt buộc | Điều kiện bổ sung Row 1: Tổng cam kết: Đến 5.000.000 VND | Phê duyệt bắt buộc: Quản lý trực tiếp | Điều kiện bổ sung: Một báo giá có hồ sơ; ngân sách xác nhận. Row 2: Tổng cam kết: 5.000.001-50.000.000 VND | Phê duyệt bắt buộc: Trưởng bộ phận | Điều kiện bổ sung: Ít nhất hai báo giá tương đương nếu thị trường cho ph_

Review: 

### T013 · role `employee` · vi · expected **answer**
**Q:** Đi công tác 2 ngày, mỗi ngày ăn 2 bữa thì tối đa được hoàn bao nhiêu tiền ăn?

**Expected:** Tối đa 300.000 VND/người/bữa: 2 ngày × 2 bữa × 300.000 = 1.200.000 VND.
- must include: `1.200.000|1,2 triệu`
- gold VN#179: _Hạn mức chi phí, ăn uống và công tác Quy tắc bắt buộc. Trừ khi hợp đồng hoặc kế hoạch công tác đã duyệt đặt hạn thấp hơn, ăn uống tại địa phương được hoàn tối đa 300.000 VND/người/bữa; lưu trú công tác qua đêm tối đa 1.800.000 VND/phòng/đêm ở địa điểm nội địa thông thường và 2.500.000 VND tại thành phố lớn được chỉ định._

Review: 

### T014 · role `employee` · vi · expected **answer**
**Q:** Cùng một nhu cầu mà chia làm 3 lô 30 triệu, 15 triệu và 10 triệu thì cần mấy báo giá?

**Expected:** Tính theo tổng cam kết: 30 + 15 + 10 = 55.000.000 VND, trên 50.000.000 VND nên cần ít nhất ba báo giá văn bản hoặc giải trình chỉ định nguồn.
- must include: `55.000.000|55 triệu` · `ba|3`
- gold VN#261: _Tìm nguồn cạnh tranh và đánh giá báo giá Quy tắc bắt buộc. Cam kết dự toán đến 5.000.000 VND có thể dùng một báo giá được lập hồ sơ. Từ 5.000.001 đến 50.000.000 VND cần tìm ít nhất hai báo giá tương đương nếu thị trường cho phép. Trên 50.000.000 VND cần ít nhất ba báo giá bằng văn bản hoặc giải trình chỉ định nguồn được lập hồ sơ._
- gold VN#730: _Phụ lục B - Hạn mức phê duyệt và bảng quyết định vận hành Columns: Tổng cam kết | Phê duyệt bắt buộc | Điều kiện bổ sung Row 1: Tổng cam kết: Đến 5.000.000 VND | Phê duyệt bắt buộc: Quản lý trực tiếp | Điều kiện bổ sung: Một báo giá có hồ sơ; ngân sách xác nhận. Row 2: Tổng cam kết: 5.000.001-50.000.000 VND | Phê duyệt bắt buộc: Trưởng bộ phận | Điều kiện bổ sung: Ít nhất hai báo giá tương đương nếu thị trường cho ph_

Review: 

### T015 · role `employee` · vi · expected **answer**
**Q:** Ở khách sạn nội địa thông thường 2 đêm, mỗi đêm 2 triệu thì phần vượt hạn mức là bao nhiêu?

**Expected:** Hạn 1.800.000 VND/phòng/đêm ở địa điểm nội địa thông thường: vượt 200.000 VND mỗi đêm, tổng 400.000 VND; phần vượt cần ngoại lệ văn bản duyệt trước.
- must include: `400.000`
- gold VN#179: _Hạn mức chi phí, ăn uống và công tác Quy tắc bắt buộc. Trừ khi hợp đồng hoặc kế hoạch công tác đã duyệt đặt hạn thấp hơn, ăn uống tại địa phương được hoàn tối đa 300.000 VND/người/bữa; lưu trú công tác qua đêm tối đa 1.800.000 VND/phòng/đêm ở địa điểm nội địa thông thường và 2.500.000 VND tại thành phố lớn được chỉ định._
- gold VN#182: _Quy trình bắt buộc Vượt hạn cần ngoại lệ bằng văn bản được duyệt trước; cấm chia nhỏ đề nghị._

Review: 

## multi_part

### T016 · role `employee` · vi · expected **answer**
**Q:** Nghỉ phép theo kế hoạch cần báo trước bao lâu, và đơn nghỉ phải có những thông tin gì?

**Expected:** Báo trước ít nhất năm ngày làm việc; cung cấp mã nhân viên, loại nghỉ, ngày bắt đầu/kết thúc, số giờ nghỉ, cách liên hệ và kế hoạch bàn giao.
- must include: `năm ngày làm việc|5 ngày làm việc` · `loại nghỉ` · `bàn giao`
- gold VN#97: _Nộp yêu cầu nghỉ và thời hạn báo trước Quy tắc bắt buộc. Nghỉ theo kế hoạch nên được đề nghị ít nhất năm ngày làm việc trước ngày đầu nghỉ. Nghỉ khẩn, do bệnh hoặc được pháp luật bảo vệ phải báo sớm nhất có thể một cách hợp lý và không mất hiệu lực vì thiếu thời gian báo trước._
- gold VN#98: _Quy trình bắt buộc Cung cấp mã nhân viên, loại nghỉ, ngày bắt đầu/kết thúc, số giờ nghỉ cả ngày hoặc một phần ngày, cách liên hệ và kế hoạch bàn giao._

Review: 

### T017 · role `employee` · vi · expected **answer**
**Q:** Sự cố mức Trung bình và mức Thấp lần lượt phải báo trong bao lâu?

**Expected:** Trung bình: báo trong bốn giờ làm việc; Thấp: báo trước cuối ngày làm việc.
- must include: `bốn giờ làm việc|4 giờ làm việc` · `cuối ngày làm việc`
- gold VN#600: _Quy trình bắt buộc Trung bình: ảnh hưởng giới hạn, có biện pháp khoanh vùng; báo trong bốn giờ làm việc._
- gold VN#601: _Quy trình bắt buộc Thấp: vấn đề nhỏ, chưa có bằng chứng lộ dữ liệu; báo trước cuối ngày làm việc._

Review: 

### T018 · role `employee` · vi · expected **answer**
**Q:** Trước khi phát hành PO phải hoàn tất những kiểm tra gì, và nếu sửa PO sau khi phát hành thì sao?

**Expected:** Chỉ phát hành PO sau khi hoàn tất kiểm tra yêu cầu, nhà cung cấp, nguồn cung, ngân sách và duyệt; sửa PO sau phát hành phải có phiên bản, gửi nhà cung cấp và lưu các bản trước.
- must include: `ngân sách` · `phiên bản`
- gold VN#288: _Tạo và phát hành đơn mua hàng Quy tắc bắt buộc. Chỉ phát hành PO sau khi hoàn tất kiểm tra yêu cầu, nhà cung cấp, nguồn cung, ngân sách và duyệt._
- gold VN#293: _Yêu cầu kiểm soát Sửa PO sau phát hành phải có phiên bản và gửi nhà cung cấp; lưu các bản trước._

Review: 

### T019 · role `employee` · vi · expected **answer**
**Q:** Trước khi chia sẻ dữ liệu ra bên ngoài cần xác nhận gì, và có được tải dữ liệu Hạn chế lên dịch vụ AI chưa được duyệt không?

**Expected:** Trước chia sẻ ngoài phải xác nhận mục đích, người nhận, tối thiểu hóa và phê duyệt; không tải dữ liệu Hạn chế lên dịch vụ AI chưa được duyệt.
- must include: `mục đích` · `không`
- gold VN#572: _Quy trình bắt buộc Trước chia sẻ ngoài, xác nhận mục đích, người nhận, tối thiểu hóa và phê duyệt._
- gold VN#573: _Yêu cầu kiểm soát Không tải dữ liệu Hạn chế lên dịch vụ AI chưa được duyệt._

Review: 

### T020 · role `employee` · vi · expected **answer**
**Q:** Khi nhân viên nghỉ việc thì xử lý quyền truy cập thế nào, và xóa tài khoản có lập tức vô hiệu token không?

**Expected:** Khóa truy cập tương tác và thu hồi token/khóa theo quy trình nghỉ việc; xóa người dùng chưa chắc lập tức vô hiệu token hiện có.
- must include: `khóa|thu hồi` · `token`
- gold VN#541: _Quy trình bắt buộc Nghỉ việc: khóa truy cập tương tác và thu hồi token/khóa theo quy trình nghỉ việc._
- gold VN#544: _Yêu cầu kiểm soát Xóa người dùng chưa chắc lập tức vô hiệu token hiện có._

Review: 

## multi_passage

### T021 · role `employee` · vi · expected **answer**
**Q:** Hàng đang giữ kiểm định có được tính là hàng có thể bán không, và có được đánh dấu hỏng để giảm dư hàng không?

**Expected:** Không: hàng giữ kiểm định, hỏng, thu hồi hoặc hạn chế không được tính là hàng có thể bán; không đánh dấu hàng hỏng chỉ để loại dư hàng, ghi giảm cần bằng chứng độc lập và phê duyệt.
- must include: `không`
- gold VN#482: _Xếp kho, trách nhiệm giữ và trạng thái tồn Quy tắc bắt buộc. Hàng giữ kiểm định, hỏng, thu hồi hoặc hạn chế khác không được tính là hàng có thể bán._
- gold VN#431: _Yêu cầu kiểm soát Không đánh dấu hàng hỏng chỉ để loại dư hàng.  Kiểm quy tắc khuyến mãi và tồn trước giảm giá.  Ghi giảm cần đếm/bằng chứng độc lập và phê duyệt._

Review: 

### T022 · role `employee` · vi · expected **answer**
**Q:** Yêu cầu mua đã được phê duyệt thì đã là cam kết chưa, và khi nào mới được phát hành PO?

**Expected:** Chưa: yêu cầu không phải cam kết và phê duyệt không phải bằng chứng đã thực hiện; 'đã cam kết' là khi phát hành cam kết hợp lệ như PO, và PO chỉ phát hành sau khi hoàn tất kiểm tra yêu cầu, nhà cung cấp, nguồn cung, ngân sách và duyệt.
- must include: `không|chưa` · `PO`
- gold VN#33: _Định nghĩa và trạng thái giao dịch Quy tắc bắt buộc. Yêu cầu không phải cam kết; phê duyệt không phải bằng chứng đã thực hiện; một hàng dữ liệu phân tích chưa chắc chứng minh trạng thái vật lý hoặc tài chính hiện tại._
- gold VN#36: _Quy trình bắt buộc Đã cam kết: đã phát hành cam kết nghiệp vụ hợp lệ, chẳng hạn đơn mua hàng đã phát hành._
- gold VN#288: _Tạo và phát hành đơn mua hàng Quy tắc bắt buộc. Chỉ phát hành PO sau khi hoàn tất kiểm tra yêu cầu, nhà cung cấp, nguồn cung, ngân sách và duyệt._

Review: 

### T023 · role `employee` · vi · expected **answer**
**Q:** Tác tử AI có được phát hành PO hay trả hóa đơn không, và nếu hai nguồn đã duyệt mâu thuẫn thì xử lý ra sao?

**Expected:** Không: tác tử AI không được duyệt chi, phát hành PO, trả hóa đơn, điều chỉnh tồn hay cấp quyền trừ luồng được phê duyệt riêng; nếu hai nguồn đã duyệt mâu thuẫn, tạm dừng hành động tự động liên quan và chuyển chủ sở hữu chịu trách nhiệm.
- must include: `không` · `chuyển`
- gold VN#629: _Quản lý thay đổi, an toàn tác tử AI và kiểm soát phát hành Quy tắc bắt buộc. Tác tử AI có thể truy chính sách đã duyệt, hỏi dữ liệu được phép và soạn đề xuất. Không được duyệt chi, phát hành PO, trả hóa đơn, điều chỉnh tồn hay cấp quyền, trừ luồng được phê duyệt và kiểm toán riêng cho phép rõ hành động đó._
- gold VN#74: _Yêu cầu kiểm soát Nếu hai nguồn đã duyệt mâu thuẫn, tạm dừng hành động tự động liên quan và chuyển chủ sở hữu chịu trách nhiệm xử lý._

Review: 

### T024 · role `employee` · vi · expected **answer**
**Q:** Người đề nghị hoàn chi có được là người duyệt duy nhất không, và người đếm có được tự duyệt điều chỉnh tồn trọng yếu không?

**Expected:** Không cho cả hai: người đề nghị không được là người duyệt duy nhất cho hoàn chi; người đếm không được là người duyệt duy nhất cho điều chỉnh tồn trọng yếu.
- must include: `không`
- gold VN#197: _Yêu cầu kiểm soát Người đề nghị không được là người duyệt duy nhất.  Không đánh dấu đã chi chỉ dựa vào lệnh thanh toán._
- gold VN#459: _Yêu cầu kiểm soát Người đếm không được là người duyệt duy nhất cho điều chỉnh trọng yếu._

Review: 

### T025 · role `employee` · vi · expected **answer**
**Q:** Phát hiện kiểm toán trọng yếu chưa xử lý thì chuyển cho ai, và bản chính sách lỗi thời có còn được truy xuất không?

**Expected:** Phát hiện trọng yếu chưa xử lý chuyển Hội đồng Điều hành Vận hành; bản lỗi thời được rút khỏi truy xuất đang hoạt động nhưng vẫn giữ để phục vụ kiểm toán.
- must include: `Hội đồng Điều hành Vận hành` · `kiểm toán`
- gold VN#717: _Yêu cầu kiểm soát Phát hiện trọng yếu chưa xử lý chuyển Hội đồng Điều hành Vận hành._
- gold VN#73: _Yêu cầu kiểm soát Rút bản lỗi thời khỏi truy xuất đang hoạt động nhưng giữ bản phục vụ kiểm toán._

Review: 

## table

### T026 · role `employee` · vi · expected **answer**
**Q:** Theo Phụ lục C, biểu mẫu yêu cầu nghỉ phép có những điều kiện chặn nào?

**Expected:** Ngày cuối phải lớn hơn hoặc bằng ngày đầu; rà trùng; nghỉ được bảo vệ chuyển Nhân sự.
- must include: `ngày đầu` · `trùng`
- gold VN#737: _Phụ lục C - Biểu mẫu chuẩn và kiểm tra tối thiểu Columns: Biểu mẫu | Trường tối thiểu | Kiểm tra / điều kiện chặn Row 1: Biểu mẫu: Yêu cầu nghỉ phép | Trường tối thiểu: Mã nhân viên; loại nghỉ; ngày đầu/cuối; cả/một phần ngày; bàn giao; thời điểm nộp. | Kiểm tra / điều kiện chặn: Ngày cuối >= ngày đầu; rà trùng; nghỉ được bảo vệ chuyển Nhân sự. Row 2: Biểu mẫu: Đề nghị hoàn chi phí | Trường tối thiểu: Người đề nghị; _

Review: 

### T027 · role `employee` · vi · expected **answer**
**Q:** Theo Phụ lục C, đơn mua hàng phải có những trường tối thiểu nào?

**Expected:** Số PO; nhà cung cấp; ngày phát hành; tiền tệ; dòng hàng; số lượng; đơn giá; điều kiện giao/thanh toán.
- must include: `Số PO` · `đơn giá`
- gold VN#738: _Phụ lục C - Biểu mẫu chuẩn và kiểm tra tối thiểu Columns: Biểu mẫu | Trường tối thiểu | Kiểm tra / điều kiện chặn Row 4: Biểu mẫu: Đơn mua hàng | Trường tối thiểu: Số PO; nhà cung cấp; ngày phát hành; tiền tệ; dòng hàng; số lượng; đơn giá; điều kiện giao/thanh toán. | Kiểm tra / điều kiện chặn: Chỉ phát hành sau duyệt; tổng khớp thẩm quyền; sửa có phiên bản._

Review: 

### T028 · role `employee` · vi · expected **answer**
**Q:** Trong Exception Log, sản phẩm VietMotion RP-09 có calculated DOS là bao nhiêu?

**Expected:** VietMotion RP-09 (Product ID 2212, Outdoor, snapshot 2022-12-31) có Calculated DOS 25440, ưu tiên P1 - DATA CONFLICT.
- must include: `25440|25.440`
- gold 04_Inventory_Control_and#435: _Exception Log Columns: Snapshot Date | Product ID | Product Name | Category | On-hand | Units Sold Latest | Avg Monthly Demand (3 snapshots) | Calculated DOS | Fill Rate | Priority | Review Status Row 1: Snapshot Date: 2022-12-31 | Product ID: 2212 | Product Name: VietMotion RP-09 | Category: Outdoor | On-hand: 848 | Units Sold Latest: 1 | Avg Monthly Demand (3 snapshots): 1 | Calculated DOS: 25440 | Fill Rate: 0.933_

Review: 

### T029 · role `employee` · vi · expected **answer**
**Q:** Theo SOP kiểm kê, khi không có chênh lệch thì ai duyệt đóng phiếu?

**Expected:** Không chênh lệch: đóng phiếu và lưu audit trail, người duyệt là Warehouse Supervisor.
- must include: `Warehouse Supervisor`
- gold 02_SOP_Cycle_Count_and_S#7: _Columns: Tình huống | Hành động tối thiểu | Người duyệt Row 1: Tình huống: Không chênh lệch | Hành động tối thiểu: Đóng phiếu; lưu audit trail | Người duyệt: Warehouse Supervisor Row 2: Tình huống: Chênh lệch nhỏ, có nguyên nhân rõ và bằng chứng | Hành động tối thiểu: Recount + biên bản; cập nhật sau duyệt | Người duyệt: Inventory Controller / Supervisor Row 3: Tình huống: Chênh lệch lặp lại, giá trị lớn hoặc vượt ng_

Review: 

### T030 · role `employee` · vi · expected **answer**
**Q:** Theo Phụ lục B, cam kết trên 200 triệu cần điều kiện bổ sung gì?

**Expected:** Trên 200.000.000 VND: Hội đồng Điều hành Vận hành + Tài chính duyệt; điều kiện bổ sung là đánh giá nguồn cung và rà rủi ro được lập hồ sơ.
- must include: `Đánh giá nguồn cung|đánh giá nguồn cung` · `rủi ro`
- gold VN#730: _Phụ lục B - Hạn mức phê duyệt và bảng quyết định vận hành Columns: Tổng cam kết | Phê duyệt bắt buộc | Điều kiện bổ sung Row 1: Tổng cam kết: Đến 5.000.000 VND | Phê duyệt bắt buộc: Quản lý trực tiếp | Điều kiện bổ sung: Một báo giá có hồ sơ; ngân sách xác nhận. Row 2: Tổng cam kết: 5.000.001-50.000.000 VND | Phê duyệt bắt buộc: Trưởng bộ phận | Điều kiện bổ sung: Ít nhất hai báo giá tương đương nếu thị trường cho ph_

Review: 

## not_covered

### T031 · role `employee` · vi · expected **not_covered**
**Q:** Nghỉ thai sản được bao nhiêu tháng?

**Expected:** Tài liệu được phép truy cập không quy định nghỉ thai sản.

Review: 

### T032 · role `employee` · vi · expected **not_covered**
**Q:** Giờ làm việc hành chính của công ty bắt đầu lúc mấy giờ?

**Expected:** Tài liệu không quy định giờ làm việc.

Review: 

### T033 · role `employee` · vi · expected **not_covered**
**Q:** Nhân viên được phụ cấp điện thoại bao nhiêu mỗi tháng?

**Expected:** Tài liệu không đề cập phụ cấp điện thoại.

Review: 

### T034 · role `employee` · vi · expected **not_covered**
**Q:** Công ty có xe đưa đón nhân viên không?

**Expected:** Tài liệu không đề cập xe đưa đón.

Review: 

### T035 · role `employee` · vi · expected **not_covered**
**Q:** Có được tạm ứng lương giữa tháng không?

**Expected:** Tài liệu không đề cập tạm ứng lương.

Review: 

## false_premise

### T036 · role `employee` · vi · expected **answer**
**Q:** Yêu cầu mua đã được duyệt rồi nên coi như đơn hàng đã đặt xong đúng không?

**Expected:** Không: phê duyệt không phải bằng chứng đã thực hiện; chỉ 'đã cam kết' khi phát hành cam kết hợp lệ như PO, và 'đã hoàn thành' khi sự kiện thực tế đã diễn ra và được đối chiếu.
- must include: `không|chưa`
- gold VN#33: _Định nghĩa và trạng thái giao dịch Quy tắc bắt buộc. Yêu cầu không phải cam kết; phê duyệt không phải bằng chứng đã thực hiện; một hàng dữ liệu phân tích chưa chắc chứng minh trạng thái vật lý hoặc tài chính hiện tại._
- gold VN#36: _Quy trình bắt buộc Đã cam kết: đã phát hành cam kết nghiệp vụ hợp lệ, chẳng hạn đơn mua hàng đã phát hành._

Review: 

### T037 · role `employee` · vi · expected **answer**
**Q:** Hạn mức khách sạn ở đâu cũng là 2,5 triệu một đêm phải không?

**Expected:** Không: 1.800.000 VND/phòng/đêm ở địa điểm nội địa thông thường; 2.500.000 VND chỉ áp dụng tại thành phố lớn được chỉ định (Tài chính công bố danh sách).
- must include: `1.800.000` · `thành phố lớn`
- gold VN#179: _Hạn mức chi phí, ăn uống và công tác Quy tắc bắt buộc. Trừ khi hợp đồng hoặc kế hoạch công tác đã duyệt đặt hạn thấp hơn, ăn uống tại địa phương được hoàn tối đa 300.000 VND/người/bữa; lưu trú công tác qua đêm tối đa 1.800.000 VND/phòng/đêm ở địa điểm nội địa thông thường và 2.500.000 VND tại thành phố lớn được chỉ định._
- gold VN#185: _Yêu cầu kiểm soát Tài chính công bố danh sách thành phố lớn hiện hành và rà hạn mức hằng năm._

Review: 

### T038 · role `employee` · vi · expected **answer**
**Q:** Nghỉ ốm đột xuất mà không báo trước 5 ngày thì đơn nghỉ bị mất hiệu lực đúng không?

**Expected:** Không: nghỉ khẩn, do bệnh hoặc được pháp luật bảo vệ phải báo sớm nhất có thể một cách hợp lý và không mất hiệu lực vì thiếu thời gian báo trước.
- must include: `không`
- gold VN#97: _Nộp yêu cầu nghỉ và thời hạn báo trước Quy tắc bắt buộc. Nghỉ theo kế hoạch nên được đề nghị ít nhất năm ngày làm việc trước ngày đầu nghỉ. Nghỉ khẩn, do bệnh hoặc được pháp luật bảo vệ phải báo sớm nhất có thể một cách hợp lý và không mất hiệu lực vì thiếu thời gian báo trước._

Review: 

### T039 · role `employee` · vi · expected **answer**
**Q:** Khi tồn kho thấp thì AI agent được tự phát hành PO để bổ sung đúng không?

**Expected:** Không: tín hiệu đặt lại chỉ kích hoạt rà bổ sung, không tự tạo PO; tác tử AI không được phát hành PO trừ luồng được phê duyệt và kiểm toán riêng.
- must include: `không`
- gold VN#629: _Quản lý thay đổi, an toàn tác tử AI và kiểm soát phát hành Quy tắc bắt buộc. Tác tử AI có thể truy chính sách đã duyệt, hỏi dữ liệu được phép và soạn đề xuất. Không được duyệt chi, phát hành PO, trả hóa đơn, điều chỉnh tồn hay cấp quyền, trừ luồng được phê duyệt và kiểm toán riêng cho phép rõ hành động đó._
- gold VN#398: _Tín hiệu đặt lại và rà bổ sung hàng Quy tắc bắt buộc. Hàng có reorder_flag=true, stockout_flag=true hoặc days_of_supply thấp kích hoạt rà bổ sung, không tự tạo PO._

Review: 

### T040 · role `employee` · vi · expected **answer**
**Q:** Đã đổi lịch làm rồi thì coi như chứng minh được là có làm thêm giờ đúng không?

**Expected:** Không: đổi lịch không chứng minh đã làm thêm; nhân viên ghi giờ thực tế vào hệ thống chấm công và quản lý xác nhận giờ thực.
- must include: `không`
- gold VN#156: _Yêu cầu kiểm soát Đổi lịch không chứng minh đã làm thêm.  Không dùng "nghỉ bù" không chính thức thay khoản lương pháp luật bắt buộc, trừ khi được phép và lập hồ sơ._
- gold VN#154: _Quy trình bắt buộc Nhân viên ghi giờ thực tế vào hệ thống chấm công.  Quản lý xác nhận giờ thực và giải thích lệch so với dự kiến đã duyệt._

Review: 

## language

### T041 · role `employee` · en · expected **answer**
**Q:** How far in advance should planned leave be requested?

**Expected:** Planned leave should be requested at least five working days before the first day of leave.
- must include: `five|5`
- gold EN#94: _Leave request submission and notice Mandatory rule. Planned leave should be submitted at least five working days before the first day. Emergency, illness-related or legally protected leave must be reported as soon as reasonably practicable and is not invalidated by missing advance notice._

Review: 

### T042 · role `employee` · en · expected **answer**
**Q:** What is the reimbursement limit for a local meal?

**Expected:** Local meals are reimbursed up to VND 300,000 per person per meal unless a lower limit applies.
- must include: `300,000|300.000`
- gold EN#182: _Expense limits, meals and travel Mandatory rule. Unless a contract or approved travel plan sets a stricter cap, local meals are reimbursable up to VND 300,000 per person per meal; overnight travel lodging is capped at VND 1,800,000 per room-night in ordinary domestic locations and VND 2,500,000 in designated major-city locations._

Review: 

### T043 · role `employee` · mixed · expected **answer**
**Q:** Incident mức High thì phải report trong bao lâu?

**Expected:** Mức Cao: báo Bảo mật và chủ hệ thống trong một giờ.
- must include: `một giờ|1 giờ|one hour`
- gold VN#599: _Quy trình bắt buộc Cao: khả năng truy cập trái phép hoặc suy giảm dịch vụ đáng kể; báo Bảo mật và chủ hệ thống trong một giờ._

Review: 

### T044 · role `employee` · en · expected **answer**
**Q:** Who must approve a commitment above VND 200 million?

**Expected:** Above VND 200,000,000 the Operations Executive Board together with Finance approves.
- must include: `Executive|Operations Executive` · `Finance`
- gold EN#286: _Approval matrix and monetary thresholds Mandatory rule. The default delegated authority for a single commitment is: up to VND 5,000,000-line manager; VND 5,000,001-50,000,000-department head; VND 50,000,001-200,000,000-department head plus Procurement and Finance; above VND 200,000,000-Executive Operations Council plus Finance._
- gold EN#781: _Appendix B - Approval limits and operational decision table Columns: Total commitment | Required approval | Additional condition Row 1: Total commitment: Up to VND 5,000,000 | Required approval: Line manager | Additional condition: One documented quote; budget confirmed. Row 2: Total commitment: VND 5,000,001-50,000,000 | Required approval: Department head | Additional condition: At least two comparable quotes where _

Review: 

### T045 · role `employee` · mixed · expected **answer**
**Q:** Three-way match gồm những chứng từ nào?

**Expected:** Đối chiếu ba bên giữa PO đã phát hành, biên bản nhận được chấp nhận và hóa đơn nhà cung cấp; dịch vụ dùng xác nhận nghiệm thu thay phiếu nhận hàng.
- must include: `PO` · `hóa đơn` · `nhận`
- gold VN#314: _Đối chiếu hóa đơn và kiểm soát thanh toán Quy tắc bắt buộc. Kiểm soát chuẩn là đối chiếu ba bên giữa PO đã phát hành, biên bản nhận được chấp nhận và hóa đơn nhà cung cấp. Dịch vụ cần xác nhận nghiệm thu dịch vụ thay phiếu nhận hàng._

Review: 

## noisy

### T046 · role `employee` · vi · expected **answer**
**Q:** lam them gio co can xin duyet truoc khong

**Expected:** Có: làm thêm cần duyệt trước, trừ khẩn cấp hoặc quy định pháp luật khiến không thể duyệt trước; nhân viên phải báo giờ thực tế kịp thời.
- must include: `duyệt trước|duyet truoc`
- gold VN#152: _Làm thêm, đổi lịch và bỏ ca Quy tắc bắt buộc. Làm thêm cần duyệt trước, trừ khẩn cấp hoặc quy định pháp luật khiến không thể duyệt trước; nhân viên phải báo giờ thực tế kịp thời._

Review: 

### T047 · role `employee` · vi · expected **answer**
**Q:** ê bro, khách sạn ở HN hết 2tr2 một đêm thì đc hoàn hết ko?

**Expected:** Tùy danh sách thành phố lớn do Tài chính công bố: nếu Hà Nội là thành phố lớn được chỉ định thì hạn 2.500.000 VND/đêm (2.200.000 được hoàn đủ); nếu không thì hạn 1.800.000 VND/đêm và phần vượt cần ngoại lệ duyệt trước.
- must include: `2.500.000|2,5` · `1.800.000|1,8`
- gold VN#179: _Hạn mức chi phí, ăn uống và công tác Quy tắc bắt buộc. Trừ khi hợp đồng hoặc kế hoạch công tác đã duyệt đặt hạn thấp hơn, ăn uống tại địa phương được hoàn tối đa 300.000 VND/người/bữa; lưu trú công tác qua đêm tối đa 1.800.000 VND/phòng/đêm ở địa điểm nội địa thông thường và 2.500.000 VND tại thành phố lớn được chỉ định._
- gold VN#185: _Yêu cầu kiểm soát Tài chính công bố danh sách thành phố lớn hiện hành và rà hạn mức hằng năm._

Review: 

### T048 · role `employee` · vi · expected **answer**
**Q:** hóa đơn ncc bị trùng số thì sử lý sao ạ

**Expected:** Số hóa đơn trùng hoặc số tiền/ngày lặp phải được giữ lại để rà soát trước khi thanh toán.
- must include: `rà soát|giữ`
- gold VN#320: _Yêu cầu kiểm soát Số hóa đơn trùng hoặc số tiền/ngày lặp phải giữ rà soát._

Review: 

### T049 · role `employee` · vi · expected **answer**
**Q:** nhan vien moi thi khi nao moi duoc cap quyen

**Expected:** Nhân viên mới chỉ được cấp vai trò đã duyệt sau khi xác minh danh tính.
- must include: `xác minh danh tính|xac minh danh tinh`
- gold VN#539: _Quy trình bắt buộc Nhân viên mới: chỉ cấp vai trò đã duyệt sau xác minh danh tính._

Review: 

### T050 · role `employee` · vi · expected **answer**
**Q:** sp trong kho bị lệch tên danh mục thì lấy theo bảng nào vậy m

**Expected:** Dùng product_id làm khóa chuẩn; nếu tên hoặc loại trong inventory khác products thì lấy commerce.products làm metadata danh mục và đánh dấu lệch.
- must include: `commerce.products|products` · `product_id`
- gold VN#376: _Yêu cầu kiểm soát Không tạo product_id giả để nối thành công.  Nếu inventory.product_name hoặc category khác products, lấy products làm metadata danh mục và đánh dấu lệch._
- gold VN#371: _Danh tính sản phẩm, đổi danh mục và nối dữ liệu Quy tắc bắt buộc. Dùng product_id làm khóa chuẩn. Tên, loại, phân khúc, kích thước và màu là thuộc tính mô tả, không thay khóa._

Review: 

## rbac

### T051 · role `executive` · vi · expected **not_covered**
**Q:** Theo SOP kiểm kê, tỷ lệ chênh lệch được tính như thế nào?

**Expected:** Vai trò executive không được xem SOP kiểm kê (02); câu trả lời phải là không có trong tài liệu được phép.
- must not use: 02_SOP_Cycle_Count_and_Stock_Adjustment.pdf

Review: 

### T052 · role `operations` · vi · expected **answer**
**Q:** Trong SOP kiểm kê và điều chỉnh tồn, tỷ lệ chênh lệch tính thế nào?

**Expected:** Chênh lệch tuyệt đối = |thực tế − hệ thống|; tỷ lệ chênh lệch = chênh lệch / max(hệ thống, 1).
- must include: `max`
- gold 02_SOP_Cycle_Count_and_S#2: _5. Ngưỡng xử lý và phê duyệt • Đóng băng giao dịch tại vị trí cần đếm hoặc ghi lại mọi giao dịch phát sinh trong cửa sổ đếm. • Chuẩn bị thiết bị quét, nhãn cách ly, biểu mẫu ghi nhận, camera và phương án xử lý hàng đang pick / pack / chuyển kho. 4. Thực hiện đếm và đối chiếu • Đếm theo SKU + size + color + vị trí; không gộp các biến thể gần giống nhau. • Ghi số lượng thực tế, đơn vị tính, người đếm, thời điểm và tình_

Review: 

### T053 · role `procurement` · vi · expected **not_covered**
**Q:** Theo deck đào tạo chính sách tồn kho, mô hình vận hành gồm những bước nào?

**Expected:** Vai trò procurement không được xem deck đào tạo (05); câu trả lời phải là không có trong tài liệu được phép.
- must not use: 05_Inventory_Policy_Training_Deck.pptx

Review: 

### T054 · role `legal_compliance` · vi · expected **answer**
**Q:** Mô hình vận hành trong deck đào tạo tồn kho gồm các bước gì?

**Expected:** PLAN → APPROVE → RECEIVE → CONTROL → LEARN; người đếm ≠ người nhập điều chỉnh ≠ người duyệt.
- must include: `PLAN` · `APPROVE` · `RECEIVE` · `CONTROL` · `LEARN`
- gold 05_Inventory_Policy_Trai#2: _02 | Mô hình vận hành Tách quyền ra quyết định khỏi thao tác nhập liệu. PLAN Forecast / campaign ROP & target stock → APPROVE Budget / supplier PO authorization → RECEIVE PO match QC & put-away → CONTROL Cycle count Exception handling → LEARN KPI / root cause Forecast update Nguyên tắc kiểm soát: người đếm ≠ người nhập điều chỉnh ≠ người duyệt. AI Agent chỉ đọc dữ liệu được phân quyền và đề xuất; không tự phát hành P_

Review: 

### T055 · role `finance_analyst` · vi · expected **answer**
**Q:** Theo README của Inventory Planner, tín hiệu stockout được xác định thế nào?

**Expected:** Stockout signal: stockout_days ≥ 1 hoặc fill_rate < 95% hoặc calculated days of supply ≤ 14 ngày.
- must include: `14`
- gold 04_Inventory_Control_and#1: _README Columns: Mục | Nội dung Row 8: Mục: Inventory position | Nội dung: On-hand + Open PO − Backorder. Dataset không có Open PO / Backorder; workbook mặc định 0 và yêu cầu nhập số thực tế. Row 9: Mục: Stockout signal | Nội dung: stockout_days ≥ 1 hoặc fill_rate < 95% hoặc calculated days of supply ≤ 14 ngày. Row 10: Mục: Overstock signal | Nội dung: Calculated days of supply > 120 ngày. >180 ngày cần kế hoạch xử lý_

Review: 

## follow_up

### T056 · role `employee` · vi · expected **answer**
> (previous turn) **Q:** Mua hàng 80 triệu thì ai duyệt?  
> **A:** Trưởng bộ phận cùng Mua sắm và Tài chính phê duyệt.
**Q:** thế 300 triệu thì sao?

**Expected:** 300.000.000 VND trên 200.000.000 VND: Hội đồng Điều hành Vận hành cùng Tài chính phê duyệt, kèm đánh giá nguồn cung và rà rủi ro được lập hồ sơ.
- must include: `Hội đồng Điều hành Vận hành` · `Tài chính`
- gold VN#274: _Ma trận phê duyệt và ngưỡng tiền Quy tắc bắt buộc. Thẩm quyền mặc định cho một cam kết: đến 5.000.000 VND-quản lý trực tiếp; 5.000.001-50.000.000 VND-trưởng bộ phận; 50.000.001-200.000.000 VND-trưởng bộ phận cùng Mua sắm và Tài chính; trên 200.000.000 VND-Hội đồng Điều hành Vận hành cùng Tài chính._
- gold VN#730: _Phụ lục B - Hạn mức phê duyệt và bảng quyết định vận hành Columns: Tổng cam kết | Phê duyệt bắt buộc | Điều kiện bổ sung Row 1: Tổng cam kết: Đến 5.000.000 VND | Phê duyệt bắt buộc: Quản lý trực tiếp | Điều kiện bổ sung: Một báo giá có hồ sơ; ngân sách xác nhận. Row 2: Tổng cam kết: 5.000.001-50.000.000 VND | Phê duyệt bắt buộc: Trưởng bộ phận | Điều kiện bổ sung: Ít nhất hai báo giá tương đương nếu thị trường cho ph_

Review: 

### T057 · role `employee` · vi · expected **answer**
> (previous turn) **Q:** Ăn uống khi đi công tác được hoàn tối đa bao nhiêu?  
> **A:** Tối đa 300.000 VND/người/bữa.
**Q:** còn tiền khách sạn thì sao?

**Expected:** Lưu trú qua đêm tối đa 1.800.000 VND/phòng/đêm ở địa điểm nội địa thông thường và 2.500.000 VND tại thành phố lớn được chỉ định.
- must include: `1.800.000` · `2.500.000`
- gold VN#179: _Hạn mức chi phí, ăn uống và công tác Quy tắc bắt buộc. Trừ khi hợp đồng hoặc kế hoạch công tác đã duyệt đặt hạn thấp hơn, ăn uống tại địa phương được hoàn tối đa 300.000 VND/người/bữa; lưu trú công tác qua đêm tối đa 1.800.000 VND/phòng/đêm ở địa điểm nội địa thông thường và 2.500.000 VND tại thành phố lớn được chỉ định._

Review: 

### T058 · role `employee` · vi · expected **answer**
> (previous turn) **Q:** Sự cố mức Cao phải báo trong bao lâu?  
> **A:** Báo Bảo mật và chủ hệ thống trong một giờ.
**Q:** còn mức Nghiêm trọng thì sao?

**Expected:** Mức Nghiêm trọng (xâm phạm đang diễn ra, lộ rộng dữ liệu Hạn chế, gian lận tài chính trọng yếu hoặc dừng dịch vụ thiết yếu): liên hệ trưởng Bảo mật ngay.
- must include: `ngay`
- gold VN#598: _Quy trình bắt buộc Nghiêm trọng: xâm phạm đang diễn ra, lộ rộng dữ liệu Hạn chế, gian lận tài chính trọng yếu hoặc dừng dịch vụ thiết yếu; liên hệ trưởng Bảo mật ngay._

Review: 

### T059 · role `employee` · vi · expected **answer**
> (previous turn) **Q:** Ngoại lệ chính sách có tự hết hạn không?  
> **A:** Có, mỗi ngoại lệ có ngày hết hạn và tự hết hiệu lực nếu không được gia hạn.
**Q:** vậy ai có quyền gia hạn và phải làm khi nào?

**Expected:** Ngoại lệ chỉ được gia hạn bởi cùng cấp hoặc cao hơn, trước khi hết hạn, kèm bằng chứng rủi ro cập nhật; nếu không thì tự hết hiệu lực.
- must include: `cùng cấp|cao hơn` · `trước`
- gold VN#659: _Duyệt, hết hạn và đóng ngoại lệ Quy tắc bắt buộc. Mỗi ngoại lệ có chủ cụ thể, phạm vi rõ, hồ sơ duyệt, ngày đầu và hết hạn. Tự hết hiệu lực trừ khi cùng cấp hoặc cao hơn gia hạn trước hết hạn._
- gold VN#662: _Quy trình bắt buộc Trước hết hạn, trở lại tuân chuẩn hoặc xin gia hạn với bằng chứng rủi ro cập nhật._

Review: 

### T060 · role `employee` · vi · expected **answer**
> (previous turn) **Q:** Hàng dư thừa thì xử lý thế nào?  
> **A:** overstock_flag hoặc days_of_supply cao kéo dài chỉ kích hoạt rà soát, không tự cho phép thanh lý, ghi giảm hoặc khuyến mãi.
**Q:** vậy muốn giảm giá thì ai phải duyệt?

**Expected:** Cấp Kinh doanh và Tài chính cần thiết phải duyệt trước khi đổi giá hoặc xử lý hàng.
- must include: `Kinh doanh` · `Tài chính`
- gold VN#430: _Quy trình bắt buộc Được cấp Kinh doanh và Tài chính cần thiết duyệt trước đổi giá hoặc xử lý hàng.  Theo dõi kết quả và rà lại sau kỳ được xác định._

Review: 
