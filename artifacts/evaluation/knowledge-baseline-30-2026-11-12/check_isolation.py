"""Small self-check for the import-path fix and historical schema adapter."""
from pathlib import Path
import sys
import types

RUNTIME = Path(__file__).resolve().parents[3] / 'artifacts/local/knowledge-baseline-20261111/runtime'
sys.path.insert(0, str(RUNTIME))
from evaluation.run_knowledge_invoice_benchmark import assert_runtime_isolation
from core.rag import rag_service
from core.retrieval.methods.common import eligible_cte

assert Path(rag_service.__file__).resolve().is_relative_to(RUNTIME)
assert_runtime_isolation()
foreign = types.ModuleType('core.foreign_module_self_check')
foreign.__file__ = str(RUNTIME.parent / 'outside.py')
sys.modules[foreign.__name__] = foreign
try:
    try:
        assert_runtime_isolation()
    except RuntimeError:
        pass
    else:
        raise AssertionError('Import guard allowed a foreign module')
finally:
    del sys.modules[foreign.__name__]
query, parameters = eligible_cte(None, 'policy 2026', None, ['employee'],
    include_vector=False, include_lexical=False, document_ids=['DOC'])
assert "c.metadata->>'fiscal_year' = %s" in query and 'd.fiscal_year' not in query
assert parameters[:2] == ['2026', '2026']
print('Isolated imports, foreign-module rejection and schema parameter preservation: passed')
