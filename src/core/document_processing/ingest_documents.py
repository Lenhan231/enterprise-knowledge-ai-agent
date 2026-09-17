# src/core/document_processing/ingest_documents.py

from core.chunking.semantic_chunker import SemanticDocumentChunker
from core.document_processing.pdf_to_markdown import PDFtoMarkdownConverted
from core.models.document import ChunkMetadata
from uuid import uuid4
from dataclasses import asdict
from core.tokenization.token_counter import TokenCounter

from pathlib import Path

class Ingestion:

    def ingestion(self, input_path: Path, output_dir: Path):

        if not input_path.exists():
            raise FileNotFoundError(f"File does not exist: {input_path}")

        file_type = input_path.suffix.lower()

        if file_type == ".pdf":
            converter = PDFtoMarkdownConverted()

        markdown_path = converter.convert_pdf(
            input_path,
            output_dir
        )

        splitter = SemanticDocumentChunker()
        chunks = splitter.chunk(markdown_path)
        
        token_counter = TokenCounter(
            "sentence-transformers/all-MiniLM-L6-v2"
        )
        
        document_id = str(uuid4())

        for chunk_index, chunk in enumerate(chunks):

            metadata = ChunkMetadata(
                source_document=input_path.name,
                document_type=file_type.lstrip("."),
                page_number=None,
                chunk_index=chunk_index,
                section_title=None,
                parent_id=None,
                token_count=token_counter.count(chunk.page_content),
                document_id=document_id,
            )

            chunk.metadata = asdict(metadata)
        if file_type != ".pdf":
            raise NotImplementedError(
                f"Unsupported document type: {file_type}"
            )

        return chunks

if __name__ == "__main__":
    repo_root = Path(__file__).resolve().parents[3]
    input_path = repo_root / "src" /"data" /"raws" /"pdf" / "2024_Apple.pdf"
    output_dir = repo_root / "src" / "data" / "processed" / "pdf2md"

    ingestor = Ingestion()
    chunks = ingestor.ingestion(input_path, output_dir)        

    for chunk in chunks[:3]:
        print(chunk.page_content[:10])
        print(chunk.metadata)
        print("-" * 50)
