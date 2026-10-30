import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))

from core.analytics.metric_ontology import get_metric_definition, resolve_metric_names


class InventoryCatalogTest(unittest.TestCase):
    def test_inventory_definitions_have_independent_governance(self):
        definition = get_metric_definition('fill_rate')
        self.assertEqual(definition['version'], '1.0.0')
        self.assertEqual(definition['provenance'], 'team_defined')
        self.assertEqual(definition['approval_status'], 'team_accepted')
        self.assertEqual(definition['business_approval_status'], 'not_recorded')
        self.assertIn('unweighted', definition['description'])

    def test_plural_and_vietnamese_aliases_do_not_add_stock_on_hand(self):
        for question in ('average fill rates in inventory', 'tỷ lệ đáp ứng trung bình trong tồn kho'):
            self.assertEqual(resolve_metric_names(question), {'fill_rate'})
        self.assertEqual(resolve_metric_names('Which products have the lowest fill rates in the latest inventory snapshot?'), {'stored_fill_rate'})
        self.assertEqual(resolve_metric_names('số lượng hàng nhập kho'), {'units_received'})

    def test_catalog_scope_and_schema(self):
        from core.analytics.metric_ontology import load_inventory_catalog
        from core.analytics.text_to_sql import APPROVED_COLUMNS
        catalog = load_inventory_catalog()
        self.assertGreaterEqual(len(catalog), 12)
        for name, definition in catalog.items():
            self.assertEqual(definition['domain'], 'inventory_management')
            for table, columns in definition['source_columns'].items():
                self.assertTrue(set(columns) <= APPROVED_COLUMNS[table], name)
            self.assertTrue(definition['aliases_by_language']['en'])
            self.assertTrue(definition['aliases_by_language']['vi'])
        self.assertNotIn('revenue', catalog)

    def test_invalid_catalog_duplicate_ids_and_unresolved_formula_are_rejected(self):
        import tempfile
        import yaml
        from core.analytics.metric_ontology import CATALOG_PATH, load_inventory_catalog
        original = yaml.safe_load(CATALOG_PATH.read_text(encoding='utf-8'))
        variants = []
        duplicate = copy.deepcopy(original)
        duplicate['metrics'].append(copy.deepcopy(duplicate['metrics'][0]))
        variants.append(duplicate)
        bad = copy.deepcopy(original)
        bad['metrics'][0]['provenance'] = 'official_because_it_runs'
        variants.append(bad)
        for payload in variants:
            with tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / 'bad.yaml'
                path.write_text(yaml.safe_dump(payload, allow_unicode=True), encoding='utf-8')
                with self.assertRaises(ValueError):
                    load_inventory_catalog(path)
