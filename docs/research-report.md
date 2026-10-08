# Research report: Commerce decision-support prototype

**Status:** implementation report for the local capstone prototype, 2026-10-07.

## Scope

This prototype explores decision support for inventory allocation, promotion
planning, and nationwide logistics. Its transaction and operations tables come
from the synthetic Kaggle Datathon 2026 Round 1 dataset. Public retailer and
platform materials are retrieved as attributed examples or issuer-specific
rules; they are not policies for the synthetic business.

## System and evidence path

Uploaded PDFs pass through page extraction, OCR fallback, parsing, chunking,
PostgreSQL persistence, embedding, role-filtered retrieval, and the FastAPI
interface. Structured SQL aggregates provide business observations. The
report path combines those observations with domain-relevant retrieved
references and must state when the data cannot support a recommendation.
Commerce dashboard values are queried from the SQL schema rather than stored
as hard-coded UI metrics.

## Findings and limits

- The dashboard exposes inventory, promotions, and logistics views from the
  synthetic dataset. Promotion comparisons are observational, not causal;
  the schema lacks key operational details such as route, carrier, and promised
  service levels.
- The application has nine SQL-plus-RAG decision cases. The latest captured
  responses pass 9/9 mechanical checks after current-evaluator rescoring across
  a full replay and three focused reruns; this is not a single full live replay
  or a semantic quality score. Provider output can vary and human review is
  still required.
- OCR upload has been exercised with generated image-only and mildly degraded
  fixtures. These checks verify processing and table structure, not accuracy on
  representative physical scans.
- Public references offer management methods and attributed examples. They
  cannot establish the synthetic company's internal policies or prove that an
  action is profitable for it.

## Reproduction and current status

Use the [Commerce status and proposal coverage](commerce-decision-support.md)
for dated API checks, artifacts, test commands, known gaps, and proposal
coverage. The [technical guides](README.md#technical-guides) document
processing, chunking, embeddings, retrieval, agents, and configuration.

This report describes a prototype slice, not a completed proposal evaluation
or production-ready decision system. Human review of recommendations,
representative physical-scan ground truth, provider-backed agent evaluation,
and the remaining proposal benchmarks are still required.
