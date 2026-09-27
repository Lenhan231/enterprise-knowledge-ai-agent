FROM python:3.11-slim
WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        tesseract-ocr tesseract-ocr-eng tesseract-ocr-vie \
    && rm -rf /var/lib/apt/lists/* \
    && python -m pip install --no-cache-dir uv==0.12.13

COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --no-install-project

COPY src ./src
COPY data/vietnam_enterprises/manifest.json ./data/vietnam_enterprises/manifest.json
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONPATH="/app/src"
EXPOSE 8000
CMD ["uvicorn", "src.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
