import json
import os
import unittest
from unittest.mock import patch

from core.llm.Cloudflare_provider import CloudflareProvider


class CloudflareDashboardBudgetTest(unittest.TestCase):
    @patch('core.llm.Cloudflare_provider.urlopen')
    def test_reasoning_model_leaves_room_for_final_json(self, urlopen):
        urlopen.return_value.__enter__.return_value.read.return_value = json.dumps({'choices': [{'message': {'content': '{}'}}]}).encode()
        with patch.dict(os.environ, {'CLOUDFLARE_ACCOUNT_ID': 'test', 'CLOUDFLARE_API_TOKEN': 'test'}):
            provider = CloudflareProvider(model='@cf/openai/gpt-oss-20b')
            self.assertEqual('{}', provider.generate('Return JSON'))
        payload = json.loads(urlopen.call_args.args[0].data)
        self.assertEqual('low', payload['reasoning_effort'])
        self.assertEqual(2048, payload['max_tokens'])

    def test_explicit_token_budget_and_nonreasoning_defaults_are_preserved(self):
        with patch.dict(os.environ, {'CLOUDFLARE_ACCOUNT_ID': 'test', 'CLOUDFLARE_API_TOKEN': 'test'}):
            self.assertEqual(1000, CloudflareProvider(model='@cf/meta/llama-3.1-8b-instruct').max_tokens)
            self.assertEqual(500, CloudflareProvider(model='@cf/openai/gpt-oss-20b', max_tokens=500).max_tokens)
