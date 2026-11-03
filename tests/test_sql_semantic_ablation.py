import unittest

from evaluation.run_sql_semantic_ablation import VARIANTS, variant_sources


class AblationIsolationTest(unittest.TestCase):
    def test_variants_compile_and_change_only_their_intended_modules(self):
        sources = {variant: variant_sources(variant) for variant in VARIANTS}
        changed = {'temporal': {'metric_validation','metric_mapping'},
                   'ontology': {'metric_validation','metric_mapping','sql_analytics_agent'},
                   'schema': {'text_to_sql'},
                   'compiler': {'metric_mapping','sql_analytics_agent'}}
        for variant, modules in sources.items():
            for name, source in modules.items():
                with self.subTest(variant=variant,module=name):
                    compile(source, name, 'exec')
                    if variant in changed:
                        self.assertEqual(source != sources['baseline'][name], name.rsplit('.',1)[1] in changed[variant])


if __name__ == '__main__':
    unittest.main()
