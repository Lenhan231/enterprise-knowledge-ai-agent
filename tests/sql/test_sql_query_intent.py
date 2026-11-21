import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'src'))

from core.agents.sql.intent_resolution import (
    adapt_inventory_intent, interpret_query_intent, resolve_pending_clarification,
)
from core.agents.sql.query_intent import (
    ClarificationChoice, PendingClarification, QueryIntent,
)
from core.agents.sql.text_to_sql import APPROVED_COLUMNS


def intent_payload(question, **changes):
    intent = {
        'original_question': question,
        'operation': 'aggregate',
        'metrics': ['revenue'],
        'unverified_metric_request': None,
        'dimensions': [],
        'filters': [],
        'time_scope': {'mode': 'range', 'ranges': [
            {'start': '2025-01-01', 'end_exclusive': '2026-01-01'}]},
        'requested_sources': [{'name': 'commerce.sales', 'provenance': 'user'}],
        'explicit_source_restriction': False,
        'geographic_basis': None,
        'geographic_coverage': None,
        'ranking': None,
        'unresolved_slots': [],
    }
    intent.update(changes)
    return {'intent': intent}


class JSONProvider:
    def __init__(self, response):
        self.response = response
        self.prompts = []
        self.calls = 0

    async def generate(self, prompt, **_kwargs):
        self.calls += 1
        self.prompts.append(prompt)
        return json.dumps(self.response, ensure_ascii=False)


class StructuredIntentTest(unittest.IsolatedAsyncioTestCase):
    async def test_simple_annual_revenue_becomes_canonical_typed_intent(self):
        provider = JSONProvider(intent_payload('Total revenue in 2025'))
        result = await interpret_query_intent('Total revenue in 2025', provider, APPROVED_COLUMNS)
        self.assertEqual(result.metrics, ['revenue'])
        self.assertEqual(result.time_scope.ranges[0].start.isoformat(), '2025-01-01')
        self.assertEqual(result.time_scope.ranges[0].end_exclusive.isoformat(), '2026-01-01')
        self.assertEqual(provider.calls, 1)

    async def test_regional_revenue_adds_ontology_sources_and_clarifies_geography(self):
        question = 'Revenue by region for May 2026'
        payload = intent_payload(question, metrics=['regional_revenue'], dimensions=['region'],
            time_scope={'mode': 'range', 'ranges': [
                {'start': '2026-05-01', 'end_exclusive': '2026-06-01'}]},
            requested_sources=[], geographic_basis='unknown', geographic_coverage='unspecified')
        result = await interpret_query_intent(question, JSONProvider(payload), APPROVED_COLUMNS)
        self.assertIsInstance(result, PendingClarification)
        self.assertEqual(result.intent.metrics, ['regional_revenue'])
        self.assertEqual(result.intent.dimensions, ['region'])
        self.assertEqual(result.intent.time_scope.ranges[0].start.isoformat(), '2026-05-01')
        self.assertIn('commerce.order_items', {source.name for source in result.intent.requested_sources})
        self.assertEqual(result.unresolved_slots, ['geographic_coverage', 'geographic_basis'])

    async def test_unknown_metric_is_not_accepted_as_a_canonical_metric(self):
        payload = intent_payload('revenue growth')
        payload['intent']['metrics'] = ['invented_revenue_growth']
        with self.assertRaises(ValueError):
            await interpret_query_intent('revenue growth', JSONProvider(payload), APPROVED_COLUMNS)

    async def test_unknown_source_is_retained_as_unresolved_and_not_authorized(self):
        payload = intent_payload('total revenue')
        payload['intent']['requested_sources'] = [{'name': 'commerce.secret', 'provenance': 'user'}]
        result = await interpret_query_intent('total revenue', JSONProvider(payload), APPROVED_COLUMNS)
        self.assertIsInstance(result, PendingClarification)
        self.assertIn('source_scope', result.unresolved_slots)
        self.assertEqual(result.intent.requested_sources[0].name, 'commerce.secret')

    async def test_multiple_filters_are_retained_in_the_typed_intent(self):
        question = 'Revenue for delivered orders in the shoes category'
        filters = [
            {'field': 'commerce.orders.order_status', 'operator': 'eq', 'value': 'delivered'},
            {'field': 'commerce.products.category', 'operator': 'eq', 'value': 'shoes'},
        ]
        payload = intent_payload(question, filters=filters)
        provider = JSONProvider(payload)

        result = await interpret_query_intent(question, provider, APPROVED_COLUMNS)

        self.assertIsInstance(result, QueryIntent)
        self.assertEqual([(item.field, item.operator, item.value) for item in result.filters], [
            ('commerce.orders.order_status', 'eq', 'delivered'),
            ('commerce.products.category', 'eq', 'shoes'),
        ])
        self.assertEqual(provider.calls, 1)

    async def test_contradictory_all_regions_and_region_filter_require_clarification(self):
        question = 'Revenue for May 2026 across all regions, only North'
        payload = intent_payload(question, metrics=['regional_revenue'], dimensions=['region'],
            time_scope={'mode': 'range', 'ranges': [
                {'start': '2026-05-01', 'end_exclusive': '2026-06-01'}]},
            geographic_coverage='all', geographic_basis='order_destination',
            filters=[{'field': 'commerce.geography.region', 'operator': 'eq', 'value': 'North'}])

        result = await interpret_query_intent(question, JSONProvider(payload), APPROVED_COLUMNS)

        self.assertIsInstance(result, PendingClarification)
        self.assertEqual(result.intent.geographic_coverage, 'all')
        self.assertEqual(result.intent.filters[0].value, 'North')
        self.assertIn('geographic_coverage', result.unresolved_slots)

    async def test_yes_resolves_only_an_unambiguous_confirmation_slot(self):
        question = 'Revenue by region for May 2026'
        intent = QueryIntent.model_validate_json(json.dumps({
            'original_question': question, 'operation': 'aggregate',
            'metrics': ['regional_revenue'], 'dimensions': ['region'], 'filters': [],
            'time_scope': {'mode': 'range', 'ranges': [
                {'start': '2026-05-01', 'end_exclusive': '2026-06-01'}]},
            'requested_sources': [
                {'name': 'commerce.orders', 'provenance': 'user'},
                {'name': 'commerce.order_items', 'provenance': 'ontology_required'},
                {'name': 'commerce.geography', 'provenance': 'user'},
            ],
            'explicit_source_restriction': False,
            'geographic_basis': 'unknown', 'geographic_coverage': 'unspecified',
            'ranking': None, 'unresolved_slots': ['geographic_coverage', 'geographic_basis'],
        }))
        pending = PendingClarification(
            original_question=question, intent=intent,
            unresolved_slots=intent.unresolved_slots,
            clarification_question='Do you want all regions included?',
            allowed_choices=[
                ClarificationChoice(number=1, label='Yes, all regions',
                    slot='geographic_coverage', value='all'),
                ClarificationChoice(number=2, label='No, filter one region',
                    slot='geographic_coverage', value='filtered'),
            ],
        )
        for reply in ('yes', 'đúng rồi'):
            with self.subTest(reply=reply):
                provider = JSONProvider({'action': 'answer',
                    'updates': {'geographic_coverage': 'all'},
                    'clarified_slots': ['geographic_coverage']})
                result = await resolve_pending_clarification(
                    pending, reply, provider, APPROVED_COLUMNS)
                self.assertIsInstance(result, PendingClarification)
                self.assertEqual(result.intent.geographic_coverage, 'all')
                self.assertEqual(result.intent.geographic_basis, 'unknown')
                self.assertEqual(result.intent.metrics, ['regional_revenue'])
                self.assertEqual(result.intent.time_scope.ranges[0].start.isoformat(), '2026-05-01')

    async def test_yes_does_not_resolve_an_either_or_scope_question(self):
        question = 'Revenue by region for May 2026'
        payload = intent_payload(question, metrics=['regional_revenue'], dimensions=['region'],
            geographic_basis='unknown', geographic_coverage='unspecified')
        pending = await interpret_query_intent(question, JSONProvider(payload), APPROVED_COLUMNS)
        provider = JSONProvider({'action': 'clarify', 'updates': {},
            'clarified_slots': [],
            'clarification_question': 'Do you want all regions or one specific region?'})

        result = await resolve_pending_clarification(pending, 'yes', provider, APPROVED_COLUMNS)

        self.assertIsInstance(result, PendingClarification)
        self.assertEqual(result.intent.geographic_coverage, 'unspecified')
        self.assertIn('geographic_coverage', result.unresolved_slots)

    async def test_explicit_source_restriction_never_adds_required_order_items(self):
        question = 'Revenue by region using only orders and geography'
        payload = intent_payload(question, metrics=['regional_revenue'], dimensions=['region'],
            requested_sources=[{'name': 'commerce.orders', 'provenance': 'user'},
                               {'name': 'commerce.geography', 'provenance': 'user'}],
            explicit_source_restriction=True, geographic_basis='order_destination',
            geographic_coverage='all')
        result = await interpret_query_intent(question, JSONProvider(payload), APPROVED_COLUMNS)
        self.assertIsInstance(result, PendingClarification)
        self.assertIn('source_scope', result.unresolved_slots)
        self.assertNotIn('commerce.order_items', {source.name for source in result.intent.requested_sources})

    async def test_all_regions_reply_updates_only_coverage_and_preserves_other_slots(self):
        question = 'Revenue by region for May 2026 using named sources'
        payload = intent_payload(question, metrics=['regional_revenue'], dimensions=['region'],
            time_scope={'mode': 'range', 'ranges': [
                {'start': '2026-05-01', 'end_exclusive': '2026-06-01'}]},
            requested_sources=[{'name': 'commerce.orders', 'provenance': 'user'},
                               {'name': 'commerce.customers', 'provenance': 'user'},
                               {'name': 'commerce.geography', 'provenance': 'user'}],
            explicit_source_restriction=True, geographic_basis='unknown',
            geographic_coverage='unspecified')
        pending = await interpret_query_intent(question, JSONProvider(payload), APPROVED_COLUMNS)
        self.assertIsInstance(pending, PendingClarification)
        resolution_provider = JSONProvider({
            'action': 'answer', 'updates': {'geographic_coverage': 'all'},
            'clarified_slots': ['geographic_coverage'],
        })
        resumed = await resolve_pending_clarification(pending, 'tất cả khu vực',
                                                      resolution_provider, APPROVED_COLUMNS)
        self.assertIsInstance(resumed, PendingClarification)
        self.assertEqual(resumed.intent.geographic_coverage, 'all')
        self.assertEqual(resumed.intent.metrics, ['regional_revenue'])
        self.assertEqual(resumed.intent.dimensions, ['region'])
        self.assertEqual(resumed.intent.time_scope.ranges[0].start.isoformat(), '2026-05-01')
        self.assertTrue(resumed.intent.explicit_source_restriction)
        self.assertIn('delivery address', resumed.clarification_question)
        self.assertIn('customer profile address', resumed.clarification_question)
        self.assertEqual(resolution_provider.calls, 1)

    async def test_equivalent_all_region_replies_are_passed_to_structured_resolution(self):
        question = 'Revenue by region for May 2026'
        payload = intent_payload(question, metrics=['regional_revenue'], dimensions=['region'],
            geographic_basis='unknown', geographic_coverage='unspecified')
        pending = await interpret_query_intent(question, JSONProvider(payload), APPROVED_COLUMNS)
        for reply in ('không lọc khu vực', 'lấy hết các vùng', 'all regions'):
            with self.subTest(reply=reply):
                provider = JSONProvider({'action': 'answer',
                    'updates': {'geographic_coverage': 'all'},
                    'clarified_slots': ['geographic_coverage']})
                result = await resolve_pending_clarification(pending, reply, provider, APPROVED_COLUMNS)
                self.assertIsInstance(result, PendingClarification)
                self.assertEqual(result.intent.geographic_coverage, 'all')
                self.assertIn(reply, provider.prompts[0])

    async def test_geographic_basis_replies_change_only_the_basis_slot(self):
        question = 'Revenue by region for May 2026'
        payload = intent_payload(question, metrics=['regional_revenue'], dimensions=['region'],
            time_scope={'mode': 'range', 'ranges': [
                {'start': '2026-05-01', 'end_exclusive': '2026-06-01'}]},
            geographic_basis='unknown', geographic_coverage='all')
        pending = await interpret_query_intent(question, JSONProvider(payload), APPROVED_COLUMNS)
        for reply, basis in (('theo địa chỉ giao hàng', 'order_destination'),
                             ('theo địa chỉ khách hàng', 'customer_profile')):
            with self.subTest(reply=reply):
                provider = JSONProvider({'action': 'answer',
                    'updates': {'geographic_basis': basis},
                    'clarified_slots': ['geographic_basis']})
                result = await resolve_pending_clarification(pending, reply, provider, APPROVED_COLUMNS)
                self.assertIsInstance(result, QueryIntent)
                self.assertEqual(result.geographic_basis, basis)
                self.assertEqual(result.geographic_coverage, 'all')
                self.assertEqual(result.metrics, ['regional_revenue'])
                self.assertEqual(result.time_scope.ranges[0].start.isoformat(), '2026-05-01')

    async def test_existing_numbered_choice_resolves_its_declared_slot(self):
        question = 'Revenue by region for May 2026'
        payload = intent_payload(question, metrics=['regional_revenue'], dimensions=['region'],
            geographic_basis='unknown', geographic_coverage='unspecified')
        pending = await interpret_query_intent(question, JSONProvider(payload), APPROVED_COLUMNS)
        provider = JSONProvider({'action': 'answer',
            'updates': {'geographic_coverage': 'all'},
            'clarified_slots': ['geographic_coverage']})
        result = await resolve_pending_clarification(pending, '1', provider, APPROVED_COLUMNS)
        self.assertIsInstance(result, PendingClarification)
        self.assertEqual(result.intent.geographic_coverage, 'all')
        self.assertEqual(result.intent.metrics, ['regional_revenue'])

    async def test_explicit_date_correction_replaces_only_the_time_slot(self):
        question = 'Revenue for an unspecified period'
        intent = QueryIntent.model_validate({
            'original_question': question, 'operation': 'aggregate', 'metrics': ['revenue'],
            'dimensions': [], 'filters': [], 'time_scope': {'mode': 'unknown', 'ranges': []},
            'requested_sources': [{'name': 'commerce.sales', 'provenance': 'user'}],
            'explicit_source_restriction': False, 'geographic_basis': None,
            'geographic_coverage': None, 'ranking': None, 'unresolved_slots': ['time_scope'],
        })
        pending = PendingClarification(original_question=question, intent=intent,
            unresolved_slots=['time_scope'], clarification_question='Which period should I use?')
        provider = JSONProvider({'action': 'answer',
            'updates': {'time_scope': {'mode': 'range', 'ranges': [
                {'start': '2025-02-01', 'end_exclusive': '2025-03-01'}]}},
            'explicitly_corrected_slots': ['time_scope']})
        result = await resolve_pending_clarification(pending, 'Use February 2025 instead',
                                                     provider, APPROVED_COLUMNS)
        self.assertIsInstance(result, QueryIntent)
        self.assertEqual(result.original_question, question)
        self.assertEqual(result.metrics, ['revenue'])
        self.assertEqual(result.time_scope.ranges[0].start.isoformat(), '2025-02-01')
        self.assertEqual(result.time_scope.ranges[0].end_exclusive.isoformat(), '2025-03-01')

    async def test_unrelated_reply_clears_pending_without_inheriting_scope(self):
        question = 'Revenue by region for May 2026'
        payload = intent_payload(question, metrics=['regional_revenue'], dimensions=['region'],
            geographic_basis='unknown', geographic_coverage='unspecified')
        pending = await interpret_query_intent(question, JSONProvider(payload), APPROVED_COLUMNS)
        result = await resolve_pending_clarification(pending, 'List invoices from 2025',
            JSONProvider({'action': 'new_request'}), APPROVED_COLUMNS)
        self.assertIsNone(result)

    async def test_wrong_slot_update_is_rejected(self):
        question = 'Revenue by region for May 2026'
        payload = intent_payload(question, metrics=['regional_revenue'], dimensions=['region'],
            geographic_basis='unknown', geographic_coverage='unspecified')
        pending = await interpret_query_intent(question, JSONProvider(payload), APPROVED_COLUMNS)
        provider = JSONProvider({'action': 'answer', 'updates': {'metrics': ['order_count']},
                                 'clarified_slots': ['geographic_coverage']})
        with self.assertRaises(ValueError):
            await resolve_pending_clarification(pending, 'all regions', provider, APPROVED_COLUMNS)

    async def test_untrusted_extra_intent_keys_are_rejected(self):
        payload = intent_payload('Total revenue')
        payload['intent']['sql'] = 'DELETE FROM commerce.sales'
        with self.assertRaises(ValueError):
            await interpret_query_intent('Total revenue', JSONProvider(payload), APPROVED_COLUMNS)

    def test_inventory_intent_adapts_through_existing_mapping_validation(self):
        intent = QueryIntent.model_validate_json(json.dumps({
            'original_question': 'Top blue products by stock_on_hand on 2022-12-31',
            'operation': 'rank', 'metrics': ['stock_on_hand'],
            'unverified_metric_request': None,
            'dimensions': ['product_id', 'product_name'],
            'filters': [{'field': 'commerce.products.color', 'operator': 'eq', 'value': 'blue'}],
            'time_scope': {'mode': 'snapshot', 'ranges': [
                {'start': '2022-12-31', 'end_exclusive': '2023-01-01'}]},
            'requested_sources': [
                {'name': 'commerce.inventory', 'provenance': 'ontology_required'},
                {'name': 'commerce.products', 'provenance': 'ontology_required'},
            ],
            'explicit_source_restriction': False, 'geographic_basis': None,
            'geographic_coverage': None,
            'ranking': {'metric': 'stock_on_hand', 'direction': 'desc', 'limit': 10},
            'unresolved_slots': [],
        }))
        mapping = adapt_inventory_intent(intent, intent.original_question)
        self.assertEqual(mapping.metrics, ['stock_on_hand'])
        self.assertEqual(mapping.dimensions, ['product_id', 'product_name'])
        self.assertEqual(mapping.time.mode, 'snapshot')
        self.assertEqual(mapping.time.start, '2022-12-31')
        self.assertEqual([(item.field, item.operator, item.value) for item in mapping.filters],
                         [('color', 'eq', 'blue')])

    async def test_list_intent_does_not_require_a_metric(self):
        question = 'List product IDs, names and categories.'
        payload = intent_payload(question, operation='list', metrics=[],
            dimensions=['product_id', 'product_name', 'category'],
            time_scope={'mode': 'all', 'ranges': []},
            requested_sources=[{'name': 'commerce.products', 'provenance': 'user'}])
        result = await interpret_query_intent(question, JSONProvider(payload), APPROVED_COLUMNS)
        self.assertIsInstance(result, QueryIntent)
        self.assertEqual(result.operation, 'list')
        self.assertEqual(result.metrics, [])
        self.assertEqual(result.dimensions, ['product_id', 'product_name', 'category'])


if __name__ == '__main__':
    unittest.main()
