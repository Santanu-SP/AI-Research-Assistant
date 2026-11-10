#!/bin/sh
# Usage: docker-entrypoint.sh api|worker|migrate|<any command>
set -eu
cd /app

case "${1:-api}" in
  api)
    if [ "${RUN_MIGRATIONS:-true}" = "true" ]; then
      alembic upgrade head
    fi
    # One process: the rate limiter and the in-process worker live in memory.
    # Scale out with more containers plus WORKER_ENABLED=false and a worker service.
    exec uvicorn app.main:app --app-dir backend \
      --host 0.0.0.0 --port "${PORT:-8000}" \
      --proxy-headers --forwarded-allow-ips="${FORWARDED_ALLOW_IPS:-127.0.0.1}" \
      --no-server-header
    ;;
  worker)
    cd /app/backend
    exec python -m app.worker
    ;;
  migrate)
    exec alembic upgrade head
    ;;
  *)
    exec "$@"
    ;;
esac
