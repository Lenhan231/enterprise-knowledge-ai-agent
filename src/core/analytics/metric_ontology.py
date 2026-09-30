"""Bilingual labels used by routing, KPI filtering, and review-candidate extraction."""

from __future__ import annotations

import re
import unicodedata


METRIC_ONTOLOGY = {
    "net_revenue": {
        "label": "Net revenue",
        "definition": "Revenue recognized from sales after deductions such as returns, discounts, and allowances; follow the reporting entity's stated accounting basis.",
        "unit_guidance": "Use the source unit (for example, VND or billion VND) consistently across periods.",
        "aliases": ("net revenue", "net sales", "revenue", "doanh thu", "doanh thu thuần"),
        "source_labels": ("net revenue", "net sales", "doanh thu thuần"),
    },
    "total_consolidated_revenue": {
        "label": "Total consolidated revenue",
        "definition": "Consolidated revenue of the parent and subsidiaries for the reporting period, using the report's stated revenue line.",
        "unit_guidance": "Use the source unit (for example, VND or billion VND) consistently across periods.",
        "aliases": (
            "total consolidated revenue",
            "total revenue",
            "consolidated revenue",
            "consolidated net revenue",
            "revenue from sales of goods and provision of services",
            "doanh thu hợp nhất",
            "tổng doanh thu hợp nhất",
            "doanh thu bán hàng và cung cấp dịch vụ",
        ),
        "source_labels": (
            "total consolidated revenue", "total revenue", "consolidated revenue", "consolidated net revenue",
            "revenue from sales of goods and provision of services",
            "tổng doanh thu hợp nhất", "doanh thu hợp nhất", "doanh thu bán hàng và cung cấp dịch vụ",
        ),
    },
    "profit_after_tax": {
        "label": "Profit after tax",
        "definition": "Profit for the reporting period after income-tax expense; distinguish consolidated profit from profit attributable to owners when the source does.",
        "unit_guidance": "Use the source unit (for example, VND or billion VND) consistently across periods.",
        "aliases": (
            "profit after tax",
            "after-tax profit",
            "profit",
            "net income",
            "earnings",
            "consolidated net profit after tax",
            "net profit after tax",
            "lợi nhuận sau thuế",
            "lợi nhuận sau thuế tndn",
            "lợi nhuận hợp nhất sau thuế",
            "lợi nhuận sau thuế hợp nhất",
        ),
        "source_labels": (
            "profit after tax", "after-tax profit", "net income",
            "consolidated net profit after tax", "net profit after tax",
            "lợi nhuận sau thuế", "lợi nhuận sau thuế hợp nhất",
            "lợi nhuận sau thuế tndn",
        ),
    },
    "profit_before_tax": {
        "label": "Profit before tax",
        "definition": "Profit before income-tax expense for the reporting period and reporting entity shown in the source.",
        "unit_guidance": "Use the source unit (for example, VND or billion VND) consistently across periods.",
        "aliases": ("profit before tax", "consolidated profit before tax", "earnings before tax", "lợi nhuận trước thuế"),
        "source_labels": ("profit before tax", "consolidated profit before tax", "earnings before tax", "lợi nhuận trước thuế"),
    },
    "total_assets": {
        "label": "Total assets",
        "definition": "Total assets at the reporting date, using the consolidated or separate statement basis stated by the source.",
        "unit_guidance": "Use the source unit and reporting date consistently across periods.",
        "aliases": ("total assets", "assets", "tổng tài sản", "tài sản"),
        "source_labels": ("total assets", "tổng tài sản"),
    },
    "cost_of_goods_sold": {
        "label": "Cost of goods sold",
        "definition": "Cost of sales for the same reporting entity and period as the revenue figure; preserve the source's classification.",
        "unit_guidance": "Use the source unit (for example, VND or billion VND) consistently across periods.",
        "aliases": ("cost of goods sold", "cost of sales", "giá vốn hàng bán", "giá vốn hàng bán và dịch vụ cung cấp"),
        "source_labels": ("cost of goods sold", "cost of sales", "giá vốn hàng bán"),
    },
    "gross_profit": {
        "label": "Gross profit",
        "definition": "Gross profit as reported by the source; do not calculate it from revenue and cost unless separately labeled as derived.",
        "unit_guidance": "Use the source unit (for example, VND or billion VND) consistently across periods.",
        "aliases": ("gross profit", "lợi nhuận gộp"),
        "source_labels": ("gross profit", "lợi nhuận gộp"),
    },
    "cash_and_equivalents": {
        "label": "Cash and cash equivalents",
        "definition": "Cash and cash equivalents at the reporting date, using the source's statement basis.",
        "unit_guidance": "Use the source unit and reporting date consistently across periods.",
        "aliases": ("cash and cash equivalents", "cash equivalents", "tiền và các khoản tương đương tiền"),
        "source_labels": ("cash and cash equivalents", "tiền và các khoản tương đương tiền"),
    },
    "inventory": {
        "label": "Inventory",
        "definition": "Inventory carrying amount at the reporting date, using the source's statement basis.",
        "unit_guidance": "Use the source unit and reporting date consistently across periods.",
        "aliases": ("inventory", "inventories", "hàng tồn kho"),
        "source_labels": ("inventories", "inventory", "hàng tồn kho"),
    },
    "employees": {
        "label": "Employees",
        "definition": "Employee count explicitly reported for the stated entity and reporting date or period; record the scope used.",
        "unit_guidance": "Use people or employees and keep the entity scope consistent.",
        "aliases": ("employee count", "number of employees", "employees", "nhân sự", "số lượng nhân viên"),
        "source_labels": ("the whole group has", "số lượng nhân viên"),
    },
    "state_budget_contribution": {
        "label": "State budget contribution",
        "definition": "Amount explicitly reported as contributed to the state budget for the stated period; do not infer from tax expense.",
        "unit_guidance": "Use the source unit (for example, VND or billion VND) consistently across periods.",
        "aliases": ("state budget contribution", "contribution to the state budget", "đóng góp ngân sách nhà nước"),
        "source_labels": ("contribution to the state budget", "đóng góp ngân sách nhà nước"),
    },
}


def _normalize(text: str) -> str:
    return " ".join(unicodedata.normalize("NFC", text).casefold().split())


def resolve_metric_names(text: str) -> set[str]:
    """Resolve the longest non-overlapping aliases to canonical metric names."""
    normalized = _normalize(text)
    matches = []
    for metric_name, definition in METRIC_ONTOLOGY.items():
        for alias in definition["aliases"]:
            phrase = _normalize(alias)
            pattern = re.compile(rf"(?<!\w){re.escape(phrase)}(?!\w)")
            matches.extend((match.start(), match.end(), metric_name) for match in pattern.finditer(normalized))

    selected = []
    for start, end, metric_name in sorted(matches, key=lambda item: (-(item[1] - item[0]), item[0])):
        if any(start < chosen_end and chosen_start < end for chosen_start, chosen_end, _ in selected):
            continue
        selected.append((start, end, metric_name))
    return {metric_name for _, _, metric_name in selected}
