FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app/backend \
    APP_ENVIRONMENT=production

WORKDIR /app

# Install FFmpeg (audio/video ingestion) and TLS root certificates.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements-prod-lite.txt /app/backend/requirements-prod-lite.txt
RUN pip install --upgrade pip \
    && pip install -r /app/backend/requirements-prod-lite.txt

COPY alembic.ini /app/alembic.ini
COPY backend /app/backend

RUN useradd --create-home --shell /bin/bash appuser \
    && mkdir -p /app/backend/data/uploads \
    && chown -R appuser:appuser /app

USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD python -c "import os, urllib.request; port = os.environ.get('PORT', '8000'); urllib.request.urlopen(f'http://127.0.0.1:{port}/api/v1/health', timeout=4)"

CMD ["sh", "-c", "alembic upgrade head && exec uvicorn app.main:app --app-dir backend --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips='*'"]
