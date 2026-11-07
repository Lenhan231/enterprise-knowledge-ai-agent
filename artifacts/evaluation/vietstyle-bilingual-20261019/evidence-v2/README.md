# Evidence v2 — rà soát nhãn Việt/Anh

Đã đọc lại định nghĩa câu hỏi/yêu cầu của 20 ý; tập trung đối chiếu nguồn chi tiết Q11, Q12, Q13, Q18 và Q20 ở cả Việt/Anh. Đây không phải việc gán nhãn độc lập toàn bộ corpus; alternative vẫn có thể chưa đầy đủ. Nhãn do assistant rà soát sau khi đã thấy lỗi v1, nên kết quả v2 là đánh giá khám phá, chưa phải kết quả held-out để kết luận cải thiện model.

## Thay đổi từ v1

- Q11.conflict: chấp nhận thêm quy tắc stockout + hơn 120 ngày → DATA CONFLICT trong slide.
- Q11.block_checks và Q12.verify: thêm phương án AND(SOP checklist, slide kiểm tra giao dịch/nhu cầu). Giữ các chi tiết bắt buộc; một nửa phương án vẫn chưa đạt. Áp dụng cùng quy tắc cho câu liên quan Q12 thay vì chỉ sửa câu E5 bị mất điểm.
- Q18.no_guess: chuyển từ bằng chứng bắt buộc sang optional context. Q18.missing_inputs vẫn bắt buộc: phải lấy được bằng chứng dữ liệu PO/backorder không có và số 0 là placeholder. Không bịa số vẫn là yêu cầu hành vi của câu trả lời, cần đánh giá riêng ở generation.
- Q20.no_write: thêm registry có đầy đủ giới hạn truy cập, không tự ghi PO/tồn kho và yêu cầu duyệt; Q20.citation_snapshot nhận thêm cặp chỉ dẫn source citation + snapshot trong slide.
- Q20.human_approval: vẫn cần đúng luồng Planner → Procurement Manager. Giữ phương án cũ gồm cả hai dòng và thêm dòng luồng thông thường làm phương án hoàn chỉnh cho tình huống câu hỏi. Dòng ngoại lệ lên Operations/Finance được giữ thành optional context Q20.exception_approval; câu hỏi không nêu vượt ngân sách/SKU mới/campaign bất thường.
- Q20.conflict: thêm bundle hoàn chỉnh từ SOP + registry chỉ định Controller, không chấp nhận chỉ một câu chung chung “cần người duyệt”.

Giữ nguyên toàn bộ Q13: chuẩn bị chi tiết, blind count và quy tắc không xóa/sửa nguồn vẫn là kiểm soát bắt buộc. Bảng tóm tắt audit trail chưa đủ chứng minh toàn bộ kiểm soát. Q14 giữ nguyên hai component needs_policy_resolution; chưa tự chọn vai trò phê duyệt. Q12.conflict_block giữ nguồn trực tiếp về xung đột hai cờ, không coi riêng quy tắc stockout/DOS có điều kiện là đủ.

Mọi thay đổi before/after, exact quote, Unicode offsets và hash nguồn nằm trong annotation-changes.json và evidence.json. Không đổi source documents, câu hỏi, reference answers hay nhãn v1. Schema vẫn là phiên bản 1; label_version=2. Có 66 component: 61 required ready, 2 required chưa giải quyết, 3 optional; 198 span (99 mỗi ngôn ngữ), 19 intent đủ điều kiện.

## Code thay đổi

- validate_vietstyle_evidence.py: trước chỉ chạy v1 cố định; giờ có --folder để kiểm tra v2 riêng. Mặc định vẫn là v1. Tiêu đề REVIEW dùng dataset_id. Các kiểm tra hash/quote/location/derivation giữ nguyên.
- rescore_vietstyle_evidence.py: script mới đọc vector/ranking cũ, kiểm tra hash và tự tính lại top 10 rồi chấm bằng nhãn v2. Không tải model hoặc thay thứ hạng. Kiểm tra độc lập từng span bằng tập vị trí ký tự thay cho interval union. Kết quả mới tham chiếu hash của kết quả gốc; không sao chép vector hoặc sửa config gốc để giả thành một lần chạy encoder mới.
- tests/test_evidence_labels.py: 4 test mới cho cả hai ngôn ngữ, kiểm tra giữ nguyên version/source/question/Q13/Q14, phương án SOP+slide phải đủ hai phần, thiếu dữ liệu vẫn bắt buộc và duyệt chung chung không thay thế luồng duyệt cụ thể, bộ kiểm tra độc lập bắt lỗi span bị đánh đủ giả.

15 evidence tests qua; validator self-check từ chối quote bị sửa và nguồn sai ngôn ngữ. Tính lại và kiểm tra 240 thứ hạng cũ; không đổi vector/ranking. Kết quả trong ../dense-evidence-benchmark-v1/rescored-evidence-v2/comparison.md.

## Kết quả Việt→Việt

| Model | Full evidence v1 | Full evidence v2 |
|---|---:|---:|
| E5 multilingual base | 15/19 | 17/19 |
| BGE-M3 | 13/19 | 14/19 |
| Qwen3 0.6B | 13/19 | 14/19 |

E5 Q11 và Q18 được chấp nhận theo nhãn mới; Q13 vẫn thiếu chi tiết chuẩn bị/blind count/no-delete-history, Q20 còn thiếu luồng duyệt cụ thể. Q14 vẫn báo riêng. Mẫu số component giảm từ 62 xuống 61; phần trăm v1/v2 không biểu thị encoder tốt lên. Không đánh giá generation.

## Chạy kiểm tra/chấm lại

```bash
.venv/bin/python scripts/retrieval/validate_vietstyle_evidence.py --folder artifacts/evaluation/vietstyle-bilingual-20261019/evidence-v2 --self-check
.venv/bin/python -m unittest discover -s tests -p 'test_evidence*.py' -v
# Kết quả mặc định đã tồn tại: dùng thư mục mới khi lặp lại.
.venv/bin/python scripts/retrieval/rescore_vietstyle_evidence.py --output-dir artifacts/evaluation/vietstyle-evidence-v2-repeat
```

Các label/question/reference-answer file chỉ phục vụ đánh giá, không được index hoặc dùng để chọn/rank chunk. Không đổi production embedding/retrieval, database/index hoặc translation. Chưa commit.
