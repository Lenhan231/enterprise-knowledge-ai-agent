from pathlib import Path

from langchain_core.documents import Document
from langchain_experimental.text_splitter import SemanticChunker
from langchain_huggingface import HuggingFaceEmbeddings

from dotenv import load_dotenv
load_dotenv()

class SemanticDocumentChunker:
    def __init__(self):
        self.embeddings = HuggingFaceEmbeddings(
            model_name="sentence-transformers/all-MiniLM-L6-v2"
        )

    def read_markdown(self, markdown_file: str) -> str:
        """
        Args:
            markdown_file: path
        Returns:
            markdown content
        """
        return Path(markdown_file).read_text(encoding="utf-8")

    def chunk(self,
            markdown_file: str
            ) -> list[Document]:
        """
        Generate semantic chunks from markdown

        Args:
            markdown_file: path
            embeddings: embedding model use the hugging face for local implement
        
        Returns:
            List of semantic chunks.
        """
        markdown_content = self.read_markdown(markdown_file)

        splitter = SemanticChunker(
            embeddings=self.embeddings,
            breakpoint_threshold_type="percentile"
            )

        return splitter.create_documents([markdown_content])

if __name__ == "__main__":
    repo_root = Path(__file__).resolve().parents[3]
    test_path = repo_root / "src" /"data"/"processed" / "pdf2md" / "2024_Apple.md"

    chunker = SemanticDocumentChunker()
    chunks = chunker.chunk(test_path)
    for i, chunk in enumerate(chunks[:4]):
        print(f"\n===== CHUNK {i + 1} =====")
        print(f"Characters: {len(chunk.page_content)}")
        print(chunk.page_content)
        print("=" * 80)
        vector = chunker.embeddings.embed_query(chunk.page_content)
        print(len(vector))
