# Integrated translated hybrid — 2026-10-17

Implemented locally on Huy; no commit/push, database writes, or live translation calls.

`retrieval_method="translated_hybrid"` now works through RAGService, the shared
RetrievalService, the knowledge agent, and the app/API strategy selector.
The existing `hybrid` default remains unchanged. `document_ids` is now forwarded
by RAGService for every retrieval strategy. Every dense/BM25 candidate search
keeps the ready/company/role/document filters.

One original EN/VI question is sufficient: the translator detects its language
and produces the other version in one structured call. Known-language callers
can supply `query_language="en"` or `"vn"`. Translation failures explicitly record
dense fallback. Owned translation providers are initialized lazily and closed.
Generated queries/model, translation timing, scopes and fallback details are
available in the shared response, RAG contexts, agent evidence and API citations.

Without a `document_languages` map this is bilingual fusion over the permitted
scope, not the language-aware experiment. Supply a complete verified map plus
`document_ids` to route each lexical query to its document-language group.
No document-language detection or database language column was added.

For An's benchmark, after receiving these changes:

```python
contexts = rag.retrieve_contexts(
    q, limit=10, company="Commerce Demo", roles=["admin"],
    retrieval_method="translated_hybrid", document_ids=IDS,
)
```

Use the same `document_ids=IDS` on dense and untranslated hybrid comparisons.
See `scripts/README.md` for the exact two-report language-aware call.

Validation: 138 tests passed across translated hybrid (9), translation (3),
retrieval service (10), RAG callers (5), document scope (2), retrieval contracts
(16), repository (15), app request/API (23), agents (35), and RAG (20).
Fusion self-check, compilation, and `git diff --check` passed.

The environment lacked declared app dependencies; the project-pinned
langgraph==1.2.4 and sqlglot==30.19.0 were requested through uv, installing the
missing langgraph packages. No dependency declarations or lockfile changed.

Real read-only GPU replay used the saved translations and verified original
249-chunk corpus hash. All 48 original-language cases exactly matched their
saved top-10 hybrid rankings, with zero scope violations and zero translation
API calls. This verifies integration parity, not new translation quality or
live automatic-language-detection accuracy. Automatic detection/failure paths
were tested with mocked LLM responses. The detailed replay is saved in
`integrated-translated-hybrid-replay-20261017.json`.

The old experimental runner now shares its fusion helper with production;
previous benchmark result files are unchanged. Earlier investigation artifacts
and the tracing script already in the workspace remain untouched.
