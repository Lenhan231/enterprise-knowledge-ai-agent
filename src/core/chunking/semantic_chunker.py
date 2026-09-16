# src/core/chunking/semantic_chunker.py

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
    from core.models.document import ChunkMetadata
    repo_root = Path(__file__).resolve().parents[3]
    test_path = repo_root / "src" /"data"/"processed" / "pdf2md" / "2024_Apple.md"

    splitter = SemanticDocumentChunker()
    chunks = splitter.chunk(test_path)
    print(chunks[:1])

    # for chunk_index, chunk in enumerate(chunks[:3]):
    #     chunk.metadata = ChunkMetadata{
    #         "document_id": document_id,
    #         "source_document": ...,
    #         "document_type": ...,
    #         "page_number": ...,
    #         "chunk_index": chunk_index,
    #         "section_title": ...,
    #         "parent_id": ...,
    #         "token_count": ...,
    #     }
