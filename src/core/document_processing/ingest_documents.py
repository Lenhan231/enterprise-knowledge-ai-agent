# src/core/document_processing/ingest_documents.py

from core.chunking.semantic_chunker import SemanticDocumentChunker
from core.document_processing.pdf_to_markdown import PDFtoMarkdownConverted
from core.models.document import ChunkMetadata
from uuid import uuid4
from dataclasses import asdict
from core.utils.token_counter import TokenCounter

from pathlib import Path

class Ingestion:
    def __init__(self):
        self.token_counter = TokenCounter(
                    "sentence-transformers/all-MiniLM-L6-v2"
                )
        self.splitter = SemanticDocumentChunker()
        self.PDFconverter = PDFtoMarkdownConverted()

        
    def ingestion(self, input_path: Path, output_dir: Path):

        if not input_path.exists():
            raise FileNotFoundError(f"File does not exist: {input_path}")

        file_type = input_path.suffix.lower()

        if file_type == ".pdf":
            markdown_content = self.PDFconverter.convert_pdf(
                        input_path,
                        output_dir
                    )
        document_id = str(uuid4())
        chunk_index = 0
        all_chunks = []

        for page in markdown_content:
            page_number = page["metadata"]["page_number"]
            page_text = page["text"]

            page_chunks = self.splitter.chunk_text(page_text)

            for chunk in page_chunks:
                metadata = ChunkMetadata(
                    source_document=input_path.name,
                    document_type=file_type.lstrip("."),
                    page_number=page_number,
                    chunk_index=chunk_index,
                    section_title=None,
                    parent_id=None,
                    token_count=self.token_counter.count(chunk.page_content),
                    document_id=document_id,
                )

                chunk.metadata = asdict(metadata)

                all_chunks.append(chunk)

                chunk_index += 1
                

        if file_type != ".pdf":
            raise NotImplementedError(
                f"Unsupported document type: {file_type}"
            )

        return all_chunks

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
