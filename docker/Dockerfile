FROM python:3.11-slim
WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        tesseract-ocr tesseract-ocr-eng tesseract-ocr-vie \
    && rm -rf /var/lib/apt/lists/* \
    && python -m pip install --no-cache-dir uv==0.12.13

COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --no-install-project --extra docling

COPY src ./src
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONPATH="/app/src" \
    RERANKER_PRELOAD="1" \
    PORT="8000"
EXPOSE 8000
CMD ["sh", "-c", "exec uvicorn src.app.main:app --host 0.0.0.0 --port \"${PORT:-8000}\""]
