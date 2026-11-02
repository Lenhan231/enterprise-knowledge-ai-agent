import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from core.reports.facts import ReportFact, compare_facts, validate_fact_claim, display_value


def fact(**changes):
    return ReportFact(id='F1', evidence_id='S1', task_id='stock', metric='stock_on_hand',
                      value='10', unit='units', dimensions={'category': 'A'}, snapshot_date='2022-01-31', **changes)


class ReportFactTest(unittest.TestCase):
    def test_claim_must_match_metric_product_date_and_value(self):
        original = fact()
        for key, value in [('metric', 'units_sold'), ('snapshot_date', '2022-02-28'),
                           ('dimensions', {'category': 'B'}), ('value', '100')]:
            claim = original.model_dump()
            claim[key] = value
            with self.assertRaises(ValueError):
                validate_fact_claim(claim, {'F1': original})

    def test_comparison_uses_decimal_and_records_lineage(self):
        before = fact()
        after = before.model_copy(update={'id': 'F2', 'value': '15', 'snapshot_date': '2022-02-28'})
        difference, percent = compare_facts(before, after, 'F3')
        self.assertEqual(difference.value, '5')
        self.assertEqual(percent.value, '0.5')
        self.assertEqual(percent.operands, ['F1', 'F2'])
        self.assertEqual(display_value(percent), '50%')

    def test_zero_and_incompatible_comparisons_are_unavailable(self):
        before = fact().model_copy(update={'value': '0'})
        after = fact().model_copy(update={'id': 'F2', 'snapshot_date': '2022-02-28'})
        self.assertIsNone(compare_facts(before, after, 'F3')[1].value)
        with self.assertRaises(ValueError):
            compare_facts(before, after.model_copy(update={'unit': 'days'}), 'F3')

    def test_rate_difference_is_percentage_points_not_relative_percent(self):
        before = fact().model_copy(update={'metric': 'fill_rate', 'unit': 'percent', 'value': '0.25'})
        after = before.model_copy(update={'id': 'F2', 'value': '0.5', 'snapshot_date': '2022-02-28'})
        difference, percent = compare_facts(before, after, 'F3')
        self.assertEqual((difference.value, difference.unit), ('25.00', 'percentage_points'))
        self.assertEqual(display_value(percent), '100%')


if __name__ == '__main__':
    unittest.main()
