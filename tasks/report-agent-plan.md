# Report Agent implementation

Approved scope, specifications and implementation authorized 2026-10-29.
Current specifications: [orchestration capability map](../CAPABILITY-MAP-agent-orchestration.md)
and [Report source follow-up](../docs/technical/report-source-orchestration.md).

Approved follow-up: replace Combined source broadcasting with bounded Knowledge/SQL
orchestration, preserve the separate Report interface, update docs/contracts, and
push the completed changes to main and local Docker. This supersedes the earlier
leave-uncommitted instruction below. Temporary verification helpers and generated
run output remain local.

1. Source collection and identity: add explicit source options, verified document roles, raw section retrieval, stable evidence and bounded coverage. Verify denied modes do no work and forged metadata cannot expand access.
2. Grounding: deterministic citation/numeric checks, one repair, partial section replacement and total-failure handling. Verify unsupported output never reaches downloads.
3. Generation: optional built-in templates, section-by-section output, larger report-only token budget, placeholder replacement and readable rendering. Verify actual Markdown/DOCX output, escaping and bounds.
4. Delivery: update both APIs, chat/router, telemetry and Streamlit; document the external frontend contract. Verify complete/partial/failed API responses and optional uploads.
5. Review and run focused regressions, inspect generated DOCX, then start a loopback Streamlit demo and confirm its health.

Use the unittest commands in the capability map. Leave changes uncommitted. Preserve unrelated tasks/plan.md.

## Tasks

- [x] Sources and permission regression tests pass.
- [x] Grounding, repair and failure regression tests pass.
- [x] Template/provider regression tests pass.
- [x] Both API and client contract tests pass.
- [x] Review, compilation, diff checks and demo startup complete.

## Verification 2026-10-29

- 26 report tests, 9 standalone API tests and 7 Streamlit client tests pass (42 total). Four analytics-agent contract tests also pass.
- Compilation and git diff --check pass. Reviewed authorization before source/model work, model-output bounds, DOCX expanded-size checks before decompression, report-only provider budgets/timeouts, source-specific citations and partial telemetry compatibility.
- A real configured LLM generated a complete report from synthetic evidence (100 demonstration units), with no validation issues. No live business document was sent for this smoke check.
- Authenticated production route contract tests cover complete/partial/failed downloads and employee restrictions. Live Docker API smoke verified existing viewer sign-in, analytics denial and invalid-source rejection.
- Streamlit AppTest verified live sign-in, optional-template Report controls, enabled generation with a question and no upload, and sign-out. Backend and Streamlit health checks pass.
- Rebuilt backend-api with local changes. Docker backend-api, embeddings, reranker and document-processing services are healthy. Streamlit is running at http://127.0.0.1:8501 against http://127.0.0.1:8000. Sign in with an existing configured demo account.
- DOCX tests verify heading/paragraph/list order, placeholder replacement, table structure, source appendix and template-free output. Visual rendering through the installed Word automation hung; its task-owned Word and renderer processes were stopped and the temporary fixture removed. No visual layout approval is claimed.

## Existing unrelated failures

Broader runs exposed issues confirmed in the unchanged HEAD implementations: test_agents cannot import missing _financial_retrieval_query; two test_llm_provider cases call missing caption_image; one benchmark test expects citation errors to be transient but the existing classifier does not do that. These four issues were not changed or suppressed. The broad suite is not green.

## Remaining boundaries

### Clarification follow-up

SQL planner clarification now stops collection and is preserved in report/chat results and both download APIs. The demo displays the actual clarification instead of a generic 503/section-failure list. Regression: 28 report tests, 8 Streamlit tests and 9 standalone API tests pass (45 total). Rebuilt/restarted the local backend and replayed the screenshot's Vietnamese question with combined sources: HTTP 422, code clarification_required, actual question preserved. The planner asks for the returns definition and whether it should be computed independently because sales/returns lack an approved direct join. Backend services and Streamlit remain healthy. No default meaning for ambiguous returns was invented.

Grounding is deterministic citation/numeric checking, not semantic fact certification. Retrieval is bounded and not exhaustive; ambiguous numbers/conversions can be withheld. The external Vercel frontend is unchanged; integration instructions are in docs/technical/report-agent.md. No dependencies, schema migrations, production deployment or commits were added.
