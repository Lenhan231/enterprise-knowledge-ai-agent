"""Exercise automatic query translation without API or database calls."""
import hashlib
import importlib.util
import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'src'), str(ROOT / 'scripts/retrieval')]
from core.retrieval.query_translator import QueryTranslator

spec = importlib.util.spec_from_file_location('automatic_benchmark', ROOT / 'scripts/retrieval/evaluate_bilingual_two_document_benchmark.py')
benchmark = importlib.util.module_from_spec(spec)
spec.loader.exec_module(benchmark)


class AutomaticTranslationTest(unittest.TestCase):
    def test_translation_validates_outputs_preserves_original_and_caches(self):
        llm = Mock()
        llm.generate.return_value = '{"translation":"Doanh thu?"}'
        translator = QueryTranslator(llm)
        self.assertEqual(translator.translate('Revenue?', 'en'), {'en': 'Revenue?', 'vn': 'Doanh thu?'})
        translator.translate('Revenue?', 'en')
        self.assertEqual(llm.generate.call_count, 1)
        for value in ('', ' ', 'x' * 4001):
            with self.assertRaises(ValueError):
                translator.translate(value, 'en')
        for raw in ('not json', '{"translation":"   "}', '{"translation":1}', '{"translation":"ok","extra":1}'):
            llm = Mock()
            llm.generate.return_value = raw
            with self.assertRaises(ValueError):
                QueryTranslator(llm).translate('question', 'en')

    def test_help_and_self_check_do_not_construct_provider_or_repository(self):
        with patch.object(benchmark, 'GroqProvider') as provider, patch.object(benchmark, 'DocumentChunkRepository') as repository:
            with patch.object(sys, 'argv', ['runner', '--self-check']), redirect_stdout(io.StringIO()):
                benchmark.main()
            with patch.object(sys, 'argv', ['runner', '--help']), redirect_stdout(io.StringIO()), self.assertRaises(SystemExit) as exit:
                benchmark.main()
            self.assertEqual(exit.exception.code, 0)
            provider.assert_not_called()
            repository.assert_not_called()

    def test_complete_mocked_runner_success_failure_and_provider_cleanup(self):
        for mode in ('success', 'translation_failure', 'provider_failure'):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as folder:
                root = Path(folder)
                data = root / 'data/evaluation'
                artifacts = root / 'artifacts/evaluation/retrieval'
                data.mkdir(parents=True)
                artifacts.mkdir(parents=True)
                translator_path = root / 'src/core/retrieval/query_translator.py'
                translator_path.parent.mkdir(parents=True)
                translator_path.write_bytes((ROOT / 'src/core/retrieval/query_translator.py').read_bytes())
                doc_ids = list(benchmark.SOURCES.values())
                db_rows = [(0, 'text', {'document_id': doc_id, 'page_number': 1, 'embedding_model': 'mock-model'}, '[0.1]', doc_id, ['admin'], None, 'Company') for doc_id in doc_ids]
                corpus_hash = hashlib.sha256(json.dumps(db_rows, ensure_ascii=False, default=str).encode()).hexdigest()
                for language, suffix in (('en', '_en'), ('vn', '')):
                    cases = [{'id': f'Q{i:02}', 'question': f'{language} original {i}', 'evidence': [{'source': 'annual_report', 'chunk_index': 0, 'page_number': 1}]} for i in range(1, 25)]
                    case_bytes = json.dumps(cases).encode()
                    (data / f'long_hau_2008_cases{suffix}.json').write_bytes(case_bytes)
                    (artifacts / f'scoped-{language}-gpu.json').write_text(json.dumps({'scoped_corpus_sha256': corpus_hash, 'cases_sha256': hashlib.sha256(case_bytes).hexdigest(), 'summary': {}}))
                repository = Mock()
                repository.conn.execute.return_value.fetchall.return_value = db_rows
                def search(vector, limit, **options):
                    self.assertEqual(options['roles'], ['admin'])
                    return [SimpleNamespace(document_id=options['document_ids'][0], chunk_index=0)]
                repository.similarity_search.side_effect = search
                llm = Mock(model_name='mock-translation-model', last_usage=None)
                def generate(prompt):
                    if mode == 'translation_failure':
                        raise RuntimeError('mock failure')
                    llm.last_usage = {'input_tokens': 2, 'output_tokens': 1, 'total_tokens': 3}
                    return '{"translation":"automatic translated query"}'
                llm.generate.side_effect = generate
                embedding = Mock()
                embedding.embed_query.return_value = [0.1]
                huggingface = SimpleNamespace(HuggingFaceEmbeddings=Mock(return_value=embedding))
                provider = Mock(return_value=llm)
                if mode == 'provider_failure':
                    provider.side_effect = RuntimeError('construction failed')
                args = ['runner', '--language-aware', '--device', 'cpu']
                with patch.object(benchmark, 'ROOT', root), patch.object(benchmark, 'DocumentChunkRepository', return_value=repository), patch.object(benchmark, 'GroqProvider', provider), patch.dict(sys.modules, {'langchain_huggingface': huggingface}), patch.object(sys, 'argv', args), redirect_stdout(io.StringIO()):
                    if mode == 'provider_failure':
                        with self.assertRaises(RuntimeError):
                            benchmark.main()
                    else:
                        benchmark.main()
                repository.close.assert_called_once()
                if mode == 'provider_failure':
                    continue
                llm.close.assert_called_once()
                output = json.loads((artifacts / 'scoped-automatic_language_aware.json').read_text())
                self.assertEqual(len(output['results']), 96)
                self.assertEqual(output['translation_summary']['attempted_cases'], 48)
                self.assertEqual(embedding.embed_query.call_count, 48)
                for row in output['results']:
                    self.assertEqual(row['translation_model'], 'mock-translation-model')
                    self.assertGreaterEqual(row['translation_latency_ms'], 0)
                    if mode == 'success':
                        self.assertEqual(row['lexical_queries'][row['language']], row['question'])
                        other = 'vn' if row['language'] == 'en' else 'en'
                        self.assertEqual(row['lexical_queries'][other], 'automatic translated query')
                        self.assertIsNone(row['translation_error'])
                    else:
                        self.assertEqual(row['translation_error'], 'RuntimeError')
                        self.assertEqual(row['dense_fallbacks'], row['method'].endswith('_hybrid'))
                        self.assertEqual(bool(row['ranked_chunk_ids']), row['method'].endswith('_hybrid'))
                self.assertEqual(output['translation_summary']['failed_cases'], 48 if mode == 'translation_failure' else 0)
                self.assertEqual(output['translation_summary']['usage']['total_tokens'], 0 if mode == 'translation_failure' else 144)


if __name__ == '__main__':
    unittest.main()