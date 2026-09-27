import os
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from core.llm.groq_provider import GroqProvider


class GroqProviderTest(unittest.TestCase):
    @patch("core.llm.groq_provider.OpenAI")
    def test_model_is_configurable_without_exposing_key(self, openai):
        with patch.dict(os.environ, {"GROQ_API_KEY": "test-secret", "GROQ_MODEL": "test/model"}):
            provider = GroqProvider()

        self.assertEqual(provider.model_name, "test/model")
        self.assertNotIn("test-secret", repr(provider))
        self.assertEqual(openai.call_args.kwargs["api_key"], "test-secret")

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


if __name__ == "__main__":
    unittest.main()
