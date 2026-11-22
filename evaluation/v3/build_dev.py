"""Write artifacts/evaluation/vietstyle-v3/dev-v3.json from the hand-written items below (see SPEC.md).

Gold passages are written as (document, chunk_index, grade). A Vietnamese policy rule passage automatically
gets its English counterpart from rule_pairs.json at grade 1, so a correct English hit still counts.
"""
import json
from pathlib import Path

HERE = Path("artifacts/evaluation/vietstyle-v3")
VN = "VietStyle_Enterprise_Operating_Policy_v1.0_VN.pdf"
EN = "VietStyle_Enterprise_Operating_Policy_v1.0_EN.pdf"
MAN = "01_Inventory_Management_Policy_Manual.docx"
PLAN = "04_Inventory_Control_and_Reorder_Planner.xlsx"


def g(*refs):
    """refs: ints are VN chunks at grade 2; tuples are (document, index, grade)."""
    return [{"document": VN, "chunk_index": r, "grade": 2} if isinstance(r, int)
            else {"document": r[0], "chunk_index": r[1], "grade": r[2]} for r in refs]


def item(category, question, gold, must, reference, *, role="employee", language="vi", outcome="answer",
         must_not=(), facts=(), history=(), topic="", forbidden=()):
    return {"category": category, "question": question, "role": role, "language": language,
            "history": [{"question": q, "answer": a} for q, a in history], "expected_outcome": outcome,
            "gold": gold, "must_include": list(must), "must_not_include": list(must_not),
            "reference_answer": reference, "facts": list(facts), "topic": topic,
            "forbidden_documents": list(forbidden)}


ITEMS = [
    # lookup: one rule in one passage
    item("lookup", "Nhân viên làm đủ một năm được bao nhiêu ngày nghỉ phép năm có lương?", g(82), ["12"],
         "VietStyle cấp 12 ngày làm việc nghỉ phép năm có lương cho một năm làm việc đầy đủ, tính theo tỷ lệ nếu chưa đủ năm; quyền lợi theo luật hoặc hợp đồng có lợi hơn được ưu tiên.",
         topic="Điều kiện và quyền nghỉ phép"),
    item("lookup", "Đề nghị hoàn chi phí công việc phải nộp trong thời hạn bao lâu?", g(166), ["30 ngày"],
         "Nộp trong 30 ngày lịch kể từ ngày giao dịch hoặc ngày trở về từ chuyến công tác đã duyệt, lấy mốc muộn hơn.",
         topic="Điều kiện hoàn trả chi phí và chứng từ"),
    item("lookup", "Nếu phải mua khẩn mà không kịp xin duyệt trước, chậm nhất khi nào phải báo cho Tài chính?", g(332, (VN, 331, 1)),
         ["một ngày làm việc|1 ngày làm việc"],
         "Báo lãnh đạo được chỉ định và Tài chính sớm nhất có thể, không muộn hơn một ngày làm việc sau khi cam kết.",
         topic="Mua khẩn, chỉ định nguồn và rà soát sau mua"),
    item("lookup", "Quyền truy cập vào hệ thống nhạy cảm phải được rà soát định kỳ bao lâu một lần?", g(528, (VN, 210, 1)),
         ["quý"], "Rà quyền khi đổi vai trò và ít nhất mỗi quý đối với hệ thống nhạy cảm.",
         topic="Danh tính, yêu cầu truy cập và quyền tối thiểu"),
    item("lookup", "Khi muốn tăng giá trị hoặc số lượng trên một PO đã phát hành thì phải làm gì trước?", g(301, 302),
         ["rà|duyệt", "tổng cam kết|cấp duyệt"],
         "Thay đổi làm tăng giá trị, số lượng, phạm vi, rủi ro hoặc nghĩa vụ giao phải được rà soát trước khi chỉ đạo nhà cung cấp; so với PO và phê duyệt ban đầu, tính lại tổng cam kết và cấp duyệt.",
         topic="Thay đổi, hủy và cam kết đang mở"),

    # amount: thresholds written in different styles (dev holds tiers 1-2 only)
    item("amount", "Mua máy lọc nước 4tr5 thì ai duyệt?", g(274, 730), ["Quản lý trực tiếp|quản lý trực tiếp"],
         "4.500.000 VND thuộc mức đến 5.000.000 VND nên do quản lý trực tiếp phê duyệt; cần một báo giá có hồ sơ và ngân sách xác nhận.",
         must_not=["Trưởng bộ phận"], facts=["F3.tier1"], topic="Ma trận phê duyệt và ngưỡng tiền"),
    item("amount", "Đặt in áo cho team 12 củ thì cần mấy báo giá?", g(261, 730), ["hai|2"],
         "12.000.000 VND nằm trong khoảng 5.000.001–50.000.000 VND nên cần ít nhất hai báo giá tương đương nếu thị trường cho phép.",
         facts=["F2.tier2"], topic="Tìm nguồn cạnh tranh và đánh giá báo giá"),
    item("amount", "Mua văn phòng phẩm 500k có cần ai duyệt không?", g(274, 730), ["Quản lý trực tiếp|quản lý trực tiếp"],
         "500.000 VND thuộc mức đến 5.000.000 VND: quản lý trực tiếp phê duyệt, kèm một báo giá có hồ sơ và ngân sách xác nhận.",
         facts=["F3.tier1"], topic="Ma trận phê duyệt và ngưỡng tiền"),
    item("amount", "Hợp đồng dịch vụ đúng 50.000.000 VND thì cấp nào phê duyệt?", g(274, 730), ["Trưởng bộ phận|trưởng bộ phận"],
         "50.000.000 VND vẫn thuộc khoảng 5.000.001–50.000.000 VND nên trưởng bộ phận phê duyệt (chưa cần Mua sắm và Tài chính).",
         must_not=["Mua sắm và Tài chính", "Mua sắm + Tài chính"], facts=["F3.tier2"], topic="Ma trận phê duyệt và ngưỡng tiền"),
    item("amount", "Mua thiết bị 5 triệu thì quản lý trực tiếp tự duyệt được không?", g(274, 730), ["Quản lý trực tiếp|quản lý trực tiếp"],
         "Được: cam kết đến 5.000.000 VND (bao gồm đúng 5.000.000 VND) thuộc thẩm quyền quản lý trực tiếp.",
         must_not=["Trưởng bộ phận phê duyệt"], facts=["F3.tier1"], topic="Ma trận phê duyệt và ngưỡng tiền"),

    # calculation: arithmetic on the user's numbers
    item("calculation", "Nếu mua 3 lần, mỗi lần 2 triệu cho cùng một nhu cầu thì ai duyệt?", g(274, 730, 224),
         ["6.000.000|6 triệu", "Trưởng bộ phận|trưởng bộ phận"],
         "Duyệt theo tổng cam kết và không được chia nhỏ để tránh ngưỡng: 3 × 2.000.000 = 6.000.000 VND, thuộc 5.000.001–50.000.000 VND nên trưởng bộ phận phê duyệt.",
         must_not=["Quản lý trực tiếp phê duyệt"], facts=["F3.tier2", "F3.total"], topic="Ma trận phê duyệt và ngưỡng tiền"),
    item("calculation", "Tôi đã làm đủ 7 tháng thì đã tích lũy được bao nhiêu ngày phép năm?", g(84, 82), ["7"],
         "Phép năm tích lũy 1/12 quyền phép năm cho mỗi tháng làm việc hoàn tất; với 12 ngày/năm, 7 tháng tích lũy 7 ngày.",
         topic="Điều kiện và quyền nghỉ phép"),
    item("calculation", "Tôi có hóa đơn ngày 2/3, đi công tác về ngày 10/3. Hạn chót nộp đề nghị hoàn chi là ngày nào?", g(166),
         ["9/4|09/04|9 tháng 4"],
         "Hạn là 30 ngày lịch kể từ mốc muộn hơn giữa ngày giao dịch và ngày trở về, tức 10/3 + 30 ngày = 9/4.",
         topic="Điều kiện hoàn trả chi phí và chứng từ"),
    item("calculation", "Mua 2 laptop, mỗi cái 20 củ thì cần mấy báo giá và ai duyệt?", g(261, 274, 730),
         ["40.000.000|40 triệu", "hai|2", "Trưởng bộ phận|trưởng bộ phận"],
         "Tổng cam kết 2 × 20.000.000 = 40.000.000 VND, thuộc 5.000.001–50.000.000 VND: cần ít nhất hai báo giá tương đương và trưởng bộ phận phê duyệt.",
         facts=["F2.tier2", "F3.tier2", "F3.total"], topic="Ma trận phê duyệt và ngưỡng tiền"),
    item("calculation", "Mua khẩn được cam kết vào thứ Hai mà chưa kịp xin duyệt. Hạn báo Tài chính và hạn hoàn tất rà soát sau mua là khi nào?",
         g(332, 333), ["thứ Ba", "năm ngày làm việc|5 ngày làm việc"],
         "Phải báo lãnh đạo chỉ định và Tài chính không muộn hơn một ngày làm việc sau cam kết (thứ Ba), và hoàn tất rà soát nguồn cung, bằng chứng, phê duyệt trong năm ngày làm việc (đến thứ Hai tuần sau).",
         topic="Mua khẩn, chỉ định nguồn và rà soát sau mua"),

    # multi_part: two sub-questions in one message
    item("multi_part", "Nghỉ phép năm được bao nhiêu ngày và ai là người có quyền duyệt đơn nghỉ?", g(82, 109),
         ["12", "quản lý|Nhân sự ủy quyền"],
         "12 ngày làm việc có lương cho một năm làm việc đầy đủ; quyết định nghỉ do quản lý hoặc người được Nhân sự ủy quyền hợp lệ thực hiện.",
         topic="Điều kiện và quyền nghỉ phép"),
    item("multi_part", "Đề nghị hoàn chi phí cần những thông tin chứng từ gì, và nếu mất hóa đơn thì xử lý sao?", g(167, 169),
         ["biên nhận|hóa đơn", "Tài chính"],
         "Cần đơn vị bán, ngày, loại chi, số tiền, tiền tệ, mục đích và hóa đơn/biên nhận; nếu mất chứng từ phải giải trình và được Tài chính duyệt trước khi hoàn trả.",
         topic="Điều kiện hoàn trả chi phí và chứng từ"),
    item("multi_part", "Tiếp nhận nhà cung cấp mới cần thu thập thông tin gì, và khi nhà cung cấp đổi tài khoản ngân hàng thì làm sao?",
         g(248, 249, 253), ["pháp nhân|đăng ký", "độc lập"],
         "Thu tên pháp nhân, đăng ký/thuế, địa chỉ kinh doanh, liên hệ và đại diện có thẩm quyền; thay đổi ngân hàng phải xác minh qua kênh liên hệ lấy độc lập (gọi lại xác minh).",
         topic="Thẩm định và tiếp nhận nhà cung cấp"),
    item("multi_part", "Khóa bí mật và thông tin đăng nhập phải lưu ở đâu, và khi nào phải thay khóa?", g(553, 557),
         ["kho bí mật", "nghi|lộ|thay nhân sự"],
         "Lưu trong kho bí mật được duyệt hoặc cấu hình môi trường được bảo vệ với quyền tối thiểu; thay khóa sau thay nhân sự, lộ vô ý hoặc nghi xâm phạm.",
         topic="Bí mật, thông tin đăng nhập và cấu hình an toàn"),
    item("multi_part", "Khi nhận hàng cần ghi những số lượng nào, và hàng chưa rõ chất lượng thì để ở đâu?", g(468, 470, 471),
         ["chấp nhận", "từ chối", "khu giữ chất lượng|giữ chất lượng"],
         "Ghi riêng lượng giao thực, lượng chấp nhận và lượng từ chối; chỉ lượng chấp nhận được xếp kho. Hàng chưa rõ hoặc không đạt đưa vào khu giữ chất lượng có nhãn rõ.",
         topic="Nhận hàng, kiểm số lượng và giữ kiểm định"),

    # multi_passage: facts from different sections
    item("multi_passage", "Người kiểm kê có được tự duyệt chênh lệch lớn mà chính mình phát hiện không, và sai lệch trọng yếu khi kiểm kê thì xử lý thế nào?",
         g(49, 443), ["không", "độc lập"],
         "Không: người nhận hàng hoặc kiểm kê không được độc lập duyệt chênh lệch trọng yếu do mình phát hiện; sai lệch trọng yếu phải được người độc lập đếm lại và so với hệ thống tồn trực tiếp, ghi nguyên nhân trước khi điều chỉnh.",
         topic="Vai trò, trách nhiệm giải trình và phân tách nhiệm vụ"),
    item("multi_passage", "Khi hai cách hiểu chính sách xung đột thì làm gì, và nếu ma trận phê duyệt không có hàng nào khớp thì sao?",
         g(20, 673), ["chuyển cấp"],
         "Chuyển cấp xử lý xung đột trước khi cam kết, không chọn cách hiểu dễ dãi hơn; nếu không hàng nào của ma trận khớp thì dừng và chuyển cấp thay vì chọn hàng thuận tiện.",
         topic="Duy trì và diễn giải ma trận phê duyệt"),
    item("multi_passage", "Dữ liệu tồn kho trong Supabase kéo dài đến năm nào, và khi trả lời câu hỏi về tồn kho phải nêu điều gì?",
         g(392, 385, (VN, 365, 1)), ["2022", "ngày dữ liệu|snapshot"],
         "Snapshot tồn kho lịch sử từ 2012-07-31 đến 2022-12-31, không phải số dư trực tiếp; mọi câu trả lời tồn phải nêu ngày dữ liệu và không trình bày snapshot lịch sử như hàng đang khả dụng.",
         topic="Độ mới snapshot và báo cáo lịch sử"),
    item("multi_passage", "Tôi có thể xin ngoại lệ để dán khóa API vào prompt cho AI dùng tạm không?", g(650, 559),
         ["không"], "Không: không dán thông tin đăng nhập vào prompt AI, và ngoại lệ không miễn yêu cầu bảo mật không được miễn.",
         topic="Điều kiện ngoại lệ và giải trình bắt buộc"),
    item("multi_passage", "Câu trả lời của trợ lý AI có được tính là phê duyệt nghỉ phép không, và AI được làm gì với phê duyệt?",
         g(110, 23, (VN, 703, 1)), ["không"],
         "Không: yêu cầu nghỉ vẫn chờ đến khi quyết định được ghi nhận, câu trả lời do AI tạo không phải phê duyệt; đề xuất của trợ lý AI không phải phê duyệt hay giao dịch, và tác tử không được tạo phê duyệt.",
         topic="Phê duyệt, từ chối và thay đổi nghỉ phép"),

    # table: the answer is in a table row
    item("table", "Theo Phụ lục A, khóa chính của bảng commerce.order_items là gì?", g(726), ["order_item_id"],
         "commerce.order_items có khóa chính order_item_id (cùng các trường order_id, product_id, quantity, unit_price, discount_amount, promo_id, promo_id_2).",
         topic="Phụ lục A - Tham chiếu lược đồ Supabase và quan hệ"),
    item("table", "SKU nhóm A phải kiểm kê bao lâu một lần và chênh lệch phải điều tra trong thời hạn nào?", g((MAN, 6, 2)),
         ["hằng tuần|Hằng tuần", "trong ngày"],
         "Nhóm A (khoảng 80% giá trị tiêu thụ năm) kiểm kê hằng tuần và điều tra chênh lệch ngay trong ngày.",
         topic="01 Manual: Phân loại ABC và lịch kiểm kê"),
    item("table", "Fill rate xuống dưới bao nhiêu thì phải phát cảnh báo P1?", g((MAN, 8, 2)), ["95%"],
         "Mục tiêu mô phỏng fill rate ≥ 98%; dưới 95% thì cảnh báo P1 và phân tích nguyên nhân.",
         topic="01 Manual: Ngưỡng vận hành và KPI"),
    item("table", "PO vượt ngân sách hoặc cho SKU mới thì đi qua luồng phê duyệt nào?", g((MAN, 13, 2)),
         ["Procurement Manager", "Finance"],
         "PO vượt ngân sách, SKU mới hoặc campaign bất thường: Procurement Manager → Operations + Finance.",
         topic="01 Manual: Phê duyệt và xử lý ngoại lệ"),
    item("table", "Chính sách vận hành phiên bản 1.0 có hiệu lực từ ngày nào và do ai phê duyệt?", g(742),
         ["23", "Hội đồng Điều hành Vận hành"],
         "Phiên bản 1.0 có hiệu lực từ 23 tháng 10 năm 2026; chủ sở hữu/cấp phê duyệt là Bộ phận Quản trị Vận hành / Hội đồng Điều hành Vận hành.",
         topic="Phụ lục D - Hồ sơ quản trị và sửa đổi"),

    # not_covered: plausible but absent from the corpus (checked by grep on 17 Nov 2026)
    item("not_covered", "Công ty có hỗ trợ tiền gửi xe cho nhân viên không?", [], [],
         "Tài liệu được phép truy cập không đề cập hỗ trợ tiền gửi xe.", outcome="not_covered", topic="(absent)"),
    item("not_covered", "Nhân viên có được thưởng tháng 13 không, tính thế nào?", [], [],
         "Tài liệu không đề cập lương hoặc thưởng tháng 13.", outcome="not_covered", topic="(absent)"),
    item("not_covered", "Chính sách làm việc từ xa cho phép tối đa mấy ngày một tuần?", [], [],
         "Tài liệu không có chính sách làm việc từ xa.", outcome="not_covered", topic="(absent)"),
    item("not_covered", "Quy định về đồng phục khi đi làm là gì?", [], [],
         "Tài liệu không quy định về đồng phục hoặc trang phục.", outcome="not_covered", topic="(absent)"),
    item("not_covered", "Công ty có mua bảo hiểm sức khỏe cho người thân của nhân viên không?", [], [],
         "Tài liệu không đề cập bảo hiểm sức khỏe.", outcome="not_covered", topic="(absent)"),

    # false_premise: the question assumes something the documents contradict, or asks for an unsupported conclusion
    # A favourable contract can exceed 12 days (rule 82), so mentioning 15 x 6/12 as that case is allowed (judge run 17 Nov).
    item("false_premise", "Vì phép năm là 15 ngày, tôi làm 6 tháng thì được bao nhiêu ngày?", g(82, 84), ["12", "6"],
         reference="Tiền đề chưa đúng: VietStyle cấp 12 ngày phép năm (không phải 15); tích lũy 1/12 mỗi tháng nên 6 tháng là 6 ngày.",
         topic="Điều kiện và quyền nghỉ phép"),
    item("false_premise", "Đơn mua dưới 5 triệu thì tôi tự duyệt cho mình được đúng không?", g(21, 49, 274), ["không"],
         "Không: không nhân viên nào được tự duyệt yêu cầu của mình; khoản đến 5.000.000 VND do quản lý trực tiếp duyệt.",
         facts=["F3.tier1"], topic="Thẩm quyền, phạm vi và áp dụng chính sách"),
    item("false_premise", "Số tồn trong bảng commerce.inventory là số tồn kho hiện tại đúng không?", g(357, 392), ["không", "lịch sử"],
         "Không: commerce.inventory là dữ liệu phân tích lịch sử (đến 2022-12-31), không phải sổ tồn trực tiếp; số hiện tại chính thức nằm ở hệ thống quản lý kho được duyệt.",
         topic="Hồ sơ tồn kho, phạm vi và thứ bậc nguồn"),
    item("false_premise", "Nhà cung cấp báo giá miệng rồi nên tôi chốt mua luôn được phải không?", g(225), ["bản ghi|ghi lại", "xác nhận"],
         "Chưa: báo giá miệng phải được tóm tắt trong bản ghi có ngày và xác nhận trước khi cam kết.",
         topic="Nguyên tắc mua sắm và thẩm quyền chi"),
    item("false_premise", "Dựa vào snapshot tồn kho, hôm nay sản phẩm 1001 còn hàng để hứa giao cho khách không?", g(390, 417, 385),
         ["không|chưa", "lịch sử|xác minh"],
         "Không thể kết luận: snapshot chỉ là lịch sử; nếu hỏi 'bây giờ' chỉ được trả ngày lịch sử mới nhất kèm giới hạn và phải xác minh tồn trực tiếp, không hứa ngày giao theo dữ liệu lịch sử.",
         topic="Độ mới snapshot và báo cáo lịch sử"),

    # language: English and mixed Vietnamese-English
    item("language", "How many days of paid annual leave does an employee get for a full year?", g((EN, 79, 2), (VN, 82, 1)), ["12"],
         "VietStyle grants 12 working days of paid annual leave for a full year of service, pro-rated for partial years.",
         language="en", topic="Leave eligibility and entitlement"),
    item("language", "What is the deadline to submit an expense claim?", g((EN, 168, 2), (VN, 166, 1)), ["30"],
         "Within 30 calendar days of the transaction or the return from approved travel, whichever is later.",
         language="en", topic="Expense claim eligibility and documentation"),
    item("language", "Vendor đổi bank account thì phải verify thế nào?", g(249, 253, (EN, 263, 1)), ["độc lập|independent"],
         "Xác minh thay đổi ngân hàng qua kênh liên hệ lấy độc lập (gọi lại xác minh độc lập) trước khi chấp nhận.",
         language="mixed", topic="Thẩm định và tiếp nhận nhà cung cấp"),
    item("language", "Service-role key có được để trong client code không?", g(529, 556, (EN, 566, 1), (EN, 594, 1)), ["không|Không"],
         "Không: không lộ service-role hoặc khóa bí mật trong mã phía khách, notebook, ảnh chụp hay prompt; giữ service-role ở máy chủ.",
         language="mixed", topic="Bí mật, thông tin đăng nhập và cấu hình an toàn"),
    item("language", "Can I approve my own leave request?", g((EN, 113, 2), (VN, 115, 1), (EN, 21, 1)), ["no|cannot|not"],
         "No. The requester cannot approve their own request; leave decisions are made by the manager or an HR-authorised delegate.",
         language="en", topic="Leave approval, rejection and changes"),

    # noisy: no diacritics, typos, chat slang
    item("noisy", "cham cong bi sai thi xin sua nhu the nao", g(139, 140), ["lý do|ly do", "quản lý|quan ly"],
         "Nộp yêu cầu sửa gồm ngày, bản ghi gốc, giá trị đề nghị và lý do; quản lý xác minh với lịch hoặc bằng chứng hợp pháp khác.",
         topic="Ghi nhận và sửa chấm công"),
    item("noisy", "ê ku m coi giùm t, hàng khách trả về là đem bán lại liền đc ko?", g(496, 498, (MAN, 11, 1)), ["không|chưa"],
         "Không: bản ghi trả không tự nghĩa đã nhập lại kho; phải kiểm tình trạng rồi quyết định nhập lại, tân trang, cách ly, trả nhà cung cấp hoặc thanh lý.",
         topic="Trả hàng, điều kiện hoàn tiền và xử lý vật phẩm"),
    item("noisy", "sếp t im lặng ko rep đơn nghỉ, vậy coi như dc duyệt hả", g(110), ["không"],
         "Không: yêu cầu vẫn chờ đến khi quyết định được ghi nhận; im lặng, mục lịch hoặc câu trả lời AI không phải phê duyệt.",
         topic="Phê duyệt, từ chối và thay đổi nghỉ phép"),
    item("noisy", "nhà cc báo giá mịêng thì có cần lưu lại j ko ạ", g(225), ["bản ghi|ghi", "ngày"],
         "Có: báo giá miệng phải được tóm tắt trong bản ghi có ngày và xác nhận trước khi cam kết.",
         topic="Nguyên tắc mua sắm và thẩm quyền chi"),
    item("noisy", "truoc campaign bao lau thi phai chot forecast ton kho", g((MAN, 12, 2)), ["4 tuần|4 tuan"],
         "Tối thiểu 4 tuần trước campaign, Merchandising và Planner thống nhất forecast theo SKU/size/màu.",
         topic="01 Manual: Khuyến mãi và mùa vụ"),

    # rbac: the same information for a role without access (not covered, nothing from the restricted document) and with access
    item("rbac", "Hàng tồn trên 240 ngày thì ai đánh giá dự phòng giảm giá trị?", [], [],
         "Vai trò legal_compliance không được xem Bộ chính sách quản lý tồn kho (01); câu trả lời phải là không có trong tài liệu được phép, không lộ nội dung 01.",
         role="legal_compliance", outcome="not_covered", forbidden=[MAN], topic="01 Manual (restricted)"),
    item("rbac", "Theo bộ chính sách tồn kho, hàng tồn trên 240 ngày thì ai đánh giá dự phòng giảm giá trị?", g((MAN, 10, 2)),
         ["Inventory Manager", "Finance"],
         "Trên 240 ngày tồn: Inventory Manager và Finance đánh giá dự phòng giảm giá trị / loại bỏ theo quy định kế toán.",
         role="finance_analyst", topic="01 Manual: Hàng dư thừa và chậm luân chuyển"),
    item("rbac", "Theo KPI Summary của Inventory Planner, nhóm Outdoor có bao nhiêu SKU?", [], [],
         "Vai trò executive không được xem Inventory Planner (04); câu trả lời phải là không có trong tài liệu được phép.",
         role="executive", outcome="not_covered", forbidden=[PLAN], topic="04 Planner (restricted)"),
    item("rbac", "Trong KPI Summary của Inventory Planner, Outdoor có bao nhiêu SKU?", g((PLAN, 433, 2)), ["144"],
         "Theo KPI Summary, nhóm Outdoor có 144 SKU.", role="procurement", topic="04 Planner: KPI Summary"),
    item("rbac", "Khi chưa đủ lịch sử nhu cầu thì nhóm ABC tạm được rà soát lại sau bao lâu?", g((MAN, 7, 2)), ["3 chu kỳ|ba chu kỳ"],
         "ABC tính từ annual consumption value; khi chưa có lịch sử đủ tin cậy thì dùng nhóm tạm và rà soát sau 3 chu kỳ.",
         role="admin", topic="01 Manual: Phân loại ABC và lịch kiểm kê"),

    # follow_up: needs the previous turn
    item("follow_up", "còn nếu 30 triệu thì sao?", g(274, 261, 730), ["Trưởng bộ phận|trưởng bộ phận", "hai|2"],
         "30.000.000 VND thuộc 5.000.001–50.000.000 VND: trưởng bộ phận phê duyệt và cần ít nhất hai báo giá tương đương.",
         facts=["F3.tier2", "F2.tier2"], history=[("Mua máy in 4 triệu thì ai duyệt?",
         "4.000.000 VND thuộc mức đến 5.000.000 VND nên quản lý trực tiếp phê duyệt.")], topic="Ma trận phê duyệt và ngưỡng tiền"),
    item("follow_up", "nếu tôi mới làm được 3 tháng thì sao?", g(84, 82), ["3"],
         "Tích lũy 1/12 quyền phép năm mỗi tháng làm việc hoàn tất: 3 tháng tương ứng 3 ngày.",
         history=[("Phép năm được bao nhiêu ngày?", "VietStyle cấp 12 ngày làm việc nghỉ phép năm có lương cho một năm làm việc đầy đủ.")],
         topic="Điều kiện và quyền nghỉ phép"),
    item("follow_up", "lỡ làm mất hóa đơn thì sao?", g(169), ["Tài chính", "giải trình"],
         "Nếu mất chứng từ phải giải trình và được Tài chính duyệt trước khi hoàn trả.",
         history=[("Hoàn chi phí phải nộp trong bao lâu?", "Trong 30 ngày lịch kể từ giao dịch hoặc ngày trở về chuyến công tác, lấy mốc muộn hơn.")],
         topic="Điều kiện hoàn trả chi phí và chứng từ"),
    item("follow_up", "vậy nếu không kịp xin duyệt trước thì phải làm gì?", g(332, 333), ["một ngày làm việc|1 ngày làm việc", "năm ngày làm việc|5 ngày làm việc"],
         "Báo lãnh đạo chỉ định và Tài chính không muộn hơn một ngày làm việc sau cam kết, và hoàn tất rà soát trong năm ngày làm việc.",
         history=[("Khi nào được mua khẩn?", "Mua khẩn giới hạn cho tình huống an toàn tức thời, liên tục dịch vụ hoặc tổn thất kinh doanh trọng yếu khi không thể theo thời gian thông thường.")],
         topic="Mua khẩn, chỉ định nguồn và rà soát sau mua"),
    item("follow_up", "thế ai duyệt và ai thực hiện cấp quyền?", g(527), ["Chủ dữ liệu|chủ dữ liệu", "chủ hệ thống"],
         "Chủ dữ liệu duyệt và chủ hệ thống thực hiện cấp quyền, dùng tài khoản cá nhân và xác thực đa yếu tố.",
         history=[("Muốn xin quyền truy cập hệ thống thì làm sao?", "Gửi yêu cầu qua bàn hỗ trợ hoặc luồng quản lý danh tính, nêu mục đích, tài nguyên, mức quyền và ngày kết thúc nếu tạm.")],
         topic="Danh tính, yêu cầu truy cập và quyền tối thiểu"),
]


def write(set_name, prefix, items):
    pairs = {int(k): v for k, v in json.load(open(HERE / "rule_pairs.json")).items()}
    pooled = {}
    if (HERE / "pooled_gold.json").exists():
        for extra in json.load(open(HERE / "pooled_gold.json", encoding="utf-8")):
            if extra.get("approved"):
                pooled.setdefault(extra["id"], []).append(extra)
    out = []
    for number, entry in enumerate(items, 1):
        gold, seen = list(entry["gold"]), {(x["document"], x["chunk_index"]) for x in entry["gold"]}
        for x in entry["gold"]:
            en = pairs.get(x["chunk_index"]) if x["document"] == VN else None
            if en is not None and (EN, en) not in seen:
                gold.append({"document": EN, "chunk_index": en, "grade": 1})
                seen.add((EN, en))
        item_id = f"{prefix}{number:03d}"
        # Human-approved passages from pooled relevance judging (judge job 2); never part of authoring.
        for extra in pooled.get(item_id, []):
            if (extra["document"], extra["chunk_index"]) not in seen:
                gold.append({"document": extra["document"], "chunk_index": extra["chunk_index"], "grade": extra["grade"], "source": "pool"})
                seen.add((extra["document"], extra["chunk_index"]))
        out.append({"id": item_id, **entry, "gold": gold})
    json.dump({"set": f"vietstyle-{set_name}-v3", "spec": "SPEC.md", "items": out},
              open(HERE / f"{set_name}-v3.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(len(out), set_name, "items written")


if __name__ == "__main__":
    write("dev", "D", ITEMS)
