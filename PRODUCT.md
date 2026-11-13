# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

**Primary:** employees and analysts of a company who need answers from internal policy documents and business data, and who must be able to trust and check each answer. Typical jobs: "who approves an 80-million-VND purchase", "what is the hotel limit per night on a business trip", "how did stock change between two dates". They ask in Vietnamese (often without accents, with shorthand such as "80tr") or in English.

Role-specific users, each seeing only what their role permits:
- Employee and other document roles (finance analyst, sustainability analyst, procurement, operations, legal/compliance, executive): ask questions about the documents their role may read; analysts and executives also see analytics.
- Document uploader: uploads and classifies documents; no Q&A or analytics.
- Admin: everything above plus upload, source review, access control, knowledge-file management, invoice review and agent monitoring.
- Tester / document-processing owner: runs isolated upload and parser tests that never enter the searchable corpus.

**Secondary:** the FPT University capstone committee (Review 3 on 2 Dec 2026, defense 19–21 Dec 2026), who judge whether the primary users' job is done well, mostly through a live demo.

## Product Purpose

Enterprise Knowledge AI Agent answers employees' questions from company documents and business data. Every answer cites its sources, the system declines when the sources do not cover the question, and it never shows a document to a role that may not read it. Success means a user gets a correct, checkable answer in seconds instead of searching files or asking colleagues, and can see where each claim comes from.

## Positioning

- Answers only from the company's own sources, with a citation for every claim, and an automatic claim check: an answer that fails the check is withheld rather than shown.
- Role filtering happens inside retrieval, before any passage reaches the language model, not after the answer is written.
- Bilingual search: a Vietnamese question finds English policy text and the reverse; unaccented Vietnamese is restored before searching.
- One assistant covers both documents (Knowledge) and structured business data (SQL), with Auto mode splitting a question between them.

## Operating Context

- Used in a desktop browser as a workspace with a sidebar: Knowledge Q&A, reports, upload, invoice review, document processing, knowledge management, access control, agent monitoring and upload tests. A phone-width layout exists.
- Answers take about 10–20 s (retrieval, reranking, generation, claim verification). The interface streams the current pipeline stage while the user waits and shows the answer only after verification passes.
- Documents are PDFs, Office files, text and scans (Vietnamese OCR); invoices go through a separate human-review flow.
- Live deployment: static frontend on Vercel, FastAPI backend in Docker Compose on a CPU-only server, PostgreSQL/pgvector on Supabase, language models through Groq.

## Capabilities and Constraints

- Chat modes: Auto (planner splits work between Knowledge and SQL), Knowledge, SQL, Dashboard, Report.
- Knowledge answers carry source chips (S1, S2 …) linked to the cited passage, page and document; answers can be rated (thumbs up/down with reasons).
- Reports can be generated from a DOCX or Markdown template with document and/or analytics sources.
- Invoice extraction drafts are always "review required" and stay outside the searchable corpus.
- Interface language is English; questions, answers and documents are Vietnamese or English as the user and the source use them. All text and fonts must render Vietnamese diacritics correctly.
- Terminology used in the product: Knowledge, Auto mode, citation / source, claim check (verification), withheld answer, knowledge base active, allowed roles.
- The Commerce dataset and the VietStyle operating policy are synthetic and must always be presented as such, never as a real company's data or policy.
- Undecided: whether an Inventory route returns to the "Route to" picker (the old inventory card was removed on 12 Nov 2026).

## Brand Commitments

- Binding product name: **Enterprise Knowledge AI Agent** (short form "Enterprise Knowledge" in the UI). "Commerce Intelligence", still in the browser title, is a leftover and is not the product name.
- Team FA26AI48, FPT University (AIP491 capstone); the FPT University logo appears in academic material, not as the product's own brand.
- Voice: plain, factual and honest about limits. The product states what it could not answer and why, rather than sounding confident.

## Evidence on Hand

- Evaluation (report Chapter VI, repository `artifacts/evaluation/`): 72% correct on 64 paired locked-test questions after the improvements (61% before; borderline, McNemar p = .065); full evidence retrieved for 69 of 80 bilingual questions; 0 of 4 role-restricted questions returned restricted content; median warm answer ≈ 12 s on the shared CPU server.
- Human check of judge verdicts: 20 development and 20 test-set-2 verdicts (`artifacts/evaluation/vietstyle-*/judge-review-*.md`).
- Datasets: VietStyle Enterprise Operating Policy v1.0 (synthetic, VN/EN) and the Kaggle Datathon 2026 Commerce schema (synthetic).
- No real customers, users, testimonials or usage statistics exist; do not invent them. No user-acceptance or usability (SUS) study has been run yet.

## Product Principles

1. Trust is earned by showing evidence: every claim links to its source, and a failed check withholds the answer instead of hiding the failure.
2. Permissions are invisible when they work: a user never sees, or learns of, content their role may not read.
3. Honest limits over fluent guesses: declining or partial answers are stated plainly, with the reason.
4. Waiting must be legible: a 10–20 s answer shows what the system is doing while the user waits.
5. Synthetic data is always labelled as synthetic.

## Accessibility & Inclusion

- Vietnamese diacritics must render correctly everywhere (fonts, inputs, citations).
- Reduced motion is respected (answer typing and stage animations turn off).
- Light and dark themes are both first-class.
