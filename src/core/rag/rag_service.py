from core.llm.groq_provider import GroqProvider
from core.retrieval import RetrievalService

class RAGService:
    def __init__(
        self,
        retrieval_service: RetrievalService | None = None,
        llm: GroqProvider | None = None,
    ):
        self.retrieval_service = retrieval_service or RetrievalService()
        self.llm = llm or GroqProvider()

    def generate_answer(self, question: str, limit: int = 5) -> str:
        retrieved = self.retrieval_service.retrieve(question, limit)
        contexts = retrieved["contexts"]

        context = "\n\n".join(item["content"] for item in contexts)
        print(context)

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
    question = "What were Apple’s total net sales in 2024, and how did they compare with 2023?"
    print(rag.generate_answer(question, 5))
