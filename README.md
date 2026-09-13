Enterprise Knowledge AI Agent (Scaffold)

Minimal scaffold for the Enterprise Knowledge AI Agent project.

Quick start

1. Create a Python virtualenv and install dependencies:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

2. Run the FastAPI app:

```bash
uvicorn src.app.main:app --reload --port 8000
```

Project layout

- src/app: FastAPI application entrypoint and API routes
- src/core: document processing, retrieval, and agent router stubs
- docker-compose.yml: local dev services (Postgres)

See the source files for implementation stubs.
