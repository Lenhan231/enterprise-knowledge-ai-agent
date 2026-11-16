import calendar
from datetime import date
import unittest

from core.analytics.metric_validation import (
    MetricDefinitionError, inventory_explicit_dates, inventory_time_scope,
    validate_independent_query_period,
)
from core.analytics.sql_validation import APPROVED_DATE_COLUMNS


class SQLMonthScopeTest(unittest.TestCase):
    def test_abbreviated_range_keeps_the_start_month(self):
        self.assertEqual(('range', '2026-01-01', '2026-05-31'),
                         inventory_time_scope('monthly traffic from Jan to May 2026'))

    def test_every_calendar_abbreviation_matches_the_full_month(self):
        for index in range(1, 13):
            for token in (calendar.month_abbr[index], calendar.month_abbr[index].upper() + '.'):
                with self.subTest(token=token):
                    self.assertEqual(inventory_time_scope(f'{calendar.month_name[index]} 2024'),
                                     inventory_time_scope(f'{token} 2024'))

    def test_mixed_month_ranges_and_repeated_year_are_supported(self):
        for question in ('Sep through November 2026', 'September to Nov 2026',
                         'Sep. 2026 until Nov. 2026', 'Sep-Nov 2026'):
            with self.subTest(question=question):
                self.assertEqual(('range', '2026-09-01', '2026-11-30'), inventory_time_scope(question))

    def test_abbreviated_exact_dates_are_not_treated_as_a_whole_year(self):
        self.assertEqual([date(2026, 1, 31)], inventory_explicit_dates('Jan. 31, 2026'))
        self.assertEqual(('snapshot', '2026-01-31', None), inventory_time_scope('Jan 31, 2026'))

    def test_reversed_abbreviated_range_is_rejected(self):
        with self.assertRaises(MetricDefinitionError):
            inventory_time_scope('Nov to Feb 2026')

    def test_named_month_selection_retains_both_months_and_excludes_intermediate_months(self):
        question = 'monthly sessions during Jan and May 2026'
        self.assertEqual(('range', '2026-01-01', '2026-05-31'), inventory_time_scope(question))
        sql = ('SELECT SUM(w.sessions) AS sessions FROM commerce.web_traffic w '
               'WHERE w.date >= $1 AND w.date < $2 AND EXTRACT(MONTH FROM w.date) IN (1, 5) LIMIT 1')
        validate_independent_query_period(sql, ('2026-01-01', '2026-06-01'), question,
                                          {'commerce.web_traffic'}, APPROVED_DATE_COLUMNS)
        for wrong in (sql.replace(' IN (1, 5)', ' IN (1, 2, 3, 4, 5)'),
                      sql.replace(' AND EXTRACT(MONTH FROM w.date) IN (1, 5)', '')):
            with self.subTest(wrong=wrong), self.assertRaises(MetricDefinitionError):
                validate_independent_query_period(wrong, ('2026-01-01', '2026-06-01'), question,
                                                  {'commerce.web_traffic'}, APPROVED_DATE_COLUMNS)

    def test_sql_period_proof_accepts_the_full_requested_range_and_rejects_shortening(self):
        sql = ('SELECT SUM(w.sessions) AS sessions FROM commerce.web_traffic w '
               'WHERE w.date >= $1 AND w.date < $2 LIMIT 1')
        question = 'total sessions from Jan to May 2026'
        validate_independent_query_period(sql, ('2026-01-01', '2026-06-01'), question,
                                          {'commerce.web_traffic'}, APPROVED_DATE_COLUMNS)
        with self.assertRaises(MetricDefinitionError):
            validate_independent_query_period(sql, ('2026-05-01', '2026-06-01'), question,
                                              {'commerce.web_traffic'}, APPROVED_DATE_COLUMNS)
