# Data directory

The active business demo uses the synthetic Kaggle Datathon 2026 Round 1
Commerce dataset. The importer keeps the supplied source fields unchanged;
these records are not observed results from a real retailer.

## Active data

- `raw/commerce_knowledge/` contains downloaded public reference files and the
  generated fictional Commerce Demo policy PDFs. Raw files stay local and are
  excluded from Git; `data/commerce_knowledge/manifest.json` is their source
  registry.
- `processed/commerce_knowledge/` contains parser output used for local review.
- `evaluation/commerce_decision_benchmark.json` and
  `evaluation/commerce_retrieval_cases.json` define the active SQL + RAG cases.
- `evaluation/ocr/` contains synthetic scan PDFs and transcription references
  for upload/OCR robustness checks, not business evidence or real-scan accuracy.
- Current OCR and agent run reports live in `artifacts/evaluation/`; older
  superseded outputs are removed rather than archived in the repository.

The structured Commerce dataset is loaded separately into the private
PostgreSQL `commerce` schema. See [tools/README.md](../tools/README.md) for
the importer, policy generation, indexing, and evaluation commands. See
[Commerce knowledge sources](commerce_knowledge/README.md) for document scope,
synthetic-policy labeling, and OCR limitations.
