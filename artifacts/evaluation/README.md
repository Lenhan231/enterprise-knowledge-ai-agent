# Phân loại evaluation

Benchmark đang dùng: **[heldout-review2-v1](heldout-review2-v1/README.md)**. Muốn chuẩn bị báo cáo, mở [review2](../review2/README.md).

## Các bộ đang dùng và mốc tích hợp

| Folder | Vai trò |
|---|---|
| [heldout-review2-v1](heldout-review2-v1/) | Benchmark mới đã chốt; giữ nguyên toàn bộ bundle, prepared/ và runs/. |
| [fresh-reviewed-v1](fresh-reviewed-v1/) | Bộ development/regression đã khóa. |
| [retrieval-metrics-20261022](retrieval-metrics-20261022/) | Metrics/diagnostic hiện tại trên bộ development. |
| [retrieval-latency-20261022](retrieval-latency-20261022/) | Phép đo latency SQL/CUDA trên bộ development. |
| [e5-production-rollout-20261021](e5-production-rollout-20261021/) | Bằng chứng rollout E5 production. |
| [parser-main-integration-20261021](parser-main-integration-20261021/) | Bằng chứng tích hợp parser main. |
| [translated-hybrid-production-integration-20261021](translated-hybrid-production-integration-20261021/) | Bằng chứng tích hợp retrieval production. |

## Nguồn/phép thử cũ giữ nguyên vị trí

Các folder dưới đây giữ nguyên vì có tham chiếu mã/dữ liệu, helper phụ thuộc độ sâu thư mục, hoặc là kết quả xử lý/OCR của nhóm. Không chuyển chỉ dựa vào ngày trong tên.

| Folder | Lý do giữ đường dẫn |
|---|---|
| [colab-fresh-reviewed-v1](colab-fresh-reviewed-v1/) | Được 4 file mã/notebook và 2 file dữ liệu/manifest tham chiếu. |
| [colab-reranker-context-20261020](colab-reranker-context-20261020/) | Helper dựa vào vị trí thư mục để tìm gốc project; giữ để chạy lại. |
| [colab-reranker-parent-20261020](colab-reranker-parent-20261020/) | Được 2 file mã/notebook và 0 file dữ liệu/manifest tham chiếu. |
| [colab-reranker-parent-plain-20261020](colab-reranker-parent-plain-20261020/) | Được 4 file mã/notebook và 0 file dữ liệu/manifest tham chiếu. |
| [colab-translated-hybrid-fresh-v1](colab-translated-hybrid-fresh-v1/) | Được 3 file mã/notebook và 2 file dữ liệu/manifest tham chiếu. |
| [embedding-comparison-20261018](embedding-comparison-20261018/) | Được 6 file mã/notebook và 9 file dữ liệu/manifest tham chiếu. |
| [embedding-full-corpus-t4](embedding-full-corpus-t4/) | Được 0 file mã/notebook và 2 file dữ liệu/manifest tham chiếu. |
| [embedding_benchmark_20261001](embedding_benchmark_20261001/) | Helper dựa vào vị trí thư mục để tìm gốc project; giữ để chạy lại. |
| [four-direction-20261018](four-direction-20261018/) | Được 2 file mã/notebook và 1 file dữ liệu/manifest tham chiếu. |
| [fresh-review-20261020](fresh-review-20261020/) | Được 2 file mã/notebook và 1 file dữ liệu/manifest tham chiếu. |
| [fresh-review-assessment-20261021](fresh-review-assessment-20261021/) | Được 1 file mã/notebook và 1 file dữ liệu/manifest tham chiếu. |
| [kaggle-reranker-dataset](kaggle-reranker-dataset/) | Kết quả lịch sử/đóng gói/OCR của nhóm; giữ khi chưa xác nhận có thể di chuyển độc lập. |
| [kaggle-reranker-metadata](kaggle-reranker-metadata/) | Kết quả lịch sử/đóng gói/OCR của nhóm; giữ khi chưa xác nhận có thể di chuyển độc lập. |
| [kaggle-reranker-output](kaggle-reranker-output/) | Được 0 file mã/notebook và 1 file dữ liệu/manifest tham chiếu. |
| [kaggle-reranker-pulled](kaggle-reranker-pulled/) | Kết quả lịch sử/đóng gói/OCR của nhóm; giữ khi chưa xác nhận có thể di chuyển độc lập. |
| [laptop-review-20261019](laptop-review-20261019/) | Helper dựa vào vị trí thư mục để tìm gốc project; giữ để chạy lại. |
| [ocr-kaggle-charter-scan-page8](ocr-kaggle-charter-scan-page8/) | Kết quả lịch sử/đóng gói/OCR của nhóm; giữ khi chưa xác nhận có thể di chuyển độc lập. |
| [ocr-kaggle-easy](ocr-kaggle-easy/) | Kết quả lịch sử/đóng gói/OCR của nhóm; giữ khi chưa xác nhận có thể di chuyển độc lập. |
| [ocr-kaggle-paddle](ocr-kaggle-paddle/) | Kết quả lịch sử/đóng gói/OCR của nhóm; giữ khi chưa xác nhận có thể di chuyển độc lập. |
| [ocr-kaggle-surya](ocr-kaggle-surya/) | Kết quả lịch sử/đóng gói/OCR của nhóm; giữ khi chưa xác nhận có thể di chuyển độc lập. |
| [ocr-kaggle-v2](ocr-kaggle-v2/) | Được 0 file mã/notebook và 4 file dữ liệu/manifest tham chiếu. |
| [ocr-kaggle-v8](ocr-kaggle-v8/) | Được 0 file mã/notebook và 4 file dữ liệu/manifest tham chiếu. |
| [ocr-kaggle-v9](ocr-kaggle-v9/) | Kết quả lịch sử/đóng gói/OCR của nhóm; giữ khi chưa xác nhận có thể di chuyển độc lập. |
| [ocr-kaggle-v9-cpu](ocr-kaggle-v9-cpu/) | Kết quả lịch sử/đóng gói/OCR của nhóm; giữ khi chưa xác nhận có thể di chuyển độc lập. |
| [ocr-kaggle-vinamilk-2011-cafef-scan-paddle](ocr-kaggle-vinamilk-2011-cafef-scan-paddle/) | Kết quả lịch sử/đóng gói/OCR của nhóm; giữ khi chưa xác nhận có thể di chuyển độc lập. |
| [ocr-kaggle-vinamilk-2011-cafef-scan-tesseract](ocr-kaggle-vinamilk-2011-cafef-scan-tesseract/) | Kết quả lịch sử/đóng gói/OCR của nhóm; giữ khi chưa xác nhận có thể di chuyển độc lập. |
| [ocr-kaggle-vinamilk-2011-cafef-scan-v2](ocr-kaggle-vinamilk-2011-cafef-scan-v2/) | Kết quả lịch sử/đóng gói/OCR của nhóm; giữ khi chưa xác nhận có thể di chuyển độc lập. |
| [ocr-rendered](ocr-rendered/) | Được 1 file mã/notebook và 0 file dữ liệu/manifest tham chiếu. |
| [reranker-narrative-context-20261020](reranker-narrative-context-20261020/) | Được 1 file mã/notebook và 0 file dữ liệu/manifest tham chiếu. |
| [retrieval](retrieval/) | Được 4 file mã/notebook và 0 file dữ liệu/manifest tham chiếu. |
| [vietstyle-bilingual-20261019](vietstyle-bilingual-20261019/) | Được 11 file mã/notebook và 3 file dữ liệu/manifest tham chiếu. |
| [vinamilk-ocr-2011-scan-diagnostic](vinamilk-ocr-2011-scan-diagnostic/) | Kết quả lịch sử/đóng gói/OCR của nhóm; giữ khi chưa xác nhận có thể di chuyển độc lập. |
| [vinamilk-ocr-v7](vinamilk-ocr-v7/) | Được 3 file mã/notebook và 0 file dữ liệu/manifest tham chiếu. |

## JSON kết quả nằm trực tiếp ở đây

Các JSON còn lại có tham chiếu từ mã, dữ liệu hoặc tài liệu tại thời điểm rà; giữ tên và vị trí để tránh gãy đường dẫn. Tra danh sách từng file ở [inventory-20261022.csv](../inventory-20261022.csv). 79 JSON không có tham chiếu đã chuyển vào [archive](../archive/legacy-reports-20261022/).

Mục lục này không chứng nhận các kết quả OCR/generation lịch sử là kết quả Review2 hiện hành. Kết quả retrieval đã chốt được trỏ riêng ở đầu.
