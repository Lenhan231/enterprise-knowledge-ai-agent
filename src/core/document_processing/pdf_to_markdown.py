from pathlib import Path
import pymupdf4llm


class PDFtoMarkdownConverted:
    def convert_pdf(self, pdf_path: str | Path, output_dir: str | Path) -> str:
        """
        convert a pdf to markdown 
        Args:
            pdf_path: source pdf path.
            output_dir: Ourput markdown directory.

        Returns:
            Generated markdown file path.
        """
        pdf_file = Path(pdf_path)
        if not pdf_file.exists():
            raise FileExistsError(f"PDF file not found: {pdf_file}")

        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        markdown_content = pymupdf4llm.to_markdown(str(pdf_file), show_progress=True)
        markdown_file = output_path / f"{pdf_file.stem}.md"

        markdown_file.write_text(
            markdown_content,
            encoding="utf-8"
        )

        return str(markdown_file)

    def convert_directory(self, dir_path: str | Path, output_dir: str | Path) -> list[str]:
        """
        Convert full pdf file from the directory to the markdown format

        Args:
            dir_path: str
            output_path: str
        
        Returns:
            Generated markdown file directory. 
        """
        source_dir = Path(dir_path)
        if not source_dir.exists():
            raise FileExistsError(f"Directory not found: {dir_path}")

        
        output_dir_path = Path(output_dir)
        generated_files: list[str] = []


        for pdf_file in source_dir.glob("*.pdf"):
            generated_files.append(self.convert_pdf(pdf_file, output_dir_path))

        return generated_files


if __name__ == "__main__":
    repo_root = Path(__file__).resolve().parents[3]

    input_dir = repo_root / "src" / "data" / "raws" / "pdf" / "2024_Apple.pdf"
    output_dir = repo_root / "src" / "data" / "processed" / "pdf2md"

    ingestor = PDFtoMarkdownConverted()
    
    print(ingestor.convert_pdf(input_dir, output_dir))


