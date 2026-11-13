# Đối chiếu Report Tasks Review 2 với tiến độ hiện tại

Ngày: **29/10/2026**. Nguồn yêu cầu: [Report Tasks cho Review lần 2.docx](https://docs.google.com/document/d/14kHUIu00ToNM7N3qnDWoMMO-Wg8WldcP/edit), bản Drive sửa cuối 29/10/2026 05:14 UTC. Đọc toàn văn và bảng tự đánh giá trong DOCX. Không sửa tài liệu Drive.

Đối chiếu code `origin/main` **169ea59f38550dce00e2f8f52121f026309ccd58**, handoff `origin/Huy` **a512feb**, artifact thí nghiệm và trạng thái GitHub Actions. VPS đã deploy/host theo người dùng xác nhận; chưa SSH, đo hoặc xác nhận commit/config đang chạy trên VPS. Không chạy benchmark/test mới và không sửa production/DB. Trạng thái dưới đây không phải phần trăm hoàn thành chung của nhóm.

## 1. Kết luận

Report có phần retrieval đúng và có bằng chứng, nhưng chưa cập nhật kiến trúc Docker và CI; mô tả metadata đang trộn đặc tính Huy/benchmark với main. Các câu hỏi về split/leakage, baseline so với paper và tính công bằng vẫn thiếu câu trả lời. Generation đã có kết quả nhưng phải chọn đúng run và mẫu số, không ghi chung “full75” như tất cả ca đều thành công và được chấm mọi metric.

Ưu tiên sửa báo cáo trước: Docker/CI → tên metric retrieval → phạm vi dataset/metadata → bảng generation → các ô câu hỏi còn trống. Code triển khai và số liệu thực nghiệm là hai loại bằng chứng khác nhau.

## 2. Những câu đã sai hoặc thiếu cập nhật

| Nội dung report hiện tại | Đối chiếu | Cách sửa |
|---|---|---|
| “Mới chỉ được gói Docker, chưa tách service” | **Lỗi thời.** Compose có backend-api, document-processing, chunking, embeddings, reranker. | Đã tách5 service backend. Auth/router/RAG/SQL/report vẫn là module trong backend-api; không gọi mỗi agent là một container. Supabase/LLM ngoài Compose. |
| “Chưa có Dockerfile cho từng service” | **Sai với main hiện tại.** Có5 Dockerfile. | Nêu đã có Dockerfile riêng; clean-machine/full dependency smoke cần log riêng. VPS deploy không tự chứng minh máy sạch chạy được. |
| Checkbox “Docker, microservices, CI/CD: Xong” | **Gộp quá mức.** CI có cấu hình nhưng run mới nhất fail, chưa thấy auto-deploy job. | Docker/service: có; VPS: đã deploy theo nhóm; CI: cần sửa để xanh; CD: chưa có bằng chứng tự động. |
| `69/80 ... +21,25 điểm phần trăm (Recall)` | **Nhầm tên metric.** Đây là Full evidence@10. | Full evidence@10 65,00% →86,25%; Recall@10 .6563→.8823; MRR@10 .5586→.9000. Không phải answer accuracy. |
| Metadata gồm source_parser_index/source_spans | **Đúng cho frozen Huy benchmark, không phải bảo đảm toàn main.** Main token chunker không tạo hai trường này. | Metadata chung + provenance theo source_elements; exact character mapping là đặc điểm bộ benchmark cũ, không khẳng định mọi tài liệu mới có. |
| “Không có nguồn hoặc ngoài tài liệu thì sẽ từ chối” | **Quá tuyệt đối.** Có insufficient-answer/citation guard, nhưng có câu trả lời lỗi và ca bị validator từ chối. | Có cơ chế báo thiếu bằng chứng và kiểm citation; khả năng chống hallucination/refusal phải đánh giá riêng. Prompt không bảo đảm đúng tuyệt đối. |
| “Đánh giá full75 câu cho2 model” | Có75 ca dự kiến/model; success và scored count khác theo run/metric. | Ghi75 =25 Knowledge+25 SQL+25 Report; kèm answered/errors và scored/eligible từng metric, nguồn run rõ ràng. |
| Dataset chung5VI/532chunks | **Đúng cho snapshot đã nêu**, không phải tổng corpus triển khai luôn luôn. | Ghi phiên bản/ngày snapshot; tách5VI, corpus retrieval10VI/EN và tài liệu mới. Không cộng các bộ độc lập rồi gắn vào điểm cũ. |
| Proposed V1 được tick “Chưa làm” | **Mâu thuẫn với kết quả pipeline đã chạy trong thân report.** | Với retrieval V1, có thể đánh dấu đã có implementation/kết quả; integration đầy đủ của mọi agent vẫn theo phạm vi riêng. |

Main sentence splitter còn fallback fixed có overlap khi một câu quá dài; không viết “sentence mode luôn không overlap”. Chưa có ablation chứng minh1100chars/overlap là tối ưu. Token splitting vẫn có thể cắt hàng bảng.

## 3. Đối chiếu các câu hỏi giai đoạn1 — dữ liệu

| Câu hỏi | Tiến độ có bằng chứng | Cần bổ sung vào report |
|---|---|---|
| Có bao nhiêu dữ liệu offline? | Có snapshot5VI/532; retrieval riêng thêm5EN/531. Có tài liệu mới và OCR cohort riêng. | Bảng nguồn theo từng bộ: số file/trang/chunk, phiên bản, dữ liệu thật/historical/mô phỏng. Không gọi532 là tổng DB hiện tại. |
| Mất cân bằng định lượng? | 485/532=91,17% VI chunks từ XLSX; đã nêu đúng. | Thêm biểu đồ theo định dạng và giải thích chunk nhiều không đồng nghĩa nhiều câu hỏi độc lập. |
| Train/Val/Test và augmentation? | Không fine-tune embedding/reranker trong benchmark retrieval; không có supervised training split để báo. | Viết rõ corpus/development questions/test questions; không dùng VI/EN của cùng intent như mẫu độc lập. Nếu OCR/model khác có training, báo riêng. |
| Trùng giữa các tập? | Frozen retrieval có overlap audit; corpus từng được dùng phát triển.6 intents có nguyên chunk table VI/EN giống nhau. | Nêu kiểm đã làm, giới hạn same-corpus và nguồn freeze; không tuyên bố tuyệt đối không leakage. |
| Ai gán nhãn/chất lượng? | Report nêu Nhân phụ trách OCR, Huy/An rà dữ liệu mô phỏng. Artifact retrieval do trợ lý soạn/đối chiếu. | Phân biệt người tạo tài liệu, người gán nhãn và người kiểm tra. Chưa có Kappa độc lập thì ghi chưa đo. AI-generated document không tự là gold label. |
| Vì sao xử lý mất cân bằng? | Không oversample corpus retrieval. | Giải thích lặp chunk sẽ đổi ranking/BM25; báo kết quả theo nhóm câu hỏi/định dạng thay vì áp SMOTE vào bài RAG. |
| Vì sao chunk size/overlap? | Đã có implementation và token checks; chưa có ablation riêng. | Ghi đây là cấu hình khởi tạo để giữ cấu trúc và vừa encoder, không phải cấu hình tối ưu; nói rõ fallback và row-cut limit. |
| Tổng token/chi phí/thời gian? | 224.845 input tokens E5 cho snapshot5VI;476/512max,0overlength. Có các phép đo encoder lịch sử trong repo, không phải VPS mới. | Giữ số token với snapshot; chọn đúng run cho thời gian. Chưa có phép đo embedding batch mới trên VPS thì không suy từ RTX2060. |
| Metadata và ngoài tài liệu? | Có identity/location/layout/roles/model metadata, scoped retrieval và citation checks. Main có source_elements cấp nhóm nguồn. | Bổ sung table/row/page/section, chính sách nguồn và ví dụ thiếu bằng chứng; không hứa exact source_spans trên mọi main chunk hoặc refusal100%. |

Các ô checklist nhỏ1.1–1.4 đầu tài liệu vẫn trống, dù đã có code. Có thể điền: chunking theo cấu trúc và token budget; multilingual-e5-base768 chiều/prefix/normalization; Supabase PostgreSQL/pgvector; metadata identity/location/access/provenance theo pipeline. Grounding cần prompt, ví dụ nguồn/answer và số liệu kiểm riêng. File output có JSON/JSONL trong artifact; không nên chỉ ghi “JSON” mà thiếu file minh họa.

## 4. Giai đoạn2 — baseline

| Câu hỏi | Đánh giá | Cần làm |
|---|---|---|
| Thấp hơn paper bao nhiêu? | **Chưa đủ chứng cứ.** Có control methods nhưng chưa có bảng paper/group tương thích. | Chọn paper cụ thể, nêu dataset/metric/setup; không trừ hai điểm khác dataset rồi gọi gap chính xác. |
| Nguyên nhân gap? | **Chưa hoàn thiện.** Corpus/domain/preprocessing khác có thể ảnh hưởng, chưa có phân tích chứng minh từng nguyên nhân. | Viết gap analysis phân biệt quan sát và giả thuyết. |
| Bao nhiêu run/seed? | Retrieval80-case: một pass/case/method. Bootstrap20 intent không phải3 run. | Điền đúng số run và seed theo artifact; không tạo mean±std chưa đo. |
| Baseline tuning công bằng? | Cùng frozen corpus/labels/E5/runtime/k, nhưng chưa có equal-budget tuning study. | Mô tả controls; công khai pipeline từng được phát triển trên corpus đã biết. |
| Nếu cao hơn paper có leakage? | Chưa có so paper để kết luận cao/thấp. | Dẫn overlap/duplicate audit; không lấy freeze làm bằng chứng không leakage tuyệt đối. |

Dense E5 và Dense E5+BGE là **hai đối chứng đã chạy**. Chúng không tự chứng minh nhóm đã “tái dựng2 paper”. Việc dùng pretrained resources là phù hợp proposed pipeline; không cần bịa training curve/optimizer/epoch.

## 5. Giai đoạn3 — proposed method

| Câu hỏi | Đánh giá hiện tại |
|---|---|
| V1 có cải thiện? | Có bằng chứng retrieval:52→69/80 đủ evidence, +21,25pp; bổ sung Recall/MRR/nDCG đúng tên. |
| Có ý nghĩa thống kê? | Có bootstrap20 intent: vsdense CI[10,35]pp; vsdense+BGE CI[0,20]pp. Không coi CI này là lặp3seed, không tuyên bố chắc chắn thắng mọi baseline. |
| V2 sửa lỗi nào? | Đã đề xuất identifier lookup/multi-ID candidate merge từ11 failures; chưa có V2 retrieval được benchmark. Worker mới là cải tiến pipeline vận hành, không thay kết quả V2 quality. |
| Ablation đủ chưa? | Có dense±BGE và translated-hybrid±BGE; chưa tách riêng translation với lexical/fusion trên80-case run, chưa ablation chunk size/overlap. |
| Failure có cherry-pick? | Retrieval đã xét cả11 final losses. OCR có lỗi số/bảng xoay/merged; generation có run errors và thiếu score. Nên nhóm lỗi ở cả3 tầng, không chỉ retrieval. |
| Tính khả thi dựa số nào? | Có RTX2060 warm retrieval mean3,609s và model sizes. Main còn có Docker CPU timing26Oct, workload/environment khác. Cần thêm measurement trên VPS12GB nếu muốn nói năng lực server hiện tại. |

## 6. Bằng chứng OCR và generation mới nên bổ sung

### OCR: report đang thiếu số liệu dù repo đã có

Ví dụ một run đã lưu `docling-vietocr-heron101-threshold05-table-rotation-kaggle-owner-reviewed-51-20261025`:

-51 trang prediction,51 inference success; runtime khoảng1123,959s CPU.
-OCR CER8,79%, WER(PyVi)18,90%.
-Layout micro F1 36,20%.
-Table detection F1 83,64% trên60 bảng/38 trang, nhưng cell CER59,03% và exact grids3,33%.

Đây là **một cấu hình minh họa có artifact**, không tự khẳng định là cấu hình tốt nhất hay bản đang deploy. Nhân cần chọn run chuẩn, baseline/proposed cùng cohort và giải thích việc tìm đúng bảng chưa đồng nghĩa đúng ô/số. Nguồn: `origin/main:artifacts/evaluation/document-pipelines/results/shared-html/.../report.md`.

### Generation: cần chốt snapshot để tránh trộn số

Trong `agent-benchmarks-2026-10-25/comparison.md`:

| Model | Knowledge answered | SQL answered | Report answered | Tổng answered |
|---|---:|---:|---:|---:|
| Qwen3.8-27B |25/25|25/25|16/25|66/75|
| GPT-OSS-120B |25/25|25/25|22/25|72/75|

| Metric | Qwen mean (scored/eligible) | GPT-OSS mean (scored/eligible) |
|---|---:|---:|
| Faithfulness |.4762 (55/57)|.4217 (65/66)|
| Answer relevancy |.7721 (66/66)|.8073 (71/72)|
| Context precision |.4620 (57/57)|.4981 (65/66)|

Một run khác dưới `agent-benchmarks-rerun-2026-10-23/full/` báo74/75 completed cho mỗi model và các denominator khác. **Không chọn số tốt từ hai run rồi gộp thành một bảng.** Report hiện không chỉ định run nên cần gắn nguồn cụ thể. Các artifact mới có thiếu metadata evaluator/package và một phần điểm chấm tay; nêu phương pháp chấm trung thực, không mặc định tất cả là cùng một RAGAS execution.

Không suy hallucination rate từ1−faithfulness; nguồn chưa cung cấp claim-level hallucination rate. Không lấy riêng Knowledge faithfulness cao rồi gọi là toàn hệ thống, vì SQL và Report khác đáng kể. Main169ea59 vừa thay source/output controls cho Report; số cũ không tự xác nhận chất lượng phiên bản này.

## 7. Kiến trúc, deployment và CI

- **5 service và5 Dockerfile:** backend-api, document-processing, chunking, embeddings, reranker; Nginx proxy là profile tùy chọn. Supabase và LLM API ở ngoài.
- **Đã host VPS:** theo xác nhận người dùng. Chưa kiểm trực tiếp version, secrets/config, HTTPS/health, RAM/concurrency tại server.
- **Ingestion chưa async hoàn toàn:** normal upload vẫn inline chunk/embed; parser-handoff→parsed→worker→chunked. Chưa có embedding worker tự động tiếp bước.
- **CI:** workflow có compile, unittest, JS syntax, Compose validation, build container và HTTP smoke. Run mới nhất [40812329700](https://github.com/Lenhan231/enterprise-knowledge-ai-agent/actions/runs/40812329700) trên169ea59 **failure ở unittest**.5 main runs gần nhất đều failure tại thời điểm kiểm tra. Không khẳng định bước build/smoke sau đó đã chạy thành công.
- **Thiếu coverage image chunking trong build step:** lệnh build hiện liệt kê backend-api/embeddings/reranker/document-processing, chưa gồm chunking.
- **CD:** workflow đã đọc không có bước tự deploy VPS. Deployment thủ công đã có không đồng nghĩa CD tự động.
- **Máy sạch:** cần log build/up và đường request đủ dependency trên môi trường sạch. Chưa có bằng chứng đó trong lần kiểm này.

## 8. Đề xuất trạng thái cho bảng tự đánh giá

| Hạng mục | Trạng thái nên ghi | Bằng chứng/điều kiện |
|---|---|---|
| Bảng thống kê nguồn | Đang làm | Có số snapshot; cần gom toàn nhóm, nguồn/size/page/version. |
| Làm sạch/gán nhãn | Đang làm | Có parser/owner-reviewed references/evidence; thiếu mô tả thống nhất và agreement. |
| Phân tích mất cân bằng | Có số liệu; bổ sung biểu đồ |485/532XLSX cho VI snapshot, không phải nhãn classification. |
| Xử lý mất cân bằng | Không áp dụng oversampling cho retrieval | Giải thích lý do; không tick chưa làm chỉ vì không dùng kỹ thuật classification. |
| Baseline1/2 | Xong ở phạm vi đối chứng thực nghiệm đã nêu | Phân biệt retrieval controls, OCR baselines, LLM comparisons và tái dựng paper. |
| Paper vs thực nghiệm | Chưa hoàn thiện | Chưa có bảng tương thích và nguồn. |
| Gap Analysis | Đang làm/chưa hoàn thiện | Cần lập luận có chứng cứ. |
| ProposedV1 | Có implementation và kết quả retrieval | Sửa tick “Chưa làm”; không tự xác nhận mọi agent hoàn tất. |
| Failure analysis | Có cho retrieval; tổng hợp thêm OCR/generation |11final failures có phân nhóm. |
| V2 quality | Đề xuất/chưa benchmark | Không tính worker mới như chất lượng retrieval đã tăng. |
| Ablation | Một phần | BGE có; translation/chunking chưa đủ. |
| Latency/model size | Có theo từng môi trường | RTX2060 và DockerCPU tách riêng; VPS cần đo riêng. |
| Slide | Có; cần rà bản cuối | Handoff ghi28trang gồm backup; chỉ tính main deck theo yêu cầu18–25. Chưa mở lại Canva hôm nay. |
| Docker/service | Đã có code; VPS deploy theo nhóm |5services; không đồng nghĩa mọi flow đã integration-test. |
| CI/CD | Đang làm | CI đang fail, chưa bằng chứng auto-deploy. Tách khỏi dòng Docker. |
| Paper Springer | Chưa xác nhận/không bắt buộc nếu nhóm không viết | Không tự đánh dấu xong. |

## 9. Việc nên làm theo thứ tự

1. Sửa câu Docker/Dockerfile, tên Full evidence và metadata ngay trong report.
2. Điền các câu trống về split, overlap/leakage, không oversample và số lần chạy; dẫn artifact.
3. Chốt run chuẩn cho OCR và generation, thêm bảng số/mẫu số/error; phân biệt các phiên bản code.
4. Sửa CI unit failures, thêm build chunking image; sau đó mới nói CI xanh. CD là hạng mục riêng.
5. Hoàn thiện bằng chứng VPS và một luồng tài liệu→parsed→chunked→embedding/ready→QA có quyền/citation.
6. Hoàn tất paper-vs-group/gap analysis theo yêu cầu giảng viên; không train/tune chỉ để điền ô.
7. Chuẩn bị baseline trên dữ liệu mới và kế hoạch V2 riêng; giữ kết quả Review2 frozen.

## Nguồn kiểm tra

- Tài liệu Drive ở đầu báo cáo (read-only).
- `origin/main@169ea59`: Compose/Dockerfiles, deployment-guide, services/runtime, agents/router/report, retrieval service, token chunker và chunking worker.
- `origin/main`: OCR report51trang, agent comparison25Oct và full rerun24Oct, Docker stage timing26Oct.
- `origin/Huy@a512feb`: HANDOFF, checklist-evidence-assessment, evidence guide, worker handoff.
- Huy frozen reviewed-r1 benchmark: report, metrics.csv, analysis.json, candidate-diagnostics, protocol/manifest.
- GitHub Actions:5latest main runs qua gh; run mới nhất đã xem failed-step metadata. Không chạy lại test trong lần đối chiếu này.

Các hình tổng quát/service đã vẽ tại [codebase-flow-20261029.vi.md](codebase-flow-20261029.vi.md) là bằng chứng sơ đồ, không phải chứng nhận cấu hình VPS đang chạy đúng169ea59.
