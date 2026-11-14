import copy
import os
from pathlib import Path
import sys
import time
import unittest
from unittest.mock import AsyncMock, Mock, patch

import httpx
from openai import OpenAI, APIConnectionError, APIStatusError, APITimeoutError

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from core.agents.sql_analytics_agent import SQLAnalyticsAgent
from core.agents.runtime import deadline
from core.models.agents import AgentRequest, VerifiedIdentity

DECISION = {'model': 'jev-test', 'answers': {'intent': {'type': 'choice', 'choice': 'clear',
            'probabilities': {'clear': .95, 'ambiguous': .05}, 'confidence': .9}}}
HTTP_REQUEST = httpx.Request('POST', 'https://openrouter.ai/api/alpha/decisions')


class JevTransportTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.environment = patch.dict(os.environ, {'OPENROUTER_API_KEY': 'test-not-a-real-key'})
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.repository = AsyncMock()
        self.agent = SQLAnalyticsAgent(self.repository)
        self.request = AgentRequest(question='Count products in the catalog by category',
            identity=VerifiedIdentity(subject='test', permissions={'analytics:read'}))

    async def test_connection_retry_reuses_and_closes_client(self):
        with patch('core.sql_agent.agent.OpenAI') as constructor, \
                patch('core.sql_agent.agent.time.sleep') as sleep:
            client = constructor.return_value
            client.post.side_effect = [APIConnectionError(request=HTTP_REQUEST), copy.deepcopy(DECISION), copy.deepcopy(DECISION)]
            first = self.agent._check_ambiguity(self.request.question)
            second = self.agent._check_ambiguity(self.request.question)
            self.assertEqual(first['attempts'], 2)
            self.assertEqual(second['attempts'], 1)
            self.assertEqual(constructor.call_count, 1)
            self.assertEqual(constructor.call_args.kwargs['max_retries'], 0)
            sleep.assert_called_once_with(.5)
            body = client.post.call_args.kwargs['body']
            self.assertIn('source_descriptions', body['state'])
            self.assertIn('commerce.products', body['state']['preferred_sources'])
            await self.agent.close()
            client.close.assert_called_once()

    async def test_real_sdk_parses_decision_and_uses_exact_endpoint(self):
        import json
        def respond(request):
            self.assertEqual(request.url.path, '/api/alpha/decisions')
            self.assertEqual(json.loads(request.content)['model'], 'typesafe/jev-1.14')
            return httpx.Response(200, json=copy.deepcopy(DECISION))
        client = OpenAI(api_key='test-not-a-real-key', base_url='https://openrouter.ai/api/',
                        http_client=httpx.Client(transport=httpx.MockTransport(respond)))
        with patch('core.sql_agent.agent.OpenAI', return_value=client):
            result = self.agent._check_ambiguity(self.request.question)
            self.assertEqual(result['probabilities']['clear'], .95)
            await self.agent.close()
            self.assertTrue(client.is_closed())

    async def test_exhausted_timeouts_do_not_run_sql(self):
        with patch('core.sql_agent.agent.OpenAI') as constructor, \
                patch('core.sql_agent.agent.time.sleep'), \
                patch.object(self.agent, '_run_payload', new_callable=AsyncMock) as query:
            constructor.return_value.post.side_effect = [APITimeoutError(HTTP_REQUEST), APITimeoutError(HTTP_REQUEST)]
            result = await self.agent.run_payload(self.request)
            self.assertEqual(result['metadata']['failure_code'], 'jev_timeout')
            self.assertEqual(result['metadata']['jev_attempts'], 2)
            self.assertTrue(result['metadata']['retryable'])
            self.assertEqual(result['metadata']['execution_status'], 'ambiguity_failed')
            query.assert_not_awaited()
            self.repository.execute_approved_query.assert_not_awaited()

    async def test_auth_and_invalid_responses_are_not_retried(self):
        response = httpx.Response(401, request=HTTP_REQUEST)
        auth = APIStatusError('unauthorized', response=response, body=None)
        for reply, code in [(auth, 'jev_auth_failed'), ({'answers': {}}, 'jev_invalid_response')]:
            with self.subTest(code=code), patch('core.sql_agent.agent.OpenAI') as constructor, \
                    patch.object(self.agent, '_run_payload', new_callable=AsyncMock) as query:
                agent = SQLAnalyticsAgent(self.repository)
                constructor.return_value.post.side_effect = [reply]
                result = await agent.run_payload(self.request)
                self.assertEqual(result['metadata']['failure_code'], code)
                self.assertEqual(constructor.return_value.post.call_count, 1)
                self.assertFalse(result['metadata']['retryable'])
                self.repository.execute_approved_query.assert_not_awaited()

    async def test_long_retry_after_and_short_parent_deadline_do_not_sleep(self):
        response = httpx.Response(429, request=HTTP_REQUEST, headers={'retry-after': '60'})
        error = APIStatusError('rate limited', response=response, body=None)
        with patch('core.sql_agent.agent.OpenAI') as constructor, \
                patch('core.sql_agent.agent.time.sleep') as sleep:
            constructor.return_value.post.side_effect = [error]
            result = await self.agent.run_payload(self.request)
            self.assertEqual(result['metadata']['failure_code'], 'jev_unavailable')
            self.assertEqual(result['metadata']['jev_attempts'], 1)
            sleep.assert_not_called()
        with patch('core.sql_agent.agent.OpenAI') as constructor, \
                patch('core.sql_agent.agent.time.sleep') as sleep:
            agent = SQLAnalyticsAgent(self.repository)
            constructor.return_value.post.side_effect = [APITimeoutError(HTTP_REQUEST)]
            token = deadline.set(time.monotonic() + .1)
            try:
                result = await agent.run_payload(self.request)
            finally:
                deadline.reset(token)
            self.assertEqual(result['metadata']['jev_attempts'], 1)
            sleep.assert_not_called()

    async def test_low_confidence_is_not_accepted_even_when_choice_is_clear(self):
        response = copy.deepcopy(DECISION)
        response['answers']['intent']['probabilities'] = {'clear': .79, 'ambiguous': .21}
        with patch('core.sql_agent.agent.OpenAI') as constructor:
            constructor.return_value.post.return_value = response
            result = await self.agent.run_payload(self.request)
            self.assertEqual(result['metadata']['status'], 'clarification_required')
            self.assertEqual(result['metadata']['jev']['threshold'], .8)
            self.repository.execute_approved_query.assert_not_awaited()

    async def test_503_retries_once_and_missing_key_does_not_construct_client(self):
        response = httpx.Response(503, request=HTTP_REQUEST, headers={'retry-after': '0'})
        error = APIStatusError('unavailable', response=response, body=None)
        with patch('core.sql_agent.agent.OpenAI') as constructor, \
                patch('core.sql_agent.agent.time.sleep') as sleep:
            constructor.return_value.post.side_effect = [error, copy.deepcopy(DECISION)]
            self.assertEqual(self.agent._check_ambiguity(self.request.question)['attempts'], 2)
            sleep.assert_called_once_with(0)
        with patch.dict(os.environ, {'OPENROUTER_API_KEY': ''}), \
                patch('core.sql_agent.agent.OpenAI') as constructor:
            result = await SQLAnalyticsAgent(self.repository).run_payload(self.request)
            self.assertEqual(result['metadata']['failure_code'], 'jev_auth_failed')
            self.assertEqual(result['metadata']['jev_attempts'], 0)
            constructor.assert_not_called()


if __name__ == '__main__':
    unittest.main()
