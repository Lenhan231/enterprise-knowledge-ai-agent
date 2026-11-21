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
