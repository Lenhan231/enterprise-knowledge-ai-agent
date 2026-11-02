import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import httpx
from openai import RateLimitError

from core.llm.groq_provider import GroqProvider


def limited(retry_after="60"):
    response = httpx.Response(429, request=httpx.Request("POST", "https://example.invalid/responses"),
                              headers={"retry-after": retry_after})
    return RateLimitError("test quota", response=response, body={"message": "test quota"})


def client():
    result = Mock()
    result.with_options.return_value = result
    result.responses.create.return_value = SimpleNamespace(output_text="OK", usage=None)
    return result


class GroqKeyFailoverTest(unittest.TestCase):
    def test_key_one_429_uses_key_two_and_keeps_it_for_next_request(self):
        first, second = client(), client()
        first.responses.create.side_effect = limited("3600")
        with patch("core.llm.groq_provider.OpenAI", side_effect=[first, second]), \
             patch("core.llm.groq_provider.time.monotonic", return_value=100):
            provider = GroqProvider(api_keys=["fake-one", "fake-two"])
            try:
                self.assertEqual(provider.generate("audit", max_output_tokens=3072), "OK")
                self.assertEqual(provider.generate("next audit", max_output_tokens=3072), "OK")
                self.assertEqual(first.responses.create.call_count, 1)
                self.assertEqual(second.responses.create.call_count, 2)
                self.assertEqual(provider._active, 1)
                self.assertEqual(second.responses.create.call_args.kwargs["max_output_tokens"], 3072)
            finally:
                provider.close()

    def test_both_limited_then_calls_during_cooldown_make_no_http_attempt(self):
        first, second = client(), client()
        first_error, second_error = limited("3600"), limited("60")
        first.responses.create.side_effect = first_error
        second.responses.create.side_effect = second_error
        with patch("core.llm.groq_provider.OpenAI", side_effect=[first, second]), \
             patch("core.llm.groq_provider.time.monotonic", return_value=100):
            provider = GroqProvider(api_keys=["fake-one", "fake-two"])
            try:
                for _ in range(2):
                    with self.assertRaises(RateLimitError) as raised:
                        provider.generate("audit")
                    self.assertIs(raised.exception, second_error)
                first.responses.create.assert_called_once()
                second.responses.create.assert_called_once()
            finally:
                provider.close()

    def test_key_two_is_retried_after_its_cooldown_even_when_key_one_still_cooling(self):
        first, second = client(), client()
        first.responses.create.side_effect = limited("3600")
        second.responses.create.side_effect = [limited("60"), SimpleNamespace(output_text="Recovered", usage=None)]
        with patch("core.llm.groq_provider.OpenAI", side_effect=[first, second]), \
             patch("core.llm.groq_provider.time.monotonic", return_value=100) as clock:
            provider = GroqProvider(api_keys=["fake-one", "fake-two"])
            try:
                with self.assertRaises(RateLimitError):
                    provider.generate("audit")
                clock.return_value = 161
                self.assertEqual(provider.generate("audit again"), "Recovered")
                first.responses.create.assert_called_once()
                self.assertEqual(second.responses.create.call_count, 2)
            finally:
                provider.close()

    def test_empty_key_two_and_duplicate_keys_do_not_create_another_client(self):
        for keys in (["fake-one", ""], ["fake-one", "fake-one"]):
            with self.subTest(keys=keys), patch("core.llm.groq_provider.OpenAI", return_value=client()) as factory:
                provider = GroqProvider(api_keys=keys)
                try:
                    self.assertEqual(len(provider._clients), 1)
                    factory.assert_called_once()
                finally:
                    provider.close()
