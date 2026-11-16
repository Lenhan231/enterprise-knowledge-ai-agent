import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from core.llm.groq_provider import GroqProvider


class StructuredDashboardGenerationTest(unittest.TestCase):
    def test_summary_of_returned_observations_reuses_chart_query_only_when_population_matches(self):
        from core.dashboards.generation import normalize_generation
        chart = "SELECT DATE_TRUNC('month', s.date) AS month, SUM(s.revenue) AS revenue FROM commerce.sales s WHERE s.date >= $1 AND s.date < $2 GROUP BY 1 LIMIT 200"
        stats = "SELECT SUM(s.revenue) AS total, AVG(s.revenue) AS average FROM commerce.sales s WHERE s.date >= $1 AND s.date < $2 LIMIT 1"
        data = {'queries': [
            {'sql': chart, 'parameters': ['2026-01-01', '2027-01-01'], 'question': 'Monthly revenue in 2026', 'explanation': 'monthly'},
            {'sql': stats, 'parameters': ['2026-01-01', '2027-01-01'], 'question': 'Revenue statistics in 2026', 'explanation': 'stats'}],
            'outputs': [{'kind': 'line', 'query': 0, 'dimension': 'month', 'measures': ['revenue']},
                        {'kind': 'summary', 'query': 1, 'dimension': None, 'measures': ['total', 'average']}]}
        result = normalize_generation(data, summarize_returned=True)
        self.assertEqual(1, len(result['queries']))
        self.assertEqual(['revenue'], result['outputs'][1]['measures'])
        self.assertEqual(0, result['outputs'][1]['query'])
        data['queries'][1]['parameters'] = ['2025-01-01', '2026-01-01']
        self.assertEqual(2, len(normalize_generation(data, summarize_returned=True)['queries']))

    def test_server_row_cap_does_not_allow_writes_wildcards_or_multiple_statements(self):
        from core.dashboards.generation import normalize_generation
        from core.analytics.sql_validation import validate_sql_security, SQLValidationError
        sql = 'WITH totals AS (SELECT SUM(s.revenue) AS revenue FROM commerce.sales s) SELECT revenue FROM totals'
        bounded = normalize_generation({'sql': sql})['sql']
        validate_sql_security(bounded)
        self.assertIn('LIMIT 200', bounded)
        for unsafe in ('DELETE FROM commerce.sales', 'SELECT * FROM commerce.sales',
                       'SELECT s.revenue FROM commerce.sales s; DELETE FROM commerce.sales'):
            with self.subTest(sql=unsafe), self.assertRaises(SQLValidationError):
                validate_sql_security(normalize_generation({'sql': unsafe})['sql'])

    def test_nested_dataset_outputs_are_lifted_without_changing_their_data(self):
        from core.dashboards.generation import normalize_generation
        data = {'queries': [
            {'sql': 'SELECT SUM(revenue) AS revenue FROM commerce.sales LIMIT 1', 'parameters': [],
             'explanation': 'Total revenue in 2026',
             'outputs': [{'kind': 'kpi', 'query': 0, 'measures': ['revenue']}]},
            {'sql': 'SELECT date, revenue FROM commerce.sales LIMIT 200', 'parameters': [],
             'explanation': 'Daily revenue in 2026',
             'outputs': [{'kind': 'line', 'query': 0, 'dimension': 'date', 'measures': ['revenue']}]},
        ]}
        result = normalize_generation(data)
        self.assertEqual([0, 1], [output['query'] for output in result['outputs']])
        self.assertEqual('Total revenue in 2026', result['queries'][0]['question'])
        self.assertEqual(data['queries'][0]['sql'], result['queries'][0]['sql'])
        self.assertNotIn('outputs', result['queries'][0])

    def test_schema_and_budget_survive_key_failover(self):
        from openai import RateLimitError
        import httpx
        first, second = Mock(), Mock()
        for client in (first, second):
            client.with_options.return_value = client
        first.chat.completions.create.side_effect = RateLimitError('quota', response=httpx.Response(429,
            request=httpx.Request('POST', 'https://api.groq.com/openai/v1/responses')), body={})
        second.chat.completions.create.return_value = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content='{}'))], usage=None)
        schema = {'type': 'object', 'properties': {}, 'additionalProperties': False}
        with patch('core.llm.groq_provider.OpenAI', side_effect=[first, second]):
            provider = GroqProvider(api_keys=['first', 'second'])
            self.assertEqual('{}', provider.generate('request', max_output_tokens=2048, response_schema=schema))
        kwargs = second.chat.completions.create.call_args.kwargs
        self.assertEqual(schema, kwargs['response_format']['json_schema']['schema'])
        self.assertTrue(kwargs['response_format']['json_schema']['strict'])
        self.assertEqual(2048, kwargs['max_completion_tokens'])
        self.assertEqual('system', kwargs['messages'][0]['role'])
        self.assertEqual('user', kwargs['messages'][1]['role'])
