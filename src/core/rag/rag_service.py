# src/core/rag/rag_service.py
from core.ingest.semantic_chunker import SemanticDocumentChunker
from core.database.vector_repository import VectorRepository
from core.llm.groq_provider import GroqProvider

class RAGService:
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

    def generate_answer(self, question: str, limit: int = 5) -> str:
        retrieved = self.retrieve(question, limit)
        contexts = retrieved["contexts"]

        for index, item in enumerate(contexts):
            print(f"RESULT {index}: type={type(item)} value={item!r}")

        context = "\n\n".join(item[1] if isinstance(item, tuple) else str(item) for item in contexts[:3])
        context = context[:24000]

        print(context)

        prompt = f"""You are an expert Enterprise Assistant. 
        Use the following context from corporate reports 
        to answer the user's question. 
        If the context does not contain relevant information, politely indicate that you do not have enough data.
        \n\nContext:\n{context}\n\nUser Question: {question}\n\nAnswer:
        """

        return self.llm.generate(prompt)

if __name__ == "__main__":
    rag = RAGService()
    question = "tell me about Apple's Share repurchase activity during the three months"
    print(rag.generate_answer(question, 5))
    print(rag.generate_answer("What were Apple's share repurchases during the three months ended September 28, 2024?", 3))
