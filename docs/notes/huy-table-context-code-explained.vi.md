# Ghi chú riêng cho Huy: hiểu bản sửa context bảng

Ngày ghi: 31/10/2026. Đây là bản giải thích để đọc lại, không phải yêu cầu thay đổi database.

## 1. Đọc phần này trước, chưa cần đọc code

Mỗi chunk nên tự nói rõ nó đang mô tả cái gì. AI có thể chỉ nhận một chunk, không nhận đoạn phía trước nó.

Ví dụ trước sửa:

```text
Chunk 39: CTL-4100
Chunk 40: Weight = 230 g
Chunk 41: CTL-4100WL
Chunk 42: Weight = 250 g
```

Nếu chỉ lấy chunk 42, AI thấy 250 g nhưng không biết thuộc model nào.

Mục tiêu sau sửa:

```text
Section: Important Product Information > CTL-4100WL
Columns: Property | Value
Weight: 250 g
```

Không sửa 250 g thành 230 g. Mình giữ tên sản phẩm cùng với con số để tránh dùng nhầm bảng.

## 2. Các tên trong code nghĩa là gì?

| Tên | Hiểu bằng lời thường |
|---|---|
| `elements` | Danh sách các phần tử theo thứ tự đọc: heading, đoạn văn, dấu đánh vị trí bảng… |
| `tables` | Danh sách nội dung bảng: cột và dòng |
| `table_ref` | Số trỏ từ một phần tử trong `elements` sang bảng trong `tables` |
| `metadata` | Thông tin đi kèm: trang, section, vị trí, quyền… |
| `section_path` | Đường dẫn từ mục lớn tới mục nhỏ |
| `section_title` | Tên mục cụ thể, thường là mục cuối đường dẫn |
| `bbox` | Khung vị trí của đối tượng trên trang |
| `source_elements` | Các tham chiếu giúp truy ngược chunk về dữ liệu đầu vào |
| `chunk` | Một phần nội dung chuẩn bị cho truy xuất |
| `embedding passage` | Chunk sau bước kiểm tra/tách theo số token để đưa vào model embedding |

Hai danh sách liên quan như sau:

```python
elements = [
    {"text": "CTL-4100WL"},
    {"table_ref": 0},
]

tables = [
    {"columns": ["Property", "Value"],
     "rows": [{"Property": "Weight", "Value": "250 g"}]},
]
```

`table_ref: 0` nghĩa là lấy bảng đầu tiên trong `tables`. Nó không phải `document_id`, cũng không phải số thứ tự chunk.

Một bảng có thể tạo nhiều chunk. Có 6 bảng nhưng 11 chunk bảng không có nghĩa là bị trùng.

## 3. Toàn bộ luồng, nhìn một lần

```text
Docling đọc tài liệu
  → mapper giữ heading/section cùng bảng
  → chuẩn hóa tham chiếu bảng, xử lý tham chiếu lặp
  → ChunkingProcessor chia bảng theo dòng
  → mỗi phần lặp lại toàn bộ đường dẫn section và tên cột
  → kiểm tra/tách theo giới hạn token E5
  → embedding và lưu chỉ mục ở bước sau
```

Code mới tập trung vào các bước trước embedding. Sửa code không tự cập nhật các chunk đang lưu trong database.

## 4. Mapper nhớ đang đọc mục nào

File: [result_mapper.py](../../src/document_processing/docling_adapter/result_mapper.py).

```python
headings_by_level = {}
```

Đây là sổ ghi heading đang có hiệu lực, ví dụ:

```python
{0: "Thông tin sản phẩm", 1: "Thông số", 2: "CTL-4100"}
```

Khi gặp heading mới:

```python
level = 0 if element_label == "title" else int(getattr(item, "level", 1))
```

Tiêu đề tài liệu dùng cấp 0; section dùng cấp mà Docling cung cấp, mặc định 1 nếu không có thuộc tính cấp.

```python
headings_by_level = {
    key: value
    for key, value in headings_by_level.items()
    if key < level
}
headings_by_level[level] = text
```

Ví dụ gặp CTL-4100WL ở cấp 2: giữ cấp 0 và 1, bỏ CTL-4100, thay bằng CTL-4100WL. Gặp heading cấp 1 mới thì các mục cấp 2 cũ cũng bị bỏ vì đã ra khỏi phạm vi của chúng.

```python
section_path = [headings_by_level[key] for key in sorted(headings_by_level)]
```

Đổi sổ thành đường dẫn theo thứ tự cấp:

```python
["Thông tin sản phẩm", "Thông số", "CTL-4100WL"]
```

Đoạn văn giải thích không thay đổi sổ heading. Vì vậy bảng không cần nằm ngay sát heading để giữ được section.

Khi gặp bảng:

```python
section_metadata = {
    "section_path": list(section_path),
    "section_title": section_path[-1] if section_path else None,
}
```

- `list(section_path)` tạo bản sao đường dẫn hiện tại.
- `[-1]` lấy phần tử cuối.
- Không có heading thì để `None`, không tự bịa tên.
- Thông tin này được chép vào cả bảng và phần tử tham chiếu bảng.

Với Word, [docx_semantics.py](../../src/document_processing/docling_adapter/digital_born/docx_semantics.py) dùng heading/style của Word để cập nhật lại đường dẫn trên cả hai nơi. Đây là bước tinh chỉnh cấu trúc, không phải OCR lại.

## 5. Vì sao VietStyle cần sửa riêng?

Dữ liệu thật có tình huống:

```text
Ở vị trí gốc:
  table_ref = 3
  nhãn trong metadata = text (sai)
  section = Appendix B (đúng)

Ở cuối tài liệu:
  table_ref = 3 lần nữa
  nhãn = table
  không có section
```

Code trước bỏ qua bản gốc vì thấy nhãn `text`, rồi dùng bản cuối nên mất section và vị trí gốc.

File mới: [references.py](../../src/core/chunking/table/references.py).

```python
if "table_ref" not in element and kind != "table":
    continue
```

Chỉ bỏ qua nếu vừa không có tham chiếu bảng, vừa không có nhãn bảng. Có `table_ref` thì kiểm tra xem nó trỏ tới bảng hợp lệ không, thay vì chỉ tin nhãn `text`.

```python
if type(ref) is not int or not 0 <= ref < len(tables):
    raise ValueError(...)
```

Chỉ chấp nhận số nguyên trỏ tới bảng tồn tại. Không âm thầm bỏ qua tham chiếu sai.

```python
if ref not in referenced:
    referenced[ref] = (index, metadata)
    continue
```

Lần đầu gặp bảng thì ghi vị trí và metadata vào sổ `referenced`.

Lần sau gặp cùng bảng:

- Giữ vị trí đầu tiên.
- Nếu section/location có giá trị ở cả hai nhưng khác nhau, báo lỗi.
- Nếu bản đầu thiếu trường section mà bản sau có, bổ sung trường thiếu.
- Không tự gộp quyền truy cập từ các tham chiếu.

Ví dụ `Appendix B` và section trống tương thích. `Appendix B` và `Appendix C` mâu thuẫn, phải kiểm tra.

## 6. Hai luồng đều dùng cách xử lý đó

[processor.py](../../src/core/chunking/processor.py) gọi `resolve_table_references()` trước khi tạo chunk bảng. Nội dung lấy từ `tables`; vị trí và section lấy từ tham chiếu đã chọn.

Khi gom văn bản:

```python
if element_type == "table" or "table_ref" in element:
    flush()
    continue
```

`flush()` nghĩa là kết thúc nhóm văn bản đang gom. Bảng được để cho bộ chia bảng xử lý riêng, kể cả khi nhãn bị sai.

[processing_output.py](../../src/core/chunking/processing_output.py) chuẩn bị output đã lưu cho worker/preview, cũng dùng cùng hàm xử lý tham chiếu. Khi gặp tham chiếu lặp:

```python
if index != source_index:
    continue
```

Nghĩa là bỏ qua bản không phải vị trí đã chọn. Nguồn tham chiếu vẫn dùng chỉ số của dữ liệu gốc; quyền lấy từ bản ghi tài liệu.

## 7. Dữ liệu cũ thiếu section thì sao?

Trong `processor.py`, `_adjacent_table_section()` là phương án dự phòng, không phải cách nối chính cho tài liệu mới.

Nó chỉ kế thừa heading ngay trước bảng nếu:

- Được đánh dấu là title/section_header.
- Có cùng số trang.
- Có bbox TOPLEFT hợp lệ.
- Bảng nằm dưới heading, khoảng cách tối đa bằng hai lần chiều cao heading.
- Tâm ngang của heading nằm trong chiều rộng bảng.

Ví dụ heading kết thúc ở y=235, bảng bắt đầu ở y=239: cách 4. Heading cao 10, nên khoảng cách này đạt ngưỡng 20.

Đủ điều kiện thì sao chép section; không đủ thì không suy đoán. Quy tắc này giúp Wacom cũ nhưng không bảo đảm đúng cho mọi layout. Section đã có sẵn được ưu tiên.

## 8. Tại sao phải đưa cả đường dẫn vào chunk?

Tên quan trọng có thể nằm ở đầu:

```python
section_path = ["CTL-4100WL", "Thông số kỹ thuật", "Trọng lượng"]
section_title = "Trọng lượng"
```

Chỉ dùng `section_title` sẽ mất tên model trong nội dung đưa vào embedding.

Hàm `section_context()` ở [text/chunk_builder.py](../../src/core/chunking/text/chunk_builder.py):

```python
if metadata.get("element_type") == "table" and isinstance(path, list):
    headings = [value.strip() for value in path
                if isinstance(value, str) and value.strip()]
    if headings:
        return " > ".join(headings)
```

Đọc là: với bảng, bỏ thành phần trống rồi nối các cấp bằng ` > `.

```text
CTL-4100WL > Thông số kỹ thuật > Trọng lượng
```

Nếu không có đường dẫn dùng được thì quay về `section_title`.

[table/chunker.py](../../src/core/chunking/table/chunker.py) dùng chuỗi này để tạo:

```text
Section: CTL-4100WL > Thông số kỹ thuật > Trọng lượng
Columns: Property | Value
Row 1: Property: Weight | Value: 250 g
```

Hàm hoàn thiện chunk chung cũng gọi `section_context()`, để không chèn thêm một dòng `Section: Trọng lượng` khác phía trên. Văn bản thường vẫn dùng cách lấy section cũ; thay đổi đường dẫn đầy đủ tập trung vào bảng.

## 9. Bảng dài và giới hạn E5

Bộ chia bảng giữ nguyên từng dòng khi tạo parser chunk, lặp section/tên bảng/tên cột cho mỗi phần.

Sau đó [embedding_chunker.py](../../src/core/tokenization/embedding_chunker.py) có thể tách thêm theo token. Nó nhận diện các dòng đầu `Section:`, `Table:`, `Columns:` để lặp lại trên mỗi đoạn. Bước token có thể cắt giữa một dòng dài; không nên hiểu rằng mỗi embedding passage luôn chứa nguyên dòng bảng.

Nếu riêng phần heading/header quá dài không còn chỗ cho nội dung thì báo lỗi, không âm thầm bỏ tên sản phẩm.

## 10. Những ký hiệu Python dễ gây rối

| Code | Nghĩa |
|---|---|
| `d.get("x")` | Lấy trường x; không có thì trả None |
| `a or b` | Dùng a nếu a có giá trị; nếu không thì dùng b |
| `continue` | Bỏ phần còn lại của vòng lặp hiện tại, sang phần tử tiếp |
| `return {}` | Hàm trả về dictionary rỗng; không tìm được thông tin bổ sung |
| `d.update(other)` | Chép trường từ other vào d; trùng tên thì ghi đè |
| `{**a, **b}` | Tạo dictionary mới từ a và b; trường trùng lấy giá trị của b |
| `enumerate(items)` | Duyệt cả số thứ tự và phần tử |
| `setdefault("metadata", {})` | Tạo metadata rỗng nếu chưa có |
| `raise ValueError(...)` | Dừng xử lý với thông báo đầu vào không hợp lệ |

## 11. Cách tự đọc lại code

Không cần đọc hết một lượt. Theo thứ tự này:

1. Nhìn một cặp heading và bảng Wacom, xác định tên model nằm ở đâu.
2. Đọc phần `section_metadata` trong mapper: bảng nhận tên model như thế nào?
3. Đọc `resolve_table_references`: chọn đúng vị trí bảng như thế nào?
4. Đọc `section_context`: biến đường dẫn thành dòng chữ như thế nào?
5. Đọc `build_table_chunks`: dòng chữ đó đi vào từng chunk như thế nào?
6. Cuối cùng mới xem fallback bbox và token splitting.

Khi đọc một hàm, tự hỏi ba câu: đầu vào là gì, nó thay đổi gì, đầu ra là gì?

## 12. Đã kiểm tra gì và chưa kiểm tra gì?

- Chạy lại 24 test liên quan, đạt.
- Preview chỉ đọc trên Wacom, hai bản VietStyle và RMIT bằng tokenizer E5 đã khóa phiên bản.
- Token lớn nhất lần lượt 304, 291, 291, 343; đều dưới 512, đã tính `passage: ` và special tokens.
- Kiểm tra các dòng bảng không rỗng được chia đúng một lần tại bước parser chunking, giữ prefix và quyền truy cập; dữ liệu nguồn không bị sửa.
- Kết quả local: `artifacts/local/table-context-validation-20261031/summary.json` (không đưa vào Git).
- Chưa chạy OCR đầy đủ trên VPS, chưa đánh giá câu trả lời sau khi embedding lại.
- Sửa mapper không tự viết lại output cũ. Các chunk cũ đang phục vụ trên VPS chưa tự đổi theo code local.
- Chưa commit, deploy hay cập nhật Supabase cho chuỗi thay đổi này tại thời điểm ghi chú.

Giới hạn: parser nhận sai heading/thứ tự đọc thì liên kết vẫn có thể sai; tham chiếu mâu thuẫn sẽ báo lỗi xử lý; chunk/index có thể đổi khi chạy lại nên cần kiểm tra các tham chiếu và bộ đánh giá đang dùng trước khi thay thế dữ liệu.
