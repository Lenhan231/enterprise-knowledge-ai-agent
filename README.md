Enterprise Knowledge AI Agent (Scaffold)

Minimal scaffold for the Enterprise Knowledge AI Agent project.

Quick start

1. Create a Python virtualenv and install dependencies:

```bash
uv sync
```

2. Run the FastAPI app:

```bash
uvicorn src.app.main:app --reload --port 8000
```

Open `http://localhost:8000` for the Enterprise Intelligence dashboard.
The UI currently reads mock data from `GET /api/dashboard`; keep that response
shape when replacing the mock implementation with live analytics services.

Project layout

- src/app: FastAPI application entrypoint and API routes
- src/core: document processing, retrieval, and agent router stubs
- docker-compose.yml: local dev services (Postgres)

See the source files for implementation stubs.

## Dataset

The reproducible Apple corpus workflow is documented in
[`data/README.md`](data/README.md). Raw PDFs and generated Markdown are not
committed.
