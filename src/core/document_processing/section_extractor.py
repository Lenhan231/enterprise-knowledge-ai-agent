# src/core/document_processing/section_extractor.py

from core.models.document import ParentSection

class MarkdownSectionExtractor:
    def extract(
            self,
            page: list[dict],
            section_title,
            parent_id,
            document_id: str,
    ) -> list[ParentSection]:
        pass