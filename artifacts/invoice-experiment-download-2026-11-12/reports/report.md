# Báo cáo đánh giá trích xuất hóa đơn

**Ngày lập:** 11/11/2026 · **Mã triển khai:** `720b265` · **Tập đánh giá chính:** 50 hóa đơn tổng hợp tiếng Việt

## Kết luận điều hành

Trong 50 hóa đơn có cùng bộ OCR đầu vào, Groq GPT-OSS 120B cùng prompt v2 đạt **74% chính xác toàn hóa đơn**, cao hơn Groq GPT-OSS 20B (50%) **24 điểm phần trăm**. Thời gian trích xuất trung bình giảm từ **32,61 giây xuống 27,69 giây** (nhanh hơn khoảng 15%). Mức thời gian này không bao gồm OCR.

Gemini 3.5 Flash Lite vẫn nhanh và chính xác hơn một chút trên benchmark này: **17,45 giây** trung bình và **76%** chính xác toàn hóa đơn. Groq 120B được chọn làm tùy chọn Groq trong ứng dụng vì chất lượng gần Gemini, vượt rõ Groq 20B, và chỉ cần một request cho mỗi hóa đơn trong lần benchmark mới. Kết quả không chứng minh tốc độ đó sẽ giữ nguyên ở mọi mức quota hoặc mạng.

Mô hình dùng OCR text và bảng làm bằng chứng rồi sinh JSON theo schema. Prompt làm rõ ý nghĩa các trường và quan hệ nhãn, không thêm luật suy đoán hoặc công thức hậu xử lý theo mẫu hóa đơn. Tập 50 mẫu là hóa đơn tổng hợp theo các mẫu có kiểm soát; cần đánh giá thêm trên hóa đơn thực tế và nhiều bố cục trước khi xem 74% là khả năng tổng quát ngoài tập này.

## So sánh mô hình

Các kết quả 50 mẫu bên dưới dùng cùng bộ OCR VietOCR và cùng cohort. Thời gian tính từ phần trích xuất mô hình, không gồm OCR. Các benchmark cũ có prompt, cách chia request và đôi chỗ cách chấm khác nhau; cột thời gian phản ánh đúng cách từng lượt chạy ghi nhận quota pacing.

| Mô hình | Mẫu | Đúng toàn hóa đơn | Đúng dòng hàng | Trung bình | Diễn giải |
|---|---:|---:|---:|---:|---|
| Qwen3-0.6B fine-tuned (Modal) | 50 | 10% | 96,1% | 22,33 giây | Benchmark tham chiếu, prompt/scorer cũ |
| Qwen3-1.7B base | 50 | 44% | 90,7% | 28,38 giây | Cùng cohort OCR |
| Gemini 3.5 Flash Lite | 50 | **76%** | 96,1% | **17,45 giây** | Nhanh nhất và chính xác nhất trong các lượt đủ 50 |
| Groq GPT-OSS 20B, prompt cũ | 50 | 50% | 96,1% | 32,61 giây | 100 request; JSON object mode |
| **Groq GPT-OSS 120B, prompt v2** | **50** | **74%** | **96,1%** | **27,69 giây** | **50 request; strict JSON Schema** |
| Groq Qwen3.8-27B, prompt cũ | 22 | 54,5% | 92,0% | 2,17 giây | Chỉ 22 mẫu; thời gian API không tính quota wait, không so trực tiếp với các dòng 50 mẫu |

**Đọc kết quả:** GPT-OSS 120B tăng 24 điểm chính xác toàn hóa đơn so với Groq 20B và giảm thời gian trung bình 4,93 giây (khoảng 15%). So với Gemini, Groq 120B thấp hơn 2 điểm và chậm hơn 10,24 giây. Độ chính xác dòng hàng giống nhau ở 96,1%, nên phần khác biệt chính nằm ở header và các hóa đơn mà chỉ một vài trường sai khiến điểm toàn hóa đơn giảm.

### Chi phí ước lượng

Groq 120B dùng 108.846 token đầu vào và 66.161 token sinh ra trong 50 request. Theo bảng giá Groq được tra trong lúc lập benchmark ($0,15/triệu token vào; $0,60/triệu token ra), chi phí ước lượng là **$0,056/50 hóa đơn**. Groq 20B ước lượng **$0,024/50 hóa đơn**. Qwen3.8-27B chạy 22 mẫu, khoảng **$0,118** theo mức giá được ghi nhận lúc đó ($0,80/$4,00 mỗi triệu token); đây là model preview và lượt chạy không đủ 50 mẫu. Giá và quota có thể thay đổi. Tham khảo [bảng model và giá Groq](https://console.groq.com/docs/models) và [Structured Outputs](https://console.groq.com/docs/structured-outputs).

## Chất lượng của Groq 120B

Trong 50 mẫu, cả 50 request thành công, 100% output hợp lệ schema, không có lỗi parse JSON hoặc xung đột trường. Tỷ lệ khớp chính xác từng header: số hóa đơn 100%, ngày 100%, người bán 96%, người mua 94%, subtotal 100%, tiền thuế 100%, tổng thanh toán 100%. Số lượng dòng hàng chính xác ở 50/50; độ chính xác từng dòng là 96,1%. CER của mô tả hàng hóa là 0,34%, WER là 0,49%.

Theo chất lượng OCR: nhóm sạch đạt 86,7% (15 mẫu), hơi suy giảm 80% (20), khó 75% (4), nhăn 45,5% (11). Hai nhóm nhỏ không đủ lớn để đại diện ổn định cho các hóa đơn khó nói chung. Các lỗi còn lại tập trung vào ảnh nhăn/mờ, nhầm vai trò người mua-bán ở một số mẫu và sai khác khi chép chữ nhỏ. Có mẫu OCR đã làm hỏng chữ trong tên công ty; mô hình văn bản không thể khôi phục chắc chắn thông tin không còn trong OCR.

Prompt v2 gửi header, bảng hàng và tổng tiền trong cùng một request. Nó chỉ dẫn mô hình phân biệt số hóa đơn với ký hiệu, mã số thuế, số hợp đồng và phiếu giao hàng; gán subtotal/thuế/tổng theo nhãn; lấy mặt hàng theo cột của bảng. Mọi giá trị phải dựa trên OCR; mô hình không tự tính hoặc sửa dữ liệu. Đây là thay đổi prompt và model cùng lúc, vì vậy mức tăng so với Groq 20B đo hiệu quả tổng hợp của hai thay đổi, không cô lập riêng tác động của từng yếu tố.

## Thử nghiệm reasoning thấp

Lượt tiếp theo đổi đồng thời cách diễn đạt ngày/vai trò người mua-bán và giảm reasoning từ medium xuống low. Groq trả HTTP 429 sau 17 mẫu; 33 mẫu còn lại chưa có kết quả. Trên cùng 17 mẫu đầu, v2 đạt 82,4%, bản đổi prompt và reasoning đạt 64,7%; thời gian trung bình có quota wait lần lượt là 26,50 và 24,41 giây. Vì hai thay đổi đi cùng nhau và lượt chạy không đủ 50 mẫu, đây không phải phép thử tách riêng tác động của reasoning. Bản low không được chọn; production dùng prompt v2 và medium.

## Fine-tune Qwen3-0.6B

### Dữ liệu

Fine-tune dùng dataset Kaggle riêng `ltrngnhn/invoice-synthetic-1000-sft-benchmark`, gồm 1.000 hóa đơn PDF tiếng Việt tổng hợp một trang với nhãn `invoice.v1`:

| Chia dữ liệu | Số hóa đơn | Số cặp prompt/target |
|---|---:|---:|
| Train | 900 | 1.800 |
| Validation | 50 | 100 |
| Test/holdout | 50 | Benchmark OCR dùng cùng cohort holdout; không đưa vào train |

Mỗi hóa đơn train tạo hai ví dụ: trích xuất header và trích xuất bảng hàng. Bằng chứng đầu vào cho train được tái tạo từ nhãn tổng hợp, sạch và ít lỗi OCR. Tập holdout được chạy qua OCR đã fine-tune. Việc tách hóa đơn tránh leakage trực tiếp, nhưng khác biệt giữa bằng chứng train sạch và OCR thực tế vẫn tạo domain gap.

### Cấu hình và kết quả

Base model `Qwen/Qwen3-0.6B`, revision `c1899de289a04d12100db370d81485cdf75e47ca`. LoRA rank 16, alpha 32, dropout 0,05 trên `q_proj`, `k_proj`, `v_proj`, `o_proj`, `gate_proj`, `up_proj`, `down_proj`; base weights được giữ cố định. Huấn luyện 3 epoch, 339 optimizer steps, learning rate `1e-4`, batch size 1, gradient accumulation 8, sequence tối đa 2.048 token, FP16, gradient checkpointing, AdamW, cosine schedule, warmup 5%, seed `20261108`. Chạy trên Kaggle Tesla T4 trong 29.437 giây, khoảng 8 giờ 11 phút. Loss train ghi nhận 0,000384; validation loss tốt nhất 0,00001085.

Benchmark chuyên biệt của notebook fine-tune ghi nhận whole-invoice exact 0% cho LoRA 0.6B, base 0.6B và base 1.7B; trong khi item-row accuracy của LoRA là 91,0% pooled. Một benchmark tham chiếu khác ghi nhận Modal adapter 0.6B đạt 10% whole-invoice và một lượt Qwen 1.7B khác đạt 44%. Các kết quả khác nhau do prompt builder/scorer khác nhau; không nên coi chúng là phép so trực tiếp. Kết luận nhất quán là Qwen nhỏ trích bảng hàng tốt hơn nhiều so với header, nhưng chưa đạt độ chính xác toàn hóa đơn phù hợp. Điều này cũng giải thích vì sao model lớn hơn, nhận đầy đủ bằng chứng, được chọn cho luồng Groq.

## OCR và nguồn dữ liệu

OCR dùng Docling 2.129.0 cùng model VietOCR fine-tuned `lenhanm1/enterprise-printed-ocr-vietocr-tesseract`, revision `6deb1cb10ecbf240aead77525e80aa4c58adfb23`. Cấu hình `vgg_seq2seq`, chiều rộng ảnh tối đa 512, greedy decoding. Chạy trên Kaggle CUDA, hoàn tất 50/50 trong 739,98 giây. Cache OCR được dùng chung cho các benchmark chính.

- OCR cache SHA-256: `d1b9f1231cab317e4132341385b73f5644287d9a4f5101c8d30498a00713feb0`.
- Commit OCR pipeline được ghi lại: `d05f16baa94e0f82648bc9018b157e5a7d3fac89`.
- ZIP fine-tune dataset SHA-256: `49df93911bd857267de0866415f8e34e204fe282a38249a3790a50e19f8bc1b7`.
- Manifest SHA-256: `4a9fc7e5341ce04d8bd049474f0a1ba170d7505a1b6541e72801af1014115b8e`.
- Ground truth SHA-256: `e00c5cb10b634622ac5f7b6d3e24c260e2a37ce723f6cf78e4c502f3f930da1c`.

Đây là dữ liệu tổng hợp theo mẫu có kiểm soát, không đại diện cho đủ ngành nghề, bố cục hóa đơn thực tế, máy scan, ảnh chụp hoặc chữ viết tay. Vì vậy các tỷ lệ là kết quả trên cohort này, không phải bảo đảm chất lượng cho mọi hóa đơn mới. Chỉ số whole-invoice exact yêu cầu schema hợp lệ, cả bảy trường header đúng, số dòng đúng và mọi trường của từng dòng đúng thứ tự; đây là chỉ số nghiêm ngặt hơn độ chính xác từng trường.

## Tái lập benchmark

### Tái tạo bảng so sánh

Mở [notebook phân tích](reproduce_results.ipynb). Notebook đọc snapshot số liệu và kết quả theo từng hóa đơn trong thư mục `inputs`, chạy lại cùng scoring implementation cho năm model đủ 50 mẫu, kiểm tra kết quả 20B/120B khớp metrics đã lưu và xuất `reproduced_comparison.csv`. Không gọi API và không cần cài pandas/matplotlib.

### Huấn luyện lại và benchmark Qwen

Mở [notebook fine-tune và benchmark](reproduce_finetune_and_benchmark.ipynb). Đặt `RUN_TRAINING=True` để huấn luyện mới từ split 900 hóa đơn; cần Kaggle GPU và Internet, thời gian dự kiến khoảng 8,2 giờ trên Tesla T4. Đặt `False` để dùng adapter đã lưu và chỉ chạy holdout. Notebook kiểm tra split 900/50/50, pin revision Qwen và ghi metrics cùng kết quả từng mẫu vào `/kaggle/working`.

Dataset Kaggle là riêng tư: `ltrngnhn/invoice-synthetic-1000-sft-benchmark`, `ltrngnhn/invoice-50-holdout-ocr-cache`; chế độ benchmark-only cần thêm `ltrngnhn/qwen3-0-6b-invoice-lora-adapter-900`. Nhánh huấn luyện mới đã được sửa để không cần adapter cũ và giữ model cho Trainer. Các cell Python đã kiểm tra cú pháp, nhưng nhánh huấn luyện sửa đổi chưa được chạy lại trọn vẹn trên GPU.

### Chạy lại Groq

Runner: `../invoice-groq120b-v2/run_benchmark.py`; dữ liệu OCR: `../invoice-pilot-50-new-vietocr/ocr_results.json`. Script đọc `GROQ_API_KEY` từ `.env`, gọi API một lần cho mỗi hóa đơn và ghi kết quả ra đường dẫn `--output`. Ví dụ chạy mới:

```bash
python artifacts/invoice-groq120b-v2/run_benchmark.py --limit 50 --output artifacts/invoice-groq120b-v2/fresh-results.json
```

Lượt chạy 50 hóa đơn dùng quota API; chi phí theo usage đã lưu ước tính $0,056. Mặc định runner pin source commit triển khai `720b265`. Kết quả nhà cung cấp có thể thay đổi theo model deployment, quota và mạng nên lần chạy mới có thể không trùng tuyệt đối.

## Triển khai

Mã được push lên `main` tại commit `720b265` và triển khai trên Contabo VPS. Image `backend-api` và `document-processing` build thành công, cả hai service báo healthy, endpoint health trả `{"status":"ok"}`. Trang Vercel đã phục vụ lựa chọn GPT-OSS 120B. Model hiệu lực trong worker được xác nhận là `openai/gpt-oss-120b`.

## Tệp kèm theo

- [Notebook tái tạo bảng so sánh](reproduce_results.ipynb)
- [Notebook fine-tune và benchmark](reproduce_finetune_and_benchmark.ipynb)
- [Snapshot metrics và provenance](benchmark_metrics.json)
- [Kết quả Groq 120B theo từng hóa đơn](../invoice-groq120b-v2/results.json)
- [HTML xem từng trường và lỗi](../invoice-groq120b-v2/groq120b-review.html)
