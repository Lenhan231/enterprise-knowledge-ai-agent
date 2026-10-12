import os
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from core.llm.groq_provider import GroqProvider


class GroqProviderTest(unittest.TestCase):
    @patch("core.llm.groq_provider.OpenAI")
    def test_close_releases_http_client(self, openai):
        with patch.dict(os.environ, {"GROQ_API_KEY": "test-secret"}):
            provider = GroqProvider()
        provider.close()
        openai.return_value.close.assert_called_once()

    @patch("core.llm.groq_provider.OpenAI")
    def test_model_can_come_from_environment_or_explicit_benchmark_argument(self, openai):
        with patch.dict(os.environ, {"GROQ_API_KEY": "test-secret", "GROQ_MODEL": "env/model"}):
            environment_provider = GroqProvider()
            benchmark_provider = GroqProvider(model="benchmark/model")

        self.assertEqual(environment_provider.model_name, "env/model")
        self.assertEqual(benchmark_provider.model_name, "benchmark/model")
        self.assertNotIn("test-secret", repr(environment_provider))

    @patch("core.llm.groq_provider.OpenAI")
    def test_explicit_benchmark_key_overrides_default_key(self, openai):
        with patch.dict(os.environ, {"GROQ_API_KEY": "default-secret"}):
            GroqProvider(model="qwen/qwen3.8-27b", api_key="second-secret")
        self.assertEqual(openai.call_args.kwargs["api_key"], "second-secret")

    @patch("core.llm.groq_provider.OpenAI")
    def test_generate_uses_configured_model_and_records_usage(self, openai):
        openai.return_value.responses.create.return_value = MagicMock(
            output_text="grounded answer",
            usage=MagicMock(input_tokens=12, output_tokens=3, total_tokens=15),
        )
        with patch.dict(os.environ, {"GROQ_API_KEY": "test-secret"}):
            provider = GroqProvider(model="test/model")
            answer = provider.generate("prompt")

        call = openai.return_value.responses.create.call_args.kwargs
        self.assertEqual(answer, "grounded answer")
        self.assertEqual(call["model"], "test/model")
        self.assertEqual(call["temperature"], 0)
        self.assertEqual(provider.last_usage, {"input_tokens": 12, "output_tokens": 3, "total_tokens": 15})

    @patch("core.llm.groq_provider.OpenAI")
    def test_qwen_uses_supported_reasoning_mode(self, openai):
        openai.return_value.responses.create.return_value = MagicMock(output_text="answer", usage=None)
        with patch.dict(os.environ, {"GROQ_API_KEY": "test-secret"}):
            GroqProvider(model="qwen/qwen3.8-27b").generate("prompt")

        self.assertEqual(openai.return_value.responses.create.call_args.kwargs["reasoning"]["effort"], "none")


if __name__ == "__main__":
    unittest.main()
