# syntax=docker/dockerfile:1.7
# Build from the repository root:  docker build -f backend/Dockerfile .
FROM python:3.11-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    HF_HOME=/models \
    APP_ENVIRONMENT=production \
    DOCUMENT_UPLOAD_DIR=/data/uploads

# Docling's PDF and OCR stack needs a few shared libraries.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# CPU-only PyTorch. Override TORCH_INDEX_URL to build a CUDA image.
ARG TORCH_INDEX_URL=https://download.pytorch.org/whl/cpu
COPY backend/requirements.txt backend/requirements.txt
RUN pip install --extra-index-url "${TORCH_INDEX_URL}" -r backend/requirements.txt

COPY alembic.ini pyproject.toml ./
COPY backend/alembic backend/alembic
COPY backend/app backend/app
COPY backend/docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh

RUN useradd --system --uid 10001 --home-dir /app --shell /usr/sbin/nologin app \
    && mkdir -p /data/uploads /models \
    && chown -R app:app /data /models \
    && chmod 0755 /usr/local/bin/docker-entrypoint.sh

USER app
VOLUME ["/data", "/models"]
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8000/api/v1/health/live || exit 1

ENTRYPOINT ["docker-entrypoint.sh"]
CMD ["api"]
