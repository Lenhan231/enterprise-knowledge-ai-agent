import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from core.agents.sql_analytics_agent import AnalyticsPermissionDenied, SQLAnalyticsAgent
from core.analytics.text_to_sql import (
    CommerceQuestionInterpreter,
    SQLValidationError,
    validate_commerce_sql,
)
from core.database.commerce_repository import CommerceRepository, verify_analytics_role
from core.models.agents import AgentRequest, VerifiedIdentity


ANALYST = VerifiedIdentity(
    subject="analyst-1",
    permissions={"analytics:read"},
)


class GeneratedQueryRepository:
    def __init__(self, rows):
        self.rows = rows
        self.calls = []

    async def execute_approved_query(self, sql, *parameters):
        self.calls.append((sql, parameters))
        return self.rows

    async def close(self):
        pass


class FakeTransaction:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return False


class RepositoryConnection:
    def __init__(self, *, role_info=None):
        self.role_info = role_info
        self.fetch_calls = []

    def transaction(self, *, readonly=False):
        self.readonly = readonly
        return FakeTransaction()

    async def execute(self, sql):
        self.execute_sql = sql

    async def fetch(self, sql, *parameters):
        self.fetch_calls.append((sql, parameters))
        return [{"product_id": 42}]

    async def fetchrow(self, sql, table_names):
        self.role_query = (sql, table_names)
        return self.role_info


class FakeAcquire:
    def __init__(self, connection):
        self.connection = connection

    async def __aenter__(self):
        return self.connection

    async def __aexit__(self, exc_type, exc, traceback):
        return False


class RepositoryPool:
    def __init__(self, connection):
        self.connection = connection

    def acquire(self):
        return FakeAcquire(self.connection)


class CommerceQuestionInterpreterTest(unittest.TestCase):
    def test_ambiguous_lowest_revenue_year_requests_time_grain(self):
        result = CommerceQuestionInterpreter().interpret("doanh thu thấp nhất 2022")

        self.assertIsNone(result.plan)
        self.assertIn("ngày hay tháng", result.clarification)

    def test_product_lookup_compiles_only_allowlisted_columns(self):
        result = CommerceQuestionInterpreter().interpret("Thông tin sản phẩm mã 42")

        self.assertIsNotNone(result.plan)
        self.assertEqual(result.plan.output_shape, "records")
        self.assertEqual(result.plan.sources, ("commerce.products",))
        validated = validate_commerce_sql(result.plan.sql)
        self.assertEqual(validated.sources, ("commerce.products",))
        self.assertEqual(result.plan.parameters, (42,))

    def test_sessions_by_source_is_compiled_from_ontology_and_schema(self):
        result = CommerceQuestionInterpreter().interpret(
            "Lượt truy cập theo nguồn năm 2022"
        )

        self.assertIsNotNone(result.plan)
        self.assertEqual(result.plan.metric, "sessions")
        self.assertEqual(result.plan.time_grain, "year")
        self.assertEqual(result.plan.sources, ("commerce.web_traffic",))
        self.assertIn("traffic_source", result.plan.sql)
        validate_commerce_sql(result.plan.sql)

    def test_order_count_can_group_by_status_without_a_new_operation(self):
        result = CommerceQuestionInterpreter().interpret(
            "Số đơn hàng theo trạng thái năm 2022"
        )

        self.assertIsNotNone(result.plan)
        self.assertEqual(result.plan.metric, "order_count")
        self.assertEqual(result.plan.sources, ("commerce.orders",))
        self.assertIn("order_status", result.plan.sql)
        self.assertIn("COUNT", result.plan.sql)
        validate_commerce_sql(result.plan.sql)

    def test_clarified_lowest_daily_revenue_has_a_bounded_plan(self):
        result = CommerceQuestionInterpreter().interpret(
            "Doanh thu thấp nhất theo ngày năm 2022"
        )

        self.assertIsNotNone(result.plan)
        self.assertEqual(result.plan.metric, "revenue")
        self.assertEqual(result.plan.time_grain, "day")
        self.assertIn("GROUP BY s.date", result.plan.sql)
        self.assertIn("LIMIT 1", result.plan.sql)
        validate_commerce_sql(result.plan.sql)


class SQLStructureValidationTest(unittest.TestCase):
    def test_rejects_writes_multiple_statements_unsafe_functions_and_unapproved_sources(self):
        rejected = (
            "DELETE FROM commerce.products",
            "SELECT product_id FROM commerce.products; SELECT product_id FROM commerce.products",
            "SELECT pg_sleep(10) FROM commerce.products LIMIT 1",
            "SELECT pg_read_file('postgresql.conf') FROM commerce.products LIMIT 1",
            "SELECT email FROM auth.users LIMIT 1",
            "SELECT * FROM commerce.products LIMIT 10",
            "SELECT p.product_id FROM commerce.products AS p FOR UPDATE LIMIT 1",
            "SELECT p.product_id INTO TEMP copied_products "
            "FROM commerce.products AS p LIMIT 1",
            "SELECT SUM(i.stock_on_hand) AS stock_on_hand "
            "FROM commerce.inventory AS i LIMIT 10",
            "SELECT SUM(i.stock_on_hand) AS stock_on_hand "
            "FROM commerce.inventory AS i "
            "WHERE i.snapshot_date = i.snapshot_date LIMIT 10",
        )

        for sql in rejected:
            with self.subTest(sql=sql), self.assertRaises(SQLValidationError):
                validate_commerce_sql(sql)

    def test_rejects_unapproved_join_even_when_both_tables_are_allowed(self):
        rejected = (
            (
                "SELECT o.order_id, p.product_id "
                "FROM commerce.orders AS o "
                "JOIN commerce.products AS p ON p.product_id = o.order_id "
                "LIMIT 10"
            ),
            (
                "SELECT o.order_id, g.region FROM commerce.orders AS o "
                "JOIN commerce.geography AS g ON g.zip = o.zip OR 1 = 1 "
                "LIMIT 10"
            ),
        )
        for sql in rejected:
            with self.subTest(sql=sql), self.assertRaises(SQLValidationError):
                validate_commerce_sql(sql)


class RepositorySecurityTest(unittest.IsolatedAsyncioTestCase):
    async def test_repository_revalidates_sql_and_executes_in_read_only_transaction(self):
        connection = RepositoryConnection()
        repository = CommerceRepository(RepositoryPool(connection))

        rows = await repository.execute_approved_query(
            "SELECT p.product_id FROM commerce.products AS p "
            "WHERE p.product_id = $1 LIMIT 10",
            42,
        )

        self.assertEqual(rows, [{"product_id": 42}])
        self.assertTrue(connection.readonly)
        self.assertIn("statement_timeout", connection.execute_sql)

        with self.assertRaises(SQLValidationError):
            await repository.execute_approved_query("DELETE FROM commerce.products")
        self.assertEqual(len(connection.fetch_calls), 1)

    async def test_privileged_or_write_capable_database_role_is_rejected(self):
        connection = RepositoryConnection(role_info={
            "role_name": "postgres",
            "rolsuper": True,
            "rolcreaterole": True,
            "rolcreatedb": True,
            "rolreplication": True,
            "rolbypassrls": True,
            "schema_usage": True,
            "schema_create": True,
            "can_select": True,
            "can_write": True,
        })

        with self.assertRaisesRegex(RuntimeError, "least-privilege"):
            await verify_analytics_role(RepositoryPool(connection))

    async def test_select_only_database_role_is_accepted(self):
        connection = RepositoryConnection(role_info={
            "role_name": "commerce_analytics_app",
            "rolsuper": False,
            "rolcreaterole": False,
            "rolcreatedb": False,
            "rolreplication": False,
            "rolbypassrls": False,
            "schema_usage": True,
            "schema_create": False,
            "can_select": True,
            "can_write": False,
        })

        await verify_analytics_role(RepositoryPool(connection))


class GeneratedAnalyticsPathTest(unittest.IsolatedAsyncioTestCase):
    async def test_short_lowest_revenue_question_clarifies_before_fixed_operation(self):
        agent = SQLAnalyticsAgent(GeneratedQueryRepository([]))

        result = await agent.run(AgentRequest(
            question="doanh thu thấp nhất 2022",
            identity=ANALYST,
        ))

        self.assertFalse(result.metadata["ok"])
        self.assertTrue(result.metadata["clarification_required"])
        self.assertIn("ngày hay tháng", result.answer)

    async def test_sessions_answer_includes_definition_grain_source_and_rows(self):
        repository = GeneratedQueryRepository([
            {"traffic_source": "organic_search", "sessions": 120},
            {"traffic_source": "direct", "sessions": 80},
        ])
        agent = SQLAnalyticsAgent(repository)

        result = await agent.run(AgentRequest(
            question="Lượt truy cập theo nguồn năm 2022",
            identity=ANALYST,
        ))

        self.assertTrue(result.metadata["ok"])
        self.assertIn("120", result.answer)
        self.assertIn("SUM(sessions)", result.answer)
        self.assertIn("năm", result.answer)
        self.assertIn("commerce.web_traffic", result.answer)
    async def test_basic_product_lookup_answers_only_from_returned_rows(self):
        repository = GeneratedQueryRepository([
            {
                "product_id": 42,
                "product_name": "DragonWear MA-42",
                "category": "Outdoor",
                "segment": "Women",
                "size": "M",
                "color": "Blue",
                "price": 125,
                "cogs": 80,
            }
        ])
        agent = SQLAnalyticsAgent(repository)

        result = await agent.run(AgentRequest(
            question="Thông tin sản phẩm mã 42",
            identity=ANALYST,
        ))

        self.assertTrue(result.metadata["ok"])
        self.assertEqual(result.data["rows"][0]["product_id"], 42)
        self.assertIn("DragonWear MA-42", result.answer)
        self.assertIn("commerce.products", result.answer)
        self.assertIn("không được dataset xác định", result.answer)
        self.assertNotIn("SELECT", result.model_dump_json())

    async def test_empty_generated_query_is_explicit(self):
        agent = SQLAnalyticsAgent(GeneratedQueryRepository([]))

        result = await agent.run(AgentRequest(
            question="Thông tin sản phẩm mã 999999",
            identity=ANALYST,
        ))

        self.assertFalse(result.metadata["ok"])
        self.assertIn("Không tìm thấy", result.answer)

    async def test_generated_query_requires_verified_permission(self):
        agent = SQLAnalyticsAgent(GeneratedQueryRepository([]))

        with self.assertRaises(AnalyticsPermissionDenied):
            await agent.run(AgentRequest(question="Thông tin sản phẩm mã 42"))

        with self.assertRaises(AnalyticsPermissionDenied):
            await agent.run(AgentRequest(
                question="Thông tin sản phẩm mã 42",
                identity=VerifiedIdentity(subject="viewer", permissions={"knowledge:read"}),
            ))


if __name__ == "__main__":
    unittest.main()
