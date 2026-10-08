import os
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import httpx
from openai import APIConnectionError, APIStatusError, RateLimitError

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from core.llm.groq_provider import GroqProvider
from core.llm.huggingface_provider import HuggingFaceProvider
from core.llm.llm_interface import EmptyLLMResponseError
from core.llm import provider_fallback
from core.llm.provider_fallback import accumulate_token_usage, generate_with_provider_fallback, sum_token_usage


class ProviderFallbackTest(unittest.TestCase):
    def tearDown(self):
        provider_fallback._huggingface_fallback_disabled = False

    def test_connection_failure_uses_configured_huggingface_fallback(self):
        request = httpx.Request("POST", "https://groq.example")
        llm = MagicMock()
        llm.generate.side_effect = APIConnectionError(request=request)
        with patch.dict(os.environ, {
            "HUGGINGFACE_LLM_FALLBACK": "true", "HUGGINGFACE_API_KEY": "test-token",
        }), patch("core.llm.provider_fallback.HuggingFaceProvider") as fallback_factory:
            fallback_factory.return_value.generate.return_value = "  safe answer  "
            fallback_factory.return_value.last_usage = {
                "input_tokens": 20, "output_tokens": 4, "total_tokens": 24,
            }
            result = generate_with_provider_fallback(llm, "prompt")

        self.assertEqual(result, ("safe answer", "huggingface_inference"))
        self.assertEqual(llm.last_usage, fallback_factory.return_value.last_usage)
        fallback_factory.return_value.close.assert_called_once()

    def test_empty_primary_output_uses_configured_huggingface_fallback(self):
        llm = MagicMock()
        llm.generate.side_effect = EmptyLLMResponseError("provider returned empty output")
        with patch.dict(os.environ, {
            "HUGGINGFACE_LLM_FALLBACK": "true", "HUGGINGFACE_API_KEY": "test-token",
        }), patch("core.llm.provider_fallback.HuggingFaceProvider") as fallback_factory:
            fallback_factory.return_value.generate.return_value = "safe answer"
            result = generate_with_provider_fallback(llm, "prompt")

        self.assertEqual(result, ("safe answer", "huggingface_inference"))
        fallback_factory.return_value.close.assert_called_once()

    def test_huggingface_credit_error_disables_retries_until_process_restart(self):
        request = httpx.Request("POST", "https://groq.example")
        hf_request = httpx.Request("POST", "https://huggingface.example")
        llm = MagicMock()
        llm.generate.side_effect = APIConnectionError(request=request)
        provider_fallback._huggingface_fallback_disabled = False
        exhausted_credits = APIStatusError(
            "insufficient credits",
            response=httpx.Response(402, request=hf_request),
            body={},
        )
        with patch.dict(os.environ, {
            "HUGGINGFACE_LLM_FALLBACK": "true", "HUGGINGFACE_API_KEY": "test-token",
        }), patch("core.llm.provider_fallback.HuggingFaceProvider") as fallback_factory:
            fallback_factory.return_value.generate.side_effect = exhausted_credits
            with self.assertRaises(APIConnectionError):
                generate_with_provider_fallback(llm, "first prompt")
            fallback_factory.return_value.close.assert_called_once()
            self.assertTrue(provider_fallback._huggingface_fallback_disabled)

        with patch.dict(os.environ, {
            "HUGGINGFACE_LLM_FALLBACK": "true", "HUGGINGFACE_API_KEY": "test-token",
        }), patch("core.llm.provider_fallback.HuggingFaceProvider") as fallback_factory:
            with self.assertRaises(APIConnectionError):
                generate_with_provider_fallback(llm, "second prompt")
            fallback_factory.assert_not_called()

    def test_token_usage_accumulates_retries_and_stages(self):
        provider = MagicMock(last_usage={"input_tokens": 20, "output_tokens": 4, "total_tokens": 24})
        first = accumulate_token_usage(None, provider)
        provider.last_usage = {"input_tokens": 30, "output_tokens": 5, "total_tokens": 35}
        second = accumulate_token_usage(first, provider)

        self.assertEqual(second, {"input_tokens": 50, "output_tokens": 9, "total_tokens": 59})
        self.assertEqual(sum_token_usage(first, second), {
            "input_tokens": 70, "output_tokens": 13, "total_tokens": 83,
        })

    def test_non_transient_provider_error_does_not_use_fallback(self):
        llm = MagicMock()
        llm.generate.side_effect = APIStatusError(
            "unauthorized",
            response=httpx.Response(401, request=httpx.Request("POST", "https://groq.example")),
            body={},
        )
        with patch.dict(os.environ, {
            "HUGGINGFACE_LLM_FALLBACK": "true", "HUGGINGFACE_API_KEY": "test-token",
        }), patch("core.llm.provider_fallback.HuggingFaceProvider") as fallback_factory:
            with self.assertRaises(APIStatusError):
                generate_with_provider_fallback(llm, "prompt")

        fallback_factory.assert_not_called()

    def test_rate_limit_log_includes_request_and_token_quota_headers(self):
        request = httpx.Request("POST", "https://groq.example")
        response = httpx.Response(429, headers={
            "retry-after": "64",
            "x-ratelimit-limit-requests": "1000",
            "x-ratelimit-remaining-requests": "991",
            "x-ratelimit-reset-requests": "2m",
            "x-ratelimit-limit-tokens": "8000",
            "x-ratelimit-remaining-tokens": "8000",
            "x-ratelimit-reset-tokens": "1ms",
        }, request=request)
        llm = MagicMock()
        llm.generate.side_effect = RateLimitError("rate limited", response=response, body={})
        with patch.dict(os.environ, {"HUGGINGFACE_LLM_FALLBACK": "false"}):
            with self.assertLogs(provider_fallback.logger, level="WARNING") as captured:
                with self.assertRaises(RateLimitError):
                    generate_with_provider_fallback(llm, "prompt")

        message = captured.output[0]
        self.assertIn("retry_after=64", message)
        self.assertIn("remaining_requests=991", message)
        self.assertIn("remaining_tokens=8000", message)


class GroqProviderTest(unittest.TestCase):
    @patch("core.llm.groq_provider.OpenAI")
    def test_close_releases_http_client(self, openai):
        with patch.dict(os.environ, {"GROQ_API_KEY": "test-secret"}):
            provider = GroqProvider()

        provider.close()

        openai.return_value.close.assert_called_once()

    @patch("core.llm.groq_provider.OpenAI")
    def test_model_is_configurable_without_exposing_key(self, openai):
        with patch.dict(os.environ, {"GROQ_API_KEY": "test-secret", "GROQ_MODEL": "test/model"}):
            provider = GroqProvider()

        self.assertEqual(provider.model_name, "test/model")
        self.assertNotIn("test-secret", repr(provider))
        self.assertEqual(openai.call_args.kwargs["api_key"], "test-secret")
        self.assertEqual(openai.call_args.kwargs["max_retries"], 0)
        self.assertEqual(openai.call_args.kwargs["timeout"], 30.0)

    @patch("core.llm.groq_provider.OpenAI")
    def test_generate_uses_configured_model_and_fixed_settings(self, openai):
        response = MagicMock(output_text="grounded answer")
        openai.return_value.responses.create.return_value = response
        with patch.dict(os.environ, {"GROQ_API_KEY": "test-secret", "GROQ_MODEL": "test/model"}):
            provider = GroqProvider()
            answer = provider.generate("prompt")

        call = openai.return_value.responses.create.call_args.kwargs
        self.assertEqual(answer, "grounded answer")
        self.assertEqual(call["model"], "test/model")
        self.assertEqual(call["temperature"], 0)
        self.assertEqual(call["max_output_tokens"], 1000)
        self.assertEqual(call["reasoning"]["effort"], "low")

    @patch("core.llm.groq_provider.OpenAI")
    def test_empty_generation_is_classified_for_safe_fallback(self, openai):
        openai.return_value.responses.create.return_value = MagicMock(output_text=" ")
        with patch.dict(os.environ, {"GROQ_API_KEY": "test-secret"}):
            with self.assertRaises(EmptyLLMResponseError):
                GroqProvider().generate("prompt")

    @patch("core.llm.groq_provider.OpenAI")
    def test_generate_sends_separate_system_instructions_when_provided(self, openai):
        openai.return_value.responses.create.return_value = MagicMock(output_text="grounded answer")
        with patch.dict(os.environ, {"GROQ_API_KEY": "test-secret"}):
            provider = GroqProvider()
            provider.generate("verified evidence", instructions="You are a source-grounded analyst.")

        call = openai.return_value.responses.create.call_args.kwargs
        self.assertEqual(call["input"], "verified evidence")
        self.assertEqual(call["instructions"], "You are a source-grounded analyst.")

    @patch("core.llm.groq_provider.OpenAI")
    def test_qwen_uses_supported_reasoning_mode(self, openai):
        openai.return_value.responses.create.return_value = MagicMock(output_text="answer")
        with patch.dict(os.environ, {"GROQ_API_KEY": "test-secret", "GROQ_MODEL": "qwen/qwen3.8-27b"}):
            provider = GroqProvider()
            provider.generate("prompt")

        self.assertEqual(
            openai.return_value.responses.create.call_args.kwargs["reasoning"]["effort"],
            "none",
        )

    @patch("core.llm.groq_provider.OpenAI")
    def test_generation_records_token_usage(self, openai):
        openai.return_value.responses.create.return_value = MagicMock(
            output_text="answer",
            usage=MagicMock(input_tokens=12, output_tokens=3, total_tokens=15),
        )
        with patch.dict(os.environ, {"GROQ_API_KEY": "test-secret"}):
            provider = GroqProvider()
            provider.generate("prompt")

        self.assertEqual(
            provider.last_usage,
            {"input_tokens": 12, "output_tokens": 3, "total_tokens": 15},
        )

    @patch("core.llm.huggingface_provider.OpenAI")
    def test_huggingface_generation_records_openai_compatible_usage(self, openai):
        openai.return_value.chat.completions.create.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(content="answer"), finish_reason="stop")],
            usage=MagicMock(prompt_tokens=7, completion_tokens=4, total_tokens=11),
        )
        with patch.dict(os.environ, {"HUGGINGFACE_API_KEY": "test-secret"}):
            provider = HuggingFaceProvider()
            self.assertEqual(provider.generate("prompt"), "answer")

        self.assertEqual(
            provider.last_usage,
            {"input_tokens": 7, "output_tokens": 4, "total_tokens": 11},
        )

    @patch("core.llm.huggingface_provider.OpenAI")
    def test_empty_huggingface_generation_is_classified(self, openai):
        openai.return_value.chat.completions.create.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(content=" "), finish_reason="stop")],
        )
        with patch.dict(os.environ, {"HUGGINGFACE_API_KEY": "test-secret"}):
            with self.assertRaises(EmptyLLMResponseError):
                HuggingFaceProvider().generate("prompt")

    @patch("core.llm.groq_provider.OpenAI")
    def test_caption_image_sends_bounded_base64_input_to_configured_vision_model(self, openai):
        openai.return_value.responses.create.return_value = MagicMock(
            output_text="A bar chart shows annual revenue."
        )
        with patch.dict(os.environ, {
            "GROQ_API_KEY": "test-secret",
            "GROQ_VISION_MODEL": "test/vision-model",
        }):
            provider = GroqProvider()
            caption = provider.caption_image(b"png bytes", "image/png")

        call = openai.return_value.responses.create.call_args.kwargs
        image_url = call["input"][0]["content"][1]["image_url"]
        self.assertEqual(caption, "A bar chart shows annual revenue.")
        self.assertEqual(call["model"], "test/vision-model")
        self.assertEqual(image_url, "data:image/png;base64,cG5nIGJ5dGVz")
        self.assertEqual(call["max_output_tokens"], 160)

    @patch("core.llm.groq_provider.OpenAI")
    def test_caption_image_rejects_payloads_over_provider_request_budget(self, openai):
        with patch.dict(os.environ, {"GROQ_API_KEY": "test-secret"}):
            provider = GroqProvider()
            with self.assertRaisesRegex(ValueError, "too large"):
                provider.caption_image(b"x" * (14 * 1024 * 1024 + 1), "image/png")

        openai.return_value.responses.create.assert_not_called()


class HuggingFaceProviderTest(unittest.TestCase):
    @patch("core.llm.huggingface_provider.OpenAI")
    def test_chat_completion_keeps_instructions_as_system_message(self, openai):
        openai.return_value.chat.completions.create.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(content="cited action"))]
        )
        with patch.dict(os.environ, {
            "HUGGINGFACE_API_KEY": "test-token",
            "HUGGINGFACE_LLM_MODEL": "openai/gpt-oss-20b:cheapest",
        }):
            provider = HuggingFaceProvider()
            answer = provider.generate("verified KPI evidence", instructions="System instructions")
            provider.close()

        call = openai.return_value.chat.completions.create.call_args.kwargs
        self.assertEqual(answer, "cited action")
        self.assertEqual(call["model"], "openai/gpt-oss-20b:cheapest")
        self.assertEqual(call["messages"], [
            {"role": "system", "content": "System instructions"},
            {"role": "user", "content": "verified KPI evidence"},
        ])
        self.assertEqual(call["max_completion_tokens"], 1600)
        self.assertEqual(call["reasoning_effort"], "low")
        self.assertEqual(openai.call_args.kwargs["base_url"], "https://router.huggingface.co/v1")
        self.assertNotIn("test-token", repr(provider))

    def test_api_key_is_required(self):
        with patch.dict(os.environ, {}, clear=True), self.assertRaisesRegex(ValueError, "HUGGINGFACE_API_KEY"):
            HuggingFaceProvider()


if __name__ == "__main__":
    unittest.main()
