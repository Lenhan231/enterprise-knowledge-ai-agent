import unittest
from unittest.mock import patch

from evaluation.ragas_judge import DEFAULT_CODEX_MODEL, build_ragas_metrics


class RagasJudgeTest(unittest.TestCase):
    def test_builds_codex_luna_judge_and_ragas_metrics(self):
        with patch("evaluation.ragas_judge.CodexCLIJudge") as judge_class, \
             patch("evaluation.ragas_judge.embedding_factory") as embedding_factory, \
             patch("evaluation.ragas_judge.Faithfulness") as faithfulness, \
             patch("evaluation.ragas_judge.AnswerRelevancy") as relevancy, \
             patch("evaluation.ragas_judge.ContextPrecision") as precision:
            metrics = build_ragas_metrics(environ={"EMBEDDING_MODEL": "test-embedding"})

        judge_class.assert_called_once_with(model=DEFAULT_CODEX_MODEL, reasoning_effort="medium")
        embedding_factory.assert_called_once_with("huggingface", model="test-embedding")
        faithfulness.assert_called_once_with(llm=judge_class.return_value)
        relevancy.assert_called_once_with(
            llm=judge_class.return_value, embeddings=embedding_factory.return_value,
        )
        precision.assert_called_once_with(llm=judge_class.return_value)
        self.assertEqual(set(metrics), {"faithfulness", "answer_relevancy", "context_precision"})


if __name__ == "__main__":
    unittest.main()
