# Repository ownership and navigation

Use this page to find the code and evaluation entry points for each workstream.
The technical guides remain the source of truth for behavior and configuration.

## Workstream boundaries

| Owner | Code to change | Main guide | Useful entry points |
| --- | --- | --- | --- |
| OCR and document processing (project owner) | `src/core/document_processing/`, `scripts/processing/` | [Document processing](document-processing.md) | `scripts/processing/evaluate_ocr.py`, `compare_ocr_reports.py`, `merge_ocr_reports.py`, `package_ocr_benchmark.py`, `evaluate_scan_document_processing.py`, `evaluate_document_extraction.py` |
| Chunking (project owner) | `src/core/chunking/` and shared chunking in format processors | [Chunking](chunking.md) | `scripts/chunking/evaluate_chunking.py`, `evaluate_chunking_retrieval.py` |
| Retrieval (collaborator) | `src/core/retrieval/methods/{dense,bm25,hybrid,parent}.py` for method ranking; `retrieval_service.py` for dispatch; `src/core/database/document_chunks_repository.py` for ACL-filtered data access; retrieval behavior in `src/core/rag/` | [Retrieval and RBAC](retrieval-rbac.md) | `scripts/retrieval/evaluate_retrieval.py`, `evaluate_embeddings.py`, `evaluate_rerankers.py`, `compare_embedding_reports.py`, `compare_reranker_reports.py` |
| Agents (collaborator) | `src/core/agents/` and agent-specific prompts in `src/core/prompts/` | [Agents and evaluation](agents-and-evaluation.md) | `scripts/agents/evaluate_agent_routes.py`, `evaluate_app_qa.py`, `evaluate_proposal_business_cases.py`, `evaluate_proposal_case_coverage.py`, `qa_human_review.py`, `score_qa_artifact.py` |

Keep the owner assignments in sync with the actual team; the collaborator labels
are responsibilities, not names. `src/core/rag/` composes retrieval with
generation, so retrieval changes that affect answer context or citations need
an integration check through RAG/API tests.

## Shared contracts

Coordinate before changing these interfaces because more than one workstream
depends on them:

- `src/core/database/` and `supabase/migrations/`: persisted document, chunk,
  table, vector and access-control shapes. Parser/chunker changes should retain
  source identity, page/layout/section metadata and role filtering expectations.
- `src/core/embeddings/`: retrieval depends on the stored vector model and
  dimensions; re-embedding is a data migration, not just a retrieval setting.
- `src/app/`: upload, processing, Q&A and dashboard API/UI integration. Keep
  business logic in its owning core module where practical.
- `src/core/models/`: shared request and persisted-data contracts.

The intended document path is parser/OCR output → chunks and structured tables
→ persisted document data → embeddings → role-filtered retrieval → RAG/agents.
Parser output and chunk metadata are independently inspectable before embedding;
do not make OCR experiments depend on changing retrieval behavior.

## Scripts and evaluation artifacts

`scripts/` groups runnable CLI entry points by workstream: `ingestion/`,
`processing/`, `chunking/`, `retrieval/`, `agents/`, `analytics/`, and
`operations/`. Use `uv run python scripts/<workstream>/<name>.py --help` before
running a data-writing command. The OCR Kaggle packager copies its evaluator to
the standalone bundle's `scripts/evaluate_ocr.py` path.

Existing evidence is intentionally retained under `artifacts/evaluation/`;
many reports are linked from the proposal and technical guides. Do not bulk-move
or delete historical runs as part of routine cleanup. Put new evidence in a
workstream subdirectory (`artifacts/evaluation/ocr/`, `chunking/`, `retrieval/`
or `agents/`) when the producing command supports an output path, and include
the input/case hash, configuration, model/version and run date in the report.
The existing top-level `artifacts/retrieval/` and `artifacts/review1/` remain
unchanged for compatibility.
