"""LLM-free end-to-end scenarios for SQL drafting, repair, review, and fallback."""

import json
import os
import sys
import unittest
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from core.analytics.join_validation import PRIMARY_KEYS
from core.analytics.text_to_sql import APPROVED_COLUMNS, APPROVED_DATE_COLUMNS, APPROVED_JOINS
from core.sql_agent.agent import SQLAnalyticsAgent
from core.sql_agent.assistant_endpoint import run_sql_assistant
from core.models.agents import AgentRequest, VerifiedIdentity


PRODUCT_GROWTH_SQL = """WITH filtered_items AS (
  SELECT oi.product_id, o.order_date, oi.quantity, oi.unit_price, oi.discount_amount
  FROM commerce.order_items AS oi
  JOIN commerce.orders AS o ON oi.order_id = o.order_id
  WHERE o.order_date >= DATE '2021-01-01' AND o.order_date < DATE '2023-01-01'
), annual_revenue AS (
  SELECT fi.product_id, EXTRACT(YEAR FROM fi.order_date) AS revenue_year,
    SUM(fi.quantity * fi.unit_price - fi.discount_amount) AS revenue
  FROM filtered_items AS fi
  GROUP BY 1, 2
), growth AS (
  SELECT ar.product_id,
    SUM(ar.revenue) FILTER (WHERE ar.revenue_year = 2021) AS revenue_2021,
    SUM(ar.revenue) FILTER (WHERE ar.revenue_year = 2022) AS revenue_2022
  FROM annual_revenue AS ar
  GROUP BY 1
  HAVING SUM(ar.revenue) FILTER (WHERE ar.revenue_year = 2021) > 0
    AND SUM(ar.revenue) FILTER (WHERE ar.revenue_year = 2022) > 0
)
SELECT p.product_id, p.product_name, g.revenue_2021, g.revenue_2022,
  g.revenue_2022 - g.revenue_2021 AS revenue_growth
FROM growth AS g
JOIN commerce.products AS p ON p.product_id = g.product_id
ORDER BY 5 DESC, 1
LIMIT 10"""

PROMOTION_RANK_SQL = """WITH promo_line_economics AS (
  SELECT oi.order_item_id, oi.promo_id, pr.promo_name,
    oi.quantity * oi.unit_price - oi.discount_amount AS net_revenue,
    oi.quantity * p.cogs AS item_cogs
  FROM commerce.order_items AS oi
  JOIN commerce.products AS p ON p.product_id = oi.product_id
  JOIN commerce.promotions AS pr ON pr.promo_id = oi.promo_id
  WHERE oi.promo_id IS NOT NULL
), promo_totals AS (
  SELECT ple.promo_id, ple.promo_name, SUM(ple.net_revenue) AS revenue,
    SUM(ple.item_cogs) AS total_cogs,
    100.0 * (SUM(ple.net_revenue) - SUM(ple.item_cogs))
      / NULLIF(SUM(ple.net_revenue), 0) AS gross_margin_percent
  FROM promo_line_economics AS ple
  GROUP BY 1, 2
), ranked_promos AS (
  SELECT pt.promo_id, pt.promo_name, pt.revenue, pt.total_cogs, pt.gross_margin_percent,
    RANK() OVER (ORDER BY pt.revenue DESC) AS revenue_rank,
    RANK() OVER (ORDER BY pt.gross_margin_percent ASC) AS margin_rank
  FROM promo_totals AS pt
)
SELECT rp.promo_id, rp.promo_name, rp.revenue, rp.total_cogs,
  rp.gross_margin_percent, rp.revenue_rank, rp.margin_rank
FROM ranked_promos AS rp
WHERE rp.revenue_rank = 1 OR rp.margin_rank = 1
ORDER BY 6, 7
LIMIT 20"""


class FakeProvider:
    def __init__(self, responses):
        self.responses = list(responses)
        self.response_index = 0
        self.prompts = []

    def generate(self, prompt, *, max_output_tokens=1000):
        self.prompts.append(prompt)
        response = self.responses[min(self.response_index, len(self.responses) - 1)]
        self.response_index += 1
        if isinstance(response, BaseException):
            raise response
        return response


class FakeRepository:
    def __init__(self):
        self.execute_approved_query = AsyncMock(return_value=[
            {"product_id": 7, "product_name": "Grid Runner", "revenue_2021": 100,
             "revenue_2022": 160, "revenue_growth": 60},
        ])

    async def get_schema(self):
        return {
            "tables": APPROVED_COLUMNS,
            "primary_keys": PRIMARY_KEYS,
            "joins": APPROVED_JOINS,
            "date_columns": APPROVED_DATE_COLUMNS,
        }


def plan(sql, explanation="Calculated from order-item rows."):
    return json.dumps({"sql": sql, "parameters": [], "explanation": explanation})


def assistant(repository, provider):
    return SimpleNamespace(repository=repository, inventory_only=False,
                           _provider=lambda: provider)


class SQLAgentFlowTest(unittest.IsolatedAsyncioTestCase):
    async def test_returned_vs_sold_prompt_includes_order_item_schema_and_executes(self):
        question = "so sánh số lượng trả hàng với số lượng đã bán"
        sql = """SELECT
  (SELECT SUM(r.return_quantity) FROM commerce.returns AS r) AS returned_units,
  (SELECT SUM(oi.quantity) FROM commerce.order_items AS oi) AS sold_units,
  CAST((SELECT SUM(r.return_quantity) FROM commerce.returns AS r) AS NUMERIC)
    / NULLIF((SELECT SUM(oi.quantity) FROM commerce.order_items AS oi), 0) AS returned_to_sold_ratio
LIMIT 1"""
        provider = FakeProvider([plan(sql, "Compare recorded returned units with recorded order-item quantities.")])
        repository = FakeRepository()
        agent = SQLAnalyticsAgent(repository, llm=provider, inventory_only=False)
        request = AgentRequest(
            question=question,
            identity=VerifiedIdentity(subject="test", permissions={"analytics:read"}),
        )

        result = await agent.run_payload(request)

        self.assertEqual(result["query_status"], "executed", result)
        self.assertIn("commerce.order_items:", provider.prompts[0])
        self.assertIn("quantity", provider.prompts[0])
        self.assertIn("commerce.returns:", provider.prompts[0])
        self.assertIn("return_quantity", provider.prompts[0])
        repository.execute_approved_query.assert_awaited_once()

    async def test_hard_prompts_across_commerce_tables_pass_sql_planning_and_validation(self):
        cases = (
            (
                "Đối soát tiền thanh toán với giá trị hàng sau giảm giá theo phương thức thanh toán. Phương thức nào lệch nhiều nhất?",
                """WITH item_totals AS (
  SELECT oi.order_id, SUM(oi.quantity * oi.unit_price - oi.discount_amount) AS order_value
  FROM commerce.order_items AS oi GROUP BY oi.order_id
)
SELECT p.payment_method, SUM(p.payment_value) AS paid_total,
  SUM(i.order_value) AS ordered_total,
  SUM(p.payment_value) - SUM(i.order_value) AS variance
FROM commerce.payments AS p
JOIN commerce.orders AS o ON o.order_id = p.order_id
JOIN item_totals AS i ON i.order_id = o.order_id
GROUP BY p.payment_method
ORDER BY ABS(SUM(p.payment_value) - SUM(i.order_value)) DESC
LIMIT 20""",
                {"commerce.payments", "commerce.orders", "commerce.order_items"},
            ),
            (
                "Danh mục nào có tỷ lệ số lượng trả hàng cao nhất so với số lượng đã bán? Chỉ tính đơn đã giao.",
                """WITH returned AS (
  SELECT p.category, SUM(r.return_quantity) AS returned_units
  FROM commerce.returns AS r JOIN commerce.products AS p ON p.product_id = r.product_id
  GROUP BY p.category
), sold AS (
  SELECT p.category, SUM(oi.quantity) AS sold_units
  FROM commerce.orders AS o
  JOIN commerce.order_items AS oi ON oi.order_id = o.order_id
  JOIN commerce.products AS p ON p.product_id = oi.product_id
  WHERE o.order_status = 'delivered'
  GROUP BY p.category
)
SELECT COALESCE(r.category, s.category) AS category, r.returned_units, s.sold_units,
  r.returned_units / NULLIF(s.sold_units, 0) AS return_rate
FROM returned AS r FULL JOIN sold AS s ON s.category = r.category
ORDER BY 4 DESC LIMIT 20""",
                {"commerce.returns", "commerce.products", "commerce.orders", "commerce.order_items"},
            ),
            (
                "Theo danh mục, so sánh điểm đánh giá trung bình với số lượng hàng trả; tránh nhân chéo review và return.",
                """WITH ratings AS (
  SELECT p.category, AVG(r.rating) AS average_rating
  FROM commerce.reviews AS r JOIN commerce.products AS p ON p.product_id = r.product_id
  GROUP BY p.category
), returns AS (
  SELECT p.category, SUM(r.return_quantity) AS returned_units
  FROM commerce.returns AS r JOIN commerce.products AS p ON p.product_id = r.product_id
  GROUP BY p.category
)
SELECT COALESCE(a.category, b.category) AS category, a.average_rating, b.returned_units
FROM ratings AS a FULL JOIN returns AS b ON b.category = a.category
ORDER BY b.returned_units DESC LIMIT 20""",
                {"commerce.reviews", "commerce.products", "commerce.returns"},
            ),
            (
                "Trong snapshot mới nhất, danh mục nào có nhiều sản phẩm cần đặt lại hàng nhất?",
                """SELECT i.category, COUNT(DISTINCT i.product_id) AS reorder_products
FROM commerce.inventory AS i
WHERE i.snapshot_date = (SELECT MAX(latest.snapshot_date) FROM commerce.inventory AS latest)
  AND i.reorder_flag = TRUE
GROUP BY i.category ORDER BY reorder_products DESC LIMIT 20""",
                {"commerce.inventory"},
            ),
            (
                "Hóa đơn nào có subtotal khác tổng amount của các dòng hàng? Hiện mã tiền tệ và độ lệch.",
                """WITH item_totals AS (
  SELECT li.invoice_id, SUM(li.amount) AS item_total
  FROM commerce.invoice_items AS li GROUP BY li.invoice_id
)
SELECT inv.invoice_no, inv.currency, inv.subtotal, t.item_total,
  inv.subtotal - t.item_total AS variance
FROM commerce.invoices AS inv
JOIN item_totals AS t ON t.invoice_id = inv.invoice_id
WHERE ABS(inv.subtotal - t.item_total) > 0.01
ORDER BY ABS(inv.subtotal - t.item_total) DESC LIMIT 20""",
                {"commerce.invoices", "commerce.invoice_items"},
            ),
            (
                "Theo khu vực và kênh thu hút, nhóm nào có nhiều khách quay lại đặt đơn nhất?",
                """WITH customer_orders AS (
  SELECT o.customer_id, COUNT(DISTINCT o.order_id) AS order_count
  FROM commerce.orders AS o GROUP BY o.customer_id
)
SELECT g.region, c.acquisition_channel,
  SUM(CASE WHEN co.order_count > 1 THEN 1 ELSE 0 END) AS repeat_customers,
  COUNT(*) AS customers_with_orders
FROM customer_orders AS co
JOIN commerce.customers AS c ON c.customer_id = co.customer_id
JOIN commerce.geography AS g ON g.zip = c.zip
GROUP BY g.region, c.acquisition_channel
ORDER BY repeat_customers DESC LIMIT 20""",
                {"commerce.orders", "commerce.customers", "commerce.geography"},
            ),
            (
                "Khu vực nào giao hàng lâu nhất? Chỉ tính chuyến đã có cả ngày gửi và ngày giao.",
                """SELECT g.region, AVG(s.delivery_date - s.ship_date) AS average_delivery_days,
  COUNT(*) AS shipment_count
FROM commerce.shipments AS s
JOIN commerce.orders AS o ON o.order_id = s.order_id
JOIN commerce.geography AS g ON g.zip = o.zip
WHERE s.ship_date IS NOT NULL AND s.delivery_date IS NOT NULL
GROUP BY g.region ORDER BY average_delivery_days DESC LIMIT 20""",
                {"commerce.shipments", "commerce.orders", "commerce.geography"},
            ),
            (
                "Tháng nào có gross profit cao nhất theo bảng sales?",
                """SELECT DATE_TRUNC('month', s.date) AS month,
  SUM(s.revenue) - SUM(s.cogs) AS gross_profit
FROM commerce.sales AS s
GROUP BY 1 ORDER BY gross_profit DESC LIMIT 1""",
                {"commerce.sales"},
            ),
            (
                "Trong tháng mới nhất có dữ liệu, nguồn truy cập nào có nhiều phiên nhất và bounce rate trung bình bao nhiêu?",
                """WITH monthly AS (
  SELECT DATE_TRUNC('month', w.date) AS month, w.traffic_source,
    SUM(w.sessions) AS sessions, AVG(w.bounce_rate) AS average_bounce_rate
  FROM commerce.web_traffic AS w GROUP BY 1, 2
)
SELECT m.month, m.traffic_source, m.sessions, m.average_bounce_rate
FROM monthly AS m
WHERE m.month = (SELECT MAX(latest.month) FROM monthly AS latest)
ORDER BY m.sessions DESC LIMIT 20""",
                {"commerce.web_traffic"},
            ),
        )
        for question, sql, expected_sources in cases:
            with self.subTest(question=question):
                provider = FakeProvider([plan(sql, "Independent aggregates preserve source grain.")])
                repository = FakeRepository()

                result = await run_sql_assistant(assistant(repository, provider), question)

                self.assertEqual(result["status"], "approval_required", result)
                self.assertEqual(set(result["sources"]), expected_sources)
                self.assertEqual(len(provider.prompts), 1)
                repository.execute_approved_query.assert_not_awaited()

    async def test_hard_promotion_questions_compile_and_pass_validators_without_llm(self):
        cases = (
            (
                "có bao nhiêu mã giảm giá hiện tại",
                "active_promotion_count",
                "FROM commerce.promotions AS p WHERE p.start_date <= $1 AND p.end_date >= $1",
                1,
            ),
            (
                "bao nhiêu mã giảm giá đang hoạt động?",
                "active_promotion_count",
                "FROM commerce.promotions AS p WHERE p.start_date <= $1 AND p.end_date >= $1",
                1,
            ),
            (
                "10 mã giảm giá có doanh thu cao nhất",
                "promotion_revenue",
                "FROM commerce.order_items AS oi JOIN commerce.promotions AS p ON p.promo_id = oi.promo_id",
                10,
            ),
            (
                "Cho tôi top 5 promo có revenue cao nhất",
                "promotion_revenue",
                "FROM commerce.order_items AS oi JOIN commerce.promotions AS p ON p.promo_id = oi.promo_id",
                5,
            ),
            (
                "Top 10 discount codes by total revenue",
                "promotion_revenue",
                "FROM commerce.order_items AS oi JOIN commerce.promotions AS p ON p.promo_id = oi.promo_id",
                10,
            ),
        )
        for question, metric, expected_sql, limit in cases:
            with self.subTest(question=question):
                provider = FakeProvider([])
                repository = FakeRepository()
                agent = SQLAnalyticsAgent(repository, llm=provider, inventory_only=False)
                request = AgentRequest(
                    question=question,
                    identity=VerifiedIdentity(subject="test", permissions={"analytics:read"}),
                )

                result = await agent.run_payload(request)

                self.assertEqual(result["query_status"], "executed", result)
                self.assertEqual(set(result["metadata"]["metrics"]), {metric})
                self.assertIn(expected_sql, result["sql"])
                self.assertTrue(result["sql"].endswith(f"LIMIT {limit}"))
                if metric == "active_promotion_count":
                    self.assertEqual(result["parameters"], [date.today()])
                else:
                    self.assertIn("oi.promo_id_2 IS NULL", result["sql"])
                    self.assertIn("oi.discount_amount IS NOT NULL", result["sql"])
                    self.assertEqual(result["parameters"], [])
                self.assertEqual(provider.prompts, [])

    async def test_product_growth_repairs_bad_schema_then_waits_for_approval_and_executes(self):
        question = (
            "Tìm 10 sản phẩm có doanh thu sau giảm giá tăng mạnh nhất từ năm 2021 sang 2022; "
            "chỉ lấy sản phẩm doanh thu dương cả hai năm. Dùng order_items và ngày trong orders."
        )
        hallucinated_sql = (
            "WITH annual AS (SELECT oi.product_id, oi.order_date, "
            "SUM(oi.quantity * oi.unit_price - oi.discount_amount) AS revenue "
            "FROM commerce.order_items AS oi GROUP BY 1, 2) "
            "SELECT a.product_id, a.revenue FROM annual AS a ORDER BY 2 DESC LIMIT 10"
        )
        provider = FakeProvider([plan(hallucinated_sql), plan(PRODUCT_GROWTH_SQL)])
        repository = FakeRepository()
        agent = assistant(repository, provider)

        draft = await run_sql_assistant(agent, question)

        self.assertEqual(draft["status"], "approval_required")
        self.assertEqual(draft["sql"], PRODUCT_GROWTH_SQL)
        self.assertEqual(set(draft["sources"]), {
            "commerce.products", "commerce.order_items", "commerce.orders",
        })
        self.assertEqual(len(provider.prompts), 2)
        self.assertIn("failed validation", provider.prompts[1].lower())
        self.assertIn("commerce.orders.order_date", provider.prompts[0])
        repository.execute_approved_query.assert_not_awaited()

        executed = await run_sql_assistant(
            agent, question, mode="execute", sql=draft["sql"], parameters=list(draft["parameters"]),
        )

        self.assertEqual(executed["status"], "executed")
        self.assertEqual(executed["rows"][0]["revenue_growth"], 60)
        repository.execute_approved_query.assert_awaited_once_with(PRODUCT_GROWTH_SQL)

    async def test_promotion_ctes_can_rank_revenue_and_lowest_margin(self):
        question = (
            "Khuyến mãi nào đứng đầu doanh thu và khuyến mãi nào có biên lợi nhuận gộp thấp nhất? "
            "Tính doanh thu sau giảm giá và COGS theo sản phẩm."
        )
        provider = FakeProvider([plan(PROMOTION_RANK_SQL, "Ranked promo totals from line economics.")])
        repository = FakeRepository()

        draft = await run_sql_assistant(assistant(repository, provider), question)

        self.assertEqual(draft["status"], "approval_required")
        self.assertIn("RANK() OVER", draft["sql"])
        self.assertEqual(set(draft["sources"]), {
            "commerce.order_items", "commerce.products", "commerce.promotions",
        })
        repository.execute_approved_query.assert_not_awaited()

    async def test_cloudflare_request_error_falls_back_to_mock_groq_with_same_prompt(self):
        from core.llm.Cloudflare_provider import CloudflareProvider

        prompt = "Generate a bounded SELECT using the supplied schema."
        with patch.dict(os.environ, {
            "CLOUDFLARE_ACCOUNT_ID": "account-test",
            "CLOUDFLARE_WORKERS_API": "test-token",
        }):
            cloudflare = CloudflareProvider()
        cloudflare.generate = Mock(side_effect=RuntimeError("offline in test"))
        fallback_response = "{\"sql\":\"SELECT 1 LIMIT 1\",\"parameters\":[]}"
        fallback = FakeProvider([fallback_response])
        agent = SQLAnalyticsAgent(FakeRepository(), llm=cloudflare, inventory_only=False)
        with patch("core.llm.groq_provider.GroqProvider", return_value=fallback):
            result = await agent._generate_sql(prompt)

        self.assertEqual(result, fallback_response)
        cloudflare.generate.assert_called_once_with(prompt)
        self.assertEqual(fallback.prompts, [prompt])

    async def test_sql_provider_can_explicitly_select_groq(self):
        provider = FakeProvider([])
        agent = SQLAnalyticsAgent(FakeRepository(), inventory_only=False)
        with patch.dict(os.environ, {"SQL_LLM_PROVIDER": "groq", "SQL_GROQ_MODEL": "openai/gpt-oss-20b"}), \
                patch("core.llm.groq_provider.GroqProvider", return_value=provider) as groq:
            selected = agent._provider()

        self.assertIs(selected, provider)
        groq.assert_called_once_with(model="openai/gpt-oss-20b")


if __name__ == "__main__":
    unittest.main()
