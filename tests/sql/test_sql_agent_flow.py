"""LLM-free end-to-end scenarios for SQL drafting, repair, review, and fallback."""

import json
import os
import re
import sys
import unittest
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from core.analytics.join_validation import PRIMARY_KEYS
from core.analytics.text_to_sql import (
    APPROVED_COLUMNS, APPROVED_DATE_COLUMNS, APPROVED_JOINS,
    relevant_schema_tables,
)
from core.analytics.metric_ontology import get_metric_definition, resolve_metric_names
from core.sql_agent.agent import SQLAnalyticsAgent, _completed_months_revenue_plan
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
        if prompt.startswith('Extract only the user-requested business intent.'):
            request = json.loads(prompt[prompt.index('\n{') + 1:])
            question = request['question']
            metrics = sorted(resolve_metric_names(question))
            custom = any(term in question.casefold() for term in (
                'bán chạy nhất', 'best seller', 'best-selling', 'gross profit là',
            ))
            if custom:
                metrics = []
            current = date.fromisoformat(request['current_date'])
            time_scope = {'mode': 'all', 'ranges': []}
            year_match = re.search(r'\b(?:in|during|trong năm|năm)\s+(20\d{2})\b', question, re.I)
            if year_match:
                year = int(year_match.group(1))
                time_scope = {'mode': 'range', 'ranges': [{
                    'start': date(year, 1, 1).isoformat(),
                    'end_exclusive': date(year + 1, 1, 1).isoformat(),
                }]}
            elif 'tháng trước' in question.casefold() or 'last month' in question.casefold():
                end = date(current.year, current.month, 1)
                start = date(end.year - 1, 12, 1) if end.month == 1 else date(end.year, end.month - 1, 1)
                time_scope = {'mode': 'range', 'ranges': [{
                    'start': start.isoformat(), 'end_exclusive': end.isoformat(),
                }]}
            return json.dumps({'intent': {
                'original_question': question,
                'operation': 'aggregate',
                'metrics': metrics,
                'unverified_metric_request': 'Explicit custom analysis in the request' if custom or not metrics else None,
                'dimensions': [], 'filters': [], 'time_scope': time_scope,
                'requested_sources': [], 'explicit_source_restriction': False,
                'geographic_basis': None, 'geographic_coverage': None,
                'ranking': None, 'unresolved_slots': [],
            }})
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
    async def test_table_selection_and_prompt_keep_the_original_auto_scope(self):
        task_question = 'Return product sales and return rate.'
        original_question = (
            'Campaign candidates by revenue, margin and inventory snapshot 2026-10-31; include returns '
            'through 2026-11-13 for orders in that period.'
        )
        sql = 'SELECT p.product_id FROM commerce.products AS p LIMIT 10'
        provider = FakeProvider([plan(sql)])
        repository = FakeRepository()
        agent = SQLAnalyticsAgent(repository, llm=provider, inventory_only=False)
        selected = {'commerce.orders', 'commerce.order_items', 'commerce.products',
                    'commerce.returns', 'commerce.inventory'}

        with patch('core.agents.sql.agent.select_jev_schema_tables', return_value={
                'tables': selected, 'required_tables': selected, 'candidate_tables': selected}) as select_tables:
            await agent.run_payload(AgentRequest(
                question=task_question,
                metadata={'_original_question': original_question},
                identity=VerifiedIdentity(subject='analyst', permissions={'analytics:read'}),
            ))

        self.assertIn(original_question, select_tables.call_args.args[0])
        sql_prompt = provider.prompts[-1]
        self.assertIn(original_question, sql_prompt)
        self.assertIn('orders.order_date must match the specified sales cohort exactly', sql_prompt)
        self.assertIn('commerce.inventory:', sql_prompt)

    def test_recent_months_revenue_plan_accepts_vietnamese_gan_day(self):
        plan = _completed_months_revenue_plan(
            "doanh thu 5 tháng gần đây", {"revenue"}, today=date(2026, 11, 15)
        )

        self.assertIsNotNone(plan)
        self.assertEqual(plan.parameters, (date(2026, 6, 1), date(2026, 11, 1)))
        self.assertIn("GROUP BY DATE_TRUNC('month'", plan.sql)

    def test_schema_fallback_keeps_full_schema_when_no_jev_selection_exists(self):
        question = (
            "Theo tháng khách hàng mua hàng lần đầu và acquisition_channel, tính tỷ lệ khách "
            "quay lại mua đơn thứ hai trong vòng 30 ngày; kèm region."
        )
        tables = relevant_schema_tables(question, {}, APPROVED_COLUMNS)
        self.assertEqual(tables, set(APPROVED_COLUMNS))

    async def test_explicit_order_item_formula_retries_unnecessary_join_clarification(self):
        question = (
            "Trong 90 ngày kết thúc tại MAX(orders.order_date), tìm 5 vùng (region) có gross profit cao nhất. "
            "Tính doanh thu sau giảm giá = quantity × unit_price − discount_amount; gross profit là "
            "doanh thu sau giảm giá trừ giá vốn; COGS theo quantity thực giữ lại sau returns. "
            "Đối soát với payments và trình bày từng tiêu chí riêng."
        )
        definitions = {name: get_metric_definition(name) for name in resolve_metric_names(question)}
        tables = relevant_schema_tables(question, definitions, APPROVED_COLUMNS)
        self.assertEqual(tables, set(APPROVED_COLUMNS))

        sql = (
            "SELECT g.region, SUM(oi.quantity * oi.unit_price - oi.discount_amount) AS revenue "
            "FROM commerce.order_items AS oi JOIN commerce.orders AS o ON oi.order_id=o.order_id "
            "JOIN commerce.geography AS g ON o.zip=g.zip GROUP BY 1 ORDER BY 2 DESC LIMIT 5"
        )
        provider = FakeProvider([
            json.dumps({"clarification": "Please confirm whether each measure needs its own result set."}),
            plan(sql),
        ])
        repository = FakeRepository()
        agent = SQLAnalyticsAgent(repository, llm=provider, inventory_only=False)

        selected = {"commerce.orders", "commerce.order_items", "commerce.products",
                    "commerce.returns", "commerce.geography", "commerce.payments"}
        with patch('core.agents.sql.agent.select_jev_schema_tables', return_value={
                'tables': selected, 'required_tables': selected,
                'candidate_tables': selected}):
            result = await agent.run_payload(AgentRequest(
                question=question,
                identity=VerifiedIdentity(subject="analyst", permissions={"analytics:read"}),
            ))

        self.assertEqual(result["query_status"], "executed")
        self.assertEqual(len(provider.prompts), 3)
        self.assertIn('Requested metrics: {"metrics": []}', provider.prompts[-1])
        self.assertIn('do not ask for clarification', provider.prompts[-1])
        repository.execute_approved_query.assert_awaited_once_with(sql)

    async def test_vietnamese_bridge_clarification_retries_through_orders(self):
        question = (
            "Trong năm 2026, theo khu vực và kênh thu hút khách hàng, tính số đơn giao thành công "
            "và thời gian giao hàng trung bình; chỉ tính đơn đã giao và có ngày giao hợp lệ."
        )
        sql = (
            "SELECT g.region, c.acquisition_channel, COUNT(DISTINCT o.order_id) AS delivered_orders, "
            "AVG(s.delivery_date - s.ship_date) AS average_delivery_days "
            "FROM commerce.shipments AS s "
            "JOIN commerce.orders AS o ON s.order_id = o.order_id "
            "JOIN commerce.customers AS c ON o.customer_id = c.customer_id "
            "JOIN commerce.geography AS g ON o.zip = g.zip "
            "WHERE o.order_status = 'delivered' AND s.ship_date IS NOT NULL "
            "AND s.delivery_date IS NOT NULL AND s.ship_date >= $1 AND s.ship_date < $2 "
            "GROUP BY 1, 2 ORDER BY 1, 4 LIMIT 200"
        )
        provider = FakeProvider([
            json.dumps({'clarification': 'Schema không có khóa nối trực tiếp giữa customers và shipments.'}),
            json.dumps({'sql': sql, 'parameters': ['2026-01-01', '2027-01-01'],
                        'explanation': 'Delivery ranking by region and acquisition channel.'}),
        ])
        repository = FakeRepository()
        agent = SQLAnalyticsAgent(repository, llm=provider, inventory_only=False)
        selected = {'commerce.customers', 'commerce.orders', 'commerce.shipments', 'commerce.geography'}

        with patch('core.agents.sql.agent.select_jev_schema_tables', return_value={
                'tables': selected, 'required_tables': selected, 'candidate_tables': selected}):
            result = await agent.run_payload(AgentRequest(
                question=question,
                identity=VerifiedIdentity(subject='analyst', permissions={'analytics:read'}),
            ))

        self.assertEqual(result['query_status'], 'executed', result)
        self.assertEqual(len(provider.prompts), 3)
        repository.execute_approved_query.assert_awaited_once_with(
            sql, date(2026, 1, 1), date(2027, 1, 1))

    async def test_delivery_time_rank_query_validates_canonical_metric_through_ctes(self):
        question = (
            "Trong năm 2026, ở từng khu vực, kênh thu hút khách hàng nào có thời gian giao hàng trung bình "
            "ngắn nhất? Chỉ xét đơn đã giao thành công và có ngày giao hợp lệ. Hiển thị số đơn giao thành công, "
            "thời gian giao hàng trung bình và thứ hạng trong từng khu vực."
        )
        sql = (
            "WITH channel_metrics AS (SELECT geo.region AS region, cust.acquisition_channel AS acquisition_channel, "
            "COUNT(DISTINCT ship.order_id) AS successful_delivered_orders, "
            "AVG(ship.delivery_date - ship.ship_date) AS avg_delivery_time_days "
            "FROM commerce.shipments AS ship "
            "JOIN commerce.orders AS ord ON ord.order_id = ship.order_id "
            "JOIN commerce.customers AS cust ON cust.customer_id = ord.customer_id "
            "JOIN commerce.geography AS geo ON geo.zip = ord.zip "
            "WHERE ord.order_status = $1 AND ship.delivery_date IS NOT NULL "
            "AND ship.ship_date >= $2 AND ship.ship_date < $3 GROUP BY 1, 2), "
            "ranked_channels AS (SELECT region, acquisition_channel, successful_delivered_orders, "
            "avg_delivery_time_days, RANK() OVER (PARTITION BY region ORDER BY avg_delivery_time_days) AS rank_in_region "
            "FROM channel_metrics) SELECT region, acquisition_channel, successful_delivered_orders, "
            "avg_delivery_time_days, rank_in_region FROM ranked_channels ORDER BY 1, 5 LIMIT 200"
        )
        provider = FakeProvider([json.dumps({
            'sql': sql, 'parameters': ['delivered', '2026-01-01', '2027-01-01'],
        })])
        repository = FakeRepository()
        agent = SQLAnalyticsAgent(repository, llm=provider, inventory_only=False)
        selected = {'commerce.customers', 'commerce.orders', 'commerce.shipments', 'commerce.geography'}

        with patch('core.agents.sql.agent.select_jev_schema_tables', return_value={
                'tables': selected, 'required_tables': selected, 'candidate_tables': selected}):
            result = await agent.run_payload(AgentRequest(
                question=question,
                identity=VerifiedIdentity(subject='analyst', permissions={'analytics:read'}),
            ))

        self.assertEqual(result['query_status'], 'executed', result)
        self.assertEqual(result['metadata']['metrics']['delivery_time']['unit'], 'days')
        executed_sql, *parameters = repository.execute_approved_query.await_args.args
        self.assertIn('ranked_channels.region', executed_sql)
        self.assertEqual(parameters, ['delivered', date(2026, 1, 1), date(2027, 1, 1)])

    async def test_product_best_seller_uses_selected_transaction_schema(self):
        provider = FakeProvider([json.dumps({'clarification': 'Please clarify the requested metric.'})])
        repository = FakeRepository()
        agent = SQLAnalyticsAgent(repository, llm=provider, inventory_only=False)
        selected = {'commerce.order_items', 'commerce.orders', 'commerce.products'}
        with patch('core.agents.sql.agent.select_jev_schema_tables', return_value={
                'tables': selected, 'required_tables': {'commerce.order_items', 'commerce.orders'},
                'candidate_tables': selected}):
            result = await agent.run_payload(AgentRequest(
                question='sản phẩm bán chạy nhất tháng trước',
                identity=VerifiedIdentity(subject='analyst', permissions={'analytics:read'}),
            ))

        self.assertTrue(result['metadata']['clarification_required'])
        self.assertEqual(len(provider.prompts), 2)
        self.assertIn('commerce.order_items:', provider.prompts[-1])
        self.assertIn('commerce.orders:', provider.prompts[-1])
        self.assertIn('commerce.products:', provider.prompts[-1])
        self.assertNotIn('Interpret the question BEFORE generating SQL', provider.prompts[-1])

    async def test_custom_metric_runs_unverified_with_a_sql_safe_supporting_filter(self):
        sql = (
            "SELECT p.product_id, p.product_name, SUM(oi.quantity) AS total_quantity_sold "
            "FROM commerce.orders AS o JOIN commerce.order_items AS oi ON oi.order_id=o.order_id "
            "JOIN commerce.products AS p ON p.product_id=oi.product_id "
            "WHERE o.order_date >= $1 AND o.order_date < $2 "
            "AND EXISTS (SELECT 1 FROM commerce.inventory AS i WHERE i.product_id=p.product_id) "
            "GROUP BY 1, 2 ORDER BY 3 DESC, 1 LIMIT 1"
        )
        provider = FakeProvider([json.dumps({'sql': sql, 'parameters': ['2026-10-01', '2026-11-01']})])
        repository = FakeRepository()
        agent = SQLAnalyticsAgent(repository, llm=provider, inventory_only=False)
        selected = {'commerce.order_items', 'commerce.orders', 'commerce.products'}
        with patch('core.agents.sql.agent.select_jev_schema_tables', return_value={
                'tables': selected, 'required_tables': selected,
                'candidate_tables': selected | {'commerce.inventory'}}):
            result = await agent.run_payload(AgentRequest(
                question='sản phẩm bán chạy nhất tháng trước',
                identity=VerifiedIdentity(subject='analyst', permissions={'analytics:read'}),
            ))

        self.assertEqual(result['query_status'], 'executed')
        self.assertEqual(result['metadata']['metric_validation']['status'], 'unverified')
        self.assertEqual(provider.response_index, 1)
        self.assertNotIn('commerce.inventory:', provider.prompts[-1])
        repository.execute_approved_query.assert_awaited_once_with(
            sql, date(2026, 10, 1), date(2026, 11, 1))

    async def test_metric_dimension_mismatch_executes_as_unverified_after_sql_safety_passes(self):
        sql = (
            "SELECT p.product_id, p.product_name, COUNT(DISTINCT o.order_id) AS order_count "
            "FROM commerce.orders AS o "
            "JOIN commerce.order_items AS oi ON oi.order_id=o.order_id "
            "JOIN commerce.products AS p ON p.product_id=oi.product_id "
            "GROUP BY p.product_id, p.product_name "
            "ORDER BY order_count DESC, p.product_id LIMIT 1"
        )
        question = 'Sản phẩm nào có số đơn hàng cao nhất?'
        self.assertEqual(resolve_metric_names(question), {'order_count'})
        provider = FakeProvider([json.dumps({'sql': sql})])
        repository = FakeRepository()
        agent = SQLAnalyticsAgent(repository, llm=provider, inventory_only=False)
        selected = {'commerce.orders', 'commerce.order_items', 'commerce.products'}
        with patch('core.agents.sql.agent.select_jev_schema_tables', return_value={
                'tables': selected, 'required_tables': selected, 'candidate_tables': selected}):
            result = await agent.run_payload(AgentRequest(
                question=question,
                identity=VerifiedIdentity(subject='analyst', permissions={'analytics:read'}),
            ))

        self.assertEqual(result['query_status'], 'rejected', result)
        self.assertNotIn('metric_validation', result['metadata'])
        repository.execute_approved_query.assert_not_awaited()

    async def test_auto_executes_unverified_metric_after_knowledge_miss(self):
        sql = (
            "SELECT p.product_id, p.product_name, SUM(oi.quantity) AS total_quantity_sold "
            "FROM commerce.orders AS o JOIN commerce.order_items AS oi ON oi.order_id=o.order_id "
            "JOIN commerce.products AS p ON p.product_id=oi.product_id "
            "WHERE o.order_date >= $1 AND o.order_date < $2 "
            "AND EXISTS (SELECT 1 FROM commerce.inventory AS i WHERE i.product_id=p.product_id) "
            "GROUP BY 1, 2 ORDER BY 3 DESC, 1 LIMIT 1"
        )
        question = 'sản phẩm bán chạy nhất tháng trước'
        provider = FakeProvider([json.dumps({
            'sql': sql, 'parameters': ['2026-10-01', '2026-11-01'],
        })])
        repository = FakeRepository()
        metric_retriever = AsyncMock(return_value=[])
        agent = SQLAnalyticsAgent(repository, llm=provider, inventory_only=False,
                                  metric_retriever=metric_retriever)
        selected = {'commerce.order_items', 'commerce.orders', 'commerce.products'}
        with patch('core.agents.sql.agent.select_jev_schema_tables', return_value={
                'tables': selected, 'required_tables': {'commerce.order_items', 'commerce.orders'},
                'candidate_tables': selected | {'commerce.inventory'}}):
            result = await agent.run_payload(AgentRequest(
                question=question,
                identity=VerifiedIdentity(subject='analyst', permissions={'analytics:read'}),
                metadata={'_auto_mode': True, '_original_question': question},
            ))

        self.assertEqual(result['query_status'], 'executed', result)
        self.assertEqual(result['rows'], repository.execute_approved_query.return_value)
        self.assertEqual(result['metadata']['metric_validation']['status'], 'unverified')
        self.assertEqual(result['metadata']['metric_validation']['knowledge_lookup'], 'not_found')
        self.assertNotIn('commerce.inventory:', provider.prompts[-1])
        metric_retriever.assert_awaited_once()
        repository.execute_approved_query.assert_awaited_once()

    async def test_sql_mode_marks_a_safe_custom_aggregate_unverified(self):
        sql = "SELECT AVG(s.shipping_fee) AS average_shipping_fee FROM commerce.shipments AS s LIMIT 1"
        question = 'What is the average recorded shipping fee?'
        provider = FakeProvider([json.dumps({'sql': sql})])
        repository = FakeRepository()
        agent = SQLAnalyticsAgent(repository, llm=provider, inventory_only=False)
        selected = {'commerce.shipments'}

        with patch('core.agents.sql.agent.select_jev_schema_tables', return_value={
                'tables': selected, 'required_tables': selected, 'candidate_tables': selected}):
            result = await agent.run_payload(AgentRequest(
                question=question,
                identity=VerifiedIdentity(subject='analyst', permissions={'analytics:read'}),
            ))

        self.assertEqual(result['query_status'], 'executed', result)
        self.assertEqual(result['metadata']['metric_validation']['status'], 'unverified')
        repository.execute_approved_query.assert_awaited_once_with(sql)

    async def test_auto_rejects_a_canonical_metric_formula_failure(self):
        wrong = "SELECT AVG(s.revenue) AS revenue FROM commerce.sales AS s LIMIT 1"
        question = 'Total revenue'
        provider = FakeProvider([json.dumps({'sql': wrong}), json.dumps({'sql': wrong})])
        repository = FakeRepository()
        agent = SQLAnalyticsAgent(repository, llm=provider, inventory_only=False)
        selected = {'commerce.sales'}

        with patch('core.agents.sql.agent.select_jev_schema_tables', return_value={
                'tables': selected, 'required_tables': selected, 'candidate_tables': selected}):
            result = await agent.run_payload(AgentRequest(
                question=question,
                identity=VerifiedIdentity(subject='analyst', permissions={'analytics:read'}),
                metadata={'_auto_mode': True, '_original_question': question},
            ))

        self.assertEqual(result['query_status'], 'rejected', result)
        self.assertEqual(result['metadata']['metric_error_code'], 'formula_violation')
        repository.execute_approved_query.assert_not_awaited()

    async def test_comparison_cte_with_canonical_component_is_not_published_as_verified(self):
        sql = """WITH product_revenue AS (
  SELECT p.product_id AS product_id, SUM(oi.quantity * oi.unit_price - oi.discount_amount) AS total_revenue
  FROM commerce.orders AS o
  JOIN commerce.order_items AS oi ON oi.order_id = o.order_id
  JOIN commerce.products AS p ON p.product_id = oi.product_id
  WHERE o.order_status = 'delivered' AND o.order_date >= $1 AND o.order_date < $2
  GROUP BY 1
), product_ratings AS (
  SELECT p.product_id AS product_id, AVG(r.rating) AS average_rating, COUNT(r.review_id) AS review_count
  FROM commerce.reviews AS r JOIN commerce.products AS p ON p.product_id = r.product_id
  WHERE r.review_date >= $1 AND r.review_date < $2 GROUP BY 1
), product_groups AS (
  SELECT pr.product_id, pr.total_revenue, COALESCE(rt.average_rating, 0) AS average_rating,
         COALESCE(rt.review_count, 0) AS review_count
  FROM product_revenue AS pr LEFT JOIN product_ratings AS rt ON rt.product_id = pr.product_id
)
SELECT CASE WHEN pg.average_rating >= 4 THEN '4 sao trở lên' ELSE 'Dưới 4 sao' END AS rating_group,
       COUNT(pg.product_id) AS product_count, SUM(pg.total_revenue) AS total_revenue,
       AVG(pg.total_revenue) AS average_revenue_per_product, SUM(pg.review_count) AS review_count
FROM product_groups AS pg GROUP BY 1 ORDER BY 1 LIMIT 2"""
        question = ('Trong năm 2026, so sánh sản phẩm có điểm đánh giá trung bình từ 4 sao trở lên '
                    'với nhóm dưới 4 sao về doanh thu sau chiết khấu, doanh thu trung bình mỗi sản phẩm '
                    'và lượt đánh giá.')
        params = ['2026-01-01', '2027-01-01']
        provider = FakeProvider([json.dumps({'sql': sql, 'parameters': params})])
        repository = FakeRepository()
        agent = SQLAnalyticsAgent(repository, llm=provider, inventory_only=False)
        selected = {'commerce.orders', 'commerce.order_items', 'commerce.products', 'commerce.reviews'}

        with patch('core.agents.sql.agent.select_jev_schema_tables', return_value={
                'tables': selected, 'required_tables': selected, 'candidate_tables': selected}):
            result = await agent.run_payload(AgentRequest(
                question=question,
                identity=VerifiedIdentity(subject='analyst', permissions={'analytics:read'}),
                metadata={'_auto_mode': True, '_original_question': question},
            ))

        self.assertEqual(result['query_status'], 'rejected', result)
        self.assertEqual(result['metadata']['metric_error_code'], 'derived_metric_formula_mismatch')
        repository.execute_approved_query.assert_not_awaited()

    async def test_auto_unapproved_join_executes_as_unverified_after_security_passes(self):
        class RepositoryWithUnverified(FakeRepository):
            async def execute_unverified_query(self, sql, *parameters):
                self.unverified_call = (sql, parameters)
                return [{'average_shipping_fee': 12}]

        sql = (
            "SELECT AVG(s.shipping_fee) AS average_shipping_fee FROM commerce.shipments AS s "
            "JOIN commerce.customers AS c ON s.order_id = c.customer_id LIMIT 1"
        )
        question = 'What is the average shipping fee by customer?'
        provider = FakeProvider([json.dumps({'sql': sql}), json.dumps({'sql': sql})])
        repository = RepositoryWithUnverified()
        agent = SQLAnalyticsAgent(repository, llm=provider, inventory_only=False)
        selected = {'commerce.shipments', 'commerce.customers'}

        with patch('core.agents.sql.agent.select_jev_schema_tables', return_value={
                'tables': selected, 'required_tables': selected, 'candidate_tables': selected}):
            result = await agent.run_payload(AgentRequest(
                question=question,
                identity=VerifiedIdentity(subject='analyst', permissions={'analytics:read'}),
                metadata={'_auto_mode': True, '_original_question': question},
            ))

        self.assertEqual(result['query_status'], 'executed', result)
        self.assertEqual(result['metadata']['metric_validation']['status'], 'unverified')
        self.assertEqual(result['metadata']['metric_validation']['code'], 'sql_validation_failed')
        self.assertEqual(repository.unverified_call, (sql, ()))
        repository.execute_approved_query.assert_not_awaited()

    async def test_auto_schema_mismatch_executes_as_unverified_after_security_passes(self):
        sql = "SELECT s.missing_column AS value FROM commerce.shipments AS s LIMIT 1"
        question = 'What is the missing shipment value?'
        provider = FakeProvider([json.dumps({'sql': sql})])
        repository = FakeRepository()
        agent = SQLAnalyticsAgent(repository, llm=provider, inventory_only=False)
        selected = {'commerce.shipments'}

        with patch('core.agents.sql.agent.select_jev_schema_tables', return_value={
                'tables': selected, 'required_tables': selected, 'candidate_tables': selected}):
            result = await agent.run_payload(AgentRequest(
                question=question,
                identity=VerifiedIdentity(subject='analyst', permissions={'analytics:read'}),
                metadata={'_auto_mode': True, '_original_question': question},
            ))

        self.assertEqual(result['query_status'], 'executed', result)
        self.assertEqual(result['metadata']['metric_validation']['status'], 'unverified')
        self.assertEqual(result['metadata']['metric_validation']['code'], 'sql_validation_failed')
        repository.execute_approved_query.assert_awaited_once()

    async def test_auto_unverified_custom_metric_cannot_bypass_sql_security(self):
        sql = (
            "SELECT AVG(s.shipping_fee) AS average_shipping_fee FROM commerce.shipments AS s; "
            "DELETE FROM commerce.shipments"
        )
        question = 'What is the average shipping fee?'
        provider = FakeProvider([json.dumps({'sql': sql}), json.dumps({'sql': sql})])
        repository = FakeRepository()
        agent = SQLAnalyticsAgent(repository, llm=provider, inventory_only=False)
        selected = {'commerce.shipments'}

        with patch('core.agents.sql.agent.select_jev_schema_tables', return_value={
                'tables': selected, 'required_tables': selected, 'candidate_tables': selected}):
            result = await agent.run_payload(AgentRequest(
                question=question,
                identity=VerifiedIdentity(subject='analyst', permissions={'analytics:read'}),
                metadata={'_auto_mode': True, '_original_question': question},
            ))

        self.assertEqual(result['query_status'], 'rejected', result)
        self.assertEqual(result['metadata']['error_type'], 'SQLSecurityError')
        self.assertNotIn('metric_validation', result['metadata'])
        repository.execute_approved_query.assert_not_awaited()

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
        self.assertIn("commerce.order_items:", provider.prompts[-1])
        self.assertIn("quantity", provider.prompts[-1])
        self.assertIn("commerce.returns:", provider.prompts[-1])
        self.assertIn("return_quantity", provider.prompts[-1])
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
        self.assertIn("failed validation", provider.prompts[-1].lower())
        self.assertIn("commerce.orders.order_date", provider.prompts[-2])
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

    async def test_groq_request_error_does_not_fall_back_to_cloudflare(self):
        from core.llm.groq_provider import GroqProvider
        from core.llm.Cloudflare_provider import CloudflareProvider
        with patch("core.llm.groq_provider.OpenAI"):
            groq = GroqProvider(api_keys=["fake-key"])
        groq.generate = Mock(side_effect=RuntimeError("request failed"))
        agent = SQLAnalyticsAgent(FakeRepository(), llm=groq, inventory_only=False)
        with patch.object(CloudflareProvider, "__init__", side_effect=AssertionError("No cross-provider fallback")) as cloudflare:
            with patch.dict(os.environ, {"CODEX_CLI_SQL_FALLBACK": "false"}):
                with self.assertRaises(RuntimeError):
                    await agent._generate_sql("same prompt")
            cloudflare.assert_not_called()
        groq.close()

    def test_cloudflare_maps_retired_llama_model_id_to_active_fast_variant(self):
        from core.llm.Cloudflare_provider import CloudflareProvider

        with patch.dict(os.environ, {
            "CLOUDFLARE_ACCOUNT_ID": "account-test",
            "CLOUDFLARE_WORKERS_API": "test-token",
        }, clear=False):
            for retired in (
                "@cf/meta/llama-3.1-8b-instruct",
                "@cf/meta/llama-3.1-8b-instruct-fp8",
            ):
                with self.subTest(model=retired):
                    self.assertEqual(
                        CloudflareProvider(model=retired).model_name,
                        "@cf/meta/llama-3.1-8b-instruct-fast",
                    )


    async def test_sql_provider_can_explicitly_select_groq(self):
        provider = FakeProvider([])
        agent = SQLAnalyticsAgent(FakeRepository(), inventory_only=False)
        with patch.dict(os.environ, {"SQL_LLM_PROVIDER": "groq", "SQL_GROQ_MODEL": "openai/gpt-oss-20b"}), \
                patch("core.llm.groq_provider.GroqProvider", return_value=provider) as groq:
            selected = agent._provider()

        self.assertIs(selected, provider)
        groq.assert_called_once_with(model="openai/gpt-oss-20b")

    async def test_sql_provider_can_select_authenticated_local_codex_cli(self):
        from core.agents.runtime import CodexCLIProvider

        agent = SQLAnalyticsAgent(FakeRepository(), inventory_only=False)
        with patch.dict(os.environ, {"SQL_LLM_PROVIDER": "codex_cli"}, clear=False), \
                patch("core.llm.groq_provider.GroqProvider") as groq, \
                patch("core.llm.Cloudflare_provider.CloudflareProvider") as cloudflare:
            selected = agent._provider()

        self.assertIsInstance(selected, CodexCLIProvider)
        groq.assert_not_called()
        cloudflare.assert_not_called()

    async def test_sql_defaults_to_groq_even_if_cloudflare_credentials_exist(self):
        provider = FakeProvider([])
        agent = SQLAnalyticsAgent(FakeRepository(), inventory_only=False)
        with patch.dict(os.environ, {'CLOUDFLARE_API_TOKEN': 'test-token', 'CLOUDFLARE_ACCOUNT_ID': 'test-account'}), \
                patch('core.llm.groq_provider.GroqProvider', return_value=provider) as groq, \
                patch('core.llm.Cloudflare_provider.CloudflareProvider') as cloudflare:
            os.environ.pop('SQL_LLM_PROVIDER', None)
            os.environ.pop('SQL_GROQ_MODEL', None)
            self.assertIs(provider, agent._provider())
            groq.assert_called_once_with(model=None)
            cloudflare.assert_not_called()


if __name__ == "__main__":
    unittest.main()
