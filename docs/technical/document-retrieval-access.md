# Document retrieval eligibility

Candidate retrieval and parent-context expansion require all of:

- `documents.processing_status = 'ready'` (a NULL status is not ready).
- `documents.knowledge_base_active IS TRUE` (false/NULL is excluded).
- When verified roles are provided, an overlapping allowed role or `admin`.
  Admin may access documents with empty/NULL ACLs; other roles may not.
- Admin cannot bypass active/ready requirements, company scope, document-ID
  scope, or metadata filters.
- Internal `roles=None` calls retain their existing nonempty-ACL requirement;
  they do not implicitly gain admin privileges.

The shared candidate CTE applies these gates before dense/BM25 ranking, limits,
hybrid fusion, and translated-hybrid reranking. Parent expansion repeats the
gates. If expansion rejects an anchor, the repository does not restore its old
content and parent retrieval drops it from the response.

Company, document-ID, and metadata filters retain their existing behavior.
Administrative indexed-chunk inspection is separate from retrieval and is not
changed by this patch; administrators may still inspect disabled content through
the protected management endpoint.

## Checks

`tests/test_retrieval_access.py` creates and drops its own database on **local**
PostgreSQL. Its server user needs permission to create databases. Set
`RETRIEVAL_TEST_DATABASE_URL` to that local server and run:

```bash
PYTHONPATH=src:tests .venv/bin/python -m unittest -v test_retrieval_access
```

The test rejects nonlocal TCP hosts. It covers lexical candidates using the
shared SQL eligibility gates, real parent expansion, admin/empty user roles,
company/document scope, and document disabling/ACL changes between candidate
selection and expansion. It does not require model weights or pgvector.

## Remaining RBAC scope

This is an eligibility fix, not complete enterprise RBAC. Verified identity is
already created server-side for Knowledge AI; internal repository calls still
allow `roles=None` under the existing contract. Caller authorization must supply
verified scope. This patch does not add tenant membership, enable the
management API to set an empty ACL,
clear conversation history after document ACL changes, or guarantee revocation
after the final database query. Cross-agent permission and citation acceptance
remain separate work.
