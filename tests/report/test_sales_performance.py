import copy
import hashlib
import json
import sys
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'src'))
from core.agents.report.sales_performance import CONTRACT_PATH, load_contract, parse_request, validate_report, evaluate_decisions, populate_sections


class SalesContractTest(unittest.TestCase):
    def test_inclusive_year_ranges(self):
        from core.agents.sql.sales_report import plans
        from core.agents.report.sales_performance import monthly_scopes
        for text, grain in (
                ('sales performance from 2025 to 2026', 'month'),
                ('Sales report between 2025 and 2026', 'month'),
                ('Revenue report 2025-2026', 'month'),
                ('Sales performance 2025 through 2026', 'month'),
                ('Sales report 2025\u20132026', 'month'),
                ('Quarterly sales report from 2025 to 2026', 'quarter'),
                ('Yearly sales performance from 2025 to 2026', 'year')):
            with self.subTest(text=text):
                scope = parse_request(text)
                self.assertEqual(scope['period'], {'start':'2025-01-01', 'end_exclusive':'2027-01-01'})
                self.assertEqual(scope['granularity'], grain)
                self.assertEqual(len(list(monthly_scopes(scope))), 24)
                self.assertEqual(plans(scope)['sales_trend'][1], (date(2025,1,1), date(2027,1,1)))
        self.assertEqual(parse_request('Sales report from 2026 to 2026')['period'],
                         {'start':'2026-01-01', 'end_exclusive':'2027-01-01'})
        for text in ('Sales report from 2026 to 2025', 'Sales report 2025 or 2026',
                     'Sales report from 2025 to 2026 or 2027', 'Sales report from 2025 to 2026 in May',
                     'Sales report Q2 from 2025 to 2026', 'Sales report from 2025 to 2026 or 2025'):
            with self.subTest(text=text), self.assertRaises(ValueError): parse_request(text)

    def test_inclusive_named_month_ranges(self):
        from core.agents.sql.sales_report import plans
        cases = [
            ('Monthly revenue report from Jan to May 2026', '2026-01-01', '2026-06-01'),
            ('Monthly revenue report between January and May 2026', '2026-01-01', '2026-06-01'),
            ('Monthly revenue report Jan-May 2026', '2026-01-01', '2026-06-01'),
            ('Monthly revenue report November 2025 through February 2026', '2025-11-01', '2026-03-01'),
            ('Monthly revenue report from May to May 2026', '2026-05-01', '2026-06-01'),
            ('Lập báo cáo tài chính từ tháng 3 đến tháng 8 năm 2024', '2024-03-01', '2024-09-01'),
            ('Báo cáo tài chính từ tháng 11 năm 2025 tới tháng 2 năm 2026', '2025-11-01', '2026-03-01'),
            ('Tao bao cao tai chinh tu thang 7 den thang 10 2025', '2025-07-01', '2025-11-01'),
        ]
        for text, start, end in cases:
            with self.subTest(text=text):
                scope = parse_request(text)
                self.assertEqual(scope['period'], {'start': start, 'end_exclusive': end})
                self.assertEqual(scope['granularity'], 'month')
                self.assertEqual(plans(scope)['sales_trend'][1], (date.fromisoformat(start), date.fromisoformat(end)))
        for text in ('Monthly revenue report from May to January 2026',
                     'Monthly revenue report Jan to May 2026 and July',
                     'Monthly revenue report between January and May 2026 or 2027'):
            with self.assertRaises(ValueError): parse_request(text)

    def test_uploaded_contract_is_preserved_byte_for_byte(self):
        self.assertEqual(hashlib.sha256(CONTRACT_PATH.read_bytes()).hexdigest(),
                         '026f55de99628aefce3a48846ceb1ae5c35d54dd6c7001805f51cb08a631b9c7')

    def test_periods(self):
        cases = [('Monthly revenue report for 2025', '2025-01-01', '2026-01-01', 'month'),
                 ('Monthly revenue report for May 2026', '2026-05-01', '2026-06-01', 'month'),
                 ('Monthly revenue report for July 2026', '2026-07-01', '2026-08-01', 'month'),
                 ('Monthly revenue report in 2026', '2026-01-01', '2027-01-01', 'month'),
                 ('Quarterly sales report Q4 2026', '2026-10-01', '2027-01-01', 'quarter'),
                 ('Annual revenue report for 2026', '2026-01-01', '2027-01-01', 'year')]
        cases.extend([('Monthly revenue report 2026-05', '2026-05-01', '2026-06-01', 'month'),
                      ('Monthly sales report Q2 2026', '2026-04-01', '2026-07-01', 'month'),
                      ('sales performance in 2026', '2026-01-01', '2027-01-01', 'month'),
                      ('Revenue report for 2025', '2025-01-01', '2026-01-01', 'month'),
                      ('Sales performance this year', '2026-01-01', '2027-01-01', 'month'),
                      ('Sales performance last year', '2025-01-01', '2026-01-01', 'month'),
                      ('Quarterly sales performance in 2026', '2026-01-01', '2027-01-01', 'quarter'),
                      ('Yearly sales performance in 2026', '2026-01-01', '2027-01-01', 'year')])
        for text, start, end, grain in cases:
            with self.subTest(text=text):
                request = parse_request(text, today=date(2026, 11, 18))
                self.assertEqual(request['period'], {'start': start, 'end_exclusive': end})
                self.assertEqual(request['granularity'], grain)
        self.assertEqual(parse_request('Monthly sales report for May', today=date(2026, 11, 18))['period']['start'], '2026-05-01')
        self.assertEqual(parse_request('Latest annual sales report', latest=date(2025, 10, 15))['period'], {'start': '2025-01-01', 'end_exclusive': '2026-01-01'})
        self.assertEqual(parse_request('Sales report last quarter', today=date(2026, 1, 18))['period'], {'start': '2025-10-01', 'end_exclusive': '2026-01-01'})
        self.assertEqual(parse_request('Monthly sales report last quarter', today=date(2026, 11, 18))['period'], {'start': '2026-07-01', 'end_exclusive': '2026-10-01'})
        self.assertEqual(parse_request('Quarterly sales report last month', today=date(2026, 11, 18))['period'], {'start': '2026-10-01', 'end_exclusive': '2026-11-01'})
        filtered = parse_request("Sales report May 2026 for category 'July'")
        self.assertEqual(filtered['period']['start'], '2026-05-01')
        self.assertEqual(filtered['dimension_value'], 'July')
        for text in ("Sales report May 2026 for region North", "Sales report May 2026 by region North", "Sales report May 2026 by category and customer"):
            with self.assertRaises(ValueError): parse_request(text)
        for text in ('sales report', 'May and July 2026 sales report', 'sales report 2025 or 2026', 'Sales report last month 2025'):
            with self.assertRaises(ValueError):
                parse_request(text)

    def test_contract_mutation_rejected(self):
        report = copy.deepcopy(load_contract()['runtime_output_template'])
        report['request'] = parse_request('Monthly revenue report May 2026')
        for metric in report['metrics']:
            metric['status'] = 'not_available'
        evaluate_decisions(report, {})
        populate_sections(report)
        validate_report(report, {})
        for mutate in (lambda r: r['metrics'][0].update(formula='SUM(total)'),
                       lambda r: r['dashboard']['widgets'].reverse(),
                       lambda r: r['decisions'][0].update(action='Invented'),
                       lambda r: r['sections'].update(extra=None)):
            changed = copy.deepcopy(report)
            mutate(changed)
            with self.assertRaises(ValueError):
                validate_report(changed)

    def test_decisions_fail_closed(self):
        report = copy.deepcopy(load_contract()['runtime_output_template'])
        evaluate_decisions(report, {})
        self.assertTrue(all(d['triggered'] is None for d in report['decisions']))
        values = {'company_revenue': 100, 'company_gross_profit': -5, 'company_revenue_change_pct': -10}
        for metric in report['metrics']:
            if metric['id'] in values:
                metric.update(value=values[metric['id']], status='available', evidence=[{'query_id': 'test'}])
        evaluate_decisions(report, {'comparable': True, 'prior_gross_profit': 20})
        self.assertEqual([d['triggered'] for d in report['decisions']], [True, True, False, False])

    def test_decision_boundaries_and_no_trigger_rule(self):
        for revenue, profit, change, prior_profit, expected in (
                (100, 20, 0, 20, [False, False, False, True]),
                (100, 0, 1, 20, [False, True, True, False]),
                (0, -10, -100, 20, [True, False, False, False]),
                (100, 20, 1, 10, [False, False, False, True])):
            report = copy.deepcopy(load_contract()['runtime_output_template'])
            values = dict(company_revenue=revenue, company_gross_profit=profit, company_revenue_change_pct=change)
            for metric in report['metrics']:
                if metric['id'] in values:
                    metric.update(value=values[metric['id']], status='available', evidence=[{'query_id':'test'}])
            evaluate_decisions(report, {'comparable':True, 'prior_gross_profit':prior_profit})
            self.assertEqual([d['triggered'] for d in report['decisions']], expected)


if __name__ == '__main__':
    unittest.main()
