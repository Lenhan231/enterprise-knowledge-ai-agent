# Main merge validation — 2026-10-18

Merged origin/main 298be61 into Huy, retaining translated_hybrid, document_ids,
verified document-language routing, translation diagnostics and the app selector.
Resolved nine conflicted files by combining both interfaces rather than selecting
one branch. Main metadata filters now reach all three translated candidate searches;
main active-knowledge-base filtering and ordinary hybrid-to-BM25 embedding-failure
fallback remain intact. RAG retains main's pre-retrieved-context support.

Added the missing psycopg-pool dependency imported unconditionally by main's
connection manager; installed version 3.3.3 locally. The lockfile changes only
add that package and root requirement. uv lock --check --offline passed.

53 tests passed in the fully passing suites: translated hybrid 9, document scope 2,
retrieval service 10, RAG callers 5, query translation 3, tokenizer 2, embeddings 4,
merge compatibility 2, retrieval models 16. Fusion self-check, Python compilation,
and git diff --check passed. No paid inference calls or database migrations ran.

Existing upstream failures were reproduced on an isolated, untouched archive of
origin/main using the same environment:

- test_document_chunks_repository.py: 13 pass, 2 assertions stale against main's
  retained Vinamilk keyword and richer source metadata SQL.
- test_app_request_models.py: imports removed CandidateReviewRequest.
- test_agents.py: imports removed _financial_retrieval_query.
- test_upload_processing_flow.py and test_pdf_upload_processing.py: import the
  removed core.document_processing.processors package after main's reorganization.

These upstream test migrations are not folded into this merge. The merged app
itself imports and accepts translated_hybrid; its selector is present, and the
new compatibility check verifies scoped BM25 fallback after an embedding error.
No push was performed.
