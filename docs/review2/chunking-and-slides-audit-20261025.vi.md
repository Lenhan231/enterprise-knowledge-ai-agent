# Chunking hiện tại và đối chiếu slide Review 2

Đối chiếu ngày25/10/2026 bằng code hiện tại, frozen artifacts và nội dung Canva revision78,29trang. Đây là kiểm tra chỉ đọc với ba nhánh rà soát độc lập (cấu trúc chunk, token/tài nguyên, slide), không phải inference hoặc memory benchmark mới. Không sửa production, frozen benchmark hoặc Canva.

**Phạm vi lịch sử:** audit code bên dưới là checkout Huy165727a, không phải mọi nhánh hoặc mọi bảnDocker. Sau đó main1ffe05b được kiểm tra riêng: module chunking chuyển sangcore/chunking, không có đầy đủ child source_spans củaHuy, mặc định translated_hybrid_rerank vàRAGtop5/cap24.000ký tự. Canva mới hơn làrevision163/28trang gồm backup; xem [lời nói hiện tại](huy-speaking-notes-20261026.vi.md). Các góp ý slide cuối file là snapshot cũ, không phải danh sách việc còn thiếu mới nhất.

## 1. Kết luận cần nhớ

Hệ thống tổ chức nội dung theo câu/hàng bảng ở bước parser, sau đó kiểm tra bằng tokenizer của embedding model. **1.100ký tự là mục tiêu cấu trúc,512token là giới hạn đầu vào E5; cả hai không phải giới hạn RAM/VRAM.** Hàng quá dài có thể được giữ nguyên ở parser nhưng bị token splitter chia tiếp. Header bảng được lặp, còn header/footer trang phụ thuộc parser engine.

## 2. Luồng xử lý và hai bảng chunk

```text
File → parser/OCR → normalized elements + structured tables
     → ChunkingProcessor (câu/nhóm hàng)
     → document_parser_chunks + lưu structured tables
     → TokenCounter + build_embedding_chunks
     → E5 embedding → document_chunks + vectors → ready
```

- [Upload integration](../../src/app/main.py): lưu parser output trước embedding. Parser-handoff có thể dừng ở trạng thái parsed, chưa searchable.
- [Parser chunk repository](../../src/core/database/parser_chunks_repository.py) lưu nội dung trước model-specific splitting.
- [Document chunk repository](../../src/core/database/document_chunks_repository.py) thay index của một tài liệu bằng transaction sau khi tạo vector.
- Khi embedding lỗi, parser output có thể còn để retry; không xem tài liệu failed/parsed là ready.

## 3. Văn bản: chia thực tế thế nào?

- [Config](../../src/core/document_processing/chunking/config.py): mặc định sentence, size1100ký tự, fixed overlap120ký tự; cho phép override qua config.
- [Upload](../../src/app/main.py) đọc DOCUMENT_CHUNKING_STRATEGY, mặc định sentence.
- [Processor](../../src/core/document_processing/chunking/processor.py) nhóm text theo vị trí/section/loại element; vị trí có page, sheet, slide hoặc paragraph khi có. Không ghép tùy tiện qua mọi ranh giới tài liệu.
- [Sentence strategy](../../src/core/document_processing/chunking/text/strategies/sentence.py) nhận diện đoạn/câu, gom câu trong phạm vi size. Không phải semantic chunking bằng model.
- Một câu riêng vượt size sẽ fallback sang [fixed splitter](../../src/core/document_processing/chunking/text/strategies/fixed.py), có tìm khoảng trắng gần điểm cắt và có thể overlap.
- [Chunk builder](../../src/core/document_processing/chunking/text/chunk_builder.py) có thể thêm `Section: ...` sau khi cắt; vì vậy output có thể dài hơn mục tiêu ký tự.

**Sai khác metadata cần biết:** sentence chunks được ghi chunk_overlap_chars=0, nhưng câu quá dài có thể fallback fixed với overlap config120. Vì vậy không dùng trường metadata đó để chứng minh mọi sentence chunk không overlap. Đây là phát hiện code-path, không phải bằng chứng toàn snapshot đã gặp fallback này. Chưa sửa code/metadata.

## 4. Bảng: chia theo nhóm hàng, giữ ngữ cảnh

[Table chunker](../../src/core/document_processing/chunking/table/chunker.py) chuyển bảng cấu trúc sang text. Khi có thông tin, mỗi fragment gồm:

```text
Section: Warehouse
Table: Inventory
Columns: Product ID | On-hand Units
Row 1: Product ID: 19 | On-hand Units: 120
```

Tên bảng và section chỉ được thêm nếu parser đã cung cấp. Header cột được lặp cùng text tên trường trong mỗi hàng. Điều này giúp hiểu giá trị, nhưng tăng số token lặp.

Thuật toán thêm từng hàng; nếu chunk đã có hàng và thêm hàng mới vượt size, flush chunk cũ rồi bắt đầu fragment mới với header lặp. **Hàng đầu tiên quá dài vẫn được thêm nguyên**, nên1100 không phải hard cap. Hàng rỗng hoàn toàn bị bỏ. Bảng không có cột không tạo chunk; bảng có cột nhưng không có hàng dữ liệu có thể tạo fragment chỉ chứa header.

Table parser chunk không overlap hàng; lặp header khác với overlap hàng. Metadata gồm table_index, table_row_start/end, fragment index/count và page khi có. Built-in PDF có [heuristic nối quan hệ bảng tiếp trang](../../src/core/document_processing/pipelines/built_in/table_processor.py): chỉ liên kết các bảng trang liền nhau khi cột/vị trí/title phù hợp và không mơ hồ, thêm continuation metadata chứ không gộp hàng thành một bảng mất ranh giới trang. Không bảo đảm mọi bảng nhiều trang hoặc tự gắn mọi chú thích sau bảng vào mọi fragment.

## 5. Khi vượt giới hạn thì chuyện gì xảy ra?

| Điều kiện | Cách xử lý hiện tại |
|---|---|
| Cả bảng dài hơn1100ký tự | Chia thành các nhóm hàng, lặp header. |
| Một hàng riêng dài hơn1100ký tự | Giữ nguyên ở parser; kiểm token ở bước sau. |
| Parser chunk vừa ngân sách token | Giữ nguyên nội dung ở bước embedding. |
| Nội dung vượt ngân sách token | Chia thành các đoạn con theo token; có thể cắt giữa câu/hàng. |
| Có prefix Section/Table/Columns hợp lệ | Dự phòng ngân sách cho prefix và lặp lại ở mỗi đoạn con. |
| Header quá dài, không còn chỗ cho body | Raise ValueError; không âm thầm bỏ header hoặc nhận chuỗi quá dài. |
| Thực sự hết RAM/VRAM | Chưa thấy fallback tự giảm batch, chia theo RAM hoặc đổi CPU. Exception bắt được sẽ đi vào luồng failed; nếu OS kill process thì không bảo đảm handler hoàn tất. |

[Embedding chunker](../../src/core/tokenization/embedding_chunker.py) chỉ nhận diện các dòng đầu liên tiếp bắt đầu đúng `Section: `, `Table: `, `Columns: `. Không nhận diện tùy ý mọi header/footer của PDF.

[Embedding service](../../src/core/embeddings/embedding_service.py) E5 mặc định encoder cap512, dự phòng4token cho prefix → truyền budget508 cho chunker. [TokenCounter](../../src/core/tokenization/token_counter.py) trừ tiếp special tokens; cached E5 có2special tokens. Như vậy giới hạn text thuần thông thường được tính bảo thủ là506token, không phải được phép dùng512token body rồi cộng thêm prefix.

Token splitter dùng truncation=False khi đo; fitting text trả nguyên. Generic overlap32token; nhánh body sau header điều chỉnh overlap theo phần budget còn lại, không quá32. Có kiểm lại các slice, nhưng không giữ hàng/câu như parser. Header lặp + overlap cũng phải vừa budget.

**Giới hạn kiểm tra:** upload/retry gọi chunk builder trước embedding. EmbeddingService trực tiếp không tự kiểm lại số token prefixed trên mọi caller; không khẳng định mọi lời gọi encode trong toàn repo đều chống truncation tuyệt đối.

## 6. Header, footer và source mapping

| Thành phần | Có giữ không? |
|---|---|
| Tên section | Thêm vào text khi metadata có và tránh một số lặp title; không có thì không tự tạo nội dung nguồn. |
| Tên bảng và header cột | Lặp theo fragment bảng khi có; token layer giữ các prefix được nhận diện nếu budget cho phép. |
| Số trang và vị trí | Metadata khi parser cung cấp; không phải mọi định dạng/chunk đều có page_number hoặc section. |
| Page header/footer PDF built-in | Không có bộ lọc tổng quát; có rule bỏ dòng cuối khớp dạng Page/Trang N of/M. Không bảo đảm giữ tất cả hoặc loại tất cả. |
| Docling | Mapper bỏ page_header/page_footer; có thể giữ footnote như element. |
| PPStructure / nhánh MinerU basic | Bỏ các block được nhận diện header/footer/page_number. |
| Header/footer DOCX riêng | Reader native đọc body trong word/document.xml, không trích riêng word/header*.xml hoặc footer*.xml. |
| Ghi chú/ngoại lệ bên dưới bảng | Chỉ giữ nếu parser xuất ra nội dung; không có bảo đảm chunker tự gắn chúng vào từng fragment bảng. |

Nguồn: [built-in footer rule](../../src/core/document_processing/pipelines/built_in/text_extractor.py), [native DOCX reader](../../src/core/document_processing/readers/office/docx/digital_born/processor.py), [Docling mapper](../../src/core/document_processing/pipelines/docling/result_mapper.py), [MinerU mapper](../../src/core/document_processing/pipelines/mineru/result_mapper.py), các PPStructure page parser.

Header có đúng hay không còn phụ thuộc reader: native DOCX lấy hàng đầu làm header; native XLSX chọn hàng sớm nhất có nhiều ô không rỗng nhất, dùng các hàng sau làm records. Vì vậy bảng có header nhiều tầng/merged cells hoặc ghi chú trước header không được bảo đảm phục hồi đầy đủ chỉ nhờ chunker.

Các embedding chunk giữ source_parser_index, source_content_sha256, source_child_index/count và source_spans. Source spans ánh xạ ký tự về parser content, không tự là tọa độ gốc trên ảnh/PDF. Bước chia token có thể copy table_row_start/end của parent; không coi đó là bằng chứng mọi đoạn con chứa trọn mọi hàng trong khoảng. Dùng source spans/nội dung để kiểm evidence thực.

## 7. Snapshot đang dùng: số đo và phạm vi

Đếm lại frozen JSONL, không phải regenerate parser hiện tại:

| Chỉ số | VI chung trong snapshot | EN mở rộng riêng |
|---|---:|---:|
| Tài liệu |5|5|
| Parser chunks |532|531|
| Embedding chunks |532|531|
| Source child count |1 cho mọi chunk|1 cho mọi chunk|
| Tổng ký tự parser content |655.615|656.300|
| Parser chunks vượt1100ký tự |425|425|
| Parser chunk dài nhất |1374ký tự|1374ký tự|
| E5 prefixed/special input tokens |224.845|224.358|
| Input dài nhất |476/512|476/512|

VI có505parser chunks dạng table_row_groups;424trong số này vượt1100ký tự. Còn1text chunk vượt1100. Không có contradiction: giữ hàng/header có thể vượt mục tiêu ký tự nhưng vẫn vừa token budget. Hai giai đoạn tồn tại, nhưng bộ này không tạo thêm child ở bước token.

Metadata/corpus frozen còn nhãn chuẩn bị Qwen cũ; actual E5 vectors đã xác minh hash và token được đếm lại riêng. Không sửa frozen file để che provenance này. Không dùng current parser config để khẳng định vừa regenerate ra cùng532chunks; thay parser có thể đổi output.

Nguồn: [VI parser JSONL](../../artifacts/evaluation/heldout-review2-v1/inputs/parser_vi.jsonl), [EN parser JSONL](../../artifacts/evaluation/heldout-review2-v1/inputs/parser_en.jsonl), [frozen corpus](../../artifacts/evaluation/heldout-review2-v1/inputs/corpus.jsonl), [token/resource stats](retrieval-report-stats.json), [kiểm đếm ngày24/10](dataset-count-verification-20261024.json).

## 8. Tài nguyên: đã biết gì, chưa biết gì?

Chunking string/token và embedding model không phải cùng khoản chi phí. Parser có thể tốn OCR/render ảnh trước khi chunking; tokenization dùng CPU/RAM; encoder/reranker có thêm weights và bộ nhớ inference. Bảng dài nhiều cột làm header/tên trường lặp, tăng token và số đoạn. Chia nhiều đoạn giúp mỗi input vừa model nhưng không tự giảm tổng công việc.

- Chưa có phép đo riêng thời gian/peakRAM cho ChunkingProcessor/TokenCounter trên bộ này. Không điền số ms/MB chunking giả định.
- [E5 service](../../src/core/embeddings/embedding_service.py) cache backend và khóa initial load, nhưng local encode không đặt batch/device/dtype rõ trong file này; không gán batch2benchmark hoặc batch4BGE cho production E5.
- [BGE](../../src/core/retrieval/reranker.py) là query-time rerank, FP32/batch4, mặc địnhCPU và một inference lock; không phải bộ chia chunk.
- Upload hiện có cap50MiB và Office reader có archive guards; không phải bảo đảm PDF render/expanded XML/model fit toàn bộRAM.
- App giữ parser output, danh sách bounded chunks, input texts, vectors và tuples lưuDB trongRAM; chưa streaming toàn luồng từng chunk.
- File weights cache E5≈1.060,68MiB; BGE≈2.165,86MiB. Kích thước file không phảiVRAM.
- PeakTorch2,212GiB là run nạp model tuần tự; không phải chunking-only hoặc production giữ nóng hai model.
- Thời gian tạo document vectors lịch sử22,12giây là cho cả1.063bilingual chunks trênRTX2060/FP32/batch2. [Pilot ngày18/10](../../artifacts/evaluation/embedding-comparison-20261018/comparison.md) có timing riêng532VI là14,15giây; cả hai không phải phép đo ingestion live mới trong audit này.
- Ước tính payload vector thuần:532×768×4byte≈1,56MiB. Không tính text, metadata, pgvector/index, Python object hoặc modelRAM; không gọi đây là kích thướcDB.

## 9. Slide live: ưu tiên chỉnh gì?

Canva revision78 có29trang; chỉ đọc text, chưa xem được thumbnail nên chưa audit layout/font/mũi tên.

**Các bảng retrieval vẫn khớp benchmark:**52/62/63/69ca, Recall/MRR, BGE ablation, latency và11failures. Giữ nhãn BM25-original/translated terms như người dùng muốn.

1. Slide10 nếu mô tả dataset chung: dùng **532 chunks /224,845 E5 input tokens**. Nếu giữ1,063/449,203 thì phải gắn nhãn bilingual benchmark.
2. Slide15 giữ scope benchmark, diễn đạt rõ: **5 Vietnamese source documents +5 corresponding English versions;1,063chunks;20intents;80cases.** Không sửa thành5docs/532 mà giữ80case metrics không giải thích extensionEN.
3. Câu source mapping nên là: **Document/chunk IDs and source spans; page/section metadata where available.** Không nói mọi chunk có page/section.
4. Slide metrics/results thêm: **Evidence coverage is not generated-answer accuracy.**
5. Ablation note: **Translation and fusion effects are not isolated.** Có thể để speaker notes.
6. Dataset overview chung, limitations/conclusions, source/owner và các phần thành viên khác còn placeholder. Roadmap/số trang cần chỉnh khi ráp deck, chọn main/backup theo khung18–25.

## 10. Đoạn trả lời với thầy

“Em chia nội dung theo cấu trúc trước, rồi kiểm tra theo tokenizer model. Với văn bản, ưu tiên câu; với bảng, ưu tiên nhóm hàng và lặp header.1.100ký tự là mục tiêu tổ chức, không phải hard cap. Nếu hàng dài mà vẫn vừa token thì giữ nguyên; nếu quá token thì chia body và giữ header khi có thể. Header quá dài sẽ báo lỗi, còn thiếuRAM/VRAM hiện chưa có cơ chế tự giảm batch. Em lưu mapping về parser để kiểm evidence. BộVI có532chunk, dài nhất476/512token, không cần tách thêm ở bước token. Em chưa có chunk-size/overlap ablation hoặc memory profile riêng để nói cấu hình đã tối ưu.”

Reranker không sửa được evidence chưa vào candidate pool.11losses trong benchmark chưa chứng minh do chunking, và chưa chứng minh đổi chunking sẽ sửa chúng.
