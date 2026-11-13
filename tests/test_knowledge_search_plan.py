import copy
import json
from pathlib import Path
import sys
import time
import os
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from core.agents.runtime import deadline
from core.rag.rag_service import RAGService, _merge_contexts, _format_contexts, MAX_CONTEXT_CHARS
from core.prompts.Knowledge import INSUFFICIENT_ANSWER, NO_MATCHING_DOCUMENTS_ANSWER


def chunk(doc, index, text='Evidence'):
    return {'source_id': 'S1', 'document_name': doc, 'chunk_index': index,
            'content': text, 'metadata': {'document_id': doc}}


class KnowledgeSearchPlanTest(unittest.TestCase):
    def service(self, plan, groups):
        rag = RAGService.__new__(RAGService)
        rag.llm = Mock()
        rag.llm.generate.side_effect = [plan, 'Approved [S1]. Released after approval [S2].']
        rag.retrieve_contexts = Mock(side_effect=groups)
        return rag

    def test_split_propagates_scope_deduplicates_and_answers_original_once(self):
        first, second = chunk('EN', 781), chunk('EN', 791)
        groups = [[first, chunk('OTHER', 2)], [second, first]]
        original = copy.deepcopy(groups)
        rag = self.service('{"questions":["approval?","PO release?"]}', groups)
        kwargs = dict(roles=['employee'], company='Company', metadata_filter={'domain': 'policy'},
                      document_ids=['EN'], query_language='vn', document_languages={'EN': 'en'})
        result = rag.generate_answer('Original compound question?', decompose=True, **kwargs)
        self.assertEqual([x['chunk_index'] for x in result.contexts], [781, 791, 2])
        self.assertEqual([x['source_id'] for x in result.contexts], ['S1', 'S2', 'S3'])
        self.assertEqual(groups, original)
        self.assertEqual(rag.llm.generate.call_count, 2)
        self.assertIn('Original compound question?', rag.llm.generate.call_args.args[0])
        for call, query in zip(rag.retrieve_contexts.call_args_list, ['approval?', 'PO release?']):
            self.assertEqual(call.args, (query,))
            for key, value in kwargs.items():
                self.assertEqual(call.kwargs[key], value)
            self.assertEqual(call.kwargs['limit'], 5)
        self.assertEqual(result.source_ids, ['S1', 'S2'])

    def test_single_or_invalid_plan_uses_original(self):
        plans = ['{"questions":["rewritten"]}', 'not JSON', '{"questions":[]}',
                 '{"questions":["a","b","c"]}', '{"questions":["a","A"]}',
                 '{"questions":[" "]}', '{"questions":[1]}']
        for plan in plans:
            with self.subTest(plan=plan):
                rag = self.service(plan, [[chunk('EN', 1)]])
                rag.llm.generate.side_effect = [plan, 'Answer [S1]']
                rag.generate_answer('Original?', decompose=True)
                self.assertEqual(rag.retrieve_contexts.call_args.args, ('Original?',))

    def test_three_searches_only_when_enabled(self):
        plan = '{"questions":["approver?","quotes?","emergency?"]}'
        for flag, expected in (('2', ['Original?']), ('3', ['approver?', 'quotes?', 'emergency?'])):
            with self.subTest(flag=flag), patch.dict(os.environ, {'KNOWLEDGE_MULTIQUERY_MAX': flag}):
                groups = [[chunk('EN', i)] for i in range(len(expected))]
                rag = self.service(plan, groups)
                rag.llm.generate.side_effect = [plan, 'Answer [S1].']
                rag.generate_answer('Original?', decompose=True, limit=8)
                self.assertEqual([c.args[0] for c in rag.retrieve_contexts.call_args_list], expected)
                self.assertEqual(('THREE' in rag.llm.generate.call_args_list[0].args[0]), flag == '3')
                # an unsplit search keeps the full top-k; split searches use at most 5 each
                self.assertEqual({c.kwargs['limit'] for c in rag.retrieve_contexts.call_args_list}, {8 if flag == '2' else 5})

    def test_missing_third_branch_does_not_generate_full_answer(self):
        with patch.dict(os.environ, {'KNOWLEDGE_MULTIQUERY_MAX': '3'}):
            rag = self.service('{"questions":["a","b","c"]}', [[chunk('EN', 1)], [chunk('EN', 2)], []])
            result = rag.generate_answer('Q', decompose=True)
        self.assertEqual(result.answer, INSUFFICIENT_ANSWER)

    def test_permission_errors_are_not_fallbacks(self):
        rag = self.service('{"questions":["a","b"]}', [])
        rag.retrieve_contexts.side_effect = PermissionError('Denied')
        with self.assertRaises(PermissionError):
            rag.generate_answer('Q', decompose=True, roles=['employee'])
        self.assertEqual(rag.llm.generate.call_count, 1)

    def test_missing_branch_does_not_generate_full_answer(self):
        rag = self.service('{"questions":["a","b"]}', [[chunk('EN', 1)], []])
        result = rag.generate_answer('Q', decompose=True)
        self.assertEqual(result.answer, INSUFFICIENT_ANSWER)
        self.assertEqual(rag.llm.generate.call_count, 1)

    def test_no_matches_retains_existing_message(self):
        rag = self.service('{"questions":["a","b"]}', [[], []])
        self.assertEqual(rag.generate_answer('Q', decompose=True).answer, NO_MATCHING_DOCUMENTS_ANSWER)
        self.assertEqual(rag.llm.generate.call_count, 1)

    def test_budget_preserves_whole_chunks_and_detects_lost_branch(self):
        huge = chunk('EN', 1, 'X' * MAX_CONTEXT_CHARS)
        self.assertEqual(_merge_contexts([[huge]]), [])
        rag = self.service('{"questions":["a","b"]}', [[huge], [chunk('EN', 2)]])
        self.assertTrue(rag.generate_answer('Q', decompose=True).insufficient_context)
        self.assertEqual(rag.llm.generate.call_count, 1)
        merged = _merge_contexts([[chunk('A', i) for i in range(20)], [chunk('B', i) for i in range(20)]])
        self.assertEqual(len(merged), 10)
        self.assertEqual(merged[1]['metadata']['document_id'], 'B')
        self.assertLessEqual(len(_format_contexts(merged)), MAX_CONTEXT_CHARS)

    def test_deadline_expiry_stops_before_planning(self):
        rag = self.service('{"questions":["a","b"]}', [])
        token = deadline.set(time.monotonic() - 1)
        try:
            with self.assertRaises(TimeoutError):
                rag.generate_answer('Q', decompose=True)
            rag.llm.generate.assert_not_called()
        finally:
            deadline.reset(token)

    def test_planner_failure_restores_deadline_and_falls_back(self):
        rag = self.service('', [[chunk('EN', 1)]])
        rag.llm.generate.side_effect = [RuntimeError('Empty output'), 'Answer [S1]']
        token = deadline.set(time.monotonic() + 60)
        before = deadline.get()
        try:
            rag.generate_answer('Q', decompose=True)
            self.assertEqual(deadline.get(), before)
        finally:
            deadline.reset(token)

    def test_default_path_does_not_plan(self):
        rag = self.service('', [[chunk('EN', 1)]])
        rag.llm.generate.side_effect = ['Answer [S1]']
        rag.generate_answer('Q')
        self.assertEqual(rag.llm.generate.call_count, 1)


if __name__ == '__main__':
    unittest.main()
