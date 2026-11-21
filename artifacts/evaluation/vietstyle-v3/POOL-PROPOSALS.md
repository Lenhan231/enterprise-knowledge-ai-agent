# Pooled gold proposals (judge: Groq gpt-oss-120b)

Approve or reject each proposed passage. Nothing is added to dev/test until approved.

## D001 (dev, lookup, expected answer)
**Q:** Nhân viên làm đủ một năm được bao nhiêu ngày nghỉ phép năm có lương?  
**Expected:** VietStyle cấp 12 ngày làm việc nghỉ phép năm có lương cho một năm làm việc đầy đủ, tính theo tỷ lệ nếu chưa đủ năm; quyền lợi theo luật hoặc hợp đồng có lợi hơn được ưu tiên.
- [ ] **grade 2** VN#84 — States 12 days annual paid leave per full year  
  _Quy trình bắt buộc Phép năm tích lũy bằng một phần mười hai quyền phép năm áp dụng cho mỗi tháng làm việc hoàn tất, trừ khi quy định hợp pháp yêu cầu cách tính có lợi hơn._

## D003 (dev, lookup, expected answer)
**Q:** Nếu phải mua khẩn mà không kịp xin duyệt trước, chậm nhất khi nào phải báo cho Tài chính?  
**Expected:** Báo lãnh đạo được chỉ định và Tài chính sớm nhất có thể, không muộn hơn một ngày làm việc sau khi cam kết.
- [ ] **grade 2** EN#349 — states notification deadline to Finance  
  _Required procedure  If prior approval is genuinely impossible, notify the designated executive and Finance as soon as practicable and no later than one business day after commitment._

## D004 (dev, lookup, expected answer)
**Q:** Quyền truy cập vào hệ thống nhạy cảm phải được rà soát định kỳ bao lâu một lần?  
**Expected:** Rà quyền khi đổi vai trò và ít nhất mỗi quý đối với hệ thống nhạy cảm.
- [ ] **grade 1** VN#537 ⚠️ belongs to test topics (fact appears in both sets) — mentions periodic access review but no frequency  
  _Nhân viên mới, chuyển vai trò, nghỉ việc và rà quyền định kỳ Quyền phải theo thay đổi việc làm và vai trò để người cũ hoặc chuyển việc không giữ quyền thừa._
- [ ] **grade 2** EN#565 — states review at role change and quarterly  
  _Required procedure  Review access at role change and at least quarterly for sensitive systems._

## D006 (dev, amount, expected answer)
**Q:** Mua máy lọc nước 4tr5 thì ai duyệt?  
**Expected:** 4.500.000 VND thuộc mức đến 5.000.000 VND nên do quản lý trực tiếp phê duyệt; cần một báo giá có hồ sơ và ngân sách xác nhận.
- [ ] **grade 2** EN#781 — Specifies line manager approval up to 5M with one quote  
  _Appendix B - Approval limits and operational decision table Columns: Total commitment | Required approval | Additional condition Row 1: Total commitment: Up to VND 5,000,000 | Required approval: Line manager | Additional condition: One documented quote; budget confirmed. Row 2: Total commitment: VND_
- [ ] **grade 1** EN#272 — Allows one quote up to 5M but no approver  
  _Competitive sourcing and quote evaluation Mandatory rule. For estimated commitments up to VND 5,000,000, one documented quote may be used. From VND 5,000,001 to VND 50,000,000, seek at least two comparable quotes where the market permits. Above VND 50,000,000, seek at least three written quotes or a_
- [ ] **grade 1** VN#261 — One quote allowed up to 5M, no approver  
  _Tìm nguồn cạnh tranh và đánh giá báo giá Quy tắc bắt buộc. Cam kết dự toán đến 5.000.000 VND có thể dùng một báo giá được lập hồ sơ. Từ 5.000.001 đến 50.000.000 VND cần tìm ít nhất hai báo giá tương đương nếu thị trường cho phép. Trên 50.000.000 VND cần ít nhất ba báo giá bằng văn bản hoặc giải trìn_

## D007 (dev, amount, expected answer)
**Q:** Đặt in áo cho team 12 củ thì cần mấy báo giá?  
**Expected:** 12.000.000 VND nằm trong khoảng 5.000.001–50.000.000 VND nên cần ít nhất hai báo giá tương đương nếu thị trường cho phép.
- [ ] **grade 2** EN#286 — Specifies quote requirement for 5M-50M range  
  _Approval matrix and monetary thresholds Mandatory rule. The default delegated authority for a single commitment is: up to VND 5,000,000-line manager; VND 5,000,001-50,000,000-department head; VND 50,000,001-200,000,000-department head plus Procurement and Finance; above VND 200,000,000-Executive Ope_
- [ ] **grade 2** EN#781 — States at least two quotes for 5M-50M  
  _Appendix B - Approval limits and operational decision table Columns: Total commitment | Required approval | Additional condition Row 1: Total commitment: Up to VND 5,000,000 | Required approval: Line manager | Additional condition: One documented quote; budget confirmed. Row 2: Total commitment: VND_

## D008 (dev, amount, expected answer)
**Q:** Mua văn phòng phẩm 500k có cần ai duyệt không?  
**Expected:** 500.000 VND thuộc mức đến 5.000.000 VND: quản lý trực tiếp phê duyệt, kèm một báo giá có hồ sơ và ngân sách xác nhận.
- [ ] **grade 1** VN#261 — States one quote needed up to 5M  
  _Tìm nguồn cạnh tranh và đánh giá báo giá Quy tắc bắt buộc. Cam kết dự toán đến 5.000.000 VND có thể dùng một báo giá được lập hồ sơ. Từ 5.000.001 đến 50.000.000 VND cần tìm ít nhất hai báo giá tương đương nếu thị trường cho phép. Trên 50.000.000 VND cần ít nhất ba báo giá bằng văn bản hoặc giải trìn_
- [ ] **grade 1** EN#272 — States one quote needed up to 5M  
  _Competitive sourcing and quote evaluation Mandatory rule. For estimated commitments up to VND 5,000,000, one documented quote may be used. From VND 5,000,001 to VND 50,000,000, seek at least two comparable quotes where the market permits. Above VND 50,000,000, seek at least three written quotes or a_
- [ ] **grade 2** EN#781 — Specifies line‑manager approval and quote condition  
  _Appendix B - Approval limits and operational decision table Columns: Total commitment | Required approval | Additional condition Row 1: Total commitment: Up to VND 5,000,000 | Required approval: Line manager | Additional condition: One documented quote; budget confirmed. Row 2: Total commitment: VND_

## D009 (dev, amount, expected answer)
**Q:** Hợp đồng dịch vụ đúng 50.000.000 VND thì cấp nào phê duyệt?  
**Expected:** 50.000.000 VND vẫn thuộc khoảng 5.000.001–50.000.000 VND nên trưởng bộ phận phê duyệt (chưa cần Mua sắm và Tài chính).
- [ ] **grade 2** EN#781 — Specifies department head approval for 5,000,001‑50,000,000 VND  
  _Appendix B - Approval limits and operational decision table Columns: Total commitment | Required approval | Additional condition Row 1: Total commitment: Up to VND 5,000,000 | Required approval: Line manager | Additional condition: One documented quote; budget confirmed. Row 2: Total commitment: VND_

## D010 (dev, amount, expected answer)
**Q:** Mua thiết bị 5 triệu thì quản lý trực tiếp tự duyệt được không?  
**Expected:** Được: cam kết đến 5.000.000 VND (bao gồm đúng 5.000.000 VND) thuộc thẩm quyền quản lý trực tiếp.
- [ ] **grade 2** EN#781 — Line manager approval up to VND 5M  
  _Appendix B - Approval limits and operational decision table Columns: Total commitment | Required approval | Additional condition Row 1: Total commitment: Up to VND 5,000,000 | Required approval: Line manager | Additional condition: One documented quote; budget confirmed. Row 2: Total commitment: VND_

## D011 (dev, calculation, expected answer)
**Q:** Nếu mua 3 lần, mỗi lần 2 triệu cho cùng một nhu cầu thì ai duyệt?  
**Expected:** Duyệt theo tổng cam kết và không được chia nhỏ để tránh ngưỡng: 3 × 2.000.000 = 6.000.000 VND, thuộc 5.000.001–50.000.000 VND nên trưởng bộ phận phê duyệt.
- [ ] **grade 2** EN#781 — Specifies 5,000,001‑50,000,000 requires department head  
  _Appendix B - Approval limits and operational decision table Columns: Total commitment | Required approval | Additional condition Row 1: Total commitment: Up to VND 5,000,000 | Required approval: Line manager | Additional condition: One documented quote; budget confirmed. Row 2: Total commitment: VND_

## D012 (dev, calculation, expected answer)
**Q:** Tôi đã làm đủ 7 tháng thì đã tích lũy được bao nhiêu ngày phép năm?  
**Expected:** Phép năm tích lũy 1/12 quyền phép năm cho mỗi tháng làm việc hoàn tất; với 12 ngày/năm, 7 tháng tích lũy 7 ngày.
- [ ] **grade 1** EN#81 — States 1/12 accrual per month  
  _Required procedure  Annual leave accrues at one-twelfth of the applicable annual entitlement for each completed service month unless a lawful rule requires a more favorable method._

## D014 (dev, calculation, expected answer)
**Q:** Mua 2 laptop, mỗi cái 20 củ thì cần mấy báo giá và ai duyệt?  
**Expected:** Tổng cam kết 2 × 20.000.000 = 40.000.000 VND, thuộc 5.000.001–50.000.000 VND: cần ít nhất hai báo giá tương đương và trưởng bộ phận phê duyệt.
- [ ] **grade 2** EN#781 — Specifies two quotes and dept head approval for 5M-50M  
  _Appendix B - Approval limits and operational decision table Columns: Total commitment | Required approval | Additional condition Row 1: Total commitment: Up to VND 5,000,000 | Required approval: Line manager | Additional condition: One documented quote; budget confirmed. Row 2: Total commitment: VND_

## D015 (dev, calculation, expected answer)
**Q:** Mua khẩn được cam kết vào thứ Hai mà chưa kịp xin duyệt. Hạn báo Tài chính và hạn hoàn tất rà soát sau mua là khi nào?  
**Expected:** Phải báo lãnh đạo chỉ định và Tài chính không muộn hơn một ngày làm việc sau cam kết (thứ Ba), và hoàn tất rà soát nguồn cung, bằng chứng, phê duyệt trong năm ngày làm việc (đến thứ Hai tuần sau).
- [ ] **grade 1** EN#349 — states finance notification within one business day  
  _Required procedure  If prior approval is genuinely impossible, notify the designated executive and Finance as soon as practicable and no later than one business day after commitment._

## D016 (dev, multi_part, expected answer)
**Q:** Nghỉ phép năm được bao nhiêu ngày và ai là người có quyền duyệt đơn nghỉ?  
**Expected:** 12 ngày làm việc có lương cho một năm làm việc đầy đủ; quyết định nghỉ do quản lý hoặc người được Nhân sự ủy quyền hợp lệ thực hiện.
- [ ] **grade 1** VN#111 — mentions approver checks leave rights  
  _Quy trình bắt buộc Người duyệt kiểm tra quyền nghỉ, nhân sự thay thế, thời gian trùng và yêu cầu bảo vệ quyền nghỉ._
- [ ] **grade 1** VN#115 — states requester cannot self‑approve  
  _Yêu cầu kiểm soát Người đề nghị không được tự duyệt yêu cầu.  Từ chối phải nêu lý do liên quan công việc và không vi phạm quyền nghỉ được bảo vệ._
- [ ] **grade 1** VN#84 — gives 1/12 accrual = 12 days yearly  
  _Quy trình bắt buộc Phép năm tích lũy bằng một phần mười hai quyền phép năm áp dụng cho mỗi tháng làm việc hoàn tất, trừ khi quy định hợp pháp yêu cầu cách tính có lợi hơn._
- [ ] **grade 1** EN#81 — states annual accrual 1/12 per month  
  _Required procedure  Annual leave accrues at one-twelfth of the applicable annual entitlement for each completed service month unless a lawful rule requires a more favorable method._

## D017 (dev, multi_part, expected answer)
**Q:** Đề nghị hoàn chi phí cần những thông tin chứng từ gì, và nếu mất hóa đơn thì xử lý sao?  
**Expected:** Cần đơn vị bán, ngày, loại chi, số tiền, tiền tệ, mục đích và hóa đơn/biên nhận; nếu mất chứng từ phải giải trình và được Tài chính duyệt trước khi hoàn trả.
- [ ] **grade 1** VN#164 — Lists required fields but omits invoice loss handling  
  _Điều kiện hoàn trả chi phí và chứng từ Đề nghị hoàn chi phí công việc phải xác định mục đích hợp lệ, số tiền thực, ngày, tiền tệ và bằng chứng._
- [ ] **grade 1** VN#172 — Provides required fields, lacks lost invoice process  
  _Bằng chứng bắt buộc Mã đề nghị, mã chứng từ, mục đích, số tiền, tiền tệ, trung tâm chi phí và ngày nộp._
- [ ] **grade 1** VN#687 ⚠️ belongs to test topics (fact appears in both sets) — Details required info, no lost invoice guidance  
  _Quy trình bắt buộc Chi phí: người đề nghị, ngày giao dịch, loại, số tiền, tiền tệ, mục đích, mã chứng từ, trung tâm chi phí, quyết định và mã thanh toán._
- [ ] **grade 1** VN#737 ⚠️ belongs to test topics (fact appears in both sets) — Specifies minimal fields, missing loss procedure  
  _Phụ lục C - Biểu mẫu chuẩn và kiểm tra tối thiểu Columns: Biểu mẫu | Trường tối thiểu | Kiểm tra / điều kiện chặn Row 1: Biểu mẫu: Yêu cầu nghỉ phép | Trường tối thiểu: Mã nhân viên; loại nghỉ; ngày đầu/cuối; cả/một phần ngày; bàn giao; thời điểm nộp. | Kiểm tra / điều kiện chặn: Ngày cuối >= ngày đ_

## D018 (dev, multi_part, expected answer)
**Q:** Tiếp nhận nhà cung cấp mới cần thu thập thông tin gì, và khi nhà cung cấp đổi tài khoản ngân hàng thì làm sao?  
**Expected:** Thu tên pháp nhân, đăng ký/thuế, địa chỉ kinh doanh, liên hệ và đại diện có thẩm quyền; thay đổi ngân hàng phải xác minh qua kênh liên hệ lấy độc lập (gọi lại xác minh).
- [ ] **grade 1** VN#247 — Lists identity, legal, payment checks  
  _Thẩm định và tiếp nhận nhà cung cấp Quy tắc bắt buộc. Chỉ dùng nhà cung cấp sau khi hoàn tất kiểm tra danh tính, chỉ dẫn thanh toán, tư cách pháp lý và rủi ro phù hợp giao dịch._
- [ ] **grade 2** VN#321 ⚠️ belongs to test topics (fact appears in both sets) — Specifies independent verification for bank changes  
  _Yêu cầu kiểm soát Không thanh toán hàng bị từ chối hoặc chưa nhận, trừ điều khoản hợp đồng đã duyệt cho phép ứng trước.  Thay đổi ngân hàng cần xác minh độc lập._
- [ ] **grade 2** EN#338 ⚠️ belongs to test topics (fact appears in both sets) — Requires independent verification of bank detail changes  
  _Control requirements  Bank detail changes require independent verification._
- [ ] **grade 2** EN#258 — Mandates independent channel verification for bank changes  
  _Required procedure  Verify bank-detail changes through an independently sourced contact channel._

## D019 (dev, multi_part, expected answer)
**Q:** Khóa bí mật và thông tin đăng nhập phải lưu ở đâu, và khi nào phải thay khóa?  
**Expected:** Lưu trong kho bí mật được duyệt hoặc cấu hình môi trường được bảo vệ với quyền tối thiểu; thay khóa sau thay nhân sự, lộ vô ý hoặc nghi xâm phạm.
- [ ] **grade 1** VN#556 — states storing credentials on server  
  _Quy trình bắt buộc Giữ service-role và thông tin cơ sở dữ liệu ở máy chủ._
- [ ] **grade 1** VN#561 — mentions change date for secrets  
  _Bằng chứng bắt buộc Chủ bí mật, mục đích, phạm vi, ngày thay, mã sự cố và kết quả xác minh._
- [ ] **grade 1** VN#529 — prohibits exposing keys, implies secure storage  
  _Yêu cầu kiểm soát Không dùng chung tài khoản cá nhân.  Không lộ service-role hoặc khóa bí mật trong mã phía khách, notebook, ảnh chụp hay prompt._
- [ ] **grade 1** VN#545 ⚠️ belongs to test topics (fact appears in both sets) — requires key rotation plan and expiry  
  _Yêu cầu kiểm soát Danh tính dịch vụ phải có chủ, mục đích, kế hoạch thay khóa và ngày hết hạn/rà soát._
- [ ] **grade 1** VN#560 — describes controlled key revocation and rotation  
  _Yêu cầu kiểm soát Không commit tệp môi trường cục bộ.  Xác minh thu hồi và thay khóa bằng phép kiểm có kiểm soát._
- [ ] **grade 1** VN#209 — stores files in access‑controlled repository  
  _Quy trình bắt buộc Lưu tệp ở kho kiểm soát truy cập và tham chiếu bằng mã._

## D020 (dev, multi_part, expected answer)
**Q:** Khi nhận hàng cần ghi những số lượng nào, và hàng chưa rõ chất lượng thì để ở đâu?  
**Expected:** Ghi riêng lượng giao thực, lượng chấp nhận và lượng từ chối; chỉ lượng chấp nhận được xếp kho. Hàng chưa rõ hoặc không đạt đưa vào khu giữ chất lượng có nhãn rõ.
- [ ] **grade 1** 01_#11 — records missing/extra quantities before receipt  
  _8. Nhận hàng, trả hàng và hàng cách ly Đối chiếu PO, SKU, size, màu, số lượng, tình trạng bao bì và chứng từ giao hàng. Ghi nhận thiếu / thừa / hư hỏng trước khi xác nhận nhận hàng; ảnh chụp và biên bản bắt buộc cho ngoại lệ. Hàng trả về phải vào trạng thái QUARANTINE cho đến khi QA kiểm tra; không _
- [ ] **grade 1** VN#467 — requires quantity verification at receipt  
  _Nhận hàng, kiểm số lượng và giữ kiểm định Nhận hàng phải xác nhận hàng giao khớp đơn được phép, đạt số lượng và tình trạng._
- [ ] **grade 1** EN#503 — states quality‑hold location  
  _Required procedure  Place uncertain or nonconforming goods in a clearly identified quality-hold area._
- [ ] **grade 1** EN#498 — requires quantity verification at receipt  
  _Receiving, quantity verification and quality hold Goods receipt must confirm that delivered goods correspond to an authorized order and meet quantity and condition requirements._

## D021 (dev, multi_passage, expected answer)
**Q:** Người kiểm kê có được tự duyệt chênh lệch lớn mà chính mình phát hiện không, và sai lệch trọng yếu khi kiểm kê thì xử lý thế nào?  
**Expected:** Không: người nhận hàng hoặc kiểm kê không được độc lập duyệt chênh lệch trọng yếu do mình phát hiện; sai lệch trọng yếu phải được người độc lập đếm lại và so với hệ thống tồn trực tiếp, ghi nguyên nhân trước khi điều chỉnh.
- [ ] **grade 1** 02_#2 ⚠️ belongs to test topics (fact appears in both sets) — Recount required before adjusting discrepancy  
  _5. Ngưỡng xử lý và phê duyệt • Đóng băng giao dịch tại vị trí cần đếm hoặc ghi lại mọi giao dịch phát sinh trong cửa sổ đếm. • Chuẩn bị thiết bị quét, nhãn cách ly, biểu mẫu ghi nhận, camera và phương án xử lý hàng đang pick / pack / chuyển kho. 4. Thực hiện đếm và đối chiếu • Đếm theo SKU + size + _
- [ ] **grade 1** 02_#3 ⚠️ belongs to test topics (fact appears in both sets) — Large discrepancy needs higher‑level approval  
  _7. Cập nhật hệ thống và đóng phiếu Ngưỡng xử lý và phê duyệt Tình huống Hành động tối thiểu Người duyệt Không chênh lệch Đóng phiếu; lưu audit trail Warehouse Supervisor Chênh lệch nhỏ, có nguyên nhân rõ và bằng chứng Recount + biên bản; cập nhật sau duyệt Inventory Controller / Supervisor Chênh lệc_
- [ ] **grade 1** 04_#5 — Major variance needs Finance/Operations approval  
  _Policy Matrix Columns: Policy ID | Chính sách | Trigger | Hành động bắt buộc | Owner | SLA / Tần suất | Approval Row 5: Policy ID: INV-POL-005 | Chính sách: Điều chỉnh tồn kho | Trigger: Có chênh lệch giữa đếm thực tế và hệ thống | Hành động bắt buộc: Không điều chỉnh khi chưa có biên bản, mã nguyên_
- [ ] **grade 1** 03_#4 — Policy forbids adjustment without separate approver  
  _Columns: policy_id | policy_name | trigger | rule_or_required_action | owner | sla_or_frequency | approval | company | document_version | effective_status | source_basis Row 5: policy_id: INV-POL-005 | policy_name: Điều chỉnh tồn kho | trigger: Có chênh lệch giữa đếm thực tế và hệ thống | rule_or_re_
- [ ] **grade 1** 02_#7 ⚠️ belongs to test topics (fact appears in both sets) — Approval levels defined for discrepancy sizes  
  _Columns: Tình huống | Hành động tối thiểu | Người duyệt Row 1: Tình huống: Không chênh lệch | Hành động tối thiểu: Đóng phiếu; lưu audit trail | Người duyệt: Warehouse Supervisor Row 2: Tình huống: Chênh lệch nhỏ, có nguyên nhân rõ và bằng chứng | Hành động tối thiểu: Recount + biên bản; cập nhật sa_
- [ ] **grade 1** 02_#6 ⚠️ belongs to test topics (fact appears in both sets) — Independent approver required separate from counter  
  _Columns: Bước | Đầu ra bắt buộc Row 1: Bước: 1. Chuẩn bị | Đầu ra bắt buộc: Danh sách SKU / vị trí, phạm vi đếm, thời điểm freeze giao dịch nếu cần Row 2: Bước: 2. Đếm độc lập | Đầu ra bắt buộc: Số lượng thực tế; người đếm; thời gian; ảnh / ghi chú ngoại lệ Row 3: Bước: 3. Đối chiếu | Đầu ra bắt buộ_
- [ ] **grade 1** VN#459 ⚠️ belongs to test topics (fact appears in both sets) — Counter cannot be sole approver for major adjustment  
  _Yêu cầu kiểm soát Người đếm không được là người duyệt duy nhất cho điều chỉnh trọng yếu._

## D022 (dev, multi_passage, expected answer)
**Q:** Khi hai cách hiểu chính sách xung đột thì làm gì, và nếu ma trận phê duyệt không có hàng nào khớp thì sao?  
**Expected:** Chuyển cấp xử lý xung đột trước khi cam kết, không chọn cách hiểu dễ dãi hơn; nếu không hàng nào của ma trận khớp thì dừng và chuyển cấp thay vì chọn hàng thuận tiện.
- judge note: No single passage fully answers both parts; expected outcome 'answer' is incorrect.
- [ ] **grade 1** VN#736 — Escalate conflict, do not conclude  
  _Điều kiện chặn bổ sung bắt buộc Nguồn chính sách mâu thuẫn hoặc truy xuất trái quyền: không kết luận, chuyển cấp._
- [ ] **grade 1** EN#71 ⚠️ belongs to test topics (fact appears in both sets) — Suspend action, refer conflict  
  _Control requirements  If two approved sources conflict, suspend the affected automated action and refer the conflict to the accountable owner._
- [ ] **grade 1** VN#731 — No matrix row → do not commit  
  _Điều kiện chặn bổ sung bắt buộc Không hàng ma trận hợp lệ hoặc không người có thẩm quyền: không cam kết._

## D023 (dev, multi_passage, expected answer)
**Q:** Dữ liệu tồn kho trong Supabase kéo dài đến năm nào, và khi trả lời câu hỏi về tồn kho phải nêu điều gì?  
**Expected:** Snapshot tồn kho lịch sử từ 2012-07-31 đến 2022-12-31, không phải số dư trực tiếp; mọi câu trả lời tồn phải nêu ngày dữ liệu và không trình bày snapshot lịch sử như hàng đang khả dụng.
- [ ] **grade 1** VN#11 ⚠️ belongs to other topics (fact appears in both sets) — states end date & not direct balance  
  _Sự phù hợp với cơ sở dữ liệu Lược đồ commerce trong Supabase là tập dữ liệu phân tích, không phải hệ thống ghi nhận nghiệp vụ trực tiếp cho mọi quy trình. Bản ghi tồn kho là các ảnh chụp lịch sử đến ngày 31 tháng 12 năm 2022. Giao dịch nhân sự, chấm công, chi phí, mua sắm, nhận hàng và sự cố phải đư_
- [ ] **grade 2** 01_#3 — gives full date range and answer requirement  
  _2. Phạm vi và cơ sở dữ liệu Dataset có 2,412 SKU trong products.csv và 60,247 bản ghi inventory.csv, bao phủ 2012-07-31 đến 2022-12-31. Snapshot mới nhất là 2022-12-31 với 424 SKU có bản ghi. Nhóm hàng quan sát gồm Streetwear, Outdoor, Casual và GenZ. Sales.csv bao phủ 2012-07-04 đến 2022-12-31. Dữ _
- [ ] **grade 1** 01_#14 — requires mentioning snapshot date  
  _11. Kiểm soát chất lượng dữ liệu Trong inventory.csv, 67.3% bản ghi có stockout_flag=1, 76.3% có overstock_flag=1, 30,495 bản ghi bật đồng thời hai cờ, và tổng reorder_flag bằng 0. Trên snapshot 2022-12-31, 232 SKU bật đồng thời stockout_flag và overstock_flag. Đây là tín hiệu cần xác minh, không ph_
- [ ] **grade 1** VN#357 — clarifies data is not direct balance  
  _Hồ sơ tồn kho, phạm vi và thứ bậc nguồn Quy tắc bắt buộc. Số hiện tại chính thức là số dư trực tiếp trong hệ thống quản lý kho/tồn được duyệt. Supabase commerce.inventory là dữ liệu phân tích lịch sử, không phải sổ tồn trực tiếp._
- [ ] **grade 1** VN#725 — describes snapshot history, not live stock  
  _Phụ lục A - Tham chiếu lược đồ Supabase và quan hệ Columns: Bảng | Trường khóa | Cách diễn giải được phép Row 1: Bảng: commerce.products | Trường khóa: product_id (PK); product_name, category, segment, size, color, price, cogs | Cách diễn giải được phép: Danh tính sản phẩm chuẩn và thuộc tính mô tả _
- [ ] **grade 1** EN#11 ⚠️ belongs to other topics (fact appears in both sets) — states snapshot through 31‑12‑2022  
  _Database alignment The Supabase commerce schema is an analytical dataset, not the live system of record for every process. Inventory records are historical snapshots through 31 December 2022. Employee HR, attendance, expense, procurement, receiving and incident transactions must be maintained in the_

## D024 (dev, multi_passage, expected answer)
**Q:** Tôi có thể xin ngoại lệ để dán khóa API vào prompt cho AI dùng tạm không?  
**Expected:** Không: không dán thông tin đăng nhập vào prompt AI, và ngoại lệ không miễn yêu cầu bảo mật không được miễn.
- [ ] **grade 2** VN#529 — Explicitly forbids pasting secret keys in prompts  
  _Yêu cầu kiểm soát Không dùng chung tài khoản cá nhân.  Không lộ service-role hoặc khóa bí mật trong mã phía khách, notebook, ảnh chụp hay prompt._
- [ ] **grade 2** EN#597 — Directly states not to paste credentials into AI prompts  
  _Control requirements  Do not paste credentials into AI prompts, tickets or policy documents._

## D025 (dev, multi_passage, expected answer)
**Q:** Câu trả lời của trợ lý AI có được tính là phê duyệt nghỉ phép không, và AI được làm gì với phê duyệt?  
**Expected:** Không: yêu cầu nghỉ vẫn chờ đến khi quyết định được ghi nhận, câu trả lời do AI tạo không phải phê duyệt; đề xuất của trợ lý AI không phải phê duyệt hay giao dịch, và tác tử không được tạo phê duyệt.
- [ ] **grade 1** VN#699 — AI answers need human approval for decisions  
  _Ánh xạ chính sách-dữ liệu và quy tắc trả lời AI Quy tắc bắt buộc. Câu trả lời có thể dẫn đến trả tiền, mua hàng, điều chỉnh tồn, cấp quyền hoặc quyết định nhân sự phải dẫn chính sách điều chỉnh và nêu bằng chứng trực tiếp còn thiếu hoặc phê duyệt con người cần có._
- [ ] **grade 1** VN#629 ⚠️ belongs to test topics (fact appears in both sets) — AI cannot approve expenses or actions  
  _Quản lý thay đổi, an toàn tác tử AI và kiểm soát phát hành Quy tắc bắt buộc. Tác tử AI có thể truy chính sách đã duyệt, hỏi dữ liệu được phép và soạn đề xuất. Không được duyệt chi, phát hành PO, trả hóa đơn, điều chỉnh tồn hay cấp quyền, trừ luồng được phê duyệt và kiểm toán riêng cho phép rõ hành đ_
- [ ] **grade 1** VN#118 — Messages not official approval records  
  _Sự phù hợp hệ thống và dữ liệu Dùng hệ thống nhân sự làm nguồn ghi nhận chính thức. Lịch hoặc tin nhắn có thể hỗ trợ trao đổi nhưng không phải hồ sơ phê duyệt có thẩm quyền._
- [ ] **grade 1** VN#109 — Leave decisions must be by manager  
  _Phê duyệt, từ chối và thay đổi nghỉ phép Quyết định nghỉ phải do quản lý hoặc người được Nhân sự ủy quyền hợp lệ thực hiện và thông báo rõ cho nhân viên._
- [ ] **grade 1** 05_#2 ⚠️ belongs to test topics (fact appears in both sets) — AI only proposes, not approve  
  _02 | Mô hình vận hành Tách quyền ra quyết định khỏi thao tác nhập liệu. PLAN Forecast / campaign ROP & target stock → APPROVE Budget / supplier PO authorization → RECEIVE PO match QC & put-away → CONTROL Cycle count Exception handling → LEARN KPI / root cause Forecast update Nguyên tắc kiểm soát: ng_
- [ ] **grade 1** VN#698 — AI must not enable actions  
  _Ánh xạ chính sách-dữ liệu và quy tắc trả lời AI Tác tử tri thức phải giải thích chính sách áp dụng, phân biệt sự thật với suy luận, tránh cho phép hành động từ dữ liệu lịch sử._
- [ ] **grade 1** 03_#11 — Human approval required for AI suggestions  
  _Columns: policy_id | policy_name | trigger | rule_or_required_action | owner | sla_or_frequency | approval | company | document_version | effective_status | source_basis Row 12: policy_id: INV-POL-012 | policy_name: AI / báo cáo tự động | trigger: AI Agent tạo câu trả lời hoặc đề xuất PO | rule_or_r_
- [ ] **grade 2** EN#23 — AI recommendation is not approval  
  _Control requirements  A recommendation from an AI assistant is not an approval or transaction._
- [ ] **grade 1** 04_#8 — Human approval mandatory for AI output  
  _Policy Matrix Columns: Policy ID | Chính sách | Trigger | Hành động bắt buộc | Owner | SLA / Tần suất | Approval Row 11: Policy ID: INV-POL-011 | Chính sách: KPI và cảnh báo | Trigger: Báo cáo vận hành định kỳ | Hành động bắt buộc: Theo dõi fill rate, stockout rate, inventory accuracy, days of suppl_
- [ ] **grade 1** EN#745 — Answers triggering actions need human approval  
  _Policy-to-data mapping and AI response rules Mandatory rule. An answer that could trigger a payment, purchase, stock adjustment, access grant or employee decision must cite the controlling policy and identify any missing live evidence or required human approval._

## D026 (dev, table, expected answer)
**Q:** Theo Phụ lục A, khóa chính của bảng commerce.order_items là gì?  
**Expected:** commerce.order_items có khóa chính order_item_id (cùng các trường order_id, product_id, quantity, unit_price, discount_amount, promo_id, promo_id_2).
- [ ] **grade 2** VN#43 ⚠️ belongs to test topics (fact appears in both sets) — Lists order_items.order_item_id as key  
  _Sự phù hợp hệ thống và dữ liệu Các khóa quan hệ đã biết gồm products.product_id, orders.order_id, order_items.order_item_id, customers.customer_id, promotions.promo_id và inventory(snapshot_date, product_id)._
- [ ] **grade 2** VN#518 ⚠️ belongs to test topics (fact appears in both sets) — Specifies order_items primary key order_item_id  
  _Sự phù hợp hệ thống và dữ liệu Cấp chi tiết tồn là snapshot_date + product_id; order_items là order_item_id; payments là order_id; shipments là order_id; returns là return_id._
- [ ] **grade 2** EN#777 — Explicitly states order_item_id as PK  
  _Appendix A - Supabase schema and relationship reference Columns: Table | Key fields | Permitted interpretation Row 4: Table: commerce.order_items | Key fields: order_item_id (PK); order_id, product_id, quantity, unit_price, discount_amount, promo_id, promo_id_2 | Permitted interpretation: Sales line_

## D027 (dev, table, expected answer)
**Q:** SKU nhóm A phải kiểm kê bao lâu một lần và chênh lệch phải điều tra trong thời hạn nào?  
**Expected:** Nhóm A (khoảng 80% giá trị tiêu thụ năm) kiểm kê hằng tuần và điều tra chênh lệch ngay trong ngày.
- [ ] **grade 1** 04_#4 — states A weekly cycle  
  _Policy Matrix Columns: Policy ID | Chính sách | Trigger | Hành động bắt buộc | Owner | SLA / Tần suất | Approval Row 3: Policy ID: INV-POL-003 | Chính sách: Xác minh mâu thuẫn tồn kho | Trigger: Có tín hiệu stockout/service thấp đồng thời days of supply > 120; hoặc cờ stockout và overstock cùng bật _
- [ ] **grade 1** 03_#3 — A weekly, from policy table  
  _Columns: policy_id | policy_name | trigger | rule_or_required_action | owner | sla_or_frequency | approval | company | document_version | effective_status | source_basis Row 4: policy_id: INV-POL-004 | policy_name: Kiểm kê chu kỳ ABC | trigger: SKU nhóm A/B/C theo giá trị tiêu thụ năm | rule_or_requ_
- [ ] **grade 1** 05_#4 ⚠️ belongs to test topics (fact appears in both sets) — A weekly cycle mentioned  
  _04 | Kiểm kê chu kỳ & điều chỉnh ABC dựa trên giá trị tiêu thụ năm, không chỉ dựa vào số lượng. NHÓM A ~80% giá trị tiêu thụ Hằng tuần NHÓM B ~15% tiếp theo Hằng tháng NHÓM C ~5% còn lại Hằng quý Quy trình: chuẩn bị danh sách → blind count → recount độc lập → đối chiếu receipts/picks/returns/transfe_

## D028 (dev, table, expected answer)
**Q:** Fill rate xuống dưới bao nhiêu thì phải phát cảnh báo P1?  
**Expected:** Mục tiêu mô phỏng fill rate ≥ 98%; dưới 95% thì cảnh báo P1 và phân tích nguyên nhân.
- [ ] **grade 1** 04_#1 ⚠️ belongs to test topics (fact appears in both sets) — Defines fill_rate <95% as stockout signal  
  _README Columns: Mục | Nội dung Row 8: Mục: Inventory position | Nội dung: On-hand + Open PO − Backorder. Dataset không có Open PO / Backorder; workbook mặc định 0 và yêu cầu nhập số thực tế. Row 9: Mục: Stockout signal | Nội dung: stockout_days ≥ 1 hoặc fill_rate < 95% hoặc calculated days of supply_
- [ ] **grade 1** 02_#1 ⚠️ belongs to test topics (fact appears in both sets) — Mentions SKU fill rate below 95% triggers action  
  _3. Chuẩn bị trước khi đếm VietStyle Commerce • SOP-INV-002 • Tài liệu mô phỏng Trang 2 1. Mục đích và phạm vi Áp dụng cho SKU thời trang và outdoor trong kho / điểm xử lý đơn của mô hình VietStyle Commerce. SOP bao gồm kiểm kê chu kỳ, kiểm kê theo sự kiện và điều chỉnh chênh lệch. Không dùng SOP này_

## D030 (dev, table, expected answer)
**Q:** Chính sách vận hành phiên bản 1.0 có hiệu lực từ ngày nào và do ai phê duyệt?  
**Expected:** Phiên bản 1.0 có hiệu lực từ 23 tháng 10 năm 2026; chủ sở hữu/cấp phê duyệt là Bộ phận Quản trị Vận hành / Hội đồng Điều hành Vận hành.
- [ ] **grade 2** VN#3 ⚠️ belongs to other topics (fact appears in both sets) — States effective date and approval authority  
  _Chính sách vận hành doanh nghiệp Columns: column_1 | column_2 Row 1: column_1: Mã tài liệu | column_2: VSC-OPS-POL-001 Row 2: column_1: Phiên bản | column_2: 1.0 Row 3: column_1: Trạng thái | column_2: Đã phê duyệt Row 4: column_1: Ngày hiệu lực | column_2: 23 tháng 10 năm 2026 Row 5: column_1: Đơn _
- [ ] **grade 2** EN#3 ⚠️ belongs to other topics (fact appears in both sets) — Provides English version of date and authority  
  _Enterprise Operating Policy Columns: column_1 | column_2 Row 1: column_1: Document ID | column_2: VSC-OPS-POL-001 Row 2: column_1: Version | column_2: 1.0 Row 3: column_1: Status | column_2: Approved Row 4: column_1: Effective date | column_2: 23 October 2026 Row 5: column_1: Policy owner | column_2_

## D037 (dev, false_premise, expected answer)
**Q:** Đơn mua dưới 5 triệu thì tôi tự duyệt cho mình được đúng không?  
**Expected:** Không: không nhân viên nào được tự duyệt yêu cầu của mình; khoản đến 5.000.000 VND do quản lý trực tiếp duyệt.
- [ ] **grade 1** EN#781 — Line manager must approve up to 5M  
  _Appendix B - Approval limits and operational decision table Columns: Total commitment | Required approval | Additional condition Row 1: Total commitment: Up to VND 5,000,000 | Required approval: Line manager | Additional condition: One documented quote; budget confirmed. Row 2: Total commitment: VND_
- [ ] **grade 1** VN#730 — Quản lý trực tiếp phê duyệt đến 5M  
  _Phụ lục B - Hạn mức phê duyệt và bảng quyết định vận hành Columns: Tổng cam kết | Phê duyệt bắt buộc | Điều kiện bổ sung Row 1: Tổng cam kết: Đến 5.000.000 VND | Phê duyệt bắt buộc: Quản lý trực tiếp | Điều kiện bổ sung: Một báo giá có hồ sơ; ngân sách xác nhận. Row 2: Tổng cam kết: 5.000.001-50.000_
- [ ] **grade 1** VN#677 — Người đề nghị không tự đặt ngưỡng duyệt  
  _Yêu cầu kiểm soát Người đề nghị không được tự đặt ngưỡng duyệt.  Hàng thiếu hoặc hết hạn là điều kiện chặn, không phải cho phép ngầm.  Đổi vai trò duyệt phải đồng bộ IAM và hệ luồng việc._
- [ ] **grade 1** VN#197 ⚠️ belongs to test topics (fact appears in both sets) — Người đề nghị không là người duyệt duy nhất  
  _Yêu cầu kiểm soát Người đề nghị không được là người duyệt duy nhất.  Không đánh dấu đã chi chỉ dựa vào lệnh thanh toán._

## D038 (dev, false_premise, expected answer)
**Q:** Số tồn trong bảng commerce.inventory là số tồn kho hiện tại đúng không?  
**Expected:** Không: commerce.inventory là dữ liệu phân tích lịch sử (đến 2022-12-31), không phải sổ tồn trực tiếp; số hiện tại chính thức nằm ở hệ thống quản lý kho được duyệt.
- [ ] **grade 2** VN#11 ⚠️ belongs to other topics (fact appears in both sets) — States inventory is historical snapshot to 2022-12-31  
  _Sự phù hợp với cơ sở dữ liệu Lược đồ commerce trong Supabase là tập dữ liệu phân tích, không phải hệ thống ghi nhận nghiệp vụ trực tiếp cho mọi quy trình. Bản ghi tồn kho là các ảnh chụp lịch sử đến ngày 31 tháng 12 năm 2022. Giao dịch nhân sự, chấm công, chi phí, mua sắm, nhận hàng và sự cố phải đư_
- [ ] **grade 2** 05_#1 ⚠️ belongs to test topics (fact appears in both sets) — Dataset simulation not current inventory  
  _01 | Bối cảnh dữ liệu Dataset là cơ sở mô phỏng; không phản ánh tồn kho hiện tại. 2,412 SKU trong product master 60,247 Bản ghi inventory theo snapshot 424 SKU có snapshot 31/12/2022 67.3% Bản ghi bật stockout_flag Nhóm hàng • Streetwear • Outdoor • Casual • GenZ Vấn đề dữ liệu cần kiểm soát • 76.3%_
- [ ] **grade 2** VN#25 — Describes inventory as daily snapshots  
  _Sự phù hợp hệ thống và dữ liệu Các bảng phân tích commerce mô tả sản phẩm, bán hàng, đơn hàng, thanh toán, giao hàng, trả hàng và ảnh chụp tồn kho theo ngày. Lược đồ hiện tại chưa có bảng giao dịch nhân sự, chấm công, đề nghị hoàn chi phí, mua sắm hoặc sự cố CNTT; các quy trình đó cần hệ thống nghiệ_
- [ ] **grade 2** VN#462 ⚠️ belongs to test topics (fact appears in both sets) — Defines inventory as historical snapshot without adjustments  
  _Sự phù hợp hệ thống và dữ liệu commerce.inventory là bảng snapshot lịch sử có stock_on_hand không âm, không có sổ điều chỉnh. Không ghi sửa tại đây._
- [ ] **grade 2** VN#447 — No location fields; inventory counted elsewhere  
  _Sự phù hợp hệ thống và dữ liệu commerce.inventory không có vị trí, ô kho, người đếm, phiên kiểm kê hoặc mã điều chỉnh. Thực hiện kiểm kê thuộc hệ thống tồn nghiệp vụ._
- [ ] **grade 2** VN#365 — Specifies snapshot date range ending 2022-12-31  
  _Sự phù hợp hệ thống và dữ liệu Khóa chính commerce.inventory là (snapshot_date, product_id). Trường có stock_on_hand, units_received, units_sold, stockout_days, days_of_supply, fill_rate, stockout_flag, overstock_flag, reorder_flag và sell_through_rate. Dữ liệu lịch sử kết thúc 2022-12-31._
- [ ] **grade 2** VN#476 — Units_received is historical, not transaction log  
  _Sự phù hợp hệ thống và dữ liệu Lược đồ chưa có receiving_events hoặc bảng dòng PO. commerce.inventory.units_received là chỉ số lịch sử, không phải nhật ký giao dịch nhận._
- [ ] **grade 2** VN#725 — Explicitly says snapshot, not direct stock ledger  
  _Phụ lục A - Tham chiếu lược đồ Supabase và quan hệ Columns: Bảng | Trường khóa | Cách diễn giải được phép Row 1: Bảng: commerce.products | Trường khóa: product_id (PK); product_name, category, segment, size, color, price, cogs | Cách diễn giải được phép: Danh tính sản phẩm chuẩn và thuộc tính mô tả _
- [ ] **grade 2** VN#490 ⚠️ belongs to test topics (fact appears in both sets) — Lacks location fields; requires separate warehouse system  
  _Sự phù hợp hệ thống và dữ liệu commerce.inventory không có vị trí, lô, sê-ri, hạn dùng, trạng thái chất lượng hoặc luân chuyển; cần hệ thống kho cho các kiểm soát này._

## D040 (dev, false_premise, expected answer)
**Q:** Dựa vào snapshot tồn kho, hôm nay sản phẩm 1001 còn hàng để hứa giao cho khách không?  
**Expected:** Không thể kết luận: snapshot chỉ là lịch sử; nếu hỏi 'bây giờ' chỉ được trả ngày lịch sử mới nhất kèm giới hạn và phải xác minh tồn trực tiếp, không hứa ngày giao theo dữ liệu lịch sử.
- [ ] **grade 2** VN#384 — snapshot only historical, not current availability  
  _Độ mới snapshot và báo cáo lịch sử Chỉ số tồn lịch sử hỗ trợ phân tích xu hướng nhưng không chứng minh khả dụng hôm nay._
- [ ] **grade 2** VN#361 — missing product in snapshot ≠ zero stock  
  _Yêu cầu kiểm soát Không coi thiếu sản phẩm trong snapshot là tồn bằng không._
- [ ] **grade 2** VN#389 — cannot infer availability from snapshot  
  _Yêu cầu kiểm soát Không âm thầm kéo số dư biết cuối sang hiện tại.  Không nội suy snapshot thiếu để cam kết hàng._
- [ ] **grade 2** EN#405 — snapshot supports trend, not today’s stock  
  _Snapshot freshness and historical reporting Historical inventory measures support trend analysis but do not prove availability today._

## D041 (dev, language, expected answer)
**Q:** How many days of paid annual leave does an employee get for a full year?  
**Expected:** VietStyle grants 12 working days of paid annual leave for a full year of service, pro-rated for partial years.
- [ ] **grade 1** EN#81 — States accrual method, not total days  
  _Required procedure  Annual leave accrues at one-twelfth of the applicable annual entitlement for each completed service month unless a lawful rule requires a more favorable method._

## D043 (dev, language, expected answer)
**Q:** Vendor đổi bank account thì phải verify thế nào?  
**Expected:** Xác minh thay đổi ngân hàng qua kênh liên hệ lấy độc lập (gọi lại xác minh độc lập) trước khi chấp nhận.
- [ ] **grade 2** EN#258 — states independent verification required  
  _Required procedure  Verify bank-detail changes through an independently sourced contact channel._
- [ ] **grade 2** EN#338 ⚠️ belongs to test topics (fact appears in both sets) — requires independent verification  
  _Control requirements  Bank detail changes require independent verification._
- [ ] **grade 2** VN#321 ⚠️ belongs to test topics (fact appears in both sets) — cần xác minh độc lập  
  _Yêu cầu kiểm soát Không thanh toán hàng bị từ chối hoặc chưa nhận, trừ điều khoản hợp đồng đã duyệt cho phép ứng trước.  Thay đổi ngân hàng cần xác minh độc lập._

## D044 (dev, language, expected answer)
**Q:** Service-role key có được để trong client code không?  
**Expected:** Không: không lộ service-role hoặc khóa bí mật trong mã phía khách, notebook, ảnh chụp hay prompt; giữ service-role ở máy chủ.
- [ ] **grade 1** VN#555 — Allows only client‑side keys, not service‑role.  
  _Quy trình bắt buộc Chỉ dùng khóa phía khách có thể công khai trong ngữ cảnh trình duyệt/di động được thiết kế phù hợp._
- [ ] **grade 1** EN#593 — Publishable client keys only; service keys excluded.  
  _Required procedure  Use publishable client keys only in browser/mobile contexts designed for them._
- [ ] **grade 1** VN#552 — Secrets must not be exposed in source code.  
  _Bí mật, thông tin đăng nhập và cấu hình an toàn Bí mật bảo vệ truy cập dữ liệu/dịch vụ, không được lộ trong mã nguồn, giao diện hay nhật ký._

## D045 (dev, language, expected answer)
**Q:** Can I approve my own leave request?  
**Expected:** No. The requester cannot approve their own request; leave decisions are made by the manager or an HR-authorised delegate.
- [ ] **grade 2** EN#107 — Only managers/HR can decide leave  
  _Leave approval, rejection and changes Leave decisions must be made by an authorized manager or HR delegate and communicated clearly to the employee._

## D047 (dev, noisy, expected answer)
**Q:** ê ku m coi giùm t, hàng khách trả về là đem bán lại liền đc ko?  
**Expected:** Không: bản ghi trả không tự nghĩa đã nhập lại kho; phải kiểm tình trạng rồi quyết định nhập lại, tân trang, cách ly, trả nhà cung cấp hoặc thanh lý.
- [ ] **grade 2** 04_#6 — Quarantine until QA classification before resale  
  _Policy Matrix Columns: Policy ID | Chính sách | Trigger | Hành động bắt buộc | Owner | SLA / Tần suất | Approval Row 7: Policy ID: INV-POL-007 | Chính sách: Hàng trả về | Trigger: Nhận hàng trả về từ khách | Hành động bắt buộc: Cách ly đến khi QA phân loại: A-grade bán lại; B-grade sửa/đóng gói lại;_
- [ ] **grade 2** 03_#6 — Policy states QA isolation before selling  
  _Columns: policy_id | policy_name | trigger | rule_or_required_action | owner | sla_or_frequency | approval | company | document_version | effective_status | source_basis Row 7: policy_id: INV-POL-007 | policy_name: Hàng trả về | trigger: Nhận hàng trả về từ khách | rule_or_required_action: Cách ly đ_
- [ ] **grade 2** 05_#5 ⚠️ belongs to test topics (fact appears in both sets) — Returns only added after QA approval  
  _05 | Dư thừa, trả hàng và cách ly Tồn kho cao không có nghĩa là hàng sẵn sàng bán. DAYS OF SUPPLY >120 Tạm dừng bổ sung; kiểm tra forecast, size/màu và hàng đang chuyển. >180 NGÀY Lập kế hoạch chuyển kho, bundle, markdown hoặc thanh lý có phê duyệt. HÀNG TRẢ VỀ Quarantine → QA → A-grade bán lại / B-_
- [ ] **grade 1** VN#502 — Cannot infer status; need QA decision  
  _Yêu cầu kiểm soát Không suy tình trạng chỉ từ return_reason.  Giữ hoàn tiền khách và xử lý tồn là hai quyết định riêng._
- [ ] **grade 1** VN#726 — Returns table lacks processing status  
  _Phụ lục A - Tham chiếu lược đồ Supabase và quan hệ Columns: Bảng | Trường khóa | Cách diễn giải được phép Row 4: Bảng: commerce.order_items | Trường khóa: order_item_id (PK); order_id, product_id, quantity, unit_price, discount_amount, promo_id, promo_id_2 | Cách diễn giải được phép: Cấp dòng bán hà_
- [ ] **grade 1** VN#500 — Reconcile returns with inventory decisions  
  _Quy trình bắt buộc Đối chiếu hàng trả với xử lý tồn và xác nhận thanh toán/hoàn tiền._

## D048 (dev, noisy, expected answer)
**Q:** sếp t im lặng ko rep đơn nghỉ, vậy coi như dc duyệt hả  
**Expected:** Không: yêu cầu vẫn chờ đến khi quyết định được ghi nhận; im lặng, mục lịch hoặc câu trả lời AI không phải phê duyệt.
- [ ] **grade 1** VN#686 ⚠️ belongs to test topics (fact appears in both sets) — requires explicit decision field  
  _Quy trình bắt buộc Nghỉ phép: mã nhân viên, loại nghỉ, ngày/giờ, thời điểm gửi, người duyệt và quyết định._
- [ ] **grade 1** VN#111 — reviewer must verify and decide  
  _Quy trình bắt buộc Người duyệt kiểm tra quyền nghỉ, nhân sự thay thế, thời gian trùng và yêu cầu bảo vệ quyền nghỉ._
- [ ] **grade 1** VN#109 — decision must be communicated  
  _Phê duyệt, từ chối và thay đổi nghỉ phép Quyết định nghỉ phải do quản lý hoặc người được Nhân sự ủy quyền hợp lệ thực hiện và thông báo rõ cho nhân viên._
- [ ] **grade 1** VN#115 — no self‑approval, must state reason  
  _Yêu cầu kiểm soát Người đề nghị không được tự duyệt yêu cầu.  Từ chối phải nêu lý do liên quan công việc và không vi phạm quyền nghỉ được bảo vệ._
- [ ] **grade 1** VN#123 ⚠️ belongs to test topics (fact appears in both sets) — approved absence requires coordination  
  _Lịch nghỉ, bàn giao và trở lại làm việc Vắng mặt đã duyệt cần được phối hợp để bảo vệ cam kết khách hàng, vận hành liên tục và quyền riêng tư nhân viên._

## D050 (dev, noisy, expected answer)
**Q:** truoc campaign bao lau thi phai chot forecast ton kho  
**Expected:** Tối thiểu 4 tuần trước campaign, Merchandising và Planner thống nhất forecast theo SKU/size/màu.
- [ ] **grade 2** 05_#6 ⚠️ belongs to test topics (fact appears in both sets) — States T‑4 weeks forecast SKU/size/color  
  _06 | Khuyến mãi và KPI Campaign phải có kế hoạch tồn kho trước khi chạy. Trước campaign (T−4 tuần) • Forecast theo SKU / size / màu • Kiểm tra stock, PO, lead time, MOQ • Xác nhận discount, channel, stackable flag • Duyệt tăng target stock nếu cần Sau campaign • Sell-through / tồn còn lại • Return r_
- [ ] **grade 2** 03_#7 — Rule: forecast minimum 4 weeks before campaign  
  _Columns: policy_id | policy_name | trigger | rule_or_required_action | owner | sla_or_frequency | approval | company | document_version | effective_status | source_basis Row 8: policy_id: INV-POL-008 | policy_name: Quản lý khuyến mãi | trigger: Campaign/promotion được lên lịch | rule_or_required_act_
- [ ] **grade 1** 01_#5 — Mentions review before campaign, not exact 4 weeks  
  _4. Chính sách bổ sung hàng Mô hình tham chiếu cho SKU có nhu cầu tương đối ổn định: Inventory position = On-hand + Open PO − Backorder Reorder Point (ROP) = Nhu cầu/ngày × (Lead time + Safety days) Target Stock = Nhu cầu/ngày × (Lead time + Safety days + Review period) Giả định khởi tạo trong bộ mô _

## D056 (dev, follow_up, expected answer)
**Q:** còn nếu 30 triệu thì sao?  
**Expected:** 30.000.000 VND thuộc 5.000.001–50.000.000 VND: trưởng bộ phận phê duyệt và cần ít nhất hai báo giá tương đương.
- [ ] **grade 2** EN#781 — Specifies dept head approval for 5,000,001-50,000,000 VND  
  _Appendix B - Approval limits and operational decision table Columns: Total commitment | Required approval | Additional condition Row 1: Total commitment: Up to VND 5,000,000 | Required approval: Line manager | Additional condition: One documented quote; budget confirmed. Row 2: Total commitment: VND_

## D058 (dev, follow_up, expected answer)
**Q:** lỡ làm mất hóa đơn thì sao?  
**Expected:** Nếu mất chứng từ phải giải trình và được Tài chính duyệt trước khi hoàn trả.
- [ ] **grade 2** VN#195 ⚠️ belongs to test topics (fact appears in both sets) — Missing docs require explanation and finance approval  
  _Quy trình bắt buộc Trả hồ sơ thiếu với lý do cụ thể và hạn nộp lại.  Sau duyệt, Tài chính chi qua quy trình được phép và ghi mã/ngày thanh toán._

## T002 (test, lookup, expected answer)
**Q:** Sự cố bảo mật mức Cao phải báo cho Bảo mật trong bao lâu?  
**Expected:** Mức Cao (khả năng truy cập trái phép hoặc suy giảm dịch vụ đáng kể): báo Bảo mật và chủ hệ thống trong một giờ.
- [ ] **grade 1** VN#741 — Mentions immediate escalation for high‑level incidents  
  _Phụ lục C - Biểu mẫu chuẩn và kiểm tra tối thiểu Columns: column_1 | column_2 | column_3 Row 1: column_1: Biên bản nhận hàng | column_2: PO/dòng; phiếu giao; lượng giao/chấp nhận/từ chối; kiểm định; người nhận. | column_3: Chấp nhận + từ chối <= giao; PO hợp lệ; cách ly hàng không đạt. Row 2: column_
- [ ] **grade 2** EN#639 — Specifies one‑hour reporting for High incidents  
  _Required procedure  High: likely unauthorized access or significant service degradation; contact Security and system owner within one hour._

## T003 (test, lookup, expected answer)
**Q:** Nhà cung cấp trọng yếu phải được rà soát hiệu quả bao lâu một lần?  
**Expected:** Rà nhà cung cấp trọng yếu ít nhất hằng năm và sau lỗi lặp về chất lượng, giao hàng, bảo mật hoặc hóa đơn.
- [ ] **grade 1** VN#712 — annual and after major changes  
  _Rà quản trị, kiểm toán và cải tiến liên tục Quy tắc bắt buộc. Chủ lĩnh vực rà ít nhất hằng năm và sau thay đổi trọng yếu về luật, mô hình dữ liệu, quy trình nhà cung cấp, kiểm soát tồn, kiến trúc bảo mật hoặc ứng phó sự cố._
- [ ] **grade 1** VN#72 — at least yearly and after incidents  
  _Yêu cầu kiểm soát Rà soát ít nhất hằng năm và sau sự cố trọng yếu, thay đổi pháp luật, lược đồ hoặc lỗi kiểm soát._
- [ ] **grade 1** VN#27 ⚠️ belongs to dev topics (fact appears in both sets) — annual, after major incidents or changes  
  _Sự phù hợp hệ thống và dữ liệu Điều kiện rà soát: Hằng năm, sự cố trọng yếu, thay đổi quy trình hoặc hệ thống._

## T006 (test, amount, expected answer)
**Q:** Mua hệ thống camera 80 củ thì ai duyệt?  
**Expected:** 80.000.000 VND thuộc 50.000.001–200.000.000 VND: trưởng bộ phận cùng Mua sắm và Tài chính phê duyệt; cần ít nhất ba báo giá văn bản hoặc lý do chỉ định nguồn đã duyệt.
- [ ] **grade 2** EN#781 — Specifies required approvers for 50M-200M VND range  
  _Appendix B - Approval limits and operational decision table Columns: Total commitment | Required approval | Additional condition Row 1: Total commitment: Up to VND 5,000,000 | Required approval: Line manager | Additional condition: One documented quote; budget confirmed. Row 2: Total commitment: VND_

## T007 (test, amount, expected answer)
**Q:** Hợp đồng 1,2 tỷ thì cấp nào phê duyệt?  
**Expected:** 1.200.000.000 VND trên 200.000.000 VND: Hội đồng Điều hành Vận hành cùng Tài chính phê duyệt; cần đánh giá nguồn cung và rà rủi ro được lập hồ sơ.
- [ ] **grade 2** EN#781 — Specifies >200M needs Executive Operations Council + Finance  
  _Appendix B - Approval limits and operational decision table Columns: Total commitment | Required approval | Additional condition Row 1: Total commitment: Up to VND 5,000,000 | Required approval: Line manager | Additional condition: One documented quote; budget confirmed. Row 2: Total commitment: VND_

## T008 (test, amount, expected answer)
**Q:** Gói mua 60tr thì cần bao nhiêu báo giá?  
**Expected:** Trên 50.000.000 VND cần ít nhất ba báo giá bằng văn bản hoặc giải trình chỉ định nguồn được lập hồ sơ.
- [ ] **grade 1** EN#286 — Provides threshold but not quote count  
  _Approval matrix and monetary thresholds Mandatory rule. The default delegated authority for a single commitment is: up to VND 5,000,000-line manager; VND 5,000,001-50,000,000-department head; VND 50,000,001-200,000,000-department head plus Procurement and Finance; above VND 200,000,000-Executive Ope_
- [ ] **grade 2** EN#781 — Specifies three written quotes for 50M+  
  _Appendix B - Approval limits and operational decision table Columns: Total commitment | Required approval | Additional condition Row 1: Total commitment: Up to VND 5,000,000 | Required approval: Line manager | Additional condition: One documented quote; budget confirmed. Row 2: Total commitment: VND_
- [ ] **grade 1** VN#274 — Thresholds only, no quote rule  
  _Ma trận phê duyệt và ngưỡng tiền Quy tắc bắt buộc. Thẩm quyền mặc định cho một cam kết: đến 5.000.000 VND-quản lý trực tiếp; 5.000.001-50.000.000 VND-trưởng bộ phận; 50.000.001-200.000.000 VND-trưởng bộ phận cùng Mua sắm và Tài chính; trên 200.000.000 VND-Hội đồng Điều hành Vận hành cùng Tài chính._
- [ ] **grade 1** VN#265 — Mentions quote comparison, not count  
  _Yêu cầu kiểm soát Báo giá phải so được về phạm vi, số lượng, tiền tệ, thuế và giao hàng._

## T010 (test, amount, expected answer)
**Q:** Cam kết đúng 200 triệu thì ai duyệt?  
**Expected:** 200.000.000 VND vẫn thuộc 50.000.001–200.000.000 VND: trưởng bộ phận cùng Mua sắm và Tài chính (chưa đến Hội đồng Điều hành Vận hành).
- [ ] **grade 2** EN#781 — Specifies dept head, procurement, finance for 50M-200M  
  _Appendix B - Approval limits and operational decision table Columns: Total commitment | Required approval | Additional condition Row 1: Total commitment: Up to VND 5,000,000 | Required approval: Line manager | Additional condition: One documented quote; budget confirmed. Row 2: Total commitment: VND_

## T012 (test, calculation, expected answer)
**Q:** Mua 4 máy chủ, mỗi máy 60 triệu thì ai duyệt?  
**Expected:** Duyệt theo tổng cam kết: 4 × 60.000.000 = 240.000.000 VND, trên 200.000.000 VND nên Hội đồng Điều hành Vận hành cùng Tài chính phê duyệt.
- [ ] **grade 2** EN#781 — Specifies approval above 200M VND  
  _Appendix B - Approval limits and operational decision table Columns: Total commitment | Required approval | Additional condition Row 1: Total commitment: Up to VND 5,000,000 | Required approval: Line manager | Additional condition: One documented quote; budget confirmed. Row 2: Total commitment: VND_

## T014 (test, calculation, expected answer)
**Q:** Cùng một nhu cầu mà chia làm 3 lô 30 triệu, 15 triệu và 10 triệu thì cần mấy báo giá?  
**Expected:** Tính theo tổng cam kết: 30 + 15 + 10 = 55.000.000 VND, trên 50.000.000 VND nên cần ít nhất ba báo giá văn bản hoặc giải trình chỉ định nguồn.
- [ ] **grade 2** EN#781 — Specifies three quotes for 50‑200M commitment  
  _Appendix B - Approval limits and operational decision table Columns: Total commitment | Required approval | Additional condition Row 1: Total commitment: Up to VND 5,000,000 | Required approval: Line manager | Additional condition: One documented quote; budget confirmed. Row 2: Total commitment: VND_

## T016 (test, multi_part, expected answer)
**Q:** Nghỉ phép theo kế hoạch cần báo trước bao lâu, và đơn nghỉ phải có những thông tin gì?  
**Expected:** Báo trước ít nhất năm ngày làm việc; cung cấp mã nhân viên, loại nghỉ, ngày bắt đầu/kết thúc, số giờ nghỉ, cách liên hệ và kế hoạch bàn giao.
- [ ] **grade 1** VN#96 — mentions need to send info and advance notice  
  _Nộp yêu cầu nghỉ và thời hạn báo trước Nhân viên phải gửi đủ thông tin để quản lý và Nhân sự xác định điều kiện, bố trí thay thế và xử lý tiền lương._
- [ ] **grade 1** VN#686 — lists required fields for leave request  
  _Quy trình bắt buộc Nghỉ phép: mã nhân viên, loại nghỉ, ngày/giờ, thời điểm gửi, người duyệt và quyết định._
- [ ] **grade 1** VN#332 ⚠️ belongs to dev topics (fact appears in both sets) — states latest possible notice timing  
  _Quy trình bắt buộc Nếu thực sự không thể duyệt trước, báo lãnh đạo chỉ định và Tài chính sớm nhất có thể, không muộn hơn một ngày làm việc sau cam kết._

## T017 (test, multi_part, expected answer)
**Q:** Sự cố mức Trung bình và mức Thấp lần lượt phải báo trong bao lâu?  
**Expected:** Trung bình: báo trong bốn giờ làm việc; Thấp: báo trước cuối ngày làm việc.
- [ ] **grade 1** EN#640 — Provides medium reporting time only  
  _Required procedure  Medium: limited impact with containment available; report within four business hours._

## T018 (test, multi_part, expected answer)
**Q:** Trước khi phát hành PO phải hoàn tất những kiểm tra gì, và nếu sửa PO sau khi phát hành thì sao?  
**Expected:** Chỉ phát hành PO sau khi hoàn tất kiểm tra yêu cầu, nhà cung cấp, nguồn cung, ngân sách và duyệt; sửa PO sau phát hành phải có phiên bản, gửi nhà cung cấp và lưu các bản trước.
- [ ] **grade 1** VN#247 ⚠️ belongs to dev topics (fact appears in both sets) — Specifies supplier identity and legal checks before use  
  _Thẩm định và tiếp nhận nhà cung cấp Quy tắc bắt buộc. Chỉ dùng nhà cung cấp sau khi hoàn tất kiểm tra danh tính, chỉ dẫn thanh toán, tư cách pháp lý và rủi ro phù hợp giao dịch._
- [ ] **grade 1** VN#738 — States release after approval and versioned revision  
  _Phụ lục C - Biểu mẫu chuẩn và kiểm tra tối thiểu Columns: Biểu mẫu | Trường tối thiểu | Kiểm tra / điều kiện chặn Row 4: Biểu mẫu: Đơn mua hàng | Trường tối thiểu: Số PO; nhà cung cấp; ngày phát hành; tiền tệ; dòng hàng; số lượng; đơn giá; điều kiện giao/thanh toán. | Kiểm tra / điều kiện chặn: Chỉ _
- [ ] **grade 1** VN#294 — Mentions approved PO and revision history  
  _Bằng chứng bắt buộc PO đã phát hành, yêu cầu đã duyệt, xác nhận nhà cung cấp, điều kiện và lịch sử sửa._
- [ ] **grade 1** 01_#5 ⚠️ belongs to dev topics (fact appears in both sets) — Lists checks before PO release (stock, budget, etc.)  
  _4. Chính sách bổ sung hàng Mô hình tham chiếu cho SKU có nhu cầu tương đối ổn định: Inventory position = On-hand + Open PO − Backorder Reorder Point (ROP) = Nhu cầu/ngày × (Lead time + Safety days) Target Stock = Nhu cầu/ngày × (Lead time + Safety days + Review period) Giả định khởi tạo trong bộ mô _
- [ ] **grade 1** VN#223 ⚠️ belongs to dev topics (fact appears in both sets) — Requires approval before PO issuance  
  _Quy trình bắt buộc Được duyệt trước khi phát hành PO hoặc chấp nhận điều kiện nhà cung cấp._
- [ ] **grade 1** EN#308 — Describes versioned PO revision after release  
  _Control requirements  A PO revision after release is versioned and sent to the supplier; retain prior versions._

## T019 (test, multi_part, expected answer)
**Q:** Trước khi chia sẻ dữ liệu ra bên ngoài cần xác nhận gì, và có được tải dữ liệu Hạn chế lên dịch vụ AI chưa được duyệt không?  
**Expected:** Trước chia sẻ ngoài phải xác nhận mục đích, người nhận, tối thiểu hóa và phê duyệt; không tải dữ liệu Hạn chế lên dịch vụ AI chưa được duyệt.
- [ ] **grade 1** EN#610 — states required confirmation before external sharing  
  _Required procedure  Before sharing externally, confirm purpose, recipient, minimization and approval._
- [ ] **grade 1** EN#611 — states prohibition on uploading restricted data  
  _Control requirements  Do not upload restricted data to an unapproved AI service._

## T020 (test, multi_part, expected answer)
**Q:** Khi nhân viên nghỉ việc thì xử lý quyền truy cập thế nào, và xóa tài khoản có lập tức vô hiệu token không?  
**Expected:** Khóa truy cập tương tác và thu hồi token/khóa theo quy trình nghỉ việc; xóa người dùng chưa chắc lập tức vô hiệu token hiện có.
- [ ] **grade 1** VN#538 — Specifies timely revocation of rights on termination  
  _Nhân viên mới, chuyển vai trò, nghỉ việc và rà quyền định kỳ Quy tắc bắt buộc. Thay đổi quyền bắt đầu từ quản lý có thẩm quyền hoặc sự kiện nhân sự và hoàn thành kịp thời theo mức nghiêm trọng._
- [ ] **grade 1** VN#537 — States rights must change with job status  
  _Nhân viên mới, chuyển vai trò, nghỉ việc và rà quyền định kỳ Quyền phải theo thay đổi việc làm và vai trò để người cũ hoặc chuyển việc không giữ quyền thừa._
- [ ] **grade 1** EN#582 — Notes deletion may not instantly invalidate tokens  
  _Control requirements  Deleting a user record does not guarantee existing tokens are immediately invalid._

## T021 (test, multi_passage, expected answer)
**Q:** Hàng đang giữ kiểm định có được tính là hàng có thể bán không, và có được đánh dấu hỏng để giảm dư hàng không?  
**Expected:** Không: hàng giữ kiểm định, hỏng, thu hồi hoặc hạn chế không được tính là hàng có thể bán; không đánh dấu hàng hỏng chỉ để loại dư hàng, ghi giảm cần bằng chứng độc lập và phê duyệt.
- [ ] **grade 1** VN#412 ⚠️ belongs to dev topics (fact appears in both sets) — holds not counted as sellable  
  _Quy trình bắt buộc Xác nhận hàng hiện có thể bán và hàng giữ do chất lượng, hỏng hoặc đơn hàng._
- [ ] **grade 1** VN#417 ⚠️ belongs to dev topics (fact appears in both sets) — cannot convert unavailable to sellable  
  _Yêu cầu kiểm soát Không hứa ngày giao chỉ theo fill_rate lịch sử.  Không đổi hàng không khả dụng thành có thể bán để cải thiện chỉ số._
- [ ] **grade 1** 01_#11 ⚠️ belongs to dev topics (fact appears in both sets) — quarantine excluded from sellable  
  _8. Nhận hàng, trả hàng và hàng cách ly Đối chiếu PO, SKU, size, màu, số lượng, tình trạng bao bì và chứng từ giao hàng. Ghi nhận thiếu / thừa / hư hỏng trước khi xác nhận nhận hàng; ảnh chụp và biên bản bắt buộc cho ngoại lệ. Hàng trả về phải vào trạng thái QUARANTINE cho đến khi QA kiểm tra; không _
- [ ] **grade 1** 05_#5 — return only after QA approval  
  _05 | Dư thừa, trả hàng và cách ly Tồn kho cao không có nghĩa là hàng sẵn sàng bán. DAYS OF SUPPLY >120 Tạm dừng bổ sung; kiểm tra forecast, size/màu và hàng đang chuyển. >180 NGÀY Lập kế hoạch chuyển kho, bundle, markdown hoặc thanh lý có phê duyệt. HÀNG TRẢ VỀ Quarantine → QA → A-grade bán lại / B-_
- [ ] **grade 1** VN#468 ⚠️ belongs to dev topics (fact appears in both sets) — only accepted stock can be sold  
  _Nhận hàng, kiểm số lượng và giữ kiểm định Quy tắc bắt buộc. Lượng nhận, chấp nhận và từ chối là riêng biệt. Chỉ lượng chấp nhận được xếp kho để bán hoặc đối chiếu hóa đơn chuẩn._
- [ ] **grade 1** 03_#9 ⚠️ belongs to dev topics (fact appears in both sets) — hold/quarantine not sellable  
  _Columns: policy_id | policy_name | trigger | rule_or_required_action | owner | sla_or_frequency | approval | company | document_version | effective_status | source_basis Row 10: policy_id: INV-POL-010 | policy_name: Hàng lỗi / cách ly | trigger: SKU bị lỗi, nghi giả mạo, sai nhãn hoặc nghi sai lệch _

## T022 (test, multi_passage, expected answer)
**Q:** Yêu cầu mua đã được phê duyệt thì đã là cam kết chưa, và khi nào mới được phát hành PO?  
**Expected:** Chưa: yêu cầu không phải cam kết và phê duyệt không phải bằng chứng đã thực hiện; 'đã cam kết' là khi phát hành cam kết hợp lệ như PO, và PO chỉ phát hành sau khi hoàn tất kiểm tra yêu cầu, nhà cung cấp, nguồn cung, ngân sách và duyệt.
- [ ] **grade 1** VN#232 — states request precedes commitment  
  _Yêu cầu mua và luận chứng nghiệp vụ Yêu cầu mua ghi nhu cầu trước khi chọn nhà cung cấp hoặc cam kết._
- [ ] **grade 1** VN#294 — PO issued after request approval  
  _Bằng chứng bắt buộc PO đã phát hành, yêu cầu đã duyệt, xác nhận nhà cung cấp, điều kiện và lịch sử sửa._
- [ ] **grade 1** 01_#13 ⚠️ belongs to dev topics (fact appears in both sets) — mentions timing before PO issuance  
  _10. Phê duyệt và xử lý ngoại lệ Columns: Loại quyết định | Luồng phê duyệt | Thời điểm Row 1: Loại quyết định: Đề xuất PO trong ngân sách và trong tham số đã duyệt | Luồng phê duyệt: Planner → Procurement Manager | Thời điểm: Theo quy trình mua hàng hiện hành Row 2: Loại quyết định: PO vượt ngân sác_
- [ ] **grade 1** VN#223 ⚠️ belongs to dev topics (fact appears in both sets) — approval required before PO  
  _Quy trình bắt buộc Được duyệt trước khi phát hành PO hoặc chấp nhận điều kiện nhà cung cấp._
- [ ] **grade 1** 01_#5 ⚠️ belongs to dev topics (fact appears in both sets) — checks required before PO release  
  _4. Chính sách bổ sung hàng Mô hình tham chiếu cho SKU có nhu cầu tương đối ổn định: Inventory position = On-hand + Open PO − Backorder Reorder Point (ROP) = Nhu cầu/ngày × (Lead time + Safety days) Target Stock = Nhu cầu/ngày × (Lead time + Safety days + Review period) Giả định khởi tạo trong bộ mô _

## T023 (test, multi_passage, expected answer)
**Q:** Tác tử AI có được phát hành PO hay trả hóa đơn không, và nếu hai nguồn đã duyệt mâu thuẫn thì xử lý ra sao?  
**Expected:** Không: tác tử AI không được duyệt chi, phát hành PO, trả hóa đơn, điều chỉnh tồn hay cấp quyền trừ luồng được phê duyệt riêng; nếu hai nguồn đã duyệt mâu thuẫn, tạm dừng hành động tự động liên quan và chuyển chủ sở hữu chịu trách nhiệm.
- judge note: No passage states AI cannot trả hóa đơn; reference answer exceeds evidence.
- [ ] **grade 1** 01_#2 ⚠️ belongs to dev topics (fact appears in both sets) — AI only supports, not issue PO; conflict rule present  
  _1. Mục đích và nguyên tắc Tài liệu thiết lập cách kiểm soát hàng hóa từ lúc lập kế hoạch bổ sung đến khi nhận, lưu kho, kiểm kê, xử lý hàng trả về và thanh lý. Mục tiêu là cân bằng mức độ sẵn hàng, chi phí lưu kho, vốn bị chiếm dụng và độ chính xác của dữ liệu. Một nguồn dữ liệu chuẩn cho mỗi SKU; m_
- [ ] **grade 1** 01_#14 ⚠️ belongs to dev topics (fact appears in both sets) — Prohibits AI PO, defines DATA CONFLICT handling  
  _11. Kiểm soát chất lượng dữ liệu Trong inventory.csv, 67.3% bản ghi có stockout_flag=1, 76.3% có overstock_flag=1, 30,495 bản ghi bật đồng thời hai cờ, và tổng reorder_flag bằng 0. Trên snapshot 2022-12-31, 232 SKU bật đồng thời stockout_flag và overstock_flag. Đây là tín hiệu cần xác minh, không ph_
- [ ] **grade 1** 05_#7 — AI cannot self‑issue PO, conflict → DATA CONFLICT  
  _07 | Dữ liệu sạch trước khi tự động hóa Đối với Inventory / RAG Agent 1. Giữ snapshot date và source file. 2. Trả lời kèm policy_id và trích dẫn nguồn. 3. Không suy đoán lead time / currency / PO. 4. Mâu thuẫn → DATA CONFLICT. 5. Không tự ghi PO hoặc điều chỉnh tồn. Lộ trình triển khai • Chuẩn hóa m_
- [ ] **grade 1** 05_#2 — AI only proposes, no self‑PO; conflict escalation  
  _02 | Mô hình vận hành Tách quyền ra quyết định khỏi thao tác nhập liệu. PLAN Forecast / campaign ROP & target stock → APPROVE Budget / supplier PO authorization → RECEIVE PO match QC & put-away → CONTROL Cycle count Exception handling → LEARN KPI / root cause Forecast update Nguyên tắc kiểm soát: ng_
- [ ] **grade 1** 03_#11 ⚠️ belongs to dev topics (fact appears in both sets) — Rule bans AI PO, conflict transferred to approver  
  _Columns: policy_id | policy_name | trigger | rule_or_required_action | owner | sla_or_frequency | approval | company | document_version | effective_status | source_basis Row 12: policy_id: INV-POL-012 | policy_name: AI / báo cáo tự động | trigger: AI Agent tạo câu trả lời hoặc đề xuất PO | rule_or_r_
- [ ] **grade 1** 04_#8 ⚠️ belongs to dev topics (fact appears in both sets) — Specifies AI cannot self‑issue PO, conflict handling  
  _Policy Matrix Columns: Policy ID | Chính sách | Trigger | Hành động bắt buộc | Owner | SLA / Tần suất | Approval Row 11: Policy ID: INV-POL-011 | Chính sách: KPI và cảnh báo | Trigger: Báo cáo vận hành định kỳ | Hành động bắt buộc: Theo dõi fill rate, stockout rate, inventory accuracy, days of suppl_

## T024 (test, multi_passage, expected answer)
**Q:** Người đề nghị hoàn chi có được là người duyệt duy nhất không, và người đếm có được tự duyệt điều chỉnh tồn trọng yếu không?  
**Expected:** Không cho cả hai: người đề nghị không được là người duyệt duy nhất cho hoàn chi; người đếm không được là người duyệt duy nhất cho điều chỉnh tồn trọng yếu.
- [ ] **grade 2** VN#49 ⚠️ belongs to dev topics (fact appears in both sets) — States both requester and count cannot be sole approver  
  _Vai trò, trách nhiệm giải trình và phân tách nhiệm vụ Quy tắc bắt buộc. Người đề nghị quyền lợi hoặc cam kết không được là người duy nhất cho phép thực hiện. Người nhận hàng thực tế hoặc kiểm kê không được độc lập duyệt chênh lệch trọng yếu do chính mình phát hiện._
- [ ] **grade 1** 02_#0 — Requires independent approver for count adjustments  
  _VÀ ĐIỀU CHỈNH TỒN KHO VietStyle Commerce • SOP-INV-002 • Tài liệu mô phỏng Trang 1 VIETSTYLE COMMERCE SOP-INV-002 QUY TRÌNH KIỂM KÊ VÀ ĐIỀU CHỈNH TỒN KHO Phiên bản v1.0 • 16/10/2026 • Chủ sở hữu: Inventory Manager TÀI LIỆU MÔ PHỎNG CHO DATATHON 2026. Các ngưỡng vận hành, lead time, KPI và cấp phê du_
- [ ] **grade 1** 01_#2 ⚠️ belongs to dev topics (fact appears in both sets) — Segregates count, entry, approval roles  
  _1. Mục đích và nguyên tắc Tài liệu thiết lập cách kiểm soát hàng hóa từ lúc lập kế hoạch bổ sung đến khi nhận, lưu kho, kiểm kê, xử lý hàng trả về và thanh lý. Mục tiêu là cân bằng mức độ sẵn hàng, chi phí lưu kho, vốn bị chiếm dụng và độ chính xác của dữ liệu. Một nguồn dữ liệu chuẩn cho mỗi SKU; m_
- [ ] **grade 1** 05_#2 — Explicit segregation of duties  
  _02 | Mô hình vận hành Tách quyền ra quyết định khỏi thao tác nhập liệu. PLAN Forecast / campaign ROP & target stock → APPROVE Budget / supplier PO authorization → RECEIVE PO match QC & put-away → CONTROL Cycle count Exception handling → LEARN KPI / root cause Forecast update Nguyên tắc kiểm soát: ng_
- [ ] **grade 1** 02_#6 — Approver must be independent of counter  
  _Columns: Bước | Đầu ra bắt buộc Row 1: Bước: 1. Chuẩn bị | Đầu ra bắt buộc: Danh sách SKU / vị trí, phạm vi đếm, thời điểm freeze giao dịch nếu cần Row 2: Bước: 2. Đếm độc lập | Đầu ra bắt buộc: Số lượng thực tế; người đếm; thời gian; ảnh / ghi chú ngoại lệ Row 3: Bước: 3. Đối chiếu | Đầu ra bắt buộ_
- [ ] **grade 1** VN#453 — Material adjustments need independent approval  
  _Điều chỉnh, ghi giảm và sửa tồn kho Quy tắc bắt buộc. Mọi điều chỉnh trọng yếu cần bằng chứng tình trạng hoặc giao dịch thực, mã lý do, người duyệt độc lập và hồ sơ trước/sau được giữ._
- [ ] **grade 2** EN#46 ⚠️ belongs to dev topics (fact appears in both sets) — Mandates requester and counter not sole approvers  
  _Roles, accountability and segregation of duties Mandatory rule. The person requesting a benefit or commitment must not be the sole person authorizing it. A person performing a physical receipt or stock count must not independently approve a material discrepancy they identified._
- [ ] **grade 1** EN#489 — Count cannot be sole approver of material adjustment  
  _Control requirements  The person who performed the count cannot be the sole approver of a material adjustment._
- [ ] **grade 1** VN#115 ⚠️ belongs to dev topics (fact appears in both sets) — Requester cannot self‑approve request  
  _Yêu cầu kiểm soát Người đề nghị không được tự duyệt yêu cầu.  Từ chối phải nêu lý do liên quan công việc và không vi phạm quyền nghỉ được bảo vệ._

## T025 (test, multi_passage, expected answer)
**Q:** Phát hiện kiểm toán trọng yếu chưa xử lý thì chuyển cho ai, và bản chính sách lỗi thời có còn được truy xuất không?  
**Expected:** Phát hiện trọng yếu chưa xử lý chuyển Hội đồng Điều hành Vận hành; bản lỗi thời được rút khỏi truy xuất đang hoạt động nhưng vẫn giữ để phục vụ kiểm toán.
- [ ] **grade 2** VN#66 — Old versions kept for audit, not presented as current  
  _Kiểm soát tài liệu, thứ tự ưu tiên và rà soát Quy tắc bắt buộc. Phiên bản hiện hành đã duyệt là căn cứ duy nhất cho chủ đề chính sách mà nó điều chỉnh. Có thể giữ bản cũ để kiểm toán nhưng không trình bày như hướng dẫn hiện hành._

## T027 (test, table, expected answer)
**Q:** Theo Phụ lục C, đơn mua hàng phải có những trường tối thiểu nào?  
**Expected:** Số PO; nhà cung cấp; ngày phát hành; tiền tệ; dòng hàng; số lượng; đơn giá; điều kiện giao/thanh toán.
- [ ] **grade 2** VN#289 — Lists all required PO fields  
  _Quy trình bắt buộc Cấp số PO duy nhất trong hệ thống mua sắm.  Ghi nhà cung cấp, ngày phát hành, địa chỉ giao, tiền tệ, điều kiện thanh toán, mô tả dòng, mã sản phẩm, số lượng và đơn giá._

## T030 (test, table, expected answer)
**Q:** Theo Phụ lục B, cam kết trên 200 triệu cần điều kiện bổ sung gì?  
**Expected:** Trên 200.000.000 VND: Hội đồng Điều hành Vận hành + Tài chính duyệt; điều kiện bổ sung là đánh giá nguồn cung và rà rủi ro được lập hồ sơ.
- [ ] **grade 2** EN#781 — states documented sourcing evaluation and risk review  
  _Appendix B - Approval limits and operational decision table Columns: Total commitment | Required approval | Additional condition Row 1: Total commitment: Up to VND 5,000,000 | Required approval: Line manager | Additional condition: One documented quote; budget confirmed. Row 2: Total commitment: VND_

## T036 (test, false_premise, expected answer)
**Q:** Yêu cầu mua đã được duyệt rồi nên coi như đơn hàng đã đặt xong đúng không?  
**Expected:** Không: phê duyệt không phải bằng chứng đã thực hiện; chỉ 'đã cam kết' khi phát hành cam kết hợp lệ như PO, và 'đã hoàn thành' khi sự kiện thực tế đã diễn ra và được đối chiếu.
- [ ] **grade 1** VN#287 — states PO as approved commitment, not execution  
  _Tạo và phát hành đơn mua hàng PO truyền đạt cam kết đã duyệt và điều kiện làm căn cứ nhận, thanh toán hàng hoặc dịch vụ._

## T039 (test, false_premise, expected answer)
**Q:** Khi tồn kho thấp thì AI agent được tự phát hành PO để bổ sung đúng không?  
**Expected:** Không: tín hiệu đặt lại chỉ kích hoạt rà bổ sung, không tự tạo PO; tác tử AI không được phát hành PO trừ luồng được phê duyệt và kiểm toán riêng.
- [ ] **grade 2** 05_#2 — AI Agent không tự phát hành PO  
  _02 | Mô hình vận hành Tách quyền ra quyết định khỏi thao tác nhập liệu. PLAN Forecast / campaign ROP & target stock → APPROVE Budget / supplier PO authorization → RECEIVE PO match QC & put-away → CONTROL Cycle count Exception handling → LEARN KPI / root cause Forecast update Nguyên tắc kiểm soát: ng_
- [ ] **grade 2** 01_#2 ⚠️ belongs to dev topics (fact appears in both sets) — Không phát hành PO tự động, AI chỉ hỗ trợ  
  _1. Mục đích và nguyên tắc Tài liệu thiết lập cách kiểm soát hàng hóa từ lúc lập kế hoạch bổ sung đến khi nhận, lưu kho, kiểm kê, xử lý hàng trả về và thanh lý. Mục tiêu là cân bằng mức độ sẵn hàng, chi phí lưu kho, vốn bị chiếm dụng và độ chính xác của dữ liệu. Một nguồn dữ liệu chuẩn cho mỗi SKU; m_
- [ ] **grade 2** 05_#7 — Không tự ghi PO hoặc điều chỉnh tồn  
  _07 | Dữ liệu sạch trước khi tự động hóa Đối với Inventory / RAG Agent 1. Giữ snapshot date và source file. 2. Trả lời kèm policy_id và trích dẫn nguồn. 3. Không suy đoán lead time / currency / PO. 4. Mâu thuẫn → DATA CONFLICT. 5. Không tự ghi PO hoặc điều chỉnh tồn. Lộ trình triển khai • Chuẩn hóa m_
- [ ] **grade 2** 01_#14 ⚠️ belongs to dev topics (fact appears in both sets) — Không để AI tự phát hành PO  
  _11. Kiểm soát chất lượng dữ liệu Trong inventory.csv, 67.3% bản ghi có stockout_flag=1, 76.3% có overstock_flag=1, 30,495 bản ghi bật đồng thời hai cờ, và tổng reorder_flag bằng 0. Trên snapshot 2022-12-31, 232 SKU bật đồng thời stockout_flag và overstock_flag. Đây là tín hiệu cần xác minh, không ph_
- [ ] **grade 2** 04_#8 ⚠️ belongs to dev topics (fact appears in both sets) — AI không tự ghi PO, cần human approval  
  _Policy Matrix Columns: Policy ID | Chính sách | Trigger | Hành động bắt buộc | Owner | SLA / Tần suất | Approval Row 11: Policy ID: INV-POL-011 | Chính sách: KPI và cảnh báo | Trigger: Báo cáo vận hành định kỳ | Hành động bắt buộc: Theo dõi fill rate, stockout rate, inventory accuracy, days of suppl_
- [ ] **grade 2** 03_#11 ⚠️ belongs to dev topics (fact appears in both sets) — AI không tự ghi PO, cần human approval  
  _Columns: policy_id | policy_name | trigger | rule_or_required_action | owner | sla_or_frequency | approval | company | document_version | effective_status | source_basis Row 12: policy_id: INV-POL-012 | policy_name: AI / báo cáo tự động | trigger: AI Agent tạo câu trả lời hoặc đề xuất PO | rule_or_r_
- [ ] **grade 2** 02_#3 — Không tự động đặt hàng khi dữ liệu mâu thuẫn  
  _7. Cập nhật hệ thống và đóng phiếu Ngưỡng xử lý và phê duyệt Tình huống Hành động tối thiểu Người duyệt Không chênh lệch Đóng phiếu; lưu audit trail Warehouse Supervisor Chênh lệch nhỏ, có nguyên nhân rõ và bằng chứng Recount + biên bản; cập nhật sau duyệt Inventory Controller / Supervisor Chênh lệc_

## T040 (test, false_premise, expected answer)
**Q:** Đã đổi lịch làm rồi thì coi như chứng minh được là có làm thêm giờ đúng không?  
**Expected:** Không: đổi lịch không chứng minh đã làm thêm; nhân viên ghi giờ thực tế vào hệ thống chấm công và quản lý xác nhận giờ thực.
- [ ] **grade 1** VN#152 — must report actual hours, schedule change not enough  
  _Làm thêm, đổi lịch và bỏ ca Quy tắc bắt buộc. Làm thêm cần duyệt trước, trừ khẩn cấp hoặc quy định pháp luật khiến không thể duyệt trước; nhân viên phải báo giờ thực tế kịp thời._
- [ ] **grade 1** VN#141 ⚠️ belongs to dev topics (fact appears in both sets) — salary dept reviews changes, not proof alone  
  _Quy trình bắt buộc Bộ phận lương rà mọi thay đổi ảnh hưởng giờ trả lương, làm thêm hoặc khấu trừ._
- [ ] **grade 1** VN#151 — exception schedule recorded to compare with actual work  
  _Làm thêm, đổi lịch và bỏ ca Ngoại lệ lịch làm phải được phép và ghi nhận để đối chiếu công thực tế, an toàn và xử lý lương._
- [ ] **grade 1** VN#158 — requires actual hours and explanation for pay  
  _Bằng chứng bắt buộc Thay đổi lịch, duyệt trước, giờ thực tế, giải thích chênh lệch và quyết định lương._
- [ ] **grade 1** VN#118 ⚠️ belongs to dev topics (fact appears in both sets) — system records official hours, schedule not authoritative  
  _Sự phù hợp hệ thống và dữ liệu Dùng hệ thống nhân sự làm nguồn ghi nhận chính thức. Lịch hoặc tin nhắn có thể hỗ trợ trao đổi nhưng không phải hồ sơ phê duyệt có thẩm quyền._
- [ ] **grade 1** VN#140 ⚠️ belongs to dev topics (fact appears in both sets) — manager verifies with schedule or other evidence  
  _Quy trình bắt buộc Quản lý xác minh với lịch hoặc bằng chứng hợp pháp khác._
- [ ] **grade 1** VN#90 ⚠️ belongs to dev topics (fact appears in both sets) — evidence required beyond schedule change  
  _Bằng chứng bắt buộc Tham chiếu hồ sơ lao động, căn cứ quyền nghỉ, kỳ tính, tích lũy, điều chỉnh, ngày đã dùng và số dư trong hệ thống nhân sự._

## T045 (test, language, expected answer)
**Q:** Three-way match gồm những chứng từ nào?  
**Expected:** Đối chiếu ba bên giữa PO đã phát hành, biên bản nhận được chấp nhận và hóa đơn nhà cung cấp; dịch vụ dùng xác nhận nghiệm thu thay phiếu nhận hàng.
- [ ] **grade 2** VN#322 — Lists PO, receipt, invoice – three-way match  
  _Bằng chứng bắt buộc PO, phiếu nhận, hóa đơn, kết quả khớp, duyệt ngoại lệ và xác nhận thanh toán._
- [ ] **grade 2** EN#339 — Specifies PO, receipt, invoice required  
  _Required evidence PO, receipt, invoice, match result, exception approval and payment confirmation._

## T046 (test, noisy, expected answer)
**Q:** lam them gio co can xin duyet truoc khong  
**Expected:** Có: làm thêm cần duyệt trước, trừ khẩn cấp hoặc quy định pháp luật khiến không thể duyệt trước; nhân viên phải báo giờ thực tế kịp thời.
- [ ] **grade 1** VN#645 ⚠️ belongs to dev topics (fact appears in both sets) — Requires exception request before action  
  _Điều kiện ngoại lệ và giải trình bắt buộc Quy tắc bắt buộc. Xin ngoại lệ trước hành động, trừ an toàn hoặc tính liên tục tức thời khiến không thể duyệt trước._
- [ ] **grade 1** EN#151 — Overtime changes must be authorized  
  _Overtime, schedule changes and missed shifts Schedule exceptions must be authorized and recorded so actual work, safety and payroll treatment can be reconciled._

## T048 (test, noisy, expected answer)
**Q:** hóa đơn ncc bị trùng số thì sử lý sao ạ  
**Expected:** Số hóa đơn trùng hoặc số tiền/ngày lặp phải được giữ lại để rà soát trước khi thanh toán.
- [ ] **grade 2** VN#734 — States hold duplicate invoice for review before payment  
  _Điều kiện chặn bổ sung bắt buộc Hóa đơn chưa khớp, nghi trùng hoặc hàng chưa chấp nhận: giữ thanh toán chờ xử lý._

## T050 (test, noisy, expected answer)
**Q:** sp trong kho bị lệch tên danh mục thì lấy theo bảng nào vậy m  
**Expected:** Dùng product_id làm khóa chuẩn; nếu tên hoặc loại trong inventory khác products thì lấy commerce.products làm metadata danh mục và đánh dấu lệch.
- [ ] **grade 1** VN#227 ⚠️ belongs to dev topics (fact appears in both sets) — states commerce.products is catalog reference  
  _Sự phù hợp hệ thống và dữ liệu Cơ sở dữ liệu chưa có bảng nhà cung cấp, yêu cầu mua hoặc PO. Ghi sự kiện mua sắm trong ERP/hệ thống mua sắm đã duyệt hoặc sổ được kiểm soát; commerce.products chỉ là tham chiếu danh mục._
- [ ] **grade 1** VN#725 ⚠️ belongs to dev topics (fact appears in both sets) — lists commerce.products with product_id key  
  _Phụ lục A - Tham chiếu lược đồ Supabase và quan hệ Columns: Bảng | Trường khóa | Cách diễn giải được phép Row 1: Bảng: commerce.products | Trường khóa: product_id (PK); product_name, category, segment, size, color, price, cogs | Cách diễn giải được phép: Danh tính sản phẩm chuẩn và thuộc tính mô tả _

## T055 (test, rbac, expected answer)
**Q:** Theo README của Inventory Planner, tín hiệu stockout được xác định thế nào?  
**Expected:** Stockout signal: stockout_days ≥ 1 hoặc fill_rate < 95% hoặc calculated days of supply ≤ 14 ngày.
- [ ] **grade 2** 02_#3 — states exact stockout signal definition  
  _7. Cập nhật hệ thống và đóng phiếu Ngưỡng xử lý và phê duyệt Tình huống Hành động tối thiểu Người duyệt Không chênh lệch Đóng phiếu; lưu audit trail Warehouse Supervisor Chênh lệch nhỏ, có nguyên nhân rõ và bằng chứng Recount + biên bản; cập nhật sau duyệt Inventory Controller / Supervisor Chênh lệc_
- [ ] **grade 1** 02_#1 — mentions stockout signal without full definition  
  _3. Chuẩn bị trước khi đếm VietStyle Commerce • SOP-INV-002 • Tài liệu mô phỏng Trang 2 1. Mục đích và phạm vi Áp dụng cho SKU thời trang và outdoor trong kho / điểm xử lý đơn của mô hình VietStyle Commerce. SOP bao gồm kiểm kê chu kỳ, kiểm kê theo sự kiện và điều chỉnh chênh lệch. Không dùng SOP này_

## T056 (test, follow_up, expected answer)
**Q:** thế 300 triệu thì sao?  
**Expected:** 300.000.000 VND trên 200.000.000 VND: Hội đồng Điều hành Vận hành cùng Tài chính phê duyệt, kèm đánh giá nguồn cung và rà rủi ro được lập hồ sơ.
- [ ] **grade 2** EN#781 — States >200M approval council+finance  
  _Appendix B - Approval limits and operational decision table Columns: Total commitment | Required approval | Additional condition Row 1: Total commitment: Up to VND 5,000,000 | Required approval: Line manager | Additional condition: One documented quote; budget confirmed. Row 2: Total commitment: VND_
