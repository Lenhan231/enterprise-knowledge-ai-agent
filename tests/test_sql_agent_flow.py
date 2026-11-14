"""LLM-free end-to-end scenarios for SQL drafting, repair, review, and fallback."""

import json
import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from core.analytics.join_validation import PRIMARY_KEYS
from core.analytics.text_to_sql import APPROVED_COLUMNS, APPROVED_DATE_COLUMNS, APPROVED_JOINS
from core.sql_agent.agent import SQLAnalyticsAgent
from core.sql_agent.assistant_endpoint import run_sql_assistant


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
        self.assertEqual(draft["sources"], [
            "commerce.products", "commerce.order_items", "commerce.orders",
        ])
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
