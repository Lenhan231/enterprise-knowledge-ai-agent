# Agent and generation artifacts

This directory retains QuocAn's agent and answer-generation evaluations and their
required datasets/provenance. Nhan/Huy OCR, document processing, fine-tuning,
embedding, retrieval/reranker and held-out evaluation artifacts are removed from
the current tree. Judge caches and transient logs are not published.

Start with the [corrected historical Knowledge baseline versus integrated v3](evaluation/knowledge-baseline-30-2026-11-12/COMPARISON.md).
Both cohorts completed 30 questions and 90 metric records without errors.
V3 scores 95.00% faithfulness, 75.24% answer relevancy and 88.25% context precision;
the historical baseline scores 92.71%, 75.19% and 84.63%. See the
[reproduction and provenance notes](evaluation/knowledge-baseline-30-2026-11-12/README.md)
for the import-isolation fix and the historical schema adapter. The invalid
2026-11-11 comparison is not included.

Other retained evidence includes:

- `evaluation/agent-benchmarks-*`: historical multi-agent/model benchmarks.
- `evaluation/knowledge-invoice-*`: frozen Knowledge and invoice evaluations.
- `evaluation/sql-*`, `evaluation/inventory-*`, `evaluation/report-*`: SQL,
  inventory and report-agent experiments.
- `evaluation/router-*`, `evaluation/orchestration-*`, `evaluation/rbac-*`:
  routing, orchestration and agent access checks.
- `evaluation/*qa*`, `evaluation/proposal-*`, `benchmark/`: generation answers,
  scores, review packets and supporting retrieved contexts.
- `datasets/`, `invoice-experiment-download-2026-11-12/`, `smoke/`: retained
  policy inputs, invoice-agent evidence and analytics smoke checks.

Removed evaluation families remain available in
[Git history before cleanup](https://github.com/Lenhan231/enterprise-knowledge-ai-agent/tree/7bdb6bde4d20f09916dfc5c666138f42c1b06aa0/artifacts).
Frozen manifests and measured revisions are not rewritten; reproduce historical
runs at their pinned commits. Legacy OCR checks require their archived generator
and datasets; this artifact-only cleanup does not change application or test code.
