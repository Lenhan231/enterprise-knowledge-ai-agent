# src/core/chunking/semantic_chunker.py

from pathlib import Path

from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings
from langchain_experimental.text_splitter import SemanticChunker
from core.embeddings import EmbeddingService

class SemanticDocumentChunker:
    def __init__(self, embeddings: Embeddings | None = None):
        self.embeddings = embeddings or EmbeddingService()

    def read_markdown(self, markdown_file: str) -> str:
        """
        Args:
            markdown_file: path
        Returns:
            markdown content
        """
        return Path(markdown_file).read_text(encoding="utf-8")

    def chunk_text(self, page_text: str):
        splitter = SemanticChunker(
                    embeddings=self.embeddings,
                    breakpoint_threshold_type="percentile"
                    )
        
        return splitter.create_documents([page_text])
        

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
