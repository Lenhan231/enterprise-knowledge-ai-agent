"""Create the v3 draft from the immutable v2 case and Gold SQL files."""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path


HERE = Path(__file__).resolve().parent
V2 = HERE.parent / "40-case-preparation"
CASES_V2_SHA256 = "6036477937037c12dd90c10a1b00c90735ec8d48ba08ebbb8775f217f8a01677"
GOLD_V2_SHA256 = "422d82e809b646477af4295e3e01561b27c08ed3e505f4bafa2928fe3ea45e6d"
CASES_OUT = HERE / "cases_v3_draft.json"
GOLD_OUT = HERE / "gold_sql_v3_draft.json"


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _canonical_sha256(value: object) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _write_new(path: Path, value: object) -> None:
    if path.exists():
        raise FileExistsError(f"Refusing to overwrite existing v3 draft: {path}")
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def build() -> tuple[dict, dict]:
    cases_v2_path = V2 / "cases_v2_draft.json"
    gold_v2_path = V2 / "gold_sql_draft.json"
    if _file_sha256(cases_v2_path) != CASES_V2_SHA256:
        raise ValueError("The v2 case file changed; review its provenance before building v3.")
    if _file_sha256(gold_v2_path) != GOLD_V2_SHA256:
        raise ValueError("The v2 Gold SQL file changed; review its provenance before building v3.")

    cases_doc = json.loads(cases_v2_path.read_text(encoding="utf-8"))
    gold_doc = json.loads(gold_v2_path.read_text(encoding="utf-8"))
    cases_doc = copy.deepcopy(cases_doc)
    gold_doc = copy.deepcopy(gold_doc)
    cases = {case["id"]: case for case in cases_doc["cases"]}
    gold = {item["id"]: item for item in gold_doc["cases"]}

    case_notes = {
        "B40-002": (
            "Moved the ship-date population to 2025, where seven shipments lack delivery_date. "
            "The output now reports the missing-date count by month and averages only recorded delivery durations."
        ),
        "B40-006": (
            "Replaced no-op East/non-NULL filters with the verified profile-city Hai Phong and age_group 25-34; "
            "each filter and their intersection reduce the 2024 signup population."
        ),
        "B40-008": (
            "Retained the 2024 return-reason question but recorded that return_reason is non-NULL for every "
            "available 2023-2025 return; this case cannot test the NULL exclusion on this snapshot."
        ),
        "B40-015": (
            "Reduced TOP 5 to TOP 3 because the selected delivered-order population has four categories."
        ),
        "B40-017": (
            "Widened return_date to 2023-2025; 56 product groups combine multiple source return rows."
        ),
        "B40-020": (
            "Retained the shipping-fee business metric. All 728 2025 shipments have a recorded shipping_fee, "
            "so this case makes no claim that it tests NULL-fee handling."
        ),
        "B40-021": (
            "Made the requested population explicitly stockout_flag = TRUE; the frozen snapshot has both TRUE "
            "and FALSE values, so IS NOT NULL is a distinguishable incorrect predicate."
        ),
        "B40-023": (
            "Kept the exact requested snapshot comparison and recorded that both snapshots contain the same "
            "97 product IDs; membership-intersection logic is observationally redundant on this snapshot."
        ),
        "B40-026": (
            "Shortened the follow-up so COGS and the 2024 interval must be inherited from the frozen prior request."
        ),
        "B40-027": (
            "Moved the inherited all-status order_source seed scope to 2025, where only 719 of 733 orders are "
            "delivered; the follow-up must add the delivered population filter."
        ),
        "B40-028": (
            "Changed the follow-up to inherit gross profit and 2024 from its seed, then compare aligned months "
            "against 2023 with explicit paired business columns."
        ),
        "B40-029": (
            "Changed the follow-up limit from TOP 3 to TOP 2; all three return reasons exist in the inherited 2024 scope."
        ),
        "B40-033": (
            "Clarification now asks which product, which historical snapshot, and whether real-time availability "
            "was intended; the schema has no warehouse or live-stock data."
        ),
    }
    for case_id, note in case_notes.items():
        cases[case_id]["provenance"]["change_note"] = note
        cases[case_id]["semantic_review"]["review_note"] = note
        cases[case_id]["discriminative_review"] = {"note": note}

    c = cases["B40-002"]
    c["question"] = (
        "Thời gian giao hàng trung bình theo tháng gửi trong năm 2025, chỉ tính shipment đã có "
        "delivery_date; cho biết thêm số shipment thiếu delivery_date theo từng tháng."
    )
    c["required_columns"] = [
        "commerce.shipments.ship_date",
        "commerce.shipments.delivery_date",
    ]
    c["required_population"] = [
        "Shipment rows with ship_date in 2025; average duration includes only recorded delivery_date rows, "
        "and a separate count reports rows with missing delivery_date."
    ]
    c["required_filters"] = [
        "ship_date >= 2025-01-01",
        "ship_date < 2026-01-01",
        "delivery_date IS NOT NULL for the average",
        "delivery_date IS NULL for the missing-date count",
    ]
    c["time_scope"] = {
        "kind": "calendar_range",
        "date_field": "commerce.shipments.ship_date",
        "start": "2025-01-01",
        "end_exclusive": "2026-01-01",
    }
    c["output_contract"]["columns"] = [
        "month",
        "average_delivery_days",
        "completed_shipment_count",
        "missing_delivery_date_count",
    ]
    c["numeric_tolerance"]["absolute"] = 0.0001

    c = cases["B40-006"]
    c["question"] = (
        "Trong năm 2024, có bao nhiêu khách hàng đăng ký có profile ZIP ánh xạ đến thành phố "
        "Hai Phong và age_group là 25-34?"
    )
    c["required_population"] = [
        "Customers who signed up in 2024, whose profile ZIP maps to Hai Phong, and whose age_group is 25-34."
    ]
    c["required_filters"] = [
        "geography.city = Hai Phong",
        "age_group = 25-34",
        "signup_date >= 2024-01-01",
        "signup_date < 2025-01-01",
    ]

    c = cases["B40-015"]
    c["question"] = "Top 3 danh mục theo doanh thu dòng hàng sau discount_amount của các đơn đã giao trong năm 2025."
    c["top_n"] = 3

    c = cases["B40-017"]
    c["question"] = "Tổng số lượng hàng trả theo product_id từ năm 2023 đến hết năm 2025, tính theo return_date."
    c["required_population"] = [
        "Return rows dated from 2023-01-01 through 2025-12-31; sum repeated return_quantity rows by product_id."
    ]
    c["required_filters"] = [
        "return_date >= 2023-01-01",
        "return_date < 2026-01-01",
    ]
    c["time_scope"].update(start="2023-01-01", end_exclusive="2026-01-01")

    c = cases["B40-021"]
    c["question"] = (
        "Tại snapshot 2026-11-13, đếm số sản phẩm có stockout_flag = TRUE theo từng category."
    )
    c["required_population"] = [
        "Observed product rows from exactly one snapshot; count only rows whose stockout_flag equals TRUE, "
        "and report all observed products as the denominator."
    ]
    c["required_filters"] = [
        "snapshot_date = 2026-11-13",
        "stockout_flag = TRUE for stockout_product_count",
    ]

    cases["B40-026"]["question"] = "Hãy trình bày theo từng tháng."

    c = cases["B40-027"]
    c["time_scope"].update(start="2025-01-01", end_exclusive="2026-01-01")
    c["required_population"] = [
        "Delivered orders in inherited calendar year 2025, preserving order_source grain."
    ]
    c["required_filters"] = [
        "inherit order_date year=2025",
        "order_status = delivered",
    ]
    c["conversation_setup"]["prior_user_question"] = (
        "Count orders by order_source during 2025, including every status."
    )
    c["conversation_setup"]["semantic_context"].update(
        start="2025-01-01",
        end_exclusive="2026-01-01",
    )

    c = cases["B40-028"]
    c["question"] = "Còn so với năm trước theo từng tháng thì sao?"
    c["required_metric_or_intent"] = "aligned monthly company gross profit comparison, 2024 versus 2023"
    c["required_population"] = [
        "All company daily rows in 2023 and 2024; inherit gross profit for 2024 and compare the same calendar month in 2023."
    ]
    c["required_filters"] = [
        "inherit current gross_profit metric and year=2024",
        "date >= 2023-01-01",
        "date < 2025-01-01",
    ]
    c["time_scope"] = {
        "kind": "followup_comparison",
        "date_field": "commerce.sales.date",
        "start": "2023-01-01",
        "end_exclusive": "2025-01-01",
        "inherited": True,
        "comparison": "aligned calendar months, 2024 minus 2023",
    }
    c["grouping_grain"] = ["calendar month paired across 2023 and 2024"]
    c["ranking"] = [{"field": "month", "direction": "asc"}]
    c["output_contract"]["columns"] = [
        "month",
        "gross_profit_2023",
        "gross_profit_2024",
        "difference_2024_minus_2023",
    ]
    c["null_policy"] = (
        "If either year's monthly gross_profit is absent or NULL, preserve that NULL and return NULL for "
        "difference_2024_minus_2023; do not substitute zero."
    )
    c["conversation_setup"]["prior_user_question"] = "Gross profit theo từng tháng trong năm 2024 là bao nhiêu?"
    c["conversation_setup"]["semantic_context"].update(
        start="2024-01-01",
        end_exclusive="2025-01-01",
        grouping=["calendar month"],
    )

    c = cases["B40-029"]
    c["question"] = (
        "Trong bảng xếp hạng vừa rồi, chỉ hiện top 2; nếu hòa, xếp tên reason tăng dần."
    )
    c["top_n"] = 2
    c["conversation_setup"]["prior_user_question"] = (
        "Xếp hạng return_reason theo tổng return_quantity trong năm 2024, giảm dần; "
        "nếu bằng nhau, xếp tên reason tăng dần."
    )

    c = cases["B40-033"]
    c["expected_clarification_or_abstention"] = (
        "Bạn muốn tra sản phẩm nào (product_id hoặc tên)? Dữ liệu hiện chỉ có các snapshot tồn kho lịch sử, "
        "không có tồn kho thời gian thực. Bạn muốn dùng snapshot lịch sử ngày nào, hay đang cần số liệu real-time "
        "mà hệ thống chưa cung cấp?"
    )

    contexts = {
        "B40-026": {
            "metric": "company_cogs", "source": "commerce.sales", "date_field": "date",
            "start": "2024-01-01", "end_exclusive": "2025-01-01", "population": "all company sales rows",
            "grouping": [],
        },
        "B40-027": {
            "metric": "distinct_order_count", "source": "commerce.orders", "date_field": "order_date",
            "start": "2025-01-01", "end_exclusive": "2026-01-01", "grouping": ["order_source"],
            "population": "all order statuses",
        },
        "B40-028": {
            "metric": "company_gross_profit", "formula": "SUM(revenue)-SUM(cogs)",
            "source": "commerce.sales", "date_field": "date", "start": "2024-01-01",
            "end_exclusive": "2025-01-01", "grouping": ["calendar month"],
        },
        "B40-029": {
            "metric": "sum_return_quantity", "source": "commerce.returns", "date_field": "return_date",
            "start": "2024-01-01", "end_exclusive": "2025-01-01", "grouping": ["return_reason"],
            "ranking": [["returned_units", "desc"], ["return_reason", "asc"]],
        },
        "B40-030": {
            "metric": "days_of_supply", "source": "commerce.inventory", "date_field": "snapshot_date",
            "snapshot_date": "2025-10-31", "grouping": ["product_id"],
        },
    }
    for case_id, context in contexts.items():
        setup = cases[case_id]["conversation_setup"]
        setup["semantic_context"] = context
        setup["semantic_context_sha256"] = _canonical_sha256(context)
        setup["adapter_version"] = "context-conditioned-sql.v1"
        setup["evaluation_mode"] = "context-conditioned SQL; not conversational-memory evaluation"
        setup["assistant_output_injected"] = False
        setup["context_source"] = (
            "frozen prior user question and approved typed semantic state; no assistant answer, SQL, "
            "parameters, or result rows"
        )
        setup["mode"] = "frozen_context_injection"

    gold["B40-002"].update(
        sql=(
            "SELECT DATE_TRUNC('month', s.ship_date)::date AS month, "
            "AVG(s.delivery_date - s.ship_date) FILTER (WHERE s.delivery_date IS NOT NULL) "
            "AS average_delivery_days, COUNT(s.delivery_date) AS completed_shipment_count, "
            "COUNT(*) FILTER (WHERE s.delivery_date IS NULL) AS missing_delivery_date_count "
            "FROM commerce.shipments AS s WHERE s.ship_date >= $1 AND s.ship_date < $2 "
            "GROUP BY DATE_TRUNC('month', s.ship_date)::date ORDER BY month ASC LIMIT 200"
        ),
        parameters=["2025-01-01", "2026-01-01"],
    )
    gold["B40-006"].update(
        sql=(
            "SELECT COUNT(DISTINCT c.customer_id) AS customer_count "
            "FROM commerce.customers AS c JOIN commerce.geography AS g ON g.zip = c.zip "
            "WHERE g.city = $1 AND c.age_group = $2 AND c.signup_date >= $3 "
            "AND c.signup_date < $4 LIMIT 1"
        ),
        parameters=["Hai Phong", "25-34", "2024-01-01", "2025-01-01"],
    )
    gold["B40-015"]["sql"] = gold["B40-015"]["sql"].rsplit("LIMIT 5", 1)[0] + "LIMIT 3"
    gold["B40-017"].update(
        sql=gold["B40-017"]["sql"].replace("$1 AND $2", "$1 AND $2"),
        parameters=["2023-01-01", "2026-01-01"],
    )
    gold["B40-021"]["sql"] = gold["B40-021"]["sql"].replace(
        "i.stockout_flag IS TRUE", "i.stockout_flag = TRUE"
    )
    gold["B40-027"].update(
        parameters=["delivered", "2025-01-01", "2026-01-01"],
    )
    gold["B40-028"].update(
        sql=(
            "WITH monthly AS ("
            "SELECT EXTRACT(YEAR FROM s.date) AS sales_year, "
            "EXTRACT(MONTH FROM s.date) AS month, "
            "SUM(s.revenue) - SUM(s.cogs) AS gross_profit "
            "FROM commerce.sales AS s WHERE s.date >= $1 AND s.date < $2 "
            "GROUP BY EXTRACT(YEAR FROM s.date), EXTRACT(MONTH FROM s.date)) "
            "SELECT m.month, "
            "MAX(m.gross_profit) FILTER (WHERE m.sales_year = 2023) AS gross_profit_2023, "
            "MAX(m.gross_profit) FILTER (WHERE m.sales_year = 2024) AS gross_profit_2024, "
            "MAX(m.gross_profit) FILTER (WHERE m.sales_year = 2024) - "
            "MAX(m.gross_profit) FILTER (WHERE m.sales_year = 2023) "
            "AS difference_2024_minus_2023 "
            "FROM monthly AS m GROUP BY m.month ORDER BY m.month ASC LIMIT 12"
        ),
        parameters=["2023-01-01", "2025-01-01"],
    )
    gold["B40-029"].update(
        sql=gold["B40-029"]["sql"].rsplit("LIMIT 3", 1)[0] + "LIMIT 2",
    )

    cases_doc.update(
        format_version="sql-business-benchmark.cases.v3-draft",
        status="DRAFT_PENDING_HUMAN_REVIEW",
        v3_based_on={
            "commit": "60eafaee964a6de48a0c8d13925e3207d5116588",
            "cases_v2_sha256": CASES_V2_SHA256,
            "gold_sql_v2_sha256": GOLD_V2_SHA256,
        },
        followup_mode="context-conditioned SQL; no full conversational-memory claim",
        heldout_agent_executed=False,
    )
    gold_doc.update(
        format_version="sql-business-gold-sql-draft.v3",
        status="DRAFT_PENDING_HUMAN_REVIEW",
        author_identity="Codex draft author; no independent semantic approval claimed",
        case_set_sha256=_canonical_sha256(cases_doc),
        v3_based_on={
            "commit": "60eafaee964a6de48a0c8d13925e3207d5116588",
            "cases_v2_sha256": CASES_V2_SHA256,
            "gold_sql_v2_sha256": GOLD_V2_SHA256,
        },
        heldout_agent_executed=False,
        independent_review_approvals=0,
    )
    return cases_doc, gold_doc


if __name__ == "__main__":
    case_doc, gold_doc = build()
    _write_new(CASES_OUT, case_doc)
    _write_new(GOLD_OUT, gold_doc)
    print(json.dumps({
        "cases": len(case_doc["cases"]),
        "execute": sum(c["expected_behavior"] == "execute" for c in case_doc["cases"]),
        "clarify": sum(c["expected_behavior"] == "clarify" for c in case_doc["cases"]),
        "abstain": sum(c["expected_behavior"] == "abstain_without_query" for c in case_doc["cases"]),
        "case_set_sha256": _canonical_sha256(case_doc),
        "gold_sql_count": len(gold_doc["cases"]),
    }, indent=2))
