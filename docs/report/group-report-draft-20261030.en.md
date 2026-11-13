# Enterprise Knowledge AI Agent — Group Report Draft

Date: 30 October 2026. Main snapshot: `beac2f3c58426ddcaff3a3c95daf5b93154656aa`.

Draft written into the shared report. Pending owner contributions are explicit. Academic references and final layout remain to be completed.

## Acknowledgement

[TEAM TODO] Add acknowledgements after the team confirms the people and institutions to thank.

## Definition and Acronyms

AI: Artificial Intelligence. OCR: Optical Character Recognition. RAG: Retrieval-Augmented Generation. RBAC: Role-Based Access Control. ACL: Access Control List. JWT: JSON Web Token. BM25: a lexical retrieval scoring method. RRF: Reciprocal Rank Fusion. MRR: Mean Reciprocal Rank. CER/WER: Character/Word Error Rate. Provenance: metadata linking processed evidence to its source document.

## List of tables

[TEAM TODO] Generate the list of tables after the result tables and captions are finalized.

## List of figures

[TEAM TODO] Generate the list of figures after the architecture and processing diagrams are inserted.

## I. Project Introduction

Working group draft, 30 October 2026. Implementation statements refer to main commit beac2f3 unless a historical experiment is explicitly identified. Pending owner contributions are marked below; proposed work is not presented as a completed result.

## 1.1 Project Information

Project: Enterprise Knowledge AI Agent. The team responsibilities currently discussed are: Nhân — document parsing/OCR; Huy — chunking, embeddings/retrieval, Knowledge AI, and RBAC; An — Dashboard/SQL/Report agents. [TEAM TODO] Confirm the official project code, team member names, supervisor details, and cover-page consistency.

## 1.2 Project Overview

The project integrates document extraction, evidence retrieval, cited question answering, and structured-data analysis. Uploaded documents are transformed into searchable chunks, while an agent layer routes requests to Knowledge, SQL, Dashboard, or Report workflows. This report separates component evaluation from deployment observations and records incomplete integration work explicitly.

## 2. Project Background

Enterprise information is distributed across PDFs, Office files, tables, and scanned pages. Finding relevant evidence requires both extracting usable content and retrieving the right passages. Structured database questions require a different execution path. The project addresses these needs through document AI and specialized agent workflows, with access restrictions applied before document evidence reaches the answer model.

## 3. Project Objective

The objectives are to: (1) extract document text, tables, and source metadata; (2) create model-compatible searchable chunks; (3) retrieve relevant evidence and produce traceable answers; (4) support SQL, dashboard, and report workflows; and (5) enforce server-derived permissions. Retrieval is assessed using Recall@10, MRR@10, and Full evidence@10. [Nhân TODO] Specify parser quality criteria and measured targets. [An TODO] Specify generation, SQL, and report acceptance criteria. No retrospective target is inferred from an observed score.

## 4. Problem Statement

The technical problem is to connect noisy, multilingual, and partly structured document content to reliable evidence-based responses while restricting access to authorized information. Extraction errors, chunk boundaries, terminology differences, candidate retrieval misses, and unsupported answer generation can each affect the final result. A successful component test alone does not establish end-to-end answer quality.

## 5. Significance of the Project

The practical contribution is an integrated prototype with traceable processing outputs, document evidence retrieval, and agent-based access to structured and unstructured information. The experimental contribution is a reproducible comparison of retrieval configurations on a frozen bilingual test corpus. These are prototype and benchmark findings; production reliability and enterprise-wide benefits have not yet been established.

## 6. Project Scope & Limitations

The current scope covers text and tables, multilingual document retrieval, cited Knowledge AI responses, and integration with the other agents. Context-rich diagrams remain dependent on upstream extraction work. RBAC completion is now assigned to Huy. Limitations include a small retrieval evaluation set, synthetic/translated supplementary documents, OCR errors, incomplete asynchronous ingestion, and unverified live-server capacity. Component experiments used different questions and hardware, so their scores and latency must be reported separately.

## II. Project Management Plan

This section records the current ownership and a proposed completion plan. [TEAM TODO] Confirm the schedule, review cadence, and final acceptance checklist.

## 1.1 Team Structure and Roles

Nhân owns document parsing, OCR, layout/table extraction, and the processing-output contract. Huy owns chunking, embedding/retrieval, Knowledge AI, and RBAC completion. An owns Dashboard/SQL/Report workflows and their integration. Shared decisions include ingestion handoffs, permission contracts, deployment, and report consistency. [TEAM TODO] Confirm final ownership of deployment and cross-component acceptance testing.

## 1.2 Communication Plan

Proposed communication plan: track code changes in GitHub, record interface decisions in shared notes, and use this report for reviewed claims and evidence links. Cross-component changes should identify the affected input/output contract and the owner who must validate it. [TEAM TODO] Add the actual meeting schedule, communication channels, and advisor review dates.

## 2.1 WBS

Work packages: WP1 — parsing and source metadata (Nhân); WP2 — chunking and embedding ingestion (Huy, coordinated with upstream processing); WP3 — retrieval and Knowledge AI (Huy); WP4 — Dashboard/SQL/Report agents (An); WP5 — RBAC implementation and access-control tests (Huy, coordinated with An); WP6 — deployment and integrated evaluation (shared, deployment owner to confirm). [TEAM TODO] Add milestones, dependencies, estimates, and deadlines.

## 2.2 Risk Management

Risks and responses: OCR corruption — retain raw output and inspect representative pages; stale chunks/vectors — version inputs and rebuild after incompatible changes; unauthorized evidence exposure — enforce server-derived scope before ranking and context expansion; slow CPU reranking — measure representative candidate loads; worker interruption — use transactional claims and rollback; misleading comparisons — retain per-component datasets, timing boundaries, and hardware; unavailable shared backend — verify the VPS health and deployment procedure.

## 2.3 Quality Management

Quality evidence consists of focused unit/integration tests, retained benchmark inputs and outputs, hashes/configurations, and manually reviewed examples. Retrieval relevance is evaluated separately from generated-answer correctness. Access-control acceptance must cover allowed, denied, empty-ACL, disabled-document, and cross-agent cases. A previous chunking-worker checkpoint passed 28 focused tests; this historical result is not a claim that the latest full main suite passes.

## 2.4 Budget and Funding (Optional)

A Contabo VPS with 12 GB RAM has been rented for shared backend access, according to the user. [TEAM TODO] Record the actual invoice, billing period, storage/backup charges, external API costs, and funding responsibility. No unverified price or whole-system RAM measurement is reported here.

## 2.5 Change Management Process

Proposed change process: record the reason and affected interfaces, implement on a branch based on current main, run relevant checks, review the evidence, and then merge. Changes to chunking, tokenization, embeddings, or relevance labels require an explicit index/benchmark version decision. Keep historical benchmark artifacts unchanged and avoid merging the historical Huy implementation wholesale into current main.

## 2.6 Closure and Evaluation

Completion should include an agreed acceptance checklist, a reproducible deployment procedure, validated document ingestion, cross-agent permission tests, and linked result artifacts. [TEAM TODO] Add the final sign-off date, unresolved issues, and owner reflections after the integrated acceptance run.

## III. Existing Systems/State of the Art

Literature review framework. The topics below describe how prior methods relate to the prototype. [TEAM TODO] Add verified academic/official references and a consistent citation style before submission; this draft does not claim a systematic literature survey.

Coverage: document OCR and layout/table extraction; dense and lexical retrieval; reranking; retrieval-augmented generation; tool/agent orchestration; and application-level access control.

## 1. Overview of the Field

The system combines document understanding with information retrieval and language-model applications. Parsing produces machine-readable content and source metadata; retrieval selects evidence; generation uses that evidence to answer. Structured-data agents operate through database queries rather than treating every request as document retrieval.

## 2. Historical Context

The relevant progression is from keyword search to dense retrieval and hybrid candidate selection, followed by reranking and evidence-conditioned generation. [TEAM TODO] Add dated primary references for this progression rather than presenting it as a complete history.

## 3. Key Studies and Theories

Methods to review: BM25 for lexical matching; dense bi-encoders for semantic similarity; reciprocal rank fusion for combining ranked lists; cross-encoders for reranking query–passage pairs; and RAG for evidence-conditioned answers. [Nhân TODO] Add primary sources for the OCR/layout/table models actually evaluated. [An TODO] Add sources relevant to SQL/tool orchestration and report grounding.

## 4. Technological Advancements

The prototype uses pretrained multilingual representations, document extraction tools, vector search, and externally hosted language models. These choices enable integration without training a new foundation model. [TEAM TODO] Cite the exact model cards, library documentation, and versions used in the submitted implementation; avoid unsupported claims about the latest technology or general superiority.

## 5. Comparison of Existing Systems

Comparison framework: lexical retrieval favors exact terms but can miss cross-language matches; dense retrieval supports semantic matching but can miss precise evidence; hybrid retrieval combines candidate lists; reranking improves ordering within the available pool. The controlled project comparison is reported in Section VI. [Nhân TODO] Add the parser alternatives and their measured trade-offs. [An TODO] Add the agent/generation baselines and evaluation protocol.

## 6. Gaps in the Literature/Technology

The project-specific integration gaps are noisy extraction, incomplete evidence in the candidate pool, source traceability across processing stages, and consistent authorization across retrieval and agent outputs. These are observed engineering concerns in this prototype; this report does not establish that they are universally unresolved in the research literature.

## 7. Justification for the Project

The project is justified as an implementation and evaluation of established methods for the team's enterprise-information scenario. Its contribution is the integrated workflow, retained evidence, and measured retrieval comparison. No new retrieval algorithm, new model architecture, or fine-tuning contribution is claimed.

[TEAM TODO] Complete the source-backed comparison and check that every cited system or study is discussed in relation to a project decision.

## IV. Methodology

The methodology combines pretrained document and retrieval components with controlled component evaluation and integration testing. Reported experiments and current main behavior are identified separately.

Owner contributions: Nhân supplies the parsing/OCR protocol and evidence; Huy supplies chunking, embeddings/retrieval, Knowledge AI, and RBAC; An supplies generation and Dashboard/SQL/Report protocols. Reinforcement learning is not part of the currently audited implementation.

## 1. Research Questions and Objectives

RQ1: How does document extraction preserve usable text, tables, and provenance? RQ2: Does translated hybrid retrieval with BGE reranking improve evidence retrieval over dense E5 on the frozen test corpus? RQ3: Can the integrated agents produce grounded outputs while respecting verified user permissions? Only RQ2 has the frozen quantitative comparison included below. [Nhân/An/Huy TODO] Supply the remaining component and integrated acceptance evidence.

## 2. Data Collection and Preprocessing

The shared Review 2 corpus snapshot contained five Vietnamese documents and 532 retrieval chunks, verified on 24 October 2026. Huy's separate bilingual retrieval experiment added five corresponding English versions, producing ten document versions and 1,063 chunks. Its 80 directional cases represent 20 intent clusters, with Vietnamese/English query variants and evidence-language directions. These counts describe frozen snapshots, not the current database. [Nhân TODO] Add parser dataset selection, page types, ground-truth procedure, and sample counts. [An TODO] Add generation/SQL/report datasets and question counts.

Current ingestion retains parser output in document_processing_outputs, then converts ordered elements and table references into parser chunks. Sentence-oriented text splitting has a default target of 1,100 characters; table row groups retain available headers, and a single oversized row can exceed that target. A separate token-aware stage prepares embedding inputs for the configured model. Source element references and document/page metadata support traceability but do not guarantee exact character-level source mapping for every token child. [Nhân TODO] Document OCR cleaning and uncertainty handling with reviewed examples.

## 3. Feature Selection and Engineering

The retrieval representation uses intfloat/multilingual-e5-base: 768-dimensional normalized embeddings with query:/passage: input prefixes and a configured 512-token input cap. Lexical candidates use BM25. Translated hybrid retrieval combines original-query dense candidates with original/translated lexical results through RRF. BGE reranking scores query–candidate pairs. Model choice evidence is limited to the recorded project pilots and must not be generalized to every domain or language direction.

## 4. Model Training and Validation

No task-specific fine-tuning was performed in the reported retrieval comparison. Pretrained E5 and BGE components were used with frozen settings. Four arms were compared: Dense E5, Dense E5 + BGE, Translated Hybrid, and Translated Hybrid + BGE. The controlled benchmark used 30 candidates and retained the top 10, with an RTX 2060, FP32, and reranker batch size 4. Current online Knowledge AI uses its own context limit and must not be described as having the same top-10 benchmark output.

The frozen evaluation ran once per case and method; the 80 cases are not 80 independent intent clusters. Saved scores, rankings, translations, configurations, and manifests support replay and inspection. Confidence intervals were computed by paired bootstrap over the 20 intent clusters. This is not repeated model training or repeated inference. New OCR/chunking inputs require new reviewed labels and an unchanged-system baseline before optimization. [Nhân/An TODO] Add the validation protocols for their components.

## 5. Evaluation Metrics

For query i with gold chunk set G_i and retrieved top-k set R_i, Recall@k = |G_i ∩ R_i| / |G_i|, averaged over cases. Gold chunks are annotated evidence-bearing chunks, not merely keyword matches. MRR@k averages 1/r_i, where r_i is the first relevant rank; the contribution is 0 if none appears within k. Full evidence@k is the proportion of cases satisfying all annotated evidence requirements, including the benchmark's alternative-evidence rules. These measure retrieval evidence, not generated-answer correctness. [Nhân TODO] Define CER/WER and layout/table metrics actually measured. [An TODO] Define answer, citation, SQL, and report metrics with denominators and scoring procedures.

## 6. Implementation Plan

Implementation work is split into: parser output persistence; transactional parsed-document chunking; embedding/index persistence; scoped candidate retrieval and reranking; Knowledge AI generation; and integration with the other agents. The parsed-to-chunked worker is on main. A separate chunked-to-ready embedding worker was not found in this audit. RBAC completion must align the policy matrix, document eligibility, context expansion, report evidence, and response handling before acceptance testing.

## 7. Ethical Considerations

Only server-verified identity and permissions may define accessible scope; client metadata must not grant roles. Unauthorized chunks must be excluded before retrieval limits, reranking, prompts, and citations. General queries with no authorized evidence should receive a neutral no-evidence response, avoiding disclosure of hidden document existence. Explicit document access denial should be distinguished only through an authorized document-access check. Current main has part of this enforcement, but empty-ACL/admin behavior and disabled-document eligibility still need correction or an explicitly agreed policy exception.

## V. System Design and Implementation

Architecture snapshot: current main beac2f3. Component owners must validate their sections against the deployed revision before final submission.

## 1. AI Model Integration

The application constructs a verified identity from authenticated user information and passes it to agent execution. Knowledge AI receives document roles, retrieves evidence, and generates a cited answer; report document sources reuse the role-scoped retrieval path. SQL and other analytical tasks require their corresponding execution permission. [An TODO] Document the current planner/router, SQL safety rules, report source/output modes, and fallback behavior. [Nhân TODO] Document the parser API and output contract.

## 2. Data Flow and Processing

Parser-handoff route: parse → persist raw output in document_processing_outputs → mark parsed → chunking worker claims the document → ChunkingProcessor → document_parser_chunks → mark chunked. The worker uses row locks/SKIP LOCKED and transactional persistence. The ordinary upload route still processes chunking and embedding inline through ready. No separate embedding worker connecting the asynchronous chunked state to ready was found at this revision.
Knowledge flow: authenticated request → server-created identity → agent authorization → role-filtered dense/lexical candidates → fusion/reranking → evidence context → answer/citations. Current identity does not include company or authorized-document-ID scope. [Huy TODO] Define any required company/document scope server-side and carry it consistently through context expansion and report sources.

## 3. Deployment Strategy

Docker Compose defines backend API, document-processing, chunking, embeddings, and reranker services, with an optional proxy; Supabase and hosted language-model APIs are external. The user reports deployment on a 12 GB RAM Contabo VPS. This audit did not access the live VPS, verify its deployed commit, or measure its resource usage. [DEPLOYMENT OWNER TODO] Add the sanitized deployment steps, model-cache preparation, migrations, service health checks, restart policy, rollback procedure, endpoint, and actual live revision. Existing CI is not evidence of automated production deployment.

## 4. Scalability and Maintenance

The chunking worker's transactional claims allow multiple workers to avoid claiming the same available document; this has not established whole-system throughput. Model services and database operations should be measured under representative concurrent workloads. Retain model/index versions and provenance when updating the pipeline. [Huy TODO] Validate asynchronous embedding, disabled-document filtering, ACL changes/revocation, and cross-agent evidence handling. [An TODO] Validate orchestration budgets, report workloads, and deployment behavior. [Nhân TODO] Validate OCR resource limits and failure recovery.

RBAC implementation status (Huy): JWT authentication and route permissions exist; the server creates VerifiedIdentity; Knowledge AI rejects missing document permission/scope; shared candidate SQL applies roles before ranking; report document retrieval propagates roles. Outstanding items: knowledge_base_active is absent from candidate and parent-context eligibility filters; admin bypasses the document role ACL, including an empty ACL; the access-update schema requires at least one role; and server identity has no company/document-ID scope. The agreed deny-empty policy and three response cases require end-to-end validation. These are implementation gaps, not completed security results.

## VI. Results and Discussion

Results below separate Huy's frozen retrieval comparison from pending parser, agent, deployment, and RBAC acceptance results.

## 1. Results and Analysis

Frozen retrieval comparison (20 intent clusters; 80 directional cases; 10 document versions; top 10):
Method | Recall@10 | MRR@10 | Full evidence@10
Dense E5 | 0.6563 | 0.5586 | 52/80 (65.00%)
Dense E5 + BGE | 0.7875 | 0.8213 | 62/80 (77.50%)
Translated Hybrid | 0.7917 | 0.6590 | 63/80 (78.75%)
Translated Hybrid + BGE | 0.8823 | 0.9000 | 69/80 (86.25%)
Source: the retained review2-reviewed-r1-sql-20261022 run, linked in the appendices.
Recorded layout pilot on latest main [E5]: five reviewed pages, IoU 0.50, saved detector outputs without post-processing; PP-DocLayout-L at confidence 0.40 achieved priority macro-F1 57.5% over table/text/title, below the pilot's 85% expansion gate. This is a small detector comparison, not a full parser or production quality score. [Nhân TODO] Validate this interpretation and add OCR/table extraction metrics and reviewed examples.
[An TODO] Insert generation, SQL, dashboard, and report results with their own datasets and metrics.
[Huy TODO] Add measured RBAC acceptance results after implementation; no pass rate is available yet.

The final retrieval arm completed 17 more cases than dense E5: an increase of 21.25 percentage points. Paired bootstrap over 20 intent clusters gave a 95% interval of 10–35 percentage points versus dense and 0–20 versus Dense E5 + BGE; the latter does not establish a clear improvement over that reranked baseline. Saved diagnostics attribute the 11 final incomplete cases to required evidence missing from the top-30 candidate pool. Reranking therefore cannot repair those misses without changes to candidate retrieval. The result is evidence-retrieval performance, not 86.25% answer accuracy.

## 2. Discussion

The comparison supports translated hybrid retrieval plus reranking on this frozen corpus, with uncertainty and scope limitations. Five English document versions were supplementary experimental material; they were not part of the shared five-document Vietnamese snapshot. Shared source material does not mean all members evaluated the same questions. Current main includes later parser and agent changes, so the frozen score is not a new production quality measurement. Latest local selected checks reported 33 passes, one SQL-expectation failure, and two test-module import errors caused by missing cv2/python-docx; this does not describe the full suite or live VPS.

## 3. Recommendations

Priorities: complete the ingestion handoff; finalize the RBAC matrix and deny-empty/admin policy; enforce active/ready/scope eligibility consistently; test permitted, denied, and no-authorized-evidence outcomes across Knowledge and Report; then evaluate current chunking/Knowledge AI on newly reviewed data. Profile representative CPU reranking before changing models or candidate counts. [Nhân/An TODO] Add recommendations derived from their measured failures.

## 4. Personal Reflection (Optional)

[TEAM TODO] Each member may add a short reflection describing their contribution, a specific technical challenge, and a lesson supported by project experience.

Submission check: attach evidence for every numerical claim, identify the measured version and runtime, and keep incomplete features explicitly marked.

## VII. Conclusion

Interim conclusion; revise after the pending owner contributions and integrated acceptance run.

## 1. Summary of Findings

The project has implemented a document-processing and agent-based prototype. Huy's retained retrieval benchmark shows 69/80 complete-evidence cases for translated hybrid plus BGE compared with 52/80 for dense E5. A parsed-document chunking worker has been added to main. Current RBAC provides a working foundation but still requires policy alignment and acceptance testing. [Nhân/An TODO] Add supported conclusions for parsing and the other agents.

## 2. Contributions and Reflections on the Project

The contributions are the integration of processing outputs, provenance-aware chunking, multilingual hybrid retrieval, cited Knowledge AI, and specialist agent workflows, together with retained experimental evidence. The work applies pretrained components rather than claiming a new foundational model or retrieval algorithm. [Nhân/An TODO] Confirm their specific implementation and evaluation contributions.

A key engineering lesson is that parser chunks, embedding inputs, candidate retrieval, and answer generation have different contracts and failure modes. Likewise, successful authentication does not by itself prove document-level authorization. Keeping frozen experiments separate from changing production code makes the claims easier to verify.

The remaining work should turn the integrated prototype into a demonstrably reproducible and access-controlled system. Final conclusions must follow the completed acceptance evidence rather than anticipated behavior.

## 3. Limitations and Future Work

Limitations include a small clustered retrieval set, supplementary translated/synthetic material, possible annotation incompleteness, OCR/table errors, and a candidate-pool ceiling. Chunk source references are not universal exact character spans, and token splitting can cut oversized table rows. Component datasets/questions/hardware differ. Latest main, live VPS quality/latency, asynchronous embedding, and complete RBAC behavior have not all been validated together. No whole-system load or capacity guarantee follows from renting 12 GB RAM.

Future work: complete and test the asynchronous ingestion lifecycle; validate OCR/table extraction and chunk provenance on reviewed documents; complete RBAC and revocation behavior; measure current Knowledge AI answer/citation quality; profile CPU bottlenecks; and run integrated acceptance tests on a pinned deployed revision. Optimize retrieval using separate development questions and preserve a frozen evaluation set.

[TEAM TODO] Replace the interim conclusion with final findings once the remaining measurements and owner reviews are complete.

## VIII. References

Project evidence sources (repository may require team access):

[E1] Main implementation snapshot, commit beac2f3 (30 October 2026): https://github.com/Lenhan231/enterprise-knowledge-ai-agent/tree/beac2f3

[E2] Retrieval evidence guide, Huy documentation snapshot 244803b: https://github.com/Lenhan231/enterprise-knowledge-ai-agent/blob/244803b/docs/review2/README.md

[E3] Frozen retrieval run: https://github.com/Lenhan231/enterprise-knowledge-ai-agent/tree/244803b/artifacts/evaluation/heldout-review2-v1/runs/review2-reviewed-r1-sql-20261022

[E4] Worker handoff and historical 28-test validation: https://github.com/Lenhan231/enterprise-knowledge-ai-agent/blob/244803b/docs/handoff/chunking-worker-20261029.vi.md
[E5] Reviewed five-page layout pilot (v3): https://github.com/Lenhan231/enterprise-knowledge-ai-agent/blob/beac2f3/artifacts/evaluation/document-pipelines/results/shared-html/layout-5pilot-review-v3-20261030/report.md

[TEAM TODO] Add the primary papers/model cards/documentation actually used by each owner; verify bibliographic details and apply the institution's required citation style. E1–E4 are implementation/evidence references, not a replacement for the academic bibliography.

[Nhân TODO] OCR/layout/table references. [Huy TODO] E5, BGE reranking, BM25, RRF, and access-control references. [An TODO] RAG/generation, orchestration, SQL safety, and report-grounding references.

## IX. Appendices

Appendix A — Evidence and review checklist.

Retrieval: E3 contains metrics.csv, results.json, gold-chunk-map.json, config.json, analysis.json, and candidate-diagnostics.json; E2 maps claims to these files. Preserve the frozen files when checking results.
Chunking: E4 describes worker design, canonical processing-output mapping, transaction behavior, and the historical test checkpoint. Current source references are in E1 under src/core/chunking/ and src/core/tokenization/.
RBAC code to review in E1: src/app/security.py; src/app/agents.py; src/core/models/agents.py; src/core/agents/execution.py; src/core/agents/knowledge_agent.py; src/core/retrieval/methods/common.py; src/core/database/document_chunks_repository.py; src/core/reports/sources.py.
[Nhân TODO] Link sanitized parser datasets, labels, metrics, and representative failure cases.
[An TODO] Link agent evaluation inputs, outputs, scoring scripts, and timed stage logs.
[DEPLOYMENT OWNER TODO] Link sanitized deployment evidence and live revision.

Appendix B — RBAC acceptance checklist (planned, not yet certified).
1. Allowed role: only eligible, active, ready document evidence may reach reranking, prompts, answers, and citations.
2. General query with no authorized evidence: return a neutral no-matching-document response without revealing hidden documents.
3. Explicit document request with an authorized access check showing a role mismatch: return permission denied.
4. Empty allowed_roles: deny access under the agreed policy; resolve current admin-bypass inconsistency.
5. Client-supplied roles/permissions must not elevate access.
6. Apply the same scope to dense, lexical, translated branches, parent-context expansion, and report document sources.
7. Verify document disabling, ACL updates/revocation, and conversation handling after permission changes.
8. Test missing identity, missing permission, cross-agent dependencies, and any required company/document scope.
[Huy TODO] Record test IDs, expected/actual outcomes, code revision, and evidence links after implementation.


