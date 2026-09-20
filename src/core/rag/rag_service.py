# src/core/rag/rag_service.py
from core.llm.groq_provider import GroqProvider
from core.retrieval import RetrievalService
from core.prompts.Knowledge import ENTERPRISE_ASSISTANT_PROMPT

class RAGService:
    def __init__(
        self,
        retrieval_service: RetrievalService | None = None,
        llm: GroqProvider | None = None,
    ):
        self.retrieval_service = retrieval_service or RetrievalService()
        self.llm = llm or GroqProvider()

    def generate_answer(
        self, 
        question: str, 
        limit: int = 5
    ) -> RAGResult:
        retrieved = self.retrieval_service.retrieve(
            question,
            limit,
        )

        contexts = retrieved["contexts"]

        context = "\n\n".join(
            item["content"]
            for item in contexts
        )

        prompt = ENTERPRISE_ASSISTANT_PROMPT.format(
            context=context,
            question=question,
        )

        answer = self.llm.generate(prompt)

        return RAGResult(
            answer=answer,
            contexts=contexts,
        )

    # def generate_answer(self, question: str, limit: int = 5) -> str:
    #     retrieved = self.retrieval_service.retrieve(question, limit)
    #     contexts = retrieved["contexts"]

    #     context = "\n\n".join(item["content"] for item in contexts)
    #     print(context)

    #     prompt = ENTERPRISE_ASSISTANT_PROMPT.format(context=context, question=question)

    #     return self.llm.generate(prompt)

    def close(self) -> None:
        self.retrieval_service.close()

class RAGResult(BaseModel):
    answer:str
    context:list[dict]

if __name__ == "__main__":
    rag = RAGService()
    question = "tell me about Apple's Share repurchase activity during the three months"
    print(rag.generate_answer(question, 5))
    print(rag.generate_answer("What were Apple's share repurchases during the three months ended September 28, 2024?", 3))
