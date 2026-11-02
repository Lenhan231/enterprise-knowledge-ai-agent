import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import httpx
from openai import RateLimitError

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from core.llm.groq_provider import GroqProvider


def limited():
    response = httpx.Response(429, request=httpx.Request('POST', 'https://api.groq.com/openai/v1/responses'))
    return RateLimitError('test rate limit', response=response, body={})


class GroqFailoverTest(unittest.TestCase):
    @patch('core.llm.groq_provider.OpenAI')
    def test_third_key_is_used_only_after_both_earlier_keys_are_limited(self, factory):
        clients=[MagicMock() for _ in range(3)]
        factory.side_effect=clients
        for client in clients[:2]:
            client.with_options.return_value.responses.create.side_effect=limited()
        clients[2].with_options.return_value.responses.create.return_value=MagicMock(output_text='third key answer')
        provider=GroqProvider(model='same-model',api_keys=['primary-test','backup-test','tertiary-test'])
        try:
            self.assertEqual(provider.generate('question'),'third key answer')
            for client in clients:
                call=client.with_options.return_value.responses.create.call_args
                self.assertEqual(call.kwargs['model'],'same-model')
            provider.generate('next question')
            self.assertEqual([c.with_options.return_value.responses.create.call_count for c in clients],[1,1,2])
        finally:
            provider.close()

    @patch('core.llm.groq_provider.OpenAI')
    def test_rate_limit_switches_key_and_preserves_model(self, factory):
        primary, backup = MagicMock(), MagicMock()
        factory.side_effect = [primary, backup]
        primary.with_options.return_value.responses.create.side_effect = limited()
        backup.with_options.return_value.responses.create.return_value = MagicMock(output_text='backup answer')
        provider = GroqProvider(model='same-model', api_keys=['primary-test', 'backup-test'])
        self.assertEqual(provider.generate('question'), 'backup answer')
        self.assertEqual(primary.with_options.return_value.responses.create.call_args.kwargs['model'], 'same-model')
        self.assertEqual(backup.with_options.return_value.responses.create.call_args.kwargs['model'], 'same-model')
        provider.generate('next question')
        self.assertEqual(primary.with_options.return_value.responses.create.call_count, 1)
        self.assertEqual(backup.with_options.return_value.responses.create.call_count, 2)
        provider.close()
        primary.close.assert_called_once()
        backup.close.assert_called_once()

    @patch('core.llm.groq_provider.OpenAI')
    def test_non_rate_limit_does_not_rotate_and_all_limited_terminates(self, factory):
        primary, backup = MagicMock(), MagicMock()
        factory.side_effect = [primary, backup]
        primary.with_options.return_value.responses.create.side_effect = ValueError('bad request')
        provider = GroqProvider(api_keys=['primary-test', 'backup-test'])
        with self.assertRaises(ValueError):
            provider.generate('question')
        backup.with_options.assert_not_called()
        primary.with_options.return_value.responses.create.side_effect = limited()
        backup.with_options.return_value.responses.create.side_effect = limited()
        with self.assertRaises(RateLimitError):
            provider.generate('question')
        self.assertLessEqual(primary.with_options.return_value.responses.create.call_count, 2)
        self.assertEqual(backup.with_options.return_value.responses.create.call_count, 1)
