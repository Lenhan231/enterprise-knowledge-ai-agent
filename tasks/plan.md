# Active initiative: Unified Agent Orchestration

The capability map and five module specs were approved on 2026-10-29.
The technical plan was approved on 2026-10-29:
[agent-orchestration-plan.md](agent-orchestration-plan.md).
The [task list](todo.md) records implementation, local demo verification, and remaining live acceptance gaps.

The prior Docker plan and verification record are preserved below.

# Backend Docker rebuild plan

Status: backend extraction implemented locally; final runtime verification is recorded below.

## Objective and scope

Deploy backend services only; the frontend remains on the teammate's Vercel deployment. Each independently running backend service gets its own Dockerfile. Compose remains the single place to connect those services. Preserve API contracts, authorization, indexed documents, private storage and database contents.

Branch: switched from QuocAn to main, fetched origin, and merged origin/main while preserving both histories. No reset or force push. Implementation changes remain uncommitted.

The existing main setup has one runtime web image with API, OCR, embeddings and reranking together, separate module-check images, an optional proxy and an optional local database. It does not run three services inside one Dockerfile. Separate Dockerfiles alone will not separate the Python runtime or reduce aggregate model memory.

## Implemented service boundaries

| Service | Responsibility | Dockerfile | Dependencies |
| --- | --- | --- | --- |
| backend-api | Public API, authentication, permissions, agent routing, retrieval SQL, analytics, reports, upload coordination | docker/Dockerfile.backend-api | Internal processing/inference services; existing Supabase and configured LLM providers |
| document-processing | Docling, Tesseract, document parsing and previews; no frontend | docker/Dockerfile.document-processing | CPU parser dependencies and parser model cache |
| embeddings | One shared embedding model for document indexing and query vectors | docker/Dockerfile.embeddings | Embedding model cache |
| reranker | One shared pinned BGE reranker | docker/Dockerfile.reranker | Reranker model cache |

Chunking and tokenization remain shared libraries, not standalone network services. Tokenization must use the same model configuration without loading a second inference model. Knowledge, analytics and report agents remain in the API; they are not separate processes today. Supabase remains external for PostgreSQL/pgvector, identity integrations and private document storage. No new database container is required for the deployment. Reconfirm the Vercel API URL and authentication/proxy behavior before cutover.

## Ordered implementation

1. **Establish baseline on main.** Fetch and inspect divergent commits; integrate without dropping local or teammate work. Inventory routes, environment variables, existing tests, Docker callers and deployment scripts. Record current image sizes and representative idle/chat/upload memory before comparing the replacement. Inspect existing containers and volumes before cleanup.
2. **Define internal contracts.** Use small HTTP boundaries for parsing, embedding and reranking with typed payloads, bounded input, finite timeouts and explicit failures. Keep public authentication and permission decisions in the API. Do not accept arbitrary filesystem paths or fetch arbitrary URLs. Internal services stay on a private Compose network. Keep the existing embedding model, dimensions, normalization, query/document prefixes, reranker revision and citation ordering.
3. **Extract document processing.** Reuse DocumentProcessor through an internal service. Update normal upload, parser handoff and isolated Upload Test paths, including previews. Keep persistence and document status transitions consistent; preserve parser output and existing retry behavior on failure. Retain the current synchronous public response contract initially, without introducing a queue.
4. **Extract model inference.** Add internal service entry points and clients behind EmbeddingService and BGEReranker. Update every runtime caller and relevant CLI/config path. Remove local model preloading and heavyweight runtime dependencies from the API only after verifying imports no longer require them. Keep one inference process per model service initially to avoid loading duplicate model copies.
5. **Build service-specific images.** Add backend-api, embeddings and reranker Dockerfiles; replace the document-processing check Dockerfile with its runtime definition. Split dependency installation by service using the existing dependency tooling and locked versions. Keep OCR/system packages in document-processing, CPU-only inference dependencies in model services, and evaluation/UI tooling out of runtime images. Add health/readiness checks, persistent model caches and a restricted build context without secrets, datasets or local caches.
6. **Replace the old orchestration.** Rewrite docker-compose.yml with the four backend services, readiness dependencies, restart policies, private internal ports and only the API exposed through the deployment's HTTPS ingress. Replace old module-check commands with checks against the replacement images. Remove docker/Dockerfile, docker/Dockerfile.chunking and obsolete Compose profiles after replacements pass. Review docker/nginx.conf: retain or replace only the ingress behavior actually required, including upload limits and timeouts.
7. **Preserve Vercel integration.** Keep existing public API URLs and response schemas. Exclude bundled dashboard/static UI from the backend image and remove its runtime static mounts/home-page dependency without deleting unrelated frontend source. Verify the teammate's actual frontend calls first. Configure the exact trusted frontend origin and preserve JWT/cookie behavior, CSRF protection, secure cookies and role restrictions. Never expose Supabase service secrets to Vercel browser code or internal inference ports publicly.
8. **Verify and document.** Update README.md, docs/deployment-guide.md, .env.example, .dockerignore, Docker-related scripts and affected tests. Validate Compose, build each image, run focused regression/contract tests and smoke the full backend. Test authenticated chat, analytics, reports, uploads, parser handoff, Upload Test, previews, retry embedding, citation identity, service failure and cache reuse after restart. Measure image size, idle RAM, peak chat RAM and peak upload RAM before recommending server capacity.
9. **Cut over and retire old Docker resources.** Publish separately tagged backend images if deploying through a registry. Point the Vercel backend configuration at the verified HTTPS API. Stop/remove only identified obsolete project containers and images once replacement checks pass, keeping a rollback image until cutover succeeds. Preserve database volumes, source documents and useful model caches. Do not use a global prune or docker compose down -v. Removing old setup files does not require deleting data volumes.

## Acceptance criteria

- One Dockerfile and one runtime process per proposed backend service; no frontend or Streamlit service.
- The API never loads local embedding, reranking or Docling models.
- Existing Vercel-facing API behavior and permission restrictions pass regression checks.
- Query/document embeddings and reranking remain compatible with the existing corpus; no reindexing solely for this packaging change.
- Internal services are private; startup failures and upstream timeouts are visible and bounded.
- Replacement Docker builds and end-to-end smoke checks pass before old setup removal.
- README, environment examples and deployment commands describe only the replacement setup.
- Database contents and private source files survive migration and restarts.
- Measured memory and image sizes are reported; no promised RAM reduction based solely on splitting containers.

## Limits and unresolved details

The Vercel deployment, current remote main, production ingress and representative runtime memory have not been verified. This is a proposed boundary map and implementation plan, not an implementation. No Kubernetes, message broker, per-agent services, frontend deployment or database migration is included.

## Local implementation and verification (2026-10-28)

- Replaced the monolithic and module-check Dockerfiles with four backend runtime Dockerfiles; Compose starts backend-api, document-processing, embeddings and reranker. Optional stock Nginx ingress is retained.
- Existing public API routes and role checks remain in the API. Frontend static files are excluded from every Docker build context. The API installs no PyTorch or Docling; model services use CPU-only PyTorch.
- Internal endpoints require a private shared token, publish no host ports, enforce bounded batches/documents and use finite HTTP timeouts. The token was generated in the existing ignored local .env without printing its value.
- Embedding query/document prefixes, E5 normalization/dimensions, pinned model revisions and stable reranker ordering are preserved. A mismatched embedding model fails explicitly.
- Upload, parser handoff, Upload Test and CLI callers use the existing shared boundaries. Parser preview bytes round-trip over internal HTTP; persistence and authorization remain at their original layer.
- Reused the original Hugging Face model volume. Added a persistent Docling cache, including its separate DOCLING_CACHE_DIR. Preserved the old database volume and original documents.
- Removed the stopped legacy web, app and db containers using docker rm without -v. Old images remain available for rollback; no global image/cache/volume prune was run.
- Updated README, deployment guide, environment example, build context exclusions, Nginx upstream/timeouts, CI commands and the latency sampler's container names.
- All four images built. The parser build checks OpenCV and Docling imports to catch missing native libraries. Compose validates, and all four backend containers reached healthy status.
- 20 focused tests pass: private-service contracts/authentication, embedding batching/model checks, parser delegation/previews, remote reranking, existing embedding behavior, API startup and tokenization. Python compilation and git diff --check pass.
- Live checks passed: backend-only root, static-file exclusion, Nginx health/configuration, login/session, viewer upload restrictions, chat input validation, real 768-dimensional normalized query/document embeddings, real pinned BGE scores, Markdown parsing and an authenticated knowledge-chat HTTP 200.
- Current main has no /ws/ask handler; its frontend uses /api/agents/chat. CI's stale WebSocket smoke was replaced with authenticated HTTP/input validation. No new WebSocket endpoint was added.
- Existing unrelated test modules cannot import removed code: test_translated_hybrid_rerank imports missing test_translated_hybrid; document-processing tests import missing document_processing.pipelines.built_in; test_app_request_models imports missing AskRequest. The complete legacy suite is not green. The one-dimensional embedding fixture now explicitly uses a fake model rather than production E5.
- No DigitalOcean resources were created, registry images published, Vercel settings changed, or live database schema/data migrated. This local migration does not establish production capacity or OCR/concurrent-user peak RAM.

### Final runtime checks

- The rebuilt parser passed a real scanned-PDF OCR request through the API container's HTTP client. OpenCV native libraries are present, and Docling uses the persistent /models/docling cache. The small fixture caused a harmless Tesseract orientation warning; text extraction succeeded.
- All four backend services are running locally and healthy. The optional Nginx ingress is also running on loopback port 8080; the direct API is on loopback port 8000.
- A sampled combined memory reading was approximately 2.8 GiB before OCR and 4.2 GiB after OCR/model warm-up. These are snapshots, not peak-load figures or a comparison against the retired stack. No server-size guarantee follows from them.
- API/model service embedding model and sequence-length configuration now use the same Compose values, including when supplied from the shell.
- Cloud deployment and teammate Vercel cutover remain unperformed. Old images/build cache were retained; the explicitly requested old containers and obsolete setup files were removed.
