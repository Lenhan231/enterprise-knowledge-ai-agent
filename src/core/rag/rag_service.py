<<<<<<< HEAD
# src/core/rag/rag_service.py
from core.ingest.semantic_chunker import SemanticDocumentChunker
from core.database.vector_repository import VectorRepository

=======
>>>>>>> eca62225cf753bf2931f5ba76f3b7953f9265faf
from core.llm.groq_provider import GroqProvider
from core.retrieval import RetrievalService

class RAGService:
<<<<<<< HEAD
    def __init__(self):
        self.chunker = SemanticDocumentChunker()
        self.repository = VectorRepository()
        self.llm = GroqProvider()

    def retrieve(self, question: str, limit: int = 5) -> dict:
        query_embedding = self.chunker.embeddings.embed_query(question)
        contexts = self.repository.similarity_search(query_embedding, limit)
        return {
            "question": question,
            "contexts": contexts
        }
=======
    def __init__(
        self,
        retrieval_service: RetrievalService | None = None,
        llm: GroqProvider | None = None,
    ):
        self.retrieval_service = retrieval_service or RetrievalService()
        self.llm = llm or GroqProvider()
>>>>>>> eca62225cf753bf2931f5ba76f3b7953f9265faf

    def generate_answer(self, question: str, limit: int = 5) -> str:
        retrieved = self.retrieval_service.retrieve(question, limit)
        contexts = retrieved["contexts"]

<<<<<<< HEAD
        for index, item in enumerate(contexts):
            print(f"RESULT {index}: type={type(item)} value={item!r}")

        context = "\n\n".join(item[1] if isinstance(item, tuple) else str(item) for item in contexts[:3])
        context = context[:24000]

=======
        context = "\n\n".join(item["content"] for item in contexts)
>>>>>>> eca62225cf753bf2931f5ba76f3b7953f9265faf
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
    question = "tell me about Apple's Share repurchase activity during the three months"
    print(rag.generate_answer(question, 5))
    print(rag.generate_answer("What were Apple's share repurchases during the three months ended September 28, 2024?", 3))
