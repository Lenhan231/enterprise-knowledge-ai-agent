# Thesis papers — Enterprise Knowledge AI Agent

This directory collects **academic research papers explicitly referenced in the repository's searchable Markdown research/benchmark documents**. It is organized for thesis-defense preparation, not as a claim that every technique was implemented or independently validated.

**Start here:** [Reading progress](PROGRESS.md) · [Research-to-defense map](DEFENSE_MAP.md) · [Citation and coverage audit](CITATION_AUDIT.md) · [Reusable notes template](notes/TEMPLATE.md)

## Papers (8 identified in Markdown sources)

| ID | Paper | Area | Priority | Read/defense notes |
| --- | --- | --- | --- | --- |
| P01 | [PaddleOCR 3.0 Technical Report](https://arxiv.org/abs/2507.05595) (2025) | OCR / layout | Deep | [Notes](notes/p01-paddleocr-3-technical-report.md) |
| P02 | [Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks](https://arxiv.org/abs/2005.11401) (2020) | RAG | Deep | [Notes](notes/p02-rag-lewis-2020.md) |
| P03 | [Dense Passage Retrieval for Open-Domain Question Answering](https://arxiv.org/abs/2004.04906) (2020) | Retrieval | Deep | [Notes](notes/p03-dense-passage-retrieval.md) |
| P04 | [BGE M3-Embedding: Multi-Lingual, Multi-Functionality, Multi-Granularity Text Embeddings Through Self-Knowledge Distillation](https://arxiv.org/abs/2402.03216) (2024) | Embedding / multilingual | Review | [Notes](notes/p04-bge-m3.md) |
| P05 | [Qwen3 Embedding: Advancing Text Embedding and Reranking Through Foundation Models](https://arxiv.org/abs/2506.05176) (2025) | Embedding / reranking | Review | [Notes](notes/p05-qwen3-embedding.md) |
| P06 | [RAGAS: Automated Evaluation of Retrieval Augmented Generation](https://arxiv.org/abs/2309.15217) (2023) | RAG evaluation | Deep | [Notes](notes/p06-ragas.md) |
| P07 | [CodeS: Towards Building Open-source Language Models for Text-to-SQL](https://arxiv.org/abs/2402.16347) (2024) | Text-to-SQL | Review | [Notes](notes/p07-codes-text-to-sql.md) |
| P08 | [DTS-SQL: Decomposed Text-to-SQL with Small Large Language Models](https://aclanthology.org/2024.findings-emnlp.481/) (2024) | Text-to-SQL | Review | [Notes](notes/p08-dts-sql.md) |

## Workflow

1. Open [PROGRESS.md](PROGRESS.md) and work from **Deep** priority to **Review** priority.
2. Open the original publisher/arXiv page and read the abstract, method diagram, experiments, and limitations first. Read methods deeply if relevant to your implementation.
3. Fill in the corresponding note file using your **own words** and cite figures, pages, and experiments you check.
4. Link any claims about our system to the **current code and reproducible evaluation artifact** rather than citing the original paper as proof.
5. Tick the progress checklist after each stage. Finish by answering the defense question aloud without notes.

The full-text PDFs are not copied into this repository; links lead to the official research pages. Original paper PDFs can be opened from those pages. Reference manuals, project documentation, and benchmark data are not mislabeled as academic papers.

## Scope

Source search included Markdown references in `docs/research-report.md`, `docs/capstone-project-report.md`, and `evaluation/agent_benchmarks/MODEL_AND_EVALUATION_PLAN.md`, together with repository code-search for arXiv, DOI, ACL Anthology, and related citation links. **The binary `docs/proposal.docx` bibliography has not been audited**, so this catalog may need additions; see [CITATION_AUDIT.md](CITATION_AUDIT.md). Paper titles and links may require rechecking before final submission.

**Important:** A paper's reported results are not our project's results. The repository has dated implementation documents that can differ; verify current code and tests before making a defense claim.
