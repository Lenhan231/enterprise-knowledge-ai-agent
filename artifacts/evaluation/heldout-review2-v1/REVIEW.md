# Bộ câu hỏi mới — reviewed-r1 trước benchmark

20 ý hỏi / 40 câu chữ VI–EN / 80 directional cases. 5 câu mỗi nhóm. Chưa chạy retrieval, translation hoặc model inference. Đã áp dụng các chỉnh sửa H10/H13/H19 theo yêu cầu người dùng sau khi đọc rà soát. Nhãn do assistant soạn và đối chiếu nguồn; không phải bộ nhãn được chứng nhận độc lập.

## H01 — narrative

Theo phần mục đích của Manual, chính sách tồn kho phải cân bằng bốn yếu tố nào?

According to the Manual purpose section, which four factors should the inventory policy balance?

**Đáp án đối chiếu (VI):** Mức sẵn hàng, chi phí lưu kho, vốn bị chiếm dụng và độ chính xác dữ liệu.

**Liên quan bộ cũ:** Không phải paraphrase trực tiếp của câu cũ đã liệt kê; vẫn cùng corpus.

### H01.availability — Sẵn hàng

VI · 01_Inventory_Management_Policy_Manual.docx · parser 2 · [181, 196):

> mức độ sẵn hàng

EN · 01_Inventory_Management_Policy_Manual_EN.docx · parser 2 · [201, 221):

> product availability

### H01.holding — Chi phí lưu kho

VI · 01_Inventory_Management_Policy_Manual.docx · parser 2 · [198, 213):

> chi phí lưu kho

EN · 01_Inventory_Management_Policy_Manual_EN.docx · parser 2 · [223, 236):

> holding costs

### H01.capital — Vốn bị chiếm dụng

VI · 01_Inventory_Management_Policy_Manual.docx · parser 2 · [215, 232):

> vốn bị chiếm dụng

EN · 01_Inventory_Management_Policy_Manual_EN.docx · parser 2 · [238, 253):

> tied-up capital

### H01.accuracy — Độ chính xác dữ liệu

VI · 01_Inventory_Management_Policy_Manual.docx · parser 2 · [236, 260):

> độ chính xác của dữ liệu

EN · 01_Inventory_Management_Policy_Manual_EN.docx · parser 2 · [259, 272):

> data accuracy

## H02 — narrative

Phần mô tả dataset liệt kê những nhóm hàng nào đang được quan sát?

Which product categories are listed as observed in the dataset description?

**Đáp án đối chiếu (VI):** Streetwear, Outdoor, Casual, GenZ.

**Liên quan bộ cũ:** Không phải paraphrase trực tiếp của câu cũ đã liệt kê; vẫn cùng corpus.

### H02.streetwear — Streetwear

VI · 01_Inventory_Management_Policy_Manual.docx · parser 3 · [215, 225):

> Streetwear

VI · 05_Inventory_Policy_Training_Deck.pptx · parser 1 · [227, 237):

> Streetwear

EN · 01_Inventory_Management_Policy_Manual_EN.docx · parser 3 · [239, 249):

> Streetwear

EN · 05_Inventory_Policy_Training_Deck_EN.pptx · parser 1 · [257, 267):

> Streetwear

### H02.outdoor — Outdoor

VI · 01_Inventory_Management_Policy_Manual.docx · parser 3 · [227, 234):

> Outdoor

VI · 05_Inventory_Policy_Training_Deck.pptx · parser 1 · [240, 247):

> Outdoor

EN · 01_Inventory_Management_Policy_Manual_EN.docx · parser 3 · [251, 258):

> Outdoor

EN · 05_Inventory_Policy_Training_Deck_EN.pptx · parser 1 · [270, 277):

> Outdoor

### H02.casual — Casual

VI · 01_Inventory_Management_Policy_Manual.docx · parser 3 · [236, 242):

> Casual

VI · 05_Inventory_Policy_Training_Deck.pptx · parser 1 · [250, 256):

> Casual

EN · 01_Inventory_Management_Policy_Manual_EN.docx · parser 3 · [260, 266):

> Casual

EN · 05_Inventory_Policy_Training_Deck_EN.pptx · parser 1 · [280, 286):

> Casual

### H02.genz — GenZ

VI · 01_Inventory_Management_Policy_Manual.docx · parser 3 · [246, 250):

> GenZ

VI · 05_Inventory_Policy_Training_Deck.pptx · parser 1 · [259, 263):

> GenZ

EN · 01_Inventory_Management_Policy_Manual_EN.docx · parser 3 · [272, 276):

> GenZ

EN · 05_Inventory_Policy_Training_Deck_EN.pptx · parser 1 · [289, 293):

> GenZ

## H03 — narrative

Nếu lịch sử nhu cầu chưa đủ tin cậy để phân nhóm ABC, tài liệu cho phép làm gì và phải rà soát lại sau bao nhiêu chu kỳ?

When demand history is not reliable enough for ABC classification, what temporary approach is allowed and after how many cycles must it be reviewed?

**Đáp án đối chiếu (VI):** Dùng nhóm tạm và rà soát sau 3 chu kỳ.

**Liên quan bộ cũ:** Q03: ABC topic, but new insufficient-history rule

### H03.provisional — Dùng nhóm tạm

VI · 01_Inventory_Management_Policy_Manual.docx · parser 7 · [190, 203):

> dùng nhóm tạm

EN · 01_Inventory_Management_Policy_Manual_EN.docx · parser 8 · [213, 236):

> use provisional classes

### H03.review — Rà soát sau 3 chu kỳ

VI · 01_Inventory_Management_Policy_Manual.docx · parser 7 · [207, 227):

> rà soát sau 3 chu kỳ

EN · 01_Inventory_Management_Policy_Manual_EN.docx · parser 8 · [241, 266):

> review after three cycles

## H04 — narrative

Mục Hồ sơ bắt buộc và lưu trữ của Manual yêu cầu giữ những nhóm hồ sơ nào?

Which record groups must be retained under the Manual Required Records and Retention section?

**Đáp án đối chiếu (VI):** PR/PO và phê duyệt; hồ sơ nhận hàng; hồ sơ kiểm kê/điều chỉnh; hàng trả về và QA; KPI/exception/parameter changes/audit trail.

**Liên quan bộ cũ:** Q15: records topic; new complete retention inventory

### H04.purchase — Mua hàng

VI · 01_Inventory_Management_Policy_Manual.docx · parser 15 · [30, 65):

> Purchase request / PO và phê duyệt.

EN · 01_Inventory_Management_Policy_Manual_EN.docx · parser 16 · [35, 73):

> Purchase requests / POs and approvals.

### H04.receiving — Nhận hàng

VI · 01_Inventory_Management_Policy_Manual.docx · parser 15 · [66, 122):

> Biên bản nhận hàng, ảnh ngoại lệ, chứng từ nhà cung cấp.

EN · 01_Inventory_Management_Policy_Manual_EN.docx · parser 16 · [74, 134):

> Receiving reports, exception photos, and supplier documents.

### H04.count — Kiểm kê

VI · 01_Inventory_Management_Policy_Manual.docx · parser 15 · [123, 186):

> Phiếu kiểm kê, chênh lệch, nguyên nhân và phê duyệt điều chỉnh.

EN · 01_Inventory_Management_Policy_Manual_EN.docx · parser 16 · [135, 193):

> Count sheets, variances, causes, and adjustment approvals.

### H04.returns — Trả hàng

VI · 01_Inventory_Management_Policy_Manual.docx · parser 15 · [187, 232):

> Hồ sơ hàng trả về, kết quả QA và disposition.

EN · 01_Inventory_Management_Policy_Manual_EN.docx · parser 16 · [194, 238):

> Return records, QA results, and disposition.

### H04.kpi — Báo cáo và lịch sử

VI · 01_Inventory_Management_Policy_Manual.docx · parser 15 · [233, 293):

> Báo cáo KPI, exception log, thay đổi tham số và audit trail.

EN · 01_Inventory_Management_Policy_Manual_EN.docx · parser 16 · [239, 304):

> KPI reports, exception logs, parameter changes, and audit trails.

## H05 — narrative

Trong xử lý hàng chậm luân chuyển, ba nguyên nhân nào khiến giảm giá không được dùng làm biện pháp mặc định?

For slow-moving inventory, which three root causes mean discounting must not be the default response?

**Đáp án đối chiếu (VI):** Không mặc định giảm giá nếu nguyên nhân là sai dữ liệu, sai phân bổ size hoặc đơn hàng đang bị giữ.

**Liên quan bộ cũ:** Q07: slow-stock topic, new non-discounting causes

### H05.restriction — Không mặc định giảm giá

VI · 01_Inventory_Management_Policy_Manual.docx · parser 10 · [362, 404):

> Không dùng giảm giá làm biện pháp mặc định

EN · 01_Inventory_Management_Policy_Manual_EN.docx · parser 11 · [388, 417):

> Do not default to discounting

### H05.data — Sai dữ liệu

VI · 01_Inventory_Management_Policy_Manual.docx · parser 10 · [424, 435):

> sai dữ liệu

EN · 01_Inventory_Management_Policy_Manual_EN.docx · parser 11 · [441, 449):

> bad data

### H05.size — Sai phân bổ size

VI · 01_Inventory_Management_Policy_Manual.docx · parser 10 · [437, 453):

> sai phân bổ size

EN · 01_Inventory_Management_Policy_Manual_EN.docx · parser 11 · [451, 476):

> incorrect size allocation

### H05.held — Đơn bị giữ

VI · 01_Inventory_Management_Policy_Manual.docx · parser 10 · [459, 479):

> đơn hàng đang bị giữ

EN · 01_Inventory_Management_Policy_Manual_EN.docx · parser 11 · [481, 492):

> held orders

## H06 — table_numeric

Trong sheet Inventory Control của snapshot mẫu, Product ID 17 (DragonWear MA-17) có size, màu và On-hand Units là gì?

In the sample Inventory Control sheet, what are the size, color, and On-hand Units for Product ID 17 (DragonWear MA-17)?

**Đáp án đối chiếu (VI):** Size M, màu silver, 28 đơn vị tồn theo snapshot mẫu.

**Liên quan bộ cũ:** Không phải paraphrase trực tiếp của câu cũ đã liệt kê; vẫn cùng corpus.

### H06.size — Product 17: Size = M

VI · 04_Inventory_Control_and_Reorder_Planner.xlsx · parser 13 · [736, 743):

> Size: M

EN · 04_Inventory_Control_and_Reorder_Planner_EN.xlsx · parser 13 · [736, 743):

> Size: M

### H06.color — Product 17: Color = silver

VI · 04_Inventory_Control_and_Reorder_Planner.xlsx · parser 13 · [746, 759):

> Color: silver

EN · 04_Inventory_Control_and_Reorder_Planner_EN.xlsx · parser 13 · [746, 759):

> Color: silver

### H06.onhand — Product 17: On-hand Units = 28

VI · 04_Inventory_Control_and_Reorder_Planner.xlsx · parser 13 · [762, 779):

> On-hand Units: 28

EN · 04_Inventory_Control_and_Reorder_Planner_EN.xlsx · parser 13 · [762, 779):

> On-hand Units: 28

## H07 — table_numeric

Đọc dòng Product ID 18 (DragonWear MA-18) trong Inventory Control: Stockout Days và Fill Rate ghi bao nhiêu?

Read the Inventory Control row for Product ID 18 (DragonWear MA-18): what Stockout Days and Fill Rate values are recorded?

**Đáp án đối chiếu (VI):** Stockout Days = 2; Fill Rate = 0.9333 (93.33%); giá trị lịch sử, không phải hiện hành.

**Liên quan bộ cũ:** Không phải paraphrase trực tiếp của câu cũ đã liệt kê; vẫn cùng corpus.

### H07.days — Product 18: Stockout Days = 2

VI · 04_Inventory_Control_and_Reorder_Planner.xlsx · parser 14 · [862, 878):

> Stockout Days: 2

EN · 04_Inventory_Control_and_Reorder_Planner_EN.xlsx · parser 14 · [862, 878):

> Stockout Days: 2

### H07.fill — Product 18: Fill Rate = 0.9333

VI · 04_Inventory_Control_and_Reorder_Planner.xlsx · parser 14 · [881, 898):

> Fill Rate: 0.9333

EN · 04_Inventory_Control_and_Reorder_Planner_EN.xlsx · parser 14 · [881, 898):

> Fill Rate: 0.9333

## H08 — table_numeric

Trong Inventory Control, Product ID 19 có Units Sold (Latest) và Avg Monthly Demand (3 snapshots) bao nhiêu?

In Inventory Control, what Units Sold (Latest) and Avg Monthly Demand (3 snapshots) are recorded for Product ID 19?

**Đáp án đối chiếu (VI):** Units Sold Latest = 3; Avg Monthly Demand = 2.333333333333333 (xấp xỉ 2.3333).

**Liên quan bộ cũ:** Không phải paraphrase trực tiếp của câu cũ đã liệt kê; vẫn cùng corpus.

### H08.sold — Product 19: Units Sold (Latest) = 3

VI · 04_Inventory_Control_and_Reorder_Planner.xlsx · parser 15 · [782, 804):

> Units Sold (Latest): 3

EN · 04_Inventory_Control_and_Reorder_Planner_EN.xlsx · parser 15 · [782, 804):

> Units Sold (Latest): 3

### H08.average — Product 19: Avg Monthly Demand (3 snapshots) = 2.333333333333333

VI · 04_Inventory_Control_and_Reorder_Planner.xlsx · parser 15 · [807, 858):

> Avg Monthly Demand (3 snapshots): 2.333333333333333

EN · 04_Inventory_Control_and_Reorder_Planner_EN.xlsx · parser 15 · [807, 858):

> Avg Monthly Demand (3 snapshots): 2.333333333333333

## H09 — table_numeric

Theo KPI Summary của workbook, nhóm GenZ có bao nhiêu SKU, On-hand Units và Units Sold (Latest)?

According to the workbook KPI Summary, how many SKUs, On-hand Units, and Units Sold (Latest) are recorded for GenZ?

**Đáp án đối chiếu (VI):** 44 SKU; 5126 On-hand Units; 199 Units Sold Latest.

**Liên quan bộ cũ:** Không phải paraphrase trực tiếp của câu cũ đã liệt kê; vẫn cùng corpus.

### H09.skus — GenZ: SKU Count = 44

VI · 04_Inventory_Control_and_Reorder_Planner.xlsx · parser 433 · [256, 269):

> SKU Count: 44

EN · 04_Inventory_Control_and_Reorder_Planner_EN.xlsx · parser 433 · [256, 269):

> SKU Count: 44

### H09.onhand — GenZ: On-hand Units = 5126

VI · 04_Inventory_Control_and_Reorder_Planner.xlsx · parser 433 · [272, 291):

> On-hand Units: 5126

EN · 04_Inventory_Control_and_Reorder_Planner_EN.xlsx · parser 433 · [272, 291):

> On-hand Units: 5126

### H09.sold — GenZ: Units Sold (Latest) = 199

VI · 04_Inventory_Control_and_Reorder_Planner.xlsx · parser 433 · [294, 318):

> Units Sold (Latest): 199

EN · 04_Inventory_Control_and_Reorder_Planner_EN.xlsx · parser 433 · [294, 318):

> Units Sold (Latest): 199

## H10 — table_numeric

Theo bảng ngưỡng xử lý của SOP kiểm kê, nếu không có chênh lệch thì cần làm gì và ai là người duyệt?

According to the cycle-count SOP handling-threshold table, when there is no variance, what actions are required and who is the approver?

**Đáp án đối chiếu (VI):** Đóng phiếu; lưu audit trail; người duyệt: Warehouse Supervisor.

**Liên quan bộ cũ:** Q13: count-workflow topic; new explicit no-variance table row, not the recurring/high-value branch in F12.

### H10.close_ticket — Đóng phiếu

VI · 02_SOP_Cycle_Count_and_Stock_Adjustment.pdf · parser 3 · [130, 140):

> Đóng phiếu

VI · 02_SOP_Cycle_Count_and_Stock_Adjustment.pdf · parser 7 · [115, 125):

> Đóng phiếu

EN · 02_SOP_Cycle_Count_and_Stock_Adjustment_EN.pdf · parser 3 · [429, 445):

> Close the ticket

EN · 02_SOP_Cycle_Count_and_Stock_Adjustment_EN.pdf · parser 6 · [110, 126):

> Close the ticket

### H10.audit_trail — Lưu audit trail

VI · 02_SOP_Cycle_Count_and_Stock_Adjustment.pdf · parser 3 · [142, 157):

> lưu audit trail

VI · 02_SOP_Cycle_Count_and_Stock_Adjustment.pdf · parser 7 · [127, 142):

> lưu audit trail

EN · 02_SOP_Cycle_Count_and_Stock_Adjustment_EN.pdf · parser 3 · [447, 469):

> retain the audit trail

EN · 02_SOP_Cycle_Count_and_Stock_Adjustment_EN.pdf · parser 6 · [128, 150):

> retain the audit
trail

### H10.approver — Warehouse Supervisor duyệt

VI · 02_SOP_Cycle_Count_and_Stock_Adjustment.pdf · parser 3 · [158, 178):

> Warehouse Supervisor

VI · 02_SOP_Cycle_Count_and_Stock_Adjustment.pdf · parser 7 · [158, 178):

> Warehouse Supervisor

EN · 02_SOP_Cycle_Count_and_Stock_Adjustment_EN.pdf · parser 3 · [470, 490):

> Warehouse Supervisor

EN · 02_SOP_Cycle_Count_and_Stock_Adjustment_EN.pdf · parser 6 · [163, 183):

> Warehouse
Supervisor

## H11 — multi_chunk

So sánh hai dòng Inventory Control của Product ID 1 và Product ID 3: mỗi sản phẩm có size, màu và On-hand Units nào?

Compare the Inventory Control rows for Product ID 1 and Product ID 3: what size, color, and On-hand Units does each product have?

**Đáp án đối chiếu (VI):** ID1: M/black/3; ID3: XL/blue/151.

**Liên quan bộ cũ:** Không phải paraphrase trực tiếp của câu cũ đã liệt kê; vẫn cùng corpus.

### H11.p1_size — Product 1: Size = M

VI · 04_Inventory_Control_and_Reorder_Planner.xlsx · parser 9 · [735, 742):

> Size: M

EN · 04_Inventory_Control_and_Reorder_Planner_EN.xlsx · parser 9 · [735, 742):

> Size: M

### H11.p1_color — Product 1: Color = black

VI · 04_Inventory_Control_and_Reorder_Planner.xlsx · parser 9 · [745, 757):

> Color: black

EN · 04_Inventory_Control_and_Reorder_Planner_EN.xlsx · parser 9 · [745, 757):

> Color: black

### H11.p1_on-hand_units — Product 1: On-hand Units = 3

VI · 04_Inventory_Control_and_Reorder_Planner.xlsx · parser 9 · [760, 776):

> On-hand Units: 3

EN · 04_Inventory_Control_and_Reorder_Planner_EN.xlsx · parser 9 · [760, 776):

> On-hand Units: 3

### H11.p3_size — Product 3: Size = XL

VI · 04_Inventory_Control_and_Reorder_Planner.xlsx · parser 10 · [735, 743):

> Size: XL

EN · 04_Inventory_Control_and_Reorder_Planner_EN.xlsx · parser 10 · [735, 743):

> Size: XL

### H11.p3_color — Product 3: Color = blue

VI · 04_Inventory_Control_and_Reorder_Planner.xlsx · parser 10 · [746, 757):

> Color: blue

EN · 04_Inventory_Control_and_Reorder_Planner_EN.xlsx · parser 10 · [746, 757):

> Color: blue

### H11.p3_on-hand_units — Product 3: On-hand Units = 151

VI · 04_Inventory_Control_and_Reorder_Planner.xlsx · parser 10 · [760, 778):

> On-hand Units: 151

EN · 04_Inventory_Control_and_Reorder_Planner_EN.xlsx · parser 10 · [760, 778):

> On-hand Units: 151

## H12 — multi_chunk

Trong Exception Log, Product ID 2212 và 927 có Calculated DOS và Review Status lần lượt là gì?

In the Exception Log, what are the Calculated DOS and Review Status values for Product IDs 2212 and 927 respectively?

**Đáp án đối chiếu (VI):** 2212: DOS25440; 927: DOS6323.333333333334; cả hai có Review Status CONFLICT - VERIFY BEFORE PO.

**Liên quan bộ cũ:** Không phải paraphrase trực tiếp của câu cũ đã liệt kê; vẫn cùng corpus.

### H12.p2212_dos — Product 2212: Calculated DOS = 25440

VI · 04_Inventory_Control_and_Reorder_Planner.xlsx · parser 435 · [389, 410):

> Calculated DOS: 25440

EN · 04_Inventory_Control_and_Reorder_Planner_EN.xlsx · parser 435 · [389, 410):

> Calculated DOS: 25440

### H12.p2212_status — Product 2212: Review Status = CONFLICT - VERIFY BEFORE PO

VI · 04_Inventory_Control_and_Reorder_Planner.xlsx · parser 435 · [464, 506):

> Review Status: CONFLICT - VERIFY BEFORE PO

EN · 04_Inventory_Control_and_Reorder_Planner_EN.xlsx · parser 435 · [464, 506):

> Review Status: CONFLICT - VERIFY BEFORE PO

### H12.p927_dos — Product 927: Calculated DOS = 6323.333333333334

VI · 04_Inventory_Control_and_Reorder_Planner.xlsx · parser 436 · [393, 426):

> Calculated DOS: 6323.333333333334

EN · 04_Inventory_Control_and_Reorder_Planner_EN.xlsx · parser 436 · [393, 426):

> Calculated DOS: 6323.333333333334

### H12.p927_status — Product 927: Review Status = CONFLICT - VERIFY BEFORE PO

VI · 04_Inventory_Control_and_Reorder_Planner.xlsx · parser 436 · [480, 522):

> Review Status: CONFLICT - VERIFY BEFORE PO

EN · 04_Inventory_Control_and_Reorder_Planner_EN.xlsx · parser 436 · [480, 522):

> Review Status: CONFLICT - VERIFY BEFORE PO

## H13 — multi_chunk

Khi chuẩn bị PO trong ngân sách và đúng tham số đã duyệt, Planner chuyển cho ai duyệt? Hồ sơ nhà cung cấp phải duy trì những thông tin nào và cập nhật theo tần suất nào?

When preparing a PO within budget and approved parameters, whom does the Planner submit it to for approval? Which supplier information must be maintained, and how often must it be updated?

**Đáp án đối chiếu (VI):** Planner → Procurement Manager; duy trì lead time thực tế, MOQ, lịch giao, tỷ lệ giao đủ/đúng hạn; mỗi lần nhận/hằng tháng.

**Liên quan bộ cũ:** Q20: normal Planner-to-Procurement approval flow reused; supplier metrics and update-frequency requirements are new.

### H13.route — PO trong ngân sách

VI · 01_Inventory_Management_Policy_Manual.docx · parser 13 · [192, 221):

> Planner → Procurement Manager

EN · 01_Inventory_Management_Policy_Manual_EN.docx · parser 14 · [183, 212):

> Planner → Procurement Manager

### H13.supplier_metrics — Chỉ tiêu nhà cung cấp

VI · 03_Policy_Rules_Registry.csv · parser 8 · [310, 375):

> Duy trì lead time thực tế, MOQ, lịch giao, tỷ lệ giao đủ/đúng hạn

VI · 04_Inventory_Control_and_Reorder_Planner.xlsx · parser 7 · [256, 321):

> Duy trì lead time thực tế, MOQ, lịch giao, tỷ lệ giao đủ/đúng hạn

EN · 03_Policy_Rules_Registry_EN.csv · parser 8 · [309, 393):

> Maintain actual lead times, MOQ, delivery schedules, and fill/on-time delivery rates

EN · 04_Inventory_Control_and_Reorder_Planner_EN.xlsx · parser 7 · [242, 326):

> Maintain actual lead times, MOQ, delivery schedules, and fill/on-time delivery rates

### H13.frequency — Lịch cập nhật

VI · 03_Policy_Rules_Registry.csv · parser 8 · [444, 469):

> Mỗi lần nhận / hàng tháng

VI · 04_Inventory_Control_and_Reorder_Planner.xlsx · parser 7 · [388, 413):

> Mỗi lần nhận / hàng tháng

EN · 03_Policy_Rules_Registry_EN.csv · parser 8 · [462, 484):

> Each receipt / monthly

EN · 04_Inventory_Control_and_Reorder_Planner_EN.xlsx · parser 7 · [394, 416):

> Each receipt / monthly

## H14 — multi_chunk

Đối chiếu Product ID 8 và 9 trong Inventory Control: On-hand Units và Units Sold (Latest) của từng sản phẩm là bao nhiêu?

Compare Product IDs 8 and 9 in Inventory Control: what are the On-hand Units and Units Sold (Latest) for each product?

**Đáp án đối chiếu (VI):** ID8: On-hand101/Sold1; ID9: On-hand83/Sold6.

**Liên quan bộ cũ:** Không phải paraphrase trực tiếp của câu cũ đã liệt kê; vẫn cùng corpus.

### H14.p8_onhand — Product 8: On-hand Units = 101

VI · 04_Inventory_Control_and_Reorder_Planner.xlsx · parser 11 · [759, 777):

> On-hand Units: 101

EN · 04_Inventory_Control_and_Reorder_Planner_EN.xlsx · parser 11 · [759, 777):

> On-hand Units: 101

### H14.p8_sold — Product 8: Units Sold (Latest) = 1

VI · 04_Inventory_Control_and_Reorder_Planner.xlsx · parser 11 · [780, 802):

> Units Sold (Latest): 1

EN · 04_Inventory_Control_and_Reorder_Planner_EN.xlsx · parser 11 · [780, 802):

> Units Sold (Latest): 1

### H14.p9_onhand — Product 9: On-hand Units = 83

VI · 04_Inventory_Control_and_Reorder_Planner.xlsx · parser 12 · [761, 778):

> On-hand Units: 83

EN · 04_Inventory_Control_and_Reorder_Planner_EN.xlsx · parser 12 · [761, 778):

> On-hand Units: 83

### H14.p9_sold — Product 9: Units Sold (Latest) = 6

VI · 04_Inventory_Control_and_Reorder_Planner.xlsx · parser 12 · [781, 803):

> Units Sold (Latest): 6

EN · 04_Inventory_Control_and_Reorder_Planner_EN.xlsx · parser 12 · [781, 803):

> Units Sold (Latest): 6

## H15 — multi_chunk

Theo KPI Summary, Streetwear có bao nhiêu SKU và On-hand Units; đối chiếu với mô tả dữ liệu, toàn bộ products.csv có bao nhiêu SKU?

According to KPI Summary, how many SKUs and On-hand Units are listed for Streetwear, and how many SKUs are in the full products.csv master according to the data description?

**Đáp án đối chiếu (VI):** Streetwear196SKU/45085units; product master2412SKU. Không nhầm hai phạm vi.

**Liên quan bộ cũ:** Không phải paraphrase trực tiếp của câu cũ đã liệt kê; vẫn cùng corpus.

### H15.category_skus — Streetwear: SKU Count = 196

VI · 04_Inventory_Control_and_Reorder_Planner.xlsx · parser 433 · [516, 530):

> SKU Count: 196

EN · 04_Inventory_Control_and_Reorder_Planner_EN.xlsx · parser 433 · [516, 530):

> SKU Count: 196

### H15.category_onhand — Streetwear: On-hand Units = 45085

VI · 04_Inventory_Control_and_Reorder_Planner.xlsx · parser 433 · [533, 553):

> On-hand Units: 45085

EN · 04_Inventory_Control_and_Reorder_Planner_EN.xlsx · parser 433 · [533, 553):

> On-hand Units: 45085

### H15.master — Quy mô product master

VI · 01_Inventory_Management_Policy_Manual.docx · parser 3 · [39, 67):

> 2,412 SKU trong products.csv

VI · 04_Inventory_Control_and_Reorder_Planner.xlsx · parser 0 · [218, 246):

> 2,412 SKU trong products.csv

VI · 05_Inventory_Policy_Training_Deck.pptx · parser 1 · [82, 112):

> 2,412 SKU trong product master

EN · 01_Inventory_Management_Policy_Manual_EN.docx · parser 3 · [45, 71):

> 2,412 SKUs in products.csv

EN · 04_Inventory_Control_and_Reorder_Planner_EN.xlsx · parser 0 · [214, 223):

> 2,412 SKU

EN · 05_Inventory_Policy_Training_Deck_EN.pptx · parser 1 · [88, 116):

> 2,412 SKUs in product master

## H16 — paraphrase_terminology

Nếu gom nhật ký trả hàng, đơn bán, ưu đãi và vận chuyển thành một nguồn, có thể dùng nó thay sổ tồn chính thức không, hay chỉ phục vụ mục đích gì?

If returns, order, promotion, and delivery logs are combined, can they replace the authoritative inventory book, or what purpose may they serve instead?

**Đáp án đối chiếu (VI):** Chỉ hỗ trợ phân tích nguyên nhân; không thay thế inventory ledger.

**Liên quan bộ cũ:** Không phải paraphrase trực tiếp của câu cũ đã liệt kê; vẫn cùng corpus.

### H16.analysis — Phân tích nguyên nhân

VI · 01_Inventory_Management_Policy_Manual.docx · parser 3 · [362, 383):

> phân tích nguyên nhân

EN · 01_Inventory_Management_Policy_Manual_EN.docx · parser 3 · [377, 404):

> support root-cause analysis

### H16.ledger — Không thay sổ cái

VI · 01_Inventory_Management_Policy_Manual.docx · parser 3 · [390, 419):

> không thay thế sổ cái tồn kho

EN · 01_Inventory_Management_Policy_Manual_EN.docx · parser 3 · [409, 444):

> do not replace the inventory ledger

## H17 — paraphrase_terminology

Hàng đến có vẻ đủ số thùng rồi; để xác nhận giao đúng đơn, kho còn phải đối chiếu những thông tin nào theo Manual?

A delivery appears to contain the expected number of cartons; to confirm that the right order arrived, what details must the warehouse reconcile under the Manual?

**Đáp án đối chiếu (VI):** Đối chiếu PO, SKU, size, màu, số lượng, tình trạng bao bì, chứng từ giao hàng.

**Liên quan bộ cũ:** F01: receiving topic; new pre-receipt reconciliation fields

### H17.reconcile — Các trường đối chiếu nhận hàng

VI · 01_Inventory_Management_Policy_Manual.docx · parser 11 · [39, 119):

> Đối chiếu PO, SKU, size, màu, số lượng, tình trạng bao bì và chứng từ giao hàng.

EN · 01_Inventory_Management_Policy_Manual_EN.docx · parser 12 · [38, 124):

> Match the PO, SKU, size, color, quantity, packaging condition, and delivery documents.

## H18 — paraphrase_terminology

Doanh nghiệp không muốn bê nguyên các KPI mẫu vào vận hành. Theo tài liệu, ba yếu tố kinh doanh nào phải dùng để hiệu chỉnh các mục tiêu này?

The business does not want to copy the sample KPI targets unchanged into operations. Which three business factors should be used to calibrate those targets?

**Đáp án đối chiếu (VI):** Mức dịch vụ, margin và chiến lược tồn kho.

**Liên quan bộ cũ:** Q05: KPI topic; new calibration dimensions

### H18.service — Mức dịch vụ

VI · 01_Inventory_Management_Policy_Manual.docx · parser 9 · [111, 122):

> mức dịch vụ

VI · 05_Inventory_Policy_Training_Deck.pptx · parser 6 · [559, 570):

> mức dịch vụ

EN · 01_Inventory_Management_Policy_Manual_EN.docx · parser 10 · [131, 145):

> service levels

EN · 05_Inventory_Policy_Training_Deck_EN.pptx · parser 6 · [601, 615):

> service levels

### H18.margin — Margin

VI · 01_Inventory_Management_Policy_Manual.docx · parser 9 · [124, 130):

> margin

VI · 05_Inventory_Policy_Training_Deck.pptx · parser 6 · [549, 555):

> margin

EN · 01_Inventory_Management_Policy_Manual_EN.docx · parser 10 · [147, 154):

> margins

EN · 05_Inventory_Policy_Training_Deck_EN.pptx · parser 6 · [590, 596):

> margin

### H18.strategy — Chiến lược tồn kho

VI · 01_Inventory_Management_Policy_Manual.docx · parser 9 · [134, 152):

> chiến lược tồn kho

EN · 01_Inventory_Management_Policy_Manual_EN.docx · parser 10 · [160, 178):

> inventory strategy

## H19 — paraphrase_terminology

Khách trả hàng vì sai cỡ hoặc giao chậm. Theo tài liệu, có cần gắn mã lý do trả hàng không, và thông tin này phải phản hồi tới những bộ phận nào?

A customer returns an item because it did not fit or arrived late. Under the policy, must a return-reason code be assigned, and which departments should receive that feedback?

**Đáp án đối chiếu (VI):** Gắn return-reason code; phản hồi Merchandising, QA, Logistics.

**Liên quan bộ cũ:** Q04/Q16: returns topic; new reason-coding feedback destinations

### H19.reason_code — Mã lý do trả hàng

VI · 01_Inventory_Management_Policy_Manual.docx · parser 11 · [481, 508):

> Gắn mã nguyên nhân trả hàng

EN · 01_Inventory_Management_Policy_Manual_EN.docx · parser 12 · [534, 560):

> Assign return-reason codes

### H19.destinations — Các bộ phận nhận phản hồi

VI · 01_Inventory_Management_Policy_Manual.docx · parser 11 · [566, 596):

> Merchandising, QA và Logistics

EN · 01_Inventory_Management_Policy_Manual_EN.docx · parser 12 · [621, 653):

> Merchandising, QA, and Logistics

## H20 — paraphrase_terminology

Trong bảng vai trò của Manual, ai chịu trách nhiệm tổ chức phân quyền, giải nghĩa các trường dữ liệu, quản lý nhật ký và kiểm soát AI?

In the Manual roles table, who is responsible for access permissions, the meaning of data fields, logging, and AI controls?

**Đáp án đối chiếu (VI):** System / Data Owner.

**Liên quan bộ cũ:** Q02/Q14: roles topic; new data-governance owner

### H20.owner — Chủ sở hữu hệ thống/dữ liệu

VI · 01_Inventory_Management_Policy_Manual.docx · parser 4 · [841, 860):

> System / Data Owner

EN · 01_Inventory_Management_Policy_Manual_EN.docx · parser 5 · [91, 110):

> System / Data Owner

