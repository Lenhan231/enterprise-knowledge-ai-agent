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
        current_title = None
        current_text = []
        start_page = None
        end_page = None

        for line in page:
            if line startwith("#"):
                if section_title == "None":
                    metadata = ParentSection
