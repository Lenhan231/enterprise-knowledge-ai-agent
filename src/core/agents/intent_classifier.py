import json

from core.llm.groq_provider import GroqProvider
from core.models.intent import IntentResult
from core.prompts.intent import INTENT_CLASSIFIER_PROMPT


class IntentClassifier:
    def __init__(self, llm: GroqProvider | None = None):
        self.llm = llm or GroqProvider()

    def classify(self, question: str) -> IntentResult:
        prompt = INTENT_CLASSIFIER_PROMPT.format(
            question=question,
        )

        raw = self.llm.generate(prompt)

        return IntentResult.model_validate(
            json.loads(raw)
        )

    def close(self) -> None:
        if hasattr(self.llm, "close"):
            self.llm.close()

if __name__ == "__main__":
    intent_classifier = IntentClassifier()
    question = "Show me revenue trend for the last 5 quarters"
    print(intent_classifier.classify(question))
    intent_classifier.close()
