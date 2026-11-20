# Citation and source coverage audit

## Confirmed catalog source

The academic entries in [README.md](README.md) are collected from:

- [Research report, references](../docs/research-report.md#references): six papers (RAG, DPR, BGE-M3, Qwen3 Embedding, PaddleOCR 3.0, RAGAS).
- [Text-to-SQL evaluation plan](../evaluation/agent_benchmarks/MODEL_AND_EVALUATION_PLAN.md#2024-text-to-sql-literature-and-candidate): two papers (CodeS, DTS-SQL).
- [Capstone implementation report](../docs/capstone-project-report.md#references): repeats the original RAG paper; its remaining entries are software documentation or the proposal, not additional academic papers.

## Correction required

- **P01 arXiv mismatch:** `docs/research-report.md` currently describes arXiv `2507.05595` as **“PP-OCRv5: A Practical Ultra-lightweight OCR System”**. The linked publication is actually **“PaddleOCR 3.0 Technical Report”**. The latter discusses PP-OCRv5 and PP-StructureV3 but is not the separate PP-OCRv5 title. Verify the bibliography and update it in the submitted report.
- **Dated architecture descriptions differ:** `docs/capstone-project-report.md` (October snapshot) describes a Tesseract-centric ingestion route, while `src/document_processing/README.md` and the top-level README describe the current Docling + VietOCR/RapidOCR route. Defense slides should describe the checked current commit, not a mixture of versions.
- **Bibliography not yet audited:** `docs/proposal.docx` is binary and could contain further literature references not listed in searchable Markdown. This folder does **not** claim complete coverage of that document. Check its bibliography manually and append any missing papers.
- **Potentially missing direct primary-source citations:** your document-processing stack uses Docling, VietOCR, RapidOCR and layout/table models; the eight cataloged papers do not constitute a complete literature review of those components. Add primary papers *after verifying titles and source links*. Do not invent citations.

## Excluded by design

Software manuals and libraries such as the Tesseract user manual, pgvector, LangGraph reference; project source documents, synthetic policies and financial report PDFs; and benchmark JSON references. These are valuable project sources, but they are not academic literature papers.

## Before thesis defense

- [ ] Check every paper's publisher title, year, authors and version.
- [ ] Audit the bibliography of `docs/proposal.docx`.
- [ ] Verify each citation actually supports the attached claim.
- [ ] Match paper methods to the current code and benchmark artifacts.
- [ ] Fix inconsistent citation titles and implementation version descriptions.
