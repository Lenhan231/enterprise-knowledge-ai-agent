"""Tests for the SQL tool loop and its explicit draft/execute endpoint."""

import json
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from core.agents.main import create_app
from core.analytics.text_to_sql import APPROVED_COLUMNS
from core.models.agents import VerifiedIdentity
from core.sql_agent.agent import SQLAnalyticsAgent


IDENTITY = VerifiedIdentity(subject="sql-assistant-test", permissions={"analytics:read"})
SQL = "SELECT SUM(s.revenue) AS revenue FROM commerce.sales AS s LIMIT 1"


class FakeProvider:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.prompts = []
        self.output_limits = []

    def generate(self, prompt, *, max_output_tokens):
        self.prompts.append(prompt)
        self.output_limits.append(max_output_tokens)
        result = next(self.responses)
        if isinstance(result, BaseException):
            raise result
        return result


class SQLAssistantEndpointTest(unittest.TestCase):
    def setUp(self):
        self.repository = SimpleNamespace(
            get_schema=AsyncMock(return_value={
                "tables": APPROVED_COLUMNS,
                "primary_keys": {"commerce.sales": frozenset({"date"})},
                "joins": frozenset(), "date_columns": frozenset({("commerce.sales", "date")}),
            }),
            execute_approved_query=AsyncMock(return_value=[{"revenue": 42}]),
            close=AsyncMock(),
        )
        self.provider = FakeProvider([
            json.dumps({"sql": SQL, "parameters": [], "explanation": "Sum daily revenue."}),
        ])
        self.agent = SQLAnalyticsAgent(self.repository, llm=self.provider, inventory_only=False)
        self.client = TestClient(create_app(sql_agent=self.agent,
            identity_resolver=lambda _request: IDENTITY))
        self.client.__enter__()
        self.addCleanup(self.client.__exit__, None, None, None)

    def test_draft_uses_live_schema_and_waits_for_user_approval(self):
        response = self.client.post("/api/sql/assistant", json={"question": "Total revenue"})

        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertEqual(payload["status"], "approval_required")
        self.assertEqual(payload["sql"], SQL)
        self.assertEqual(payload["metrics"], {})
        self.assertEqual(self.provider.output_limits, [900])
        self.assertIn("commerce.order_items", self.provider.prompts[0])
        self.assertIn("Declared join keys", self.provider.prompts[0])
        self.assertIn("Do not apply a business metric ontology", self.provider.prompts[0])
        self.repository.execute_approved_query.assert_not_awaited()

    def test_noncanonical_product_revenue_can_use_transaction_tables(self):
        sql = """WITH rev AS (
          SELECT oi.product_id,
            SUM(oi.quantity * oi.unit_price) FILTER (WHERE EXTRACT(YEAR FROM o.order_date) = 2021) AS rev_2021,
            SUM(oi.quantity * oi.unit_price) FILTER (WHERE EXTRACT(YEAR FROM o.order_date) = 2022) AS rev_2022
          FROM commerce.order_items AS oi
          JOIN commerce.orders AS o ON o.order_id = oi.order_id
          WHERE EXTRACT(YEAR FROM o.order_date) IN (2021, 2022)
          GROUP BY oi.product_id
        )
        SELECT r.product_id, p.product_name, r.rev_2021, r.rev_2022,
          r.rev_2022 - r.rev_2021 AS growth
        FROM rev AS r
        JOIN commerce.products AS p ON p.product_id = r.product_id
        WHERE r.rev_2021 > 0 AND r.rev_2022 > 0
        ORDER BY 5 DESC, 1
        LIMIT 10"""
        self.provider.responses = iter([
            json.dumps({"sql": sql, "parameters": [],
                        "explanation": "Line revenue is quantity times unit price; discount is excluded."}),
        ])

        response = self.client.post("/api/sql/assistant", json={
            "question": "Product revenue by year using order_items quantity times unit_price",
        })

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["status"], "approval_required")
        self.assertEqual(response.json()["metrics"], {})
        self.assertIn("commerce.order_items", response.json()["sources"])
        self.repository.execute_approved_query.assert_not_awaited()

    def test_invalid_draft_gets_one_validator_repair_attempt(self):
        self.provider.responses = iter([
            json.dumps({"sql": "SELECT r.product_id FROM commerce.sales AS s LIMIT 10",
                        "parameters": [], "explanation": "Invalid alias."}),
            json.dumps({"sql": SQL, "parameters": [], "explanation": "Sum revenue."}),
        ])

        response = self.client.post("/api/sql/assistant", json={"question": "Total revenue"})

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["status"], "approval_required")
        self.assertEqual(self.provider.output_limits, [900, 900])
        self.assertIn("previous query failed validation", self.provider.prompts[1].lower())
        self.repository.execute_approved_query.assert_not_awaited()

    def test_approved_sql_is_revalidated_then_executed(self):
        response = self.client.post("/api/sql/assistant", json={
            "question": "Total revenue", "mode": "execute", "sql": SQL, "parameters": [],
        })

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["status"], "executed")
        self.assertEqual(response.json()["rows"], [{"revenue": 42}])
        self.repository.execute_approved_query.assert_awaited_once_with(SQL)

    def test_unsafe_approved_sql_is_rejected_without_execution(self):
        response = self.client.post("/api/sql/assistant", json={
            "question": "Total revenue", "mode": "execute",
            "sql": "DELETE FROM commerce.sales", "parameters": [],
        })

        self.assertEqual(response.status_code, 422)
        self.repository.execute_approved_query.assert_not_awaited()

    def test_ranked_approved_sql_is_semantically_checked_before_execution(self):
        sql = (
            "SELECT oi.product_id, SUM(oi.quantity * oi.unit_price - oi.discount_amount) AS revenue "
            "FROM commerce.order_items AS oi GROUP BY oi.product_id ORDER BY 1 DESC LIMIT 5"
        )
        response = self.client.post("/api/sql/assistant", json={
            "question": "Top 5 products by revenue", "mode": "execute", "sql": sql, "parameters": [],
        })

        self.assertEqual(response.status_code, 422)
        self.assertIn("requested measure", response.json()["detail"])
        self.repository.execute_approved_query.assert_not_awaited()

    def test_unverifiable_ranking_can_be_drafted_but_not_executed(self):
        question = "Which month had the highest gross profit?"
        sql = (
            "SELECT DATE_TRUNC('month', s.date) AS month, "
            "SUM(s.revenue) - SUM(s.cogs) AS gross_profit "
            "FROM commerce.sales AS s GROUP BY 1 ORDER BY 2 DESC LIMIT 1"
        )
        self.provider.responses = iter([json.dumps({
            "sql": sql, "parameters": [], "explanation": "Monthly gross profit.",
        })])

        draft = self.client.post("/api/sql/assistant", json={"question": question})

        self.assertEqual(draft.status_code, 200, draft.text)
        self.assertEqual(draft.json()["status"], "approval_required")
        self.assertIn("Review-only draft", draft.json()["message"])
        self.assertTrue(any("not verified by a typed contract" in note
                            for note in draft.json()["limitations"]))
        self.repository.execute_approved_query.assert_not_awaited()

        execution = self.client.post("/api/sql/assistant", json={
            "question": question, "mode": "execute", "sql": sql, "parameters": [],
        })

        self.assertEqual(execution.status_code, 422, execution.text)
        self.assertIn("review only", execution.json()["detail"])
        self.repository.execute_approved_query.assert_not_awaited()

    def test_custom_ranking_without_typed_contract_is_draft_only(self):
        question = "Which customer ranks highest by net item value?"
        sql = (
            "SELECT o.customer_id, SUM(oi.quantity * oi.unit_price - oi.discount_amount) AS net_value "
            "FROM commerce.orders AS o JOIN commerce.order_items AS oi ON oi.order_id=o.order_id "
            "GROUP BY o.customer_id ORDER BY net_value DESC LIMIT 1"
        )
        self.provider.responses = iter([json.dumps({
            "sql": sql, "parameters": [], "explanation": "Net item value by customer.",
        })])
        draft = self.client.post("/api/sql/assistant", json={"question": question})
        self.assertEqual(draft.status_code, 200, draft.text)
        self.assertEqual(draft.json()["status"], "approval_required")

        execution = self.client.post("/api/sql/assistant", json={
            "question": question, "mode": "execute", "sql": sql, "parameters": [],
        })
        self.assertEqual(execution.status_code, 422, execution.text)
        self.assertIn("typed ranking_contract", execution.json()["detail"])
        self.repository.execute_approved_query.assert_not_awaited()

    def test_missing_intent_without_typed_contract_is_review_only(self):
        question = "Khách hàng nào trả nhiều tiền nhất?"
        sql = (
            "SELECT o.customer_id, SUM(p.payment_value) AS total_payment "
            "FROM commerce.orders AS o JOIN commerce.payments AS p ON p.order_id=o.order_id "
            "GROUP BY o.customer_id ORDER BY 1 DESC LIMIT 1"
        )
        self.provider.responses = iter([json.dumps({
            "sql": sql, "parameters": [], "explanation": "Payment total by customer.",
        })])

        with patch("core.agents.sql.assistant_endpoint.resolve_ranking_intent", return_value=None):
            draft = self.client.post("/api/sql/assistant", json={"question": question})
            execution = self.client.post("/api/sql/assistant", json={
                "question": question, "mode": "execute", "sql": sql, "parameters": [],
            })

        self.assertEqual(draft.status_code, 200, draft.text)
        self.assertEqual(draft.json()["status"], "approval_required")
        self.assertIn("Review-only draft", draft.json()["message"])
        self.assertTrue(any("not verified by a typed contract" in note
                            for note in draft.json()["limitations"]))
        self.assertEqual(execution.status_code, 422, execution.text)
        self.assertIn("review only", execution.json()["detail"])
        self.repository.execute_approved_query.assert_not_awaited()

    def test_noncanonical_rank_contract_survives_review_and_reexecution(self):
        contract = {
            "entity": "customer",
            "measure": {"source": "commerce.payments", "column": "payment_value", "aggregation": "sum"},
            "direction": "desc", "limit": 1, "partition_by": [],
        }
        wrong = (
            "SELECT o.customer_id, SUM(p.payment_value) AS total_payment "
            "FROM commerce.orders AS o JOIN commerce.payments AS p ON p.order_id=o.order_id "
            "GROUP BY o.customer_id ORDER BY 1 DESC LIMIT 1"
        )
        correct = wrong.replace("ORDER BY 1 DESC", "ORDER BY total_payment DESC, o.customer_id")
        self.provider.responses = iter([
            json.dumps({"sql": wrong, "parameters": [], "explanation": "Payment totals.",
                        "ranking_contract": contract}),
            json.dumps({"sql": correct, "parameters": [], "explanation": "Payment totals.",
                        "ranking_contract": contract}),
        ])
        question = "Khách hàng nào trả nhiều tiền nhất?"
        with patch("core.agents.sql.assistant_endpoint.resolve_ranking_intent", return_value=None):
            draft = self.client.post("/api/sql/assistant", json={"question": question})

        self.assertEqual(draft.status_code, 200, draft.text)
        self.assertEqual(draft.json()["status"], "approval_required")
        self.assertEqual(draft.json()["ranking_contract"], contract)
        self.assertEqual(draft.json()["ranking_validation"]["status"], "verified")
        self.assertEqual(draft.json()["ranking_validation"]["measure_approval"], "unverified")
        self.repository.execute_approved_query.assert_not_awaited()

        with patch("core.agents.sql.assistant_endpoint.resolve_ranking_intent", return_value=None):
            executed = self.client.post("/api/sql/assistant", json={
                "question": question, "mode": "execute", "sql": draft.json()["sql"],
                "parameters": draft.json()["parameters"], "ranking_contract": draft.json()["ranking_contract"],
            })

        self.assertEqual(executed.status_code, 200, executed.text)
        self.assertEqual(executed.json()["status"], "executed")
        self.assertEqual(executed.json()["ranking_validation"]["status"], "verified")
        self.assertEqual(executed.json()["ranking_validation"]["measure_approval"], "unverified")
        self.repository.execute_approved_query.assert_awaited_once_with(correct)
