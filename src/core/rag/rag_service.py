# src/core/rag/rag_service.py
from core.llm.groq_provider import GroqProvider
from core.models.retrieval import RetrievalRequest
from core.retrieval import RetrievalService

MAX_CONTEXT_CHARS = 24_000

class RAGService:
    def __init__(
        self,
        retrieval_service: RetrievalService | None = None,
        llm: GroqProvider | None = None,
    ):
        self.retrieval_service = retrieval_service or RetrievalService()
        self.llm = llm or GroqProvider()

    def generate_answer(self, question: str, limit: int = 5) -> str:
        retrieved = self.retrieval_service.retrieve(RetrievalRequest(query=question, top_k=limit))
        contexts = retrieved.results

        context = "\n\n".join(item.text for item in contexts)[:MAX_CONTEXT_CHARS]

        prompt = f"""You are an expert Enterprise Assistant. 
        Use the following context from corporate reports 
        to answer the user's question. 
        If the context does not contain relevant information, politely indicate that you do not have enough data.
        \n\nContext:\n{context}\n\nUser Question: {question}\n\nAnswer:
        """

        return self.llm.generate(prompt)

    def close(self) -> None:
        self.retrieval_service.close()

if __name__ == "__main__":
    rag = RAGService()
    question = "tell me about Apple's Share repurchase activity during the three months"
    print(rag.generate_answer(question, 5))
    print(rag.generate_answer("What were Apple's share repurchases during the three months ended September 28, 2024?", 3))
