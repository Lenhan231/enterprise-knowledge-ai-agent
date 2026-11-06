# SQL Agent

Tài liệu dựa trên **`main` local tại commit `c118df325447899f8ea6108d441e31ba6df0a69b`**.

## 1. Agent làm gì?

SQL Agent nhận câu hỏi bằng ngôn ngữ tự nhiên, tạo truy vấn PostgreSQL, kiểm tra truy vấn rồi đọc dữ liệu từ schema `commerce`. Ví dụ: tổng doanh thu theo tháng, số đơn theo khu vực, hoặc tỷ lệ hết hàng tại một ngày ghi nhận tồn kho.

Cần phân biệt hai lớp:

- `SQLAnalyticsAgent`: hiểu câu hỏi, tạo và kiểm tra SQL, thực thi, trả các dòng dữ liệu cùng thông tin nguồn.
- `AnalyticsAgent`: gọi lớp trên rồi dùng mô hình để viết câu trả lời dễ đọc từ kết quả. Trong chế độ chat `sql`, router gọi lớp bọc này.

Agent có thể dùng cả 13 bảng được cho phép, không chỉ `inventory` và `products`. Tuy nhiên, câu hỏi tồn kho có luồng xử lý riêng và quy tắc chặt hơn.

## 2. Luồng tổng thể

```text
Câu hỏi + danh tính đã xác thực
    → kiểm tra quyền analytics:read
    → nhận diện chỉ số và kiểm tra yêu cầu nghiệp vụ
    → diễn giải thành mô tả có cấu trúc khi cần
    → mô hình sinh SQL từ schema và định nghĩa chỉ số
    → kiểm tra cấu trúc SQL và ý nghĩa nghiệp vụ
    → repository kiểm tra SQL lần nữa, chạy giao dịch chỉ đọc
    → trả rows, SQL, tham số, nguồn và giới hạn dữ liệu
    → AnalyticsAgent viết câu trả lời kèm nguồn [S1], [S2]...
```

API chat của ứng dụng là `POST /api/agents/chat`, chọn `agent_mode: "sql"` để gọi trực tiếp chế độ này. Chế độ tự động cũng có thể điều phối tác vụ sang analytics. Quyền phải đến từ danh tính do server xác thực; ghi quyền trong câu hỏi hoặc metadata không cấp quyền truy vấn.

### Bước diễn giải trước khi sinh SQL

Agent nhận diện chỉ số qua các tên gọi đã khai báo. Khi có ngữ cảnh SQL hội thoại, chưa nhận diện được chỉ số, hoặc nhận diện được chỉ số tồn kho, agent gọi mô hình tạo `MetricMapping`, tức mô tả có cấu trúc:

| Trường | Ý nghĩa |
| --- | --- |
| `metrics` | Chỉ số cần lấy, dùng ID có trong danh mục |
| `dimensions` | Cách chia nhóm, như sản phẩm hoặc danh mục |
| `filters` | Điều kiện lọc |
| `time` | Ngày ghi nhận (`snapshot`), mới nhất (`latest`), khoảng thời gian (`range`) hoặc lịch sử (`history`) |
| `ranking` | Chỉ số xếp hạng, chiều tăng/giảm và số dòng |
| `representation` | Kết quả tổng hợp (`aggregate`) hoặc theo sản phẩm (`product`) |

Code kiểm tra mô tả này rồi đưa vào prompt sinh SQL. **Trên `main`, mô hình vẫn sinh SQL cho câu hỏi tồn kho; chưa có `compile_inventory_query()` để biên dịch mô tả thành SQL bằng code.** Sau đó code kiểm tra SQL có giữ đúng chỉ số, nhóm, bộ lọc, thời gian và xếp hạng đã diễn giải hay không.

Câu hỏi ngoài tồn kho có thể được diễn giải thành `domain: "other"`, không chứa yêu cầu tồn kho. Khi đã nhận diện chỉ số ngoài tồn kho và không có ngữ cảnh hội thoại, agent có thể đi thẳng tới bước sinh SQL.

Ví dụ câu hỏi: “Ở lần ghi nhận mới nhất, tỷ lệ hết hàng theo danh mục là bao nhiêu?” Agent xác định chỉ số `stockout_rate`, nhóm theo `category`, dùng ngày lớn nhất trong `inventory.snapshot_date`, rồi tính theo công thức đã khai báo.

### Bước sinh SQL và sửa lỗi

Mô hình nhận câu hỏi, schema liên quan, các JOIN được phép và định nghĩa chỉ số; sau đó trả JSON chứa `sql`, `parameters`, `explanation`, hoặc yêu cầu làm rõ `clarification`.

`decode_query_plan()` đọc JSON và kiểm tra kế hoạch. Nếu SQL hoặc định nghĩa chỉ số không hợp lệ, agent có thể gửi lỗi cùng câu trả lời cũ cho mô hình sửa **một lần**: tối đa hai lần tạo kế hoạch, áp dụng cả câu hỏi tồn kho. Lỗi truy vấn database không kích hoạt vòng sửa kế hoạch.

Nếu không nhận diện được chỉ số trong danh mục, truy vấn đọc thông thường vẫn được phép, miễn vượt qua các kiểm tra áp dụng.

### Giới hạn khi kết hợp tồn kho và dữ liệu khác

Trên `main`, khi có chỉ số tồn kho, prompt chỉ cung cấp hai bảng `inventory` và `products`. `validate_metric_request()` từ chối yêu cầu chứa đồng thời chỉ số tồn kho và chỉ số thuộc mức chi tiết khác, với mã lỗi `incompatible_grain` và yêu cầu tách truy vấn.

Ví dụ, câu hỏi yêu cầu tồn kho và doanh thu trong cùng kết quả có thể bị yêu cầu tách riêng. Phiên bản này chưa có nhánh chuyên xử lý tồn kho kết hợp đơn hàng. Không nên xem các câu hỏi kết hợp đó là khả năng đã được bảo đảm chỉ vì các bảng đều có trong danh sách cho phép.

## 3. Các bảng được phép

Danh sách chính thức trong code là `APPROVED_COLUMNS` tại [text_to_sql.py](../../src/core/analytics/text_to_sql.py). Mỗi bảng chỉ được dùng những cột nằm trong danh sách này.

| Bảng | Dữ liệu chính |
| --- | --- |
| `commerce.sales` | Doanh thu và giá vốn theo ngày |
| `commerce.orders` | Đơn hàng, khách hàng, trạng thái và nguồn đặt hàng |
| `commerce.order_items` | Sản phẩm, số lượng, đơn giá và khuyến mãi trong từng dòng đơn |
| `commerce.customers` | Thông tin khách hàng, ngày đăng ký và kênh thu hút |
| `commerce.payments` | Phương thức, giá trị thanh toán và số kỳ |
| `commerce.geography` | Thành phố, khu vực và quận/huyện theo mã ZIP |
| `commerce.inventory` | Tồn kho và các chỉ số tại từng ngày ghi nhận |
| `commerce.products` | Thuộc tính sản phẩm, danh mục, phân khúc, giá và giá vốn |
| `commerce.promotions` | Điều kiện, thời gian và kênh khuyến mãi |
| `commerce.returns` | Số lượng trả hàng, lý do và tiền hoàn |
| `commerce.reviews` | Đánh giá và điểm số |
| `commerce.shipments` | Ngày gửi/giao hàng và phí vận chuyển |
| `commerce.web_traffic` | Lượt truy cập, phiên và nguồn truy cập theo ngày |

`build_sql_prompt()` chọn schema theo chỉ số: nếu có chỉ số tồn kho thì đưa `inventory` và `products`; các trường hợp khác đưa toàn bộ danh sách được phép. Prompt tồn kho còn bỏ các cột trùng thuộc tính sản phẩm ở `inventory` và bỏ `price`, `cogs` ở `products`. Agent không tự quét database để sử dụng bảng mới.

Các đường JOIN chính:

- `customers` ↔ `orders` qua `customer_id`; `customers` hoặc `orders` ↔ `geography` qua `zip`.
- `orders` ↔ `payments`, `order_items`, `shipments`, `returns`, `reviews` qua `order_id`.
- `products` ↔ `order_items`, `inventory`, `returns`, `reviews` qua `product_id`.
- `order_items` ↔ `promotions` qua `promo_id` hoặc `promo_id_2`.

Hiện không có JOIN được khai báo cho `sales` và `web_traffic`. Không thể tùy ý nối hai bảng chỉ vì chúng cùng có cột ngày.

## 4. Kiểm tra trước khi chạy

### Cấu trúc và quyền truy vấn

`validate_commerce_sql()` dùng `sqlglot` phân tích cấu trúc SQL, thay vì chỉ tìm từ khóa. Các kiểm tra chính:

- Chỉ một câu `SELECT`; kiểm tra cả truy vấn con và CTE (`WITH`).
- Chỉ bảng, cột, hàm và quan hệ JOIN đã được cho phép; tên bảng phải có schema `commerce`.
- Không cho các cấu trúc ghi dữ liệu, `SELECT *`, `CROSS JOIN`, JOIN không có `ON`, hoặc `UNION`.
- Câu SELECT cuối phải có `LIMIT` từ 1 đến 200.
- Placeholder `$1`, `$2`... phải khớp danh sách tham số; tối đa 32 tham số kiểu JSON đơn giản. Tham số ngày được nhận diện phải dùng `YYYY-MM-DD` và được chuyển thành kiểu ngày.

Prompt yêu cầu tách giá trị lọc khỏi chuỗi SQL bằng tham số. Cột trong SQL phải có alias bảng; thiếu alias hoặc thiếu `LIMIT` sẽ bị từ chối, không có bước tự bổ sung. `CAST` chỉ được phép sang `DATE` hoặc `NUMERIC`. `EXISTS` chưa nằm trong danh sách hàm được phép của phiên bản này.

### Đúng ý nghĩa nghiệp vụ

SQL chạy được chưa chắc trả lời đúng câu hỏi. `validate_metric_definitions()` và các bộ kiểm tra liên quan đối chiếu công thức, nguồn, phạm vi thời gian, điều kiện lọc và mức chi tiết của dữ liệu.

Ví dụ, một đơn có nhiều dòng sản phẩm. Nếu nối đơn hàng với các dòng chi tiết rồi cộng lại giá trị thuộc cấp đơn, tổng có thể bị nhân lên. `join_validation.py` kiểm tra kiểu sai lệch này dựa trên khóa chính đã khai báo. Có thể bỏ JOIN chi tiết không cần thiết hoặc dùng `COUNT(DISTINCT khóa)` khi đếm thực thể; `SUM(DISTINCT value)` không phải cách sửa chung. Trên `main`, bộ kiểm tra chưa chứng minh được tính duy nhất của nguồn đã GROUP BY để cho phép mọi kiểu JOIN giữa các bảng tổng hợp.

Với tồn kho, một dòng quan sát có mức chi tiết sản phẩm × ngày ghi nhận. Không được cộng `stock_on_hand` qua nhiều ngày thành tổng tồn kho. `latest` là `MAX(snapshot_date)` của toàn bảng tồn kho; không phải ngày agent tự đoán hoặc ngày mới nhất sau khi lọc sản phẩm.

Khi đã có `MetricMapping` tồn kho, `validate_mapped_sql()` yêu cầu một SELECT trực tiếp, không CTE, `HAVING`, `DISTINCT` hoặc `OFFSET`. Đầu ra, bộ lọc, nhóm, thời gian và xếp hạng phải khớp mô tả. Kết quả tổng hợp phải giữ nhóm theo từng ngày `snapshot_date`; nếu không xếp hạng thì dùng `LIMIT 200`.

Định nghĩa chỉ số thông thường nằm trong `metric_ontology.py`; danh mục tồn kho được nạp từ [vietstyle_metrics_v1.yaml](../../data/semantic/vietstyle_metrics_v1.yaml). Danh mục quy định công thức, đơn vị, cách tổng hợp, xử lý NULL, nguồn và trạng thái định nghĩa/phê duyệt. Chỉ số chưa có định nghĩa hoặc chưa được review sẽ bị chặn. Ví dụ hiện có `reorder_quantity`, `safety_stock`, `inventory_turnover` chưa được giải quyết; agent không tự bịa công thức cho chúng.

### Thực thi tại database

`CommerceRepository` kiểm tra lại SQL rồi chạy bằng `asyncpg` trong giao dịch `readonly=True`.

- Kết nối lấy từ `ANALYTICS_DATABASE_URL`, dùng tài khoản đọc dữ liệu riêng.
- Khi tạo kết nối, code kiểm tra quyền đọc các nguồn đã duyệt và từ chối role có những quyền cao hoặc quyền ghi được kiểm tra.
- Timeout câu lệnh mặc định là 5 giây, đặt bằng `SET LOCAL statement_timeout`. Pool cũng có `command_timeout` mặc định 5 giây.
- Ứng dụng dùng `LazyCommerceRepository`: kết nối analytics được tạo khi thực sự truy vấn.

## 5. Hỏi tiếp trong hội thoại

Khi chạy chế độ `sql` với `conversation_id`, router lưu mô tả tồn kho đã chấp nhận và câu hỏi đang chờ làm rõ. Người dùng có thể hỏi tiếp như “chỉ lấy 5 sản phẩm” hoặc đổi ngày, điều kiện lọc, cách nhóm.

Mô hình xác định đây là câu mới, câu tiếp nối, hay câu trả lời làm rõ. Code áp dụng thay đổi lên mô tả cũ, kiểm tra lại rồi chạy truy vấn mới. Kết quả cũ không được dùng thay cho dữ liệu nguồn mới.

Với `latest` trong luồng có ngữ cảnh hội thoại, server đọc `MAX(snapshot_date)` trước rồi gắn ngày cụ thể vào mô tả. Câu hỏi tiếp theo giữ ngày đó nếu người dùng không yêu cầu đổi hoặc làm mới. Bộ lọc chỉ thay thế điều kiện của trường được sửa; các phần không sửa được kế thừa từ mô tả trước.

Bộ nhớ hỏi tiếp chuyên biệt này hỗ trợ chỉ số tồn kho. Với chủ đề khác, nên viết lại câu hỏi đầy đủ. Trạng thái nằm trong bộ nhớ của tiến trình, gắn với người dùng và `conversation_id`, có thời hạn mặc định 30 phút; không phải lịch sử bền vững dùng chung giữa các tiến trình.

## 6. Kết quả trả về và cách đọc lỗi

`run_payload()` trả một dictionary. `run()` chuyển nó thành `AgentResult`: `answer`, `evidence`, `metadata` được giữ riêng; các dữ liệu như `rows`, `sql`, `parameters` nằm trong `data`.

| Trường | Dùng để làm gì |
| --- | --- |
| `ok` | Có kết quả thành công hay không |
| `rows` | Các dòng dữ liệu thực tế từ database |
| `sql`, `parameters` | Truy vấn và tham số khi thực thi thành công, kể cả kết quả rỗng |
| `attempted_sql` | SQL đã thử khi bị từ chối hoặc lỗi database, nếu có |
| `query_status` | Có thể là `executed`, `rejected`, `error`; một số lỗi trước khi có SQL không có trường này |
| `metadata.source`, `evidence` | Các bảng nguồn của truy vấn và thông tin trích dẫn |
| `metadata.metrics` | Định nghĩa các chỉ số được dùng |
| `metadata.semantic_interpretation` | Mô tả tồn kho đã kiểm tra, nếu đi qua nhánh tương ứng |
| `limitations` | Giới hạn cần giữ khi diễn giải kết quả |

Trên `main` chưa có trường `metadata.execution_status`. Cần đọc kết hợp các dấu hiệu sau:

| Dấu hiệu | Ý nghĩa |
| --- | --- |
| `ok: true`, `query_status: executed` | Đã chạy và có dòng dữ liệu |
| `ok: false`, `query_status: executed`, `rows: []` | Đã chạy nhưng không có dòng phù hợp |
| `metadata.clarification_required: true` | Cần người dùng làm rõ |
| `query_status: rejected` | SQL đã thử bị từ chối |
| `query_status: error` | Truy vấn database không hoàn tất |
| `metadata.error_type` | Loại lỗi, ví dụ `SQLValidationError`, `MetricDefinitionError` |
| `metadata.metric_error_code` | Mã lỗi nghiệp vụ, ví dụ `snapshot_required`, `incompatible_grain` |

Lỗi trước khi có SQL có thể không có `query_status`. Với tồn kho, metadata có thể thêm `metric_catalog_version`, `historical_inventory`, `snapshot_dates`. Phiên bản này chưa thêm các trường riêng `columns`, `filters`, `time_scope`; thông tin bộ lọc và thời gian nằm trong `semantic_interpretation` khi có.

Sau khi SQL thành công, `AnalyticsAgent` gửi dữ liệu, định nghĩa chỉ số, giới hạn và nguồn cho mô hình viết phần trả lời. Nếu bước này lỗi, code trả thông báo dự phòng về số dòng và nguồn. SQL Agent trực tiếp thường chỉ trả `Query completed.`; phần diễn giải thuộc lớp bọc.

## 7. Những giới hạn cần nhớ

- Dữ liệu tồn kho là dữ liệu lịch sử. Ngày mới nhất trong bảng không mặc nhiên là tồn kho hôm nay. Prompt yêu cầu không đổi “hiện tại” thành ngày lịch sử mới nhất; `main` chưa có bước kiểm tra độ sẵn có của kỳ hiện tại như nhánh `QuocAn`.
- Không có quan sát không đồng nghĩa tồn kho bằng 0. Cờ `reorder_flag` lịch sử không tự tạo thành khuyến nghị đặt hàng hiện tại.
- Đơn vị tiền tệ của dataset chưa được xác nhận; không tự gắn USD hoặc VND.
- Chỉ số tỷ lệ trả dạng phân số: `0.25` tương ứng `25%`; các dòng kết quả không tự nhân 100.
- Có bảng trong danh sách cho phép không bảo đảm mọi câu hỏi về bảng đó đều trả lời được. Còn phụ thuộc cột, quan hệ JOIN, định nghĩa chỉ số và dữ liệu thực tế.
- Bước hiểu câu hỏi và viết câu trả lời vẫn phụ thuộc mô hình. Các kiểm tra bằng code giảm lỗi nhưng không chứng minh mọi diễn giải đều đúng.

## 8. Đọc code và kiểm tra ở đâu?

| File | Trách nhiệm |
| --- | --- |
| [sql_analytics_agent.py](../../src/core/agents/sql_analytics_agent.py) | Luồng xử lý SQL và trạng thái kết quả |
| [analytics_agent.py](../../src/core/agents/analytics_agent.py) | Viết câu trả lời từ dữ liệu SQL |
| [text_to_sql.py](../../src/core/analytics/text_to_sql.py) | Schema, JOIN, tạo prompt và kiểm tra SQL |
| [metric_mapping.py](../../src/core/analytics/metric_mapping.py) | Mô tả ý định tồn kho, hỏi tiếp và đối chiếu SQL với mô tả |
| [metric_ontology.py](../../src/core/analytics/metric_ontology.py) | Nhận diện và nạp định nghĩa chỉ số |
| [metric_validation.py](../../src/core/analytics/metric_validation.py) | Kiểm tra công thức và phạm vi nghiệp vụ |
| [join_validation.py](../../src/core/analytics/join_validation.py) | Kiểm tra JOIN làm sai mức chi tiết/tổng hợp |
| [commerce_repository.py](../../src/core/database/commerce_repository.py) | Kết nối và truy vấn chỉ đọc |
| [sql.py](../../src/core/prompts/sql.py) | Prompt sinh và sửa SQL |
| [router.py](../../src/core/agents/router.py) | Định tuyến và trạng thái hội thoại SQL |

Các test có trên `main` nên đọc: [test_sql_analytics.py](../../tests/test_sql_analytics.py), [test_sql_generation.py](../../tests/test_sql_generation.py), [test_sql_metric_definitions.py](../../tests/test_sql_metric_definitions.py), [test_sql_join_duplication.py](../../tests/test_sql_join_duplication.py) và [test_sql_followups.py](../../tests/test_sql_followups.py).

Khi debug, bắt đầu từ `ok`, `query_status`, `metadata.error_type` và `metadata.metric_error_code`; tiếp theo xem SQL và tham số, đối chiếu `metadata.metrics`, rồi kiểm tra `limitations`. Khi thêm bảng/cột hoặc chỉ số, cần cập nhật đồng bộ danh sách cho phép, quan hệ JOIN nếu có, định nghĩa chỉ số, quyền database và test liên quan.
