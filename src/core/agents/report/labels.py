"""Approved Vietnamese display labels for fixed reports."""

LABELS = {
    'sales_performance': 'Báo cáo kết quả bán hàng',
    'company_revenue': 'Doanh thu công ty',
    'company_cogs': 'Giá vốn hàng bán của công ty',
    'company_gross_profit': 'Lợi nhuận gộp của công ty',
    'company_gross_margin_pct': 'Biên lợi nhuận gộp của công ty',
    'company_revenue_change_pct': 'Thay đổi doanh thu so với kỳ trước',
    'order_count': 'Số đơn hàng',
    'delivered_line_revenue': 'Doanh thu từ các dòng hàng đã giao',
    'delivered_average_order_value': 'Giá trị trung bình của đơn hàng đã giao',
    'promotion_discount': 'Tổng chiết khấu dòng hàng',
    'sessions': 'Số phiên truy cập website',
    'S01': 'Doanh thu giảm',
    'S02': 'Lợi nhuận gộp bằng hoặc dưới 0',
    'S03': 'Doanh thu tăng và lợi nhuận gộp giảm',
    'S04': 'Không có điều kiện cảnh báo nào được kích hoạt',
    'sales_kpis': 'Chỉ số tài chính công ty',
    'sales_trend': 'Doanh thu và lợi nhuận gộp của công ty',
    'order_kpis': 'Đơn hàng và doanh thu từ hàng đã giao',
    'line_breakdown': 'Doanh thu từ hàng đã giao theo nhóm đã chọn',
    'sales_discount': 'Chiết khấu dòng hàng theo thời gian',
    'web_sessions': 'Phiên truy cập website từ nguồn riêng',
    'inventory_operations': 'Báo cáo tồn kho và vận hành',
    'observed_products': 'Số sản phẩm có dữ liệu tồn kho',
    'stock_on_hand': 'Tổng số đơn vị tồn kho',
    'stockout_products': 'Sản phẩm có cờ hết hàng',
    'stockout_flag_pct': 'Tỷ lệ sản phẩm có cờ hết hàng',
    'overstock_products': 'Sản phẩm có cờ tồn kho quá mức',
    'reorder_products': 'Sản phẩm có cờ cần đặt lại',
    'returned_order_count': 'Đơn hàng bị trả lại',
    'avg_delivery_days': 'Thời gian giao hàng trung bình',
    'avg_review_rating': 'Điểm đánh giá trung bình',
    'I01': 'Có cờ hết hàng',
    'I02': 'Có cờ cần đặt lại',
    'I03': 'Có cờ tồn kho quá mức',
    'I04': 'Không phát hiện cờ tồn kho',
    'inventory_kpis': 'Tình trạng tồn kho hiện tại',
    'inventory_flag_distribution': 'SKU có cờ theo danh mục',
    'stockout_product_table': 'Danh sách sản phẩm hết hàng',
    'operations_kpis': 'Giao hàng và trải nghiệm khách hàng',
    'inventory_snapshots': 'Số cờ hết hàng theo ngày chốt tồn kho',
}

SALES_SECTIONS_VI = {
    'executive_summary': 'Tóm tắt điều hành',
    'sales_kpis': 'Chỉ số bán hàng',
    'performance_analysis': 'Phân tích kết quả',
    'key_findings_and_explanations': 'Phát hiện chính và diễn giải',
    'decision_support': 'Hỗ trợ ra quyết định',
}

INVENTORY_COPY_VI = {
    'Inventory & Operations Report': 'Báo cáo tồn kho và vận hành',
    'Operations Summary': 'Tổng quan vận hành',
    'Inventory Snapshot Scorecard': 'Chỉ số tại ngày chốt tồn kho',
    'Product Risks': 'Rủi ro theo sản phẩm',
    'Fulfillment & Returns': 'Giao hàng và trả hàng',
    'Policy Evidence': 'Trích dẫn quy trình',
    'Fixed Decision Support': 'Hỗ trợ ra quyết định',
    'Data Quality': 'Chất lượng dữ liệu',
    'Validation summary': 'Kết quả kiểm tra dữ liệu',
    'Validation and source details': 'Chi tiết kiểm tra và nguồn dữ liệu',
    'Inventory records': 'Dữ liệu tồn kho', 'Product catalog': 'Danh mục sản phẩm',
    'Return records': 'Dữ liệu trả hàng', 'Order records': 'Dữ liệu đơn hàng',
    'Shipment records': 'Dữ liệu giao hàng', 'Customer reviews': 'Đánh giá của khách hàng',
    'Inventory snapshot': 'Dữ liệu tại ngày chốt tồn kho', 'Snapshot coverage': 'Độ đầy đủ tại ngày chốt',
    'Flag distribution': 'Phân bố cảnh báo', 'Stockout product list': 'Danh sách sản phẩm hết hàng',
    'Snapshot history': 'Lịch sử chốt tồn kho', 'Returned orders': 'Đơn hàng bị trả lại',
    'Shipment duration': 'Thời gian giao hàng', 'Review ratings': 'Điểm đánh giá',
    'Measure': 'Chỉ số', 'Value': 'Giá trị', 'Product': 'Sản phẩm', 'Stockout flags': 'Cờ hết hàng',
    'Why unavailable?': 'Vì sao thiếu dữ liệu?', 'View chart data': 'Xem dữ liệu biểu đồ',
    'Selected snapshot:': 'Ngày chốt tồn kho:',
    'No matching observations for these dates.': 'Không có bản ghi phù hợp trong kỳ này.',
    'Source access is restricted.': 'Quyền truy cập nguồn bị giới hạn.',
    'The metric definition or reporting scope is unresolved.': 'Chưa xác định được định nghĩa chỉ số hoặc phạm vi báo cáo.',
    'Unavailable for this scope or source.': 'Không có dữ liệu cho phạm vi hoặc nguồn này.',
    'No stockout flags were observed at the selected snapshot.': 'Không ghi nhận cờ hết hàng tại ngày chốt.',
    'The stockout product list is unavailable for this scope.': 'Chưa có danh sách sản phẩm hết hàng cho phạm vi này.',
    'No chart observations available.': 'Không có dữ liệu cho biểu đồ.',
    'This annual report uses one inventory snapshot. It does not add stock balances across months.':
        'Báo cáo năm sử dụng số dư tại một ngày chốt tồn kho. Số dư các tháng được xem riêng.',
    'Inventory figures describe one snapshot.': 'Các chỉ số tồn kho phản ánh một ngày chốt.',
    'Available fulfillment, return and review records are filtered to the requested reporting dates; complete transaction coverage is unverified.':
        'Số liệu giao hàng, trả hàng và đánh giá lấy từ các bản ghi trong kỳ yêu cầu. Chưa xác minh được độ đầy đủ của dữ liệu giao dịch.',
    'Snapshot totals are unavailable for this reporting period. Open Validation and source details for the missing inputs.':
        'Chưa có số liệu tổng hợp tại ngày chốt cho kỳ này. Xem chi tiết kiểm tra và nguồn dữ liệu để biết dữ liệu còn thiếu.',
    'Snapshot totals are unavailable for this reporting period. Check the validation summary for missing inputs.':
        'Chưa có số liệu tổng hợp tại ngày chốt cho kỳ này. Xem kết quả kiểm tra để biết dữ liệu còn thiếu.',
    'A product may carry more than one flag.': 'Một sản phẩm có thể có nhiều cờ cảnh báo.',
    'Each point is an independent snapshot; stock balances are never added across dates.':
        'Mỗi điểm phản ánh một ngày chốt riêng. Số dư được xem theo từng ngày.',
    'Quoted policy context. These passages do not by themselves verify approval, effective dates or compliance.':
        'Trích đoạn quy trình cung cấp bối cảnh. Cần thêm bằng chứng để xác minh phê duyệt, ngày hiệu lực và mức độ tuân thủ.',
    'Policy evidence is unavailable because document access is restricted.': 'Quyền đọc tài liệu nguồn bị giới hạn.',
    'No matching authorized inventory policy passage was retrieved.': 'Chưa tìm thấy trích đoạn quy trình tồn kho phù hợp trong phạm vi được cấp quyền.',
    'Policy evidence could not be retrieved. No policy-compliance conclusion has been added.':
        'Chưa truy xuất được quy trình nguồn để đánh giá mức độ tuân thủ.',
    'No recommendation can be confirmed from the available inputs. Check the selected snapshot and recorded flags in Validation and source details.':
        'Dữ liệu hiện có chưa đủ để đưa ra khuyến nghị. Xem chi tiết kiểm tra ngày chốt và cờ cảnh báo.',
    'No recommendation can be confirmed. Verify the selected snapshot and flag inputs before acting.':
        'Chưa đủ dữ liệu để đưa ra khuyến nghị. Hãy kiểm tra ngày chốt và cờ đã ghi nhận.',
    'Why review this:': 'Lý do cần xem xét:', 'Recommended next step:': 'Đề xuất xử lý:',
    'View all rule evaluations': 'Xem kết quả đánh giá các quy tắc',
    'Triggered: the recorded inputs meet this predefined condition.': 'Dữ liệu đã ghi nhận thỏa điều kiện cảnh báo.',
    'Evaluated: this predefined condition was not met.': 'Kết quả đánh giá chưa thỏa điều kiện cảnh báo.',
    'A no-exception conclusion is withheld because snapshot coverage or flag evidence is incomplete.':
        'Chưa đủ dữ liệu tại ngày chốt hoặc dữ liệu cảnh báo để kết luận.',
    'Cannot evaluate: the required recorded flag count is unavailable.': 'Chưa có số lượng cờ đã ghi nhận để đánh giá.',
    'Sources': 'Nguồn dữ liệu', 'Role-authorized policy passage.': 'Trích đoạn quy trình được phép truy cập.',
    'Source queried for the requested reporting dates.': 'Nguồn được truy vấn theo kỳ báo cáo.',
    'No source observations were returned for this period.': 'Nguồn không trả về dữ liệu cho kỳ này.',
    'Retrieved inventory policy': 'Quy trình tồn kho từ tài liệu nguồn', 'Chart source': 'Nguồn biểu đồ',
    'Synthetic commerce demonstration data; source completeness and current business balances are not independently certified.':
        'Dữ liệu thương mại mô phỏng. Chưa có xác nhận độc lập về độ đầy đủ của nguồn và số dư thực tế hiện tại.',
    'Source definitions and limitations remain in the saved report. Missing values are never treated as zero.':
        'Báo cáo đã lưu có định nghĩa nguồn và các giới hạn. Giá trị thiếu được để trống.',
}


def localize_metrics(metrics):
    for item in metrics:
        item['label'] = LABELS[item['id']]


def localize_labels(report):
    localize_metrics(report['metrics'])
    for item in [*report['decisions'], *report['dashboard']['widgets']]:
        item['title'] = LABELS[item['id']]


def uses_vietnamese_labels(report):
    metrics = report.get('metrics')
    return (isinstance(metrics, list) and bool(metrics) and isinstance(metrics[0], dict)
            and metrics[0].get('label') in (LABELS['observed_products'], LABELS['company_revenue']))
