# src/core/check.py

from core.chunking.semantic_chunker import SemanticDocumentChunker
from core.document_processing.pdf_to_markdown import PDFtoMarkdownConverted
from core.models.document import ChunkMetadata
from uuid import uuid4
from dataclasses import asdict

from pathlib import Path

if __name__ == "__main__":
    repo_root = Path(__file__).resolve().parents[2]
    input_dir = repo_root / "src" /"data" /"raws" /"pdf" / "2024_Apple.pdf"

    if not input_dir.exists():
        raise ValueError(
            "The file not exist."
        )
    file_type = input_dir.suffix.lower()

    if file_type == ".pdf":
        output_dir = repo_root / "src" / "data" / "processed" / "pdf2md"
        ingestor = PDFtoMarkdownConverted()
        markdown_path = ingestor.convert_pdf(input_dir, output_dir)
        splitter = SemanticDocumentChunker()
        chunks = splitter.chunk(markdown_path)

        document_id = str(uuid4())
        for chunk_index, chunk in enumerate(chunks):
            metadata = ChunkMetadata(
                source_document=input_dir.name,
                document_type=file_type.lstrip("."),
                page_number=None,
                chunk_index=chunk_index,
                section_title=None,
                parent_id=None,
                token_count=None,
                document_id=document_id,
            )

            chunk.metadata = asdict(metadata)

    for chunk in chunks[:3]:
        print(chunk.page_content[:10])
        print(chunk.metadata)
        print("-" * 50)
