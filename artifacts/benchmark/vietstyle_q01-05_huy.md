# VietStyle Q01?Q05 Benchmark

Embedding model: `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`

Indexed VietStyle pack source files only. Q01 README.txt is absent from the indexed corpus.
Source-level recall only; CSV supplies expected filenames, not gold chunk IDs.

| ID | Dense recall@10 | Huy hybrid | Translated hybrid | First expected rank |
|---|---:|---:|---:|---:|
| Q01 | 0.67 | 0.67 | 0.67 | 1 |
| Q02 | 1.00 | 1.00 | 1.00 | 1 |
| Q03 | 1.00 | 1.00 | 1.00 | 1 |
| Q04 | 1.00 | 1.00 | 1.00 | 1 |
| Q05 | 0.50 | 1.00 | 0.50 | 1 |

Mean source recall@10: dense 0.83; hybrid 0.93; translated 0.83.

## Q01 ? Bộ chính sách VietStyle Commerce hiện ở phiên bản nào, ngày nào, và trạng thái phê duyệt ra sao?

Reference: Phiên bản v1.0, ngày 16/10/2026; trạng thái SIMULATION_DRAFT/tài liệu mô phỏng, cần chủ sở hữu nghiệp vụ phê duyệt trước khi áp dụng thực tế.

English translation: What version of the VietStyle Commerce policy is currently in place, on what date, and what is its approval status?

Generated answer:

Bộ chính sách của VietStyle Commerce hiện đang ở **phiên bản v1.0**, được cập nhật vào **ngày 16/10/2026** và đang ở trạng thái **SIMULATION_DRAFT** – tức là chưa được phê duyệt chính thức.  
[S1] [S2] [S3] [S6]

Translated-hybrid top sources:

1. `03_Policy_Rules_Registry.csv` chunk 5, page None
2. `03_Policy_Rules_Registry.csv` chunk 10, page None
3. `03_Policy_Rules_Registry.csv` chunk 3, page None
4. `02_SOP_Cycle_Count_and_Stock_Adjustment.pdf` chunk 7, page 3
5. `05_Inventory_Policy_Training_Deck.pptx` chunk 0, page 1
6. `03_Policy_Rules_Registry.csv` chunk 0, page None
7. `02_SOP_Cycle_Count_and_Stock_Adjustment.pdf` chunk 0, page 1
8. `01_Inventory_Management_Policy_Manual.docx` chunk 0, page None
9. `03_Policy_Rules_Registry.csv` chunk 9, page None
10. `02_SOP_Cycle_Count_and_Stock_Adjustment.pdf` chunk 2, page 2

## Q02 ? Ai chịu trách nhiệm chính về KPI, ngưỡng tồn kho, ngoại lệ và phê duyệt chính sách?

Reference: Inventory Manager.

English translation: Who is primarily responsible for KPI, inventory threshold, exceptions, and policy approvals?

Generated answer:

Chịu trách nhiệm chính về KPI, ngưỡng tồn kho, ngoại lệ và phê duyệt chính sách thuộc vai trò **Inventory Manager**. [S1]

Translated-hybrid top sources:

1. `01_Inventory_Management_Policy_Manual.docx` chunk 15, page None
2. `01_Inventory_Management_Policy_Manual.docx` chunk 41, page None
3. `03_Policy_Rules_Registry.csv` chunk 10, page None
4. `01_Inventory_Management_Policy_Manual.docx` chunk 38, page None
5. `03_Policy_Rules_Registry.csv` chunk 0, page None
6. `05_Inventory_Policy_Training_Deck.pptx` chunk 6, page 7
7. `04_Inventory_Control_and_Reorder_Planner.xlsx` chunk 714, page 4
8. `05_Inventory_Policy_Training_Deck.pptx` chunk 0, page 1
9. `03_Policy_Rules_Registry.csv` chunk 1, page None
10. `03_Policy_Rules_Registry.csv` chunk 4, page None

## Q03 ? Tần suất kiểm kê chu kỳ cho nhóm ABC là bao nhiêu và ABC được phân loại dựa trên tiêu chí nào?

Reference: Nhóm A: hằng tuần, xấp xỉ 80% giá trị tiêu thụ năm; nhóm B: hằng tháng, khoảng 15% tiếp theo; nhóm C: hằng quý, phần còn lại khoảng 5%. Phân loại dựa trên annual consumption value (nhu cầu năm × cost), không chỉ số lượng bán.

English translation: What is the cycle inventory frequency for group ABC, and on what criteria is ABC classified?

Generated answer:

Tần suất kiểm kê chu kỳ cho từng nhóm ABC như sau:  
- Nhóm **A**: **hằng tuần**  
- Nhóm **B**: **hằng tháng**  
- Nhóm **C**: **hằng quý**  
- Ngoài ra, còn thực hiện **kiểm kê mù** và **đối chiếu độc lập** theo lịch đã định.  
[S2]

ABC được phân loại dựa trên **giá trị tiêu thụ hàng năm** (annual consumption value = nhu cầu năm × cost), không chỉ dựa vào số lượng bán. Khi chưa có lịch sử nhu cầu đủ tin cậy, dùng nhóm tạm và rà soát lại sau 3 chu kỳ.  
[S3]

Ngoài ra, trong tài liệu đào tạo còn nêu rằng:  
- Nhóm **A** chiếm khoảng **80%** giá trị tiêu thụ,  
- Nhóm **B** khoảng **15%**,  
- Nhóm **C** khoảng **5%**.  
[S4]

Translated-hybrid top sources:

1. `01_Inventory_Management_Policy_Manual.docx` chunk 33, page None
2. `03_Policy_Rules_Registry.csv` chunk 3, page None
3. `01_Inventory_Management_Policy_Manual.docx` chunk 37, page None
4. `05_Inventory_Policy_Training_Deck.pptx` chunk 4, page 5
5. `03_Policy_Rules_Registry.csv` chunk 11, page None
6. `03_Policy_Rules_Registry.csv` chunk 10, page None
7. `01_Inventory_Management_Policy_Manual.docx` chunk 41, page None
8. `05_Inventory_Policy_Training_Deck.pptx` chunk 2, page 3
9. `03_Policy_Rules_Registry.csv` chunk 5, page None
10. `01_Inventory_Management_Policy_Manual.docx` chunk 48, page None

## Q04 ? Khi hàng trả về từ khách, hàng phải qua trạng thái nào trước khi được cộng vào tồn kho khả dụng?

Reference: Phải vào QUARANTINE để Returns QA kiểm tra và phân loại; chỉ được đưa vào available-to-promise sau khi QA xác nhận tình trạng và disposition.

English translation: When goods are returned from a customer, through which status must the goods pass before being added to available inventory?

Generated answer:

Hàng trả về từ khách phải vào trạng thái **QUARANTINE** cho đến khi được kiểm tra bởi QA; chỉ khi đạt điều kiện mới được cộng vào tồn kho khả dụng. [S1]

Translated-hybrid top sources:

1. `01_Inventory_Management_Policy_Manual.docx` chunk 53, page None
2. `01_Inventory_Management_Policy_Manual.docx` chunk 24, page None
3. `03_Policy_Rules_Registry.csv` chunk 10, page None
4. `05_Inventory_Policy_Training_Deck.pptx` chunk 6, page 7
5. `01_Inventory_Management_Policy_Manual.docx` chunk 48, page None
6. `05_Inventory_Policy_Training_Deck.pptx` chunk 3, page 4
7. `01_Inventory_Management_Policy_Manual.docx` chunk 60, page None
8. `01_Inventory_Management_Policy_Manual.docx` chunk 15, page None
9. `03_Policy_Rules_Registry.csv` chunk 2, page None
10. `01_Inventory_Management_Policy_Manual.docx` chunk 65, page None

## Q05 ? Những KPI tồn kho nào cần theo dõi định kỳ theo bộ chính sách?

Reference: Fill rate, stockout rate, inventory record accuracy, days of supply, aged/slow-moving stock và PO adherence.

English translation: Which inventory KPIs need to be monitored periodically according to the policy set?

Generated answer:

Những KPI tồn kho cần được theo dõi định kỳ theo bộ chính sách là:

- **Fill rate** – tỷ lệ hoàn thành đơn hàng từ kho.  
- **Stockout rate** – tỷ lệ thiếu hàng.  
- **Inventory accuracy** – độ chính xác của dữ liệu tồn kho.  
- **Days of supply** – số ngày tồn kho còn lại dựa trên nhu cầu hiện tại.  
- **Aged stock** – tồn kho đã tồn tại quá lâu.  
- **PO adherence** – mức độ tuân thủ đơn đặt hàng (PO) với kế hoạch.  

Những KPI này được liệt kê trong chính sách “KPI và cảnh báo” (policy_id: INV‑POL‑011) với trigger “Báo cáo vận hành định kỳ” và được theo dõi theo tần suất hằng tuần/tháng. [S1]

Translated-hybrid top sources:

1. `03_Policy_Rules_Registry.csv` chunk 10, page None
2. `03_Policy_Rules_Registry.csv` chunk 0, page None
3. `03_Policy_Rules_Registry.csv` chunk 1, page None
4. `04_Inventory_Control_and_Reorder_Planner.xlsx` chunk 714, page 4
5. `03_Policy_Rules_Registry.csv` chunk 3, page None
6. `03_Policy_Rules_Registry.csv` chunk 4, page None
7. `03_Policy_Rules_Registry.csv` chunk 11, page None
8. `05_Inventory_Policy_Training_Deck.pptx` chunk 0, page 1
9. `03_Policy_Rules_Registry.csv` chunk 2, page None
10. `03_Policy_Rules_Registry.csv` chunk 8, page None
