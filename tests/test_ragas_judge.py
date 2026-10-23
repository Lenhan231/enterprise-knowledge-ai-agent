import unittest
from unittest.mock import patch

from evaluation.ragas_judge import DEFAULT_RAGAS_MODEL, build_ragas_metrics


class RagasJudgeTest(unittest.TestCase):
    def test_requires_dedicated_groq_key(self):
        with patch.dict("os.environ", {"GROQ_API_KEY_RAGAS": ""}, clear=False):
            with self.assertRaisesRegex(RuntimeError, "GROQ_API_KEY_RAGAS"):
                build_ragas_metrics()

    def test_uses_langchain_groq_judge_for_ragas_metrics(self):
        with patch("evaluation.ragas_judge.AsyncOpenAI") as client, \
             patch("evaluation.ragas_judge.llm_factory") as llm_factory, \
             patch("evaluation.ragas_judge.embedding_factory") as embedding_factory, \
             patch("evaluation.ragas_judge.Faithfulness") as faithfulness, \
             patch("evaluation.ragas_judge.AnswerRelevancy") as relevancy, \
             patch("evaluation.ragas_judge.ContextPrecision") as precision, \
             patch.dict("os.environ", {
                 "GROQ_API_KEY_RAGAS": "judge-secret", "RAGAS_JUDGE_MODEL": "openai/gpt-oss-20b",
                 "EMBEDDING_MODEL": "intfloat/multilingual-e5-base",
             }, clear=False):
            metrics = build_ragas_metrics()

        client.assert_called_once_with(
            api_key="judge-secret", base_url="https://api.groq.com/openai/v1", timeout=60,
        )
        llm_factory.assert_called_once_with("openai/gpt-oss-20b", client=client.return_value)
        embedding_factory.assert_called_once_with(
            "huggingface", model="intfloat/multilingual-e5-base",
        )
        faithfulness.assert_called_once_with(llm=llm_factory.return_value)
        relevancy.assert_called_once_with(
            llm=llm_factory.return_value, embeddings=embedding_factory.return_value,
        )
        precision.assert_called_once_with(llm=llm_factory.return_value)
        self.assertEqual(set(metrics), {"faithfulness", "answer_relevancy", "context_precision"})


if __name__ == "__main__":
    unittest.main()
