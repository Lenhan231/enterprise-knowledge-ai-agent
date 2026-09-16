# src/core/rag/rag_service.py
from core.chunking.semantic_chunker import SemanticDocumentChunker
from core.database.vector_repository import VectorRepository
from core.llm.groq_provider import GroqProvider

class RAGService:
    def __init__(self):
        self.chunker = SemanticDocumentChunker()
        self.repository = VectorRepository()
        self.llm = GroqProvider()

    def retrieve(self, question: str, limit: int = 5) -> dict:
        query_embedding = self.chunker.embeddings.embed_query(question)
        results = self.repository.similarity_search(query_embedding, limit)
        contexts = [result[1] for result in results]
        return {
            "question": question,
            "contexts": contexts
        }

    def generate_answer(self, question: str, limit: int = 5) -> str:
        retrieved = self.retrieve(question, limit)
        contexts = retrieved["contexts"]

        context = ". ".join(contexts)
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
    question = "What were Apple’s total net sales in 2024, and how did they compare with 2023?"
    print(rag.generate_answer(question, 5))
