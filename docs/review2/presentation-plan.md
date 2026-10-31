# Kế hoạch Review 2 — Enterprise Knowledge AI Agent (RAG)

Ngày soạn: 22/10/2026. Bản nháp theo checklist giảng viên và bằng chứng hiện có trên Huy.
Nguồn: `review2-task2-checklist.docx` (bản sao nguyên file vừa tải).
Khung slide cho nhóm; phần Huy có huy-retrieval-report.vi.md và huy-speaking-notes.vi.md. Chưa tạo deck hoàn chỉnh.
Thời lượng tạm tính: 20 phút trình bày + 5 phút phản biện; cần xác nhận với nhóm/GV.
Tên người và lịch review chưa được xác nhận, nên phân công theo vai trò.

## 1. Cách đọc checklist cho nhóm RAG

Mục tiêu: chứng minh pipeline RAG hoạt động, đánh giá được từng khâu và cải tiến có căn cứ. Proposal ghi rõ không train LLM từ đầu; nhóm sử dụng pretrained models, xây dựng ingestion/retrieval/generation và đánh giá.

| Yêu cầu trong file GV | Áp dụng cho nhóm mình | Cần trình ra |
|---|---|---|
| Nguồn dữ liệu, số mẫu, định dạng, dung lượng | Có | Tách dữ liệu mô phỏng, public/historical và corpus đánh giá; thống kê file/chunk/token theo snapshot |
| Cleaning, dedup, missing, chuẩn hóa | Có | Flowchart + code/config + ví dụ trước/sau; chỉ nói các bước thực sự đã làm |
| Gán nhãn và chất lượng nhãn | Có, trên bộ câu hỏi/evidence | Ai soạn, ai duyệt, quy tắc evidence component/alternative, ngày freeze/hash |
| Train/Val/Test | Điều chỉnh theo bài toán | Không có tập train supervised nếu không fine-tune. Phân biệt corpus truy hồi, development questions, independent test questions |
| Class distribution / imbalance | Không ép thành bài toán phân loại | Đổi sang coverage theo loại file, ngôn ngữ, loại câu hỏi, bảng/văn bản. Nói rõ không có nhãn class để oversample |
| Oversampling / augmentation / Grad-CAM / loss curve | Không áp dụng nếu không training | Giải thích ngắn; không tự thêm SMOTE, accuracy/F1 phân loại hay loss giả |
| Leakage / duplicates | Vẫn bắt buộc kiểm tra | Câu hỏi paraphrase/VI–EN cùng intent không được tính như mẫu độc lập; kiểm tra overlap giữa bộ cũ và bộ mới |
| Chunking, embedding, vector DB, metadata, grounding | Trọng tâm | Ví dụ từ nguồn → parser chunk → token-bounded chunk → vector → citation |
| 2 baseline | Vẫn cần | Chốt hai cấu hình đối chứng với nhóm/GV; chỉ ra chính xác khác nhau ở module nào |
| Paper vs Group / Gap analysis | Vẫn cần, nhưng đúng phạm vi | Nêu paper, dataset, metric, cấu hình; không trừ hai con số khác dataset/metric rồi gọi là gap có ý nghĩa |
| Mean ± std / seeds | Điều chỉnh | Nhóm không train nên không bịa seed/epoch/loss. Với retrieval cố định, giải thích tính cố định; kiểm tra độ biến thiên dịch/LLM và latency nếu có lặp |
| Failure cases / ablation / latency / khả thi | Có | Ca lỗi cụ thể, bảng thêm module, đo thời gian đúng từng stage và phần cứng |
| Microservices / Docker / CI/CD | Có | Phân biệt module code với service triển khai; đưa cấu hình và kết quả chạy thực tế |
| Springer paper 6–8 trang | Có điều kiện | Chỉ ưu tiên nếu nhóm có yêu cầu viết paper; không mặc định thêm việc ngoài phạm vi |

## 2. Câu chuyện thuyết trình

"Tài liệu doanh nghiệp khác định dạng, có bảng và có thể khác ngôn ngữ câu hỏi. Nhóm xây dựng pipeline RAG có truy xuất nguồn và kiểm soát quyền. Khi đánh giá theo bằng chứng, dense retrieval còn bỏ sót nội dung; reranking xử lý thứ tự, còn translated hybrid cải thiện tập ứng viên. Nhóm đo riêng retrieval và generation, công khai giới hạn của bộ đánh giá, và tích hợp cấu hình đã chọn để kiểm thử ứng dụng."

Không biến bài trình bày thành lịch sử commit hoặc danh sách model. Mỗi cải tiến theo chuỗi: lỗi quan sát → giả thuyết → thay đổi → phép đo → kết luận có giới hạn.

## 3. Bằng chứng hiện có và việc còn thiếu

| Hạng mục | Trạng thái | Bằng chứng / việc còn lại |
|---|---|---|
| Proposal/phạm vi RAG | Có | docs/proposal.docx; không train LLM từ đầu trong phần đã đo |
| Dữ liệu đánh giá | Có snapshot | 5 tài liệu mỗi ngôn ngữ,1063 chunk; raw-file source/size/cleaning cần data owner tổng hợp |
| Parser/tokenizer | Đã tích hợp/kiểm chọn lọc | parser-main-integration-20261021; E5 tokenizer cùng revision; token dài nhất476/512 |
| Nhãn bộ mới | Đã chốt trước inference | heldout-review2-v1 reviewed-r1:20ý/40text/80case,61components/148spans; chưa double annotation độc lập |
| Retrieval mới | Hoàn tất80/80 và replay | Dense52/80;dense+BGE62;translated hybrid63;final69/80; xem báo cáo Huy |
| E5 production index | Mốc rollout21/10 đã kiểm | 532 vectorVI/768chiều; benchmark mới dùng corpus cố định khác scope production |
| Pipeline tích hợp | Lựa chọn tùy chọn | translated_hybrid_rerank; default hybrid; HTTP/UI chưa nhận language map |
| Runtime/weight size | Có warm-stage measurements | RTX2060; trung bình0,546→3,609s; chưa end-to-end/throughput/cold-start/3run độc lập |
| Generation | Cần An bổ sung | Answer/citation/faithfulness/context thực; timing API/generation/tổng |
| Paper vs Group / Gap | Chưa hoàn tất | Chọn paper/dataset/metric tương thích; không trừ điểm khác corpus rồi gọi gap |
| Docker/CI/microservices | Cần deployment owner xác nhận | Có cấu hình/workflow chưa thay cho clean-run/run xanh; không chứng minh4 service độc lập |
| Báo cáo/lời nói phần Huy | Đã soạn | huy-retrieval-report.vi.md và huy-speaking-notes.vi.md; chưa deck slide đầy đủ |

## 4. Dàn 22 slide, thời lượng dự kiến 20 phút

Phân bổ theo khối, chưa phải thời gian bắt buộc của GV: 1–2 = 1 phút; 3–7 = 4,5 phút; 8–10 = 3 phút; 11–15 = 5 phút; 16–18 = 4 phút; 19–22 = 2,5 phút.

| Slide | Nội dung / thông điệp | Hình/bảng nên có | Người chuẩn bị |
|---|---|---|---|
| 1 | Tên đề tài, mã nhóm, thành viên, GVHD | Trang bìa, đúng tên proposal | Người tổng hợp |
| 2 | Tiến độ Task 2 và agenda | 4 khối Data → Baseline → Proposed → Feasibility | Người tổng hợp |
| 3 | Bài toán, người dùng, phạm vi review | Một câu hỏi nghiệp vụ + citation; thêm agent/analytics trong bối cảnh toàn hệ thống | Nhóm chốt |
| 4 | Nguồn dữ liệu và phạm vi đánh giá | Bảng nguồn/format/số file/dung lượng/ngôn ngữ; ghi SIMULATED | Data owner |
| 5 | Làm sạch, kiểm tra trùng, bảo toàn nguồn | Flowchart + một ví dụ noise/missing thực tế đã xử lý | Data/parser owner |
| 6 | Parser, bảng và chunking | Một đoạn/bảng đi qua parser rồi token-bounded chunk, chỉ source offset | Parser owner + Huy |
| 7 | Embedding và schema metadata | E5-base768; documents → parser_chunks → document_chunks; ACL/source/page/model | Huy |
| 8 | Bộ câu hỏi và cách chấm evidence | Ví dụ F01 có timing/photos/report; lấy cả chunk chứ không chỉ vài chữ label | Huy |
| 9 | Protocol/cấu hình thực nghiệm | Corpus cố định, E5/BGE revisions, RTX2060/FP32, candidate30/final10, 4 hướng ngôn ngữ | Huy |
| 10 | Baseline và related work/gap | Hai đối chứng thực nghiệm; bảng paper/dataset/metric/group. Chốt tính phù hợp yêu cầu 2 baseline | Huy + nhóm |
| 11 | Proposed pipeline | Original query → dense; translated EN/VI → lexical → fusion → BGE → contexts → LLM | Huy |
| 12 | Kết quả retrieval chính | Bảng4 phương pháp + kết quả theo4 hướng; ghi metric full-evidence coverage@10 | Huy |
| 13 | Ablation / vai trò module | Dense → Dense+BGE → Translated hybrid+BGE; phần chưa tách riêng đánh dấu chưa đo | Huy |
| 14 | Failure analysis | H04 VI→EN: dense19→fusion33 bị cắt; H11/H14: thiếu dòng ID trong pool30 | Huy |
| 15 | Giới hạn của cải tiến | Lỗi dịch stock→cổ phiếu; top10 đủ evidence chưa chứng minh LLM đúng; dev-set dependence | Huy |
| 16 | Generation và grounding | Prompt dùng contexts/citation, kiểm tra câu trả lời với nguồn, câu ngoài tài liệu | An / LLM owner |
| 17 | Kết quả generation | Metric thực có + một answer đúng/sai có nguồn; ghi số lượng hoàn tất và cách chấm | An / LLM owner |
| 18 | Demo luồng người dùng | Một câu hỏi nghiệp vụ → trả lời → mở citation; tùy thời gian thêm câu ngoài tài liệu/quyền truy cập | Người demo |
| 19 | Tính khả thi / runtime | Bảng stage latency, cold/warm, hardware, RAM/VRAM và model size thực đo | Deployment owner + Huy/An |
| 20 | Kiến trúc triển khai và CI | Sơ đồ đúng container thực có, log Compose, ảnh CI thực; gap Task 3 | Deployment owner |
| 21 | Hạn chế, tiến độ, kế hoạch Task 3 | 3 rủi ro ưu tiên, việc chưa xong, owner và tiêu chí hoàn thành | Người tổng hợp |
| 22 | 3 kết luận chính + Q&A | Một câu mỗi kết quả, QR/link repo nếu nhóm muốn | Người kết |

Backup slide: chi tiết parser/OCR; bảng nguồn/token; schema metadata đầy đủ; hướng dẫn tái lập; bảng embedding-model cũ; quy tắc evidence alternatives; full per-question failures; paper bibliography; Docker/CI logs.

## 5. Kết quả chính đã chốt — reviewed-r1,80 ca

Dùng [báo cáo Huy](huy-retrieval-report.vi.md) và [gợi ý nói](huy-speaking-notes.vi.md). Full evidence không phải answer accuracy.

| Phương pháp | Đủ evidence@10 | Tỷ lệ | R@10 | MRR@10 | nDCG@10 |
|---|---:|---:|---:|---:|---:|
| Dense |52/80|65,00%|0,6563|0,5586|0,5594|
| Dense+BGE |62/80|77,50%|0,7875|0,8213|0,7731|
| Translated hybrid |63/80|78,75%|0,7917|0,6590|0,6694|
| **Translated hybrid+BGE** |**69/80**|**86,25%**|**0,8823**|**0,9000**|**0,8635**|

Nguồn: [run report](../../artifacts/evaluation/heldout-review2-v1/runs/review2-reviewed-r1-sql-20261022/REPORT.vi.md). Mean latency0,546/1,691/2,437/3,609s, chưa gồm live API dịch/generation.

- 20 intents/40 văn bản/80 ca, không80 câu độc lập; snapshot mô phỏng1063 chunk, scope5 tài liệu đích/admin.
- Vs dense+17ca/+21,25pp, bootstrapCI[10,35]; vs dense+BGE+7ca/+8,75pp,CI[0,20].
- Chưa original-query hybrid arm để tách riêng dịch với lexical/fusion.
- Bộ12intent/48ca đạt100% cũ thuộc development, chỉ để backup lịch sử.
- Nhãn chưa double-annotate độc lập; chưa đo generation/end-to-end.

## 6. Failure analysis

11 ca thiếu evidence: H04 VI→EN1;H08 corpusVI2;H11all4;H14all4. Tất cả thiếu từpool30, SQL replay11/11 top30 khớp.

- H04: thuật ngữ “hồ sơ lưu trữ”→“file categories/storage”; golddense19, fusion33. Trình cả hồi quy so với dense+BGE.
- H11/H14: cần đúng nhiều dòng ID; có gold ngoài200 nên tăng30→50 chưa giải quyết toàn bộ.
- Multi-chunk12/20 thấp nhất; narrative19/20,paraphrase20/20,table18/20.
- Reranker cứu6ca vs hybrid thô, không mất full-evidence case nào vs thô.
- 6 ý bảng có chunkVI/EN giống hệt. Hình F03/F08 cũ chỉ làm backup.

## 7. Demo và kế hoạch nói

Demo khoảng 2 phút trong block 16–18:
1. Mở sẵn app/cấu hình và model cache; không tải model hoặc migrate DB trước hội đồng.
2. Chọn `translated_hybrid_rerank`, hỏi một câu hỏi mô phỏng đã được kiểm tra luồng ứng dụng.
3. Mở citation và chỉ câu trả lời được hỗ trợ bởi phần nào của nguồn.
4. Nếu đủ thời gian, hỏi một câu ngoài tài liệu. Chỉ diễn giải khả năng từ chối nếu đã kiểm chứng thực tế.

Chuẩn bị video/screenshot cùng câu hỏi làm dự phòng, ghi rõ là bản ghi. Không giả vờ đó là live demo.
Không đưa gold evidence vào query/prompt. Không đưa `.env`, keys hay URL có credentials lên màn hình.
Không dùng latency Colab shared compute hoặc 827ms dense smoke để đại diện toàn pipeline; 827ms là một request dense duy nhất, không p50/p95 hay SLA.

Phân công trình bày theo vai trò (tạm):
- Data/parser owner: nguồn, xử lý tài liệu, chunking, bảng.
- Huy: tokenizer/embedding, schema, evaluation labels, retrieval/rerank, kết quả và failure.
- An nếu đúng ownership nhóm: generation/grounding, kết quả end-to-end; cần xác nhận.
- Deployment/tổng hợp: Docker/CI, tính khả thi, Task 3, mở/kết bài.
Mỗi người biết sơ đồ toàn pipeline. Chuyển người ở ranh giới khối, không đổi người mỗi slide.

## 8. Câu hỏi phản biện nên tập

| Câu hỏi | Ý trả lời dựa trên bằng chứng |
|---|---|
| Nhóm có train model không? | Dùng pretrained embedding/reranker/LLM; đóng góp ở pipeline và evaluation, không báo loss/epoch giả |
| Sao E5 thay MiniLM? | Dựa trên các so sánh cùng corpus đã lưu và yêu cầu multilingual; nêu đúng model/revision và dataset, không khẳng định model tốt nhất mọi bài toán |
| Vì sao top30 rồi top10? | Đó là cấu hình thực nghiệm đã dùng; còn giới hạn candidate recall, chưa có khảo sát rộng mọi k |
| Chunk size/overlap có căn cứ không? | Đưa config và token cap thực; phân biệt splitter theo format với token-bounded split. Chưa có ablation thì nói chưa, không nói tối ưu |
| Nhãn do ai làm? Kappa đâu? | Assistant hỗ trợ soạn/kiểm tra, Huy duyệt; chưa independent double annotation. Không tính Kappa từ hai bản do cùng luồng tạo |
|86,25% có tổng quát hóa không? |20 ý mới nhưng cùng corpus đã biết;80 ca phụ thuộc theo intent.100% cũ là development |
| Multilingual sao còn cần dịch? | Dense đa ngôn ngữ vẫn có candidate misses; lexical translated queries bổ sung tín hiệu; đây là cải thiện trên scope đã đo |
| Reranker cứu mọi câu không? | Không;11 ca mới thiếu từpool30, BGE không tìm thêm evidence ngoài pool |
| Metadata language đâu? | Thí nghiệm dùng verified mapping. API hiện chưa cấp mapping; translated search vẫn chạy nhưng không nên gọi routing language-aware tương đương thí nghiệm |
| Retrieval đúng có chắc LLM đúng? | Không; cần đo generation/citations/faithfulness độc lập và nêu context cap hiện có |
| Không có câu trả lời trong tài liệu thì sao? | Mô tả logic grounding/refusal hiện có, trình case kiểm chứng; không hứa tuyệt đối chống hallucination |
| Docker có nghĩa là microservices chưa? | Không; cấu hình hiện có web và dịch vụ hỗ trợ, chưa tách độc lập ingestion/retrieval/generation |
| CI/CD chạy thật chưa? | Đưa run link/screenshot thực. Có workflow không thay thế run xanh, có build không đồng nghĩa đã deploy |

## 9. Việc làm theo thứ tự trước review

Ưu tiên 0 — chốt scope và số liệu:
- Chốt ngày, thời lượng, thành viên và baseline được dùng cho Review 2.
- Data owner gửi bảng nguồn/format/file count/size/token/cleaning; tách synthetic, public, VI và EN.
- An gửi kết quả generation đầy đủ và script/config; báo rõ scope/case/model, không ghép khác bộ vào một bảng.
- Deployment owner kiểm tra latest CI, chạy Compose trên môi trường sạch, chụp minh chứng và kê hạn chế.

Ngày chuẩn bị 1: lập evidence inventory + tình trạng đã xong/đang làm/chưa làm theo checklist GV; chốt bảng số liệu.
Ngày 2: soạn 22 slide theo khung, vẽ architecture/schema/failure và biểu đồ từ file kết quả. Không phát triển thêm model khi chưa cần.
Ngày 3: hoàn thiện nội dung generation/demo và bảng latency thực đo nếu khả thi; thêm limitations/backup Q&A.
Ngày cuối: rehearsal ít nhất một lần có bấm giờ; kiểm tra demo/model cache, chuẩn bị video dự phòng, khóa bản slide và thống nhất đáp án phản biện.

Nếu còn ít hơn bốn ngày, gộp khâu chuẩn bị nhưng giữ thứ tự. Không hứa deadline theo ngày lịch khi lịch review chưa được xác nhận.

## 10. Điều kiện để bắt đầu làm slide hoàn chỉnh

Có thể làm ngay: slides pipeline/schema/evidence/retrieval và failure vì đã có nguồn số liệu.
Cần người phụ trách xác nhận trước khi điền số: inventory toàn dataset, cleaning/duplicate audit, hai baseline đối chiếu paper, generation quality, cold/warm latency/model size, Compose clean-run, CI history và deployment status.
Nếu chưa đủ thì ghi rõ trạng thái và plan Task 3; không tự điền số hoặc biến số historical corpus khác thành số hiện tại.

## Cập nhật ngày 22/10 — bộ development, dùng làm bổ trợ

Đã bổ sung P@10, R@10, MRR@10, nDCG@10 và đo stage latency thật trên RTX2060.
Xem [bảng dùng cho slide](../../artifacts/evaluation/retrieval-metrics-20261022/SLIDE_SUMMARY.vi.md)
và [phân tích đầy đủ](../../artifacts/evaluation/retrieval-metrics-20261022/REPORT.vi.md).
Phần metrics retrieval không còn là việc chờ ngày mai. Generation metrics vẫn cần An.
Có một lỗi citation validator sau context packing được tái lập bằng mocked LLM;
đã ghi trong report để An kiểm tra trước demo, chưa sửa production code.


## Cập nhật phần Huy

Báo cáo/lời nói đã soạn. Dùng80ca mới, RTX2060 và86,25% cho slide chính. Chưa hoàn tất paper-vs-group,3run/mean±std, ablation chunk size hoặc generation/end-to-end; ghi rõ trạng thái, không điền số giả.
