# Commerce project status

This page is the short status index. The detailed evidence and limitations live in the linked workstream guides.

## Scope

The app demonstrates the proposal against the Commerce schema: transaction data is synthetic Kaggle competition data, not observations from a real retailer. Public manuals are attributed examples and platform-specific rules; three generated, image-only PDFs are explicitly fictional Commerce Demo policies. The app keeps those evidence types separate.

## Current state

| Proposal area | Implemented and checked | Still open |
| --- | --- | --- |
| Knowledge base and RBAC | Manifest-backed Commerce references, domain/source metadata, role-filtered retrieval, Admin file management with domain/state filters, and access editing. | Independently reviewed evidence for more physical scans; sources remain examples, not internal policy for the mock business. |
| PDF/OCR and upload | Admin upload and isolated Tester Upload Test persist inspectable source pages, parser output, final embedding chunks and vectors. Three synthetic policies are fully image-only; the 9-page run scored 0.3297% CER / 1.4558% WER against authored references. A saved 48-page Sam's Club run has 80 chunks and 2 tables; its page preview API returns 200. | Synthetic OCR scores are not real-scan accuracy. Public screenshot pages remain noisy; the Sam's inventory grid is not reliably reconstructed as a table. |
| Retrieval and Q&A | Dense, BM25, Hybrid and Parent methods exist; retrieval applies domain and role filters. Answers cite document/page sources. | The retrieval label set is small. Broader embedding, reranker and model comparisons are incomplete. |
| Decision agents | ReportAgent joins bounded read-only SQL observations with domain-filtered knowledge. The nine-case set has three cases per domain. A separate AI review found the deterministic answers aligned with the expected evidence and action limits; read-only queries against Commerce base tables reconfirmed the reviewed inventory, campaign and logistics values. | The replay used deterministic fallbacks because providers were rate-limited/unavailable. Provider-backed answer quality and independent human review remain open. The workflow is sequential, not an iterative multi-agent planner. |
| Dashboard and admin UI | Three SQL-backed dashboard views: inventory allocation, promotion planning and nationwide logistics. Admin can manage knowledge files and roles; Tester can inspect OCR pages, chunks and tables. | Commerce data lacks some decision-critical dimensions listed below. |
| Deployment | Local FastAPI demo is runnable. | Hosted deployment/CI is outside the current agreed scope. |

## Next work

1. Improve and review OCR and final chunks on a representative scanned business PDF; retain parser text/tables, page previews and source provenance in Upload Test.
2. Review the nine decision answers against SQL rows, policy scope and decision limits; repeat with a model provider available and record semantic review separately from mechanical checks.
3. Only then expand model benchmarks or tune thresholds. Do not treat the current exploratory screenshot labels as primary OCR ground truth.

## Decision limits

- Inventory aggregates do not identify SKU/location overlap, forecast, lead time, transfer cost or an approved service target.
- Promotion tags are observational; there is no holdout or campaign spend. Catalog-COGS gross profit is a proxy, not contribution margin or ROI.
- Logistics data has no carrier, route, warehouse origin, capacity or promised SLA.
- Recommendations must distinguish SQL observations from sourced methods and state missing evidence; do not invent thresholds or attribute external rules to the synthetic business.

## Run locally

    uv sync
    PYTHONPATH=src .venv/bin/uvicorn app.main:app --reload --env-file .env --host 127.0.0.1 --port 8000

Open http://127.0.0.1:8000. Setup and credentials are in the [deployment guide](deployment-guide.md).

## Workstream documentation

- [Commerce sources, dashboard, decision cases and live evaluations](commerce-decision-support.md)
- [Capstone implementation report and proposal coverage](capstone-project-report.md)
- [User guide](user-guide.md)
- [Document processing and OCR](../src/document_processing/docs/document-processing.md)
- [Chunking](../src/core/chunking/README.md)
- [Embeddings and tokenization](technical/embeddings-tokenization.md)
- [Retrieval and RBAC](technical/retrieval-rbac.md)
- [Agents and evaluation](technical/agents-and-evaluation.md)
- [Database connections](technical/database-connections.md)
- [Repository ownership](technical/repository-ownership.md)
- [OCR datasets and evaluation](../data/evaluation/ocr/README.md)
- [Reproducible scripts](../tools/README.md)
