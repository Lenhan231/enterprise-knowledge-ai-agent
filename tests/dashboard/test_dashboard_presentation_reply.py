import unittest

from core.agents.dashboard.models import TileSpec
from core.agents.dashboard.presentation import presentation_only


class PresentationReplyTest(unittest.TestCase):
    def test_display_commands_are_independent_of_dataset_and_field_names(self):
        for measure in ('revenue', 'stock_on_hand', 'custom_observation'):
            tile = TileSpec(id='view', title='View', query_id='q0', kind='donut', dimension='category', measures=[measure])
            for reply in ('Use a table', 'display it all in a table', 'Use a bar chart', 'Chuyển sang dạng bảng',
                          measure.replace('_', ' ') + ' in a bar chart'):
                with self.subTest(measure=measure, reply=reply):
                    self.assertTrue(presentation_only(reply, tile))

    def test_new_measure_grouping_filter_source_or_period_requires_planning(self):
        tile = TileSpec(id='view', title='View', query_id='q0', kind='donut', dimension='category', measures=['revenue'])
        for reply in ('stock on hand in a bar chart', 'Use a bar chart for category A', 'Use a bar chart in 2027',
                      'Use a table where revenue > 10', 'Use a bar chart from commerce.inventory',
                      'Use a bar chart by region', 'Use a bar chart and a table', 'Use line chart and bar chart',
                      'Use a table for only category A', 'table for category \'all\''):
            with self.subTest(reply=reply):
                self.assertFalse(presentation_only(reply, tile))
