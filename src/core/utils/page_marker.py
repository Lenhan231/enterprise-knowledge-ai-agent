# src/core/utils/page_marker.py
import re
from langchain_community.document_loaders import PyPDFLoader
from langchain_core.documents import Document
from pathlib import Path

class PageMarker:
    def __init__(self):
        pass

    def mark(self, pdf_path: str | Path):

        # 1. Load the paginated document
        loader = PyPDFLoader(pdf_path)
        pages = loader.load()

        return pages


if __name__ == "__main__":
        repo_root = Path(__file__).resolve().parents[3]
    
        input_dir = repo_root / "src" / "data" / "raws" / "pdf" / "2024_Apple.pdf"

        marker = PageMarker()

        marker.mark(input_dir)