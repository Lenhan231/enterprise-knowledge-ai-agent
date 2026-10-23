# Repository ownership and navigation

Use this page to find the code and evaluation entry points for each workstream.
The technical guides remain the source of truth for behavior and configuration.

## Workstream boundaries

| Owner | Code to change | Main guide | Useful entry points |
| --- | --- | --- | --- |
| OCR and document processing (project owner) | `src/document_processing/`, `tools/processing/` | [Document processing](../../src/document_processing/docs/document-processing.md) | `tools/processing/evaluate_ocr.py`, `compare_ocr_reports.py`, `merge_ocr_reports.py`, `package_ocr_benchmark.py`, `evaluate_scan_document_processing.py`, `evaluate_document_extraction.py` |
| Chunking (separate workstream) | `src/core/chunking/` | [Chunking](../../src/core/chunking/README.md) | `tools/chunking/evaluate_chunking.py` |
| Retrieval (collaborator) | `src/core/retrieval/methods/{dense,bm25,hybrid,parent}.py` for method ranking; `retrieval_service.py` for dispatch; `src/core/database/document_chunks_repository.py` for ACL-filtered data access; retrieval behavior in `src/core/rag/` | [Retrieval and RBAC](retrieval-rbac.md) | `tools/retrieval/evaluate_retrieval.py`, `evaluate_embeddings.py`, `evaluate_rerankers.py`, `compare_embedding_reports.py`, `compare_reranker_reports.py` |
| Agents (collaborator) | `src/core/agents/` and agent-specific prompts in `src/core/prompts/` | [Agents and evaluation](agents-and-evaluation.md) | `tools/agents/evaluate_commerce_decision_support.py`, `qa_human_review.py`, `score_qa_artifact.py` |

Keep the owner assignments in sync with the actual team; the collaborator labels
are responsibilities, not names. `src/core/rag/` composes retrieval with
generation, so retrieval changes that affect answer context or citations need
an integration check through RAG/API tests.

## Shared contracts

Coordinate before changing these interfaces because more than one workstream
depends on them:

- `src/core/database/` and `supabase/migrations/`: persisted document,
  processing output, chunk, table, vector and access-control shapes. Parser
  changes should retain
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

## CLI tools and evaluation artifacts

`tools/` groups runnable CLI entry points by workstream: `ingestion/`,
`processing/`, `chunking/`, `retrieval/`, `agents/`, and `operations/`. Use
`uv run python tools/<workstream>/<name>.py --help` before
running a data-writing command. The OCR Kaggle packager copies its evaluator to
the standalone bundle's `scripts/processing/evaluate_ocr.py` path.

Keep active, documented evidence under `artifacts/evaluation/`, organized by
workstream. Remove superseded runs and retired-corpus outputs instead of
preserving them in a second history tree.
Put new evidence in a workstream subdirectory
(`artifacts/evaluation/document-pipelines/`, `chunking/`, `retrieval/`, `agents/` or
`operations/`) and
include the input/case hash, configuration, model/version and run date in the
report.
Legacy Apple-corpus downloader and retrieval checkpoints are retired; active
Commerce imports and evaluations live in the workstream paths above.
