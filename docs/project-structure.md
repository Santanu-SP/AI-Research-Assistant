# Project structure

The repository is a local RAG application: a FastAPI backend, a React frontend, and PostgreSQL when retrieval is enabled. SQLite is enough for the ordinary test suite.

## Backend

`backend/app/` is the import root (`uvicorn app.main:app --app-dir backend`).

- `api/` — FastAPI routes and the dependencies they share. Route modules stay thin and call services.
- `core/` — settings loaded from the repository-root `.env`, the shared error envelope and handlers, logging setup, ASGI middleware (request IDs, security headers, body size limits) and the in-process rate limiter.
- `db/` — engine, sessions, and column types.
- `domain/` — enums and the parser-neutral document contracts. These modules do not import FastAPI or LlamaIndex.
- `models/` — SQLAlchemy tables.
- `schemas/` — Pydantic request and response models. Field aliases are the JSON the frontend already uses.
- `services/` — the work behind the routes, split by job:
  - `auth/` — password sessions (`sessions.py`) and Google sign-in (`google.py`).
  - `documents/` — upload records (`records.py`) and on-disk files (`storage.py`).
  - `ingestion/` — the indexing pipeline, the Docling adapter, the explicit pypdf fallback, and PDF text helpers.
  - `jobs/` — the `background_jobs` queue (`queue.py`, claimed with `FOR UPDATE SKIP LOCKED`) and the worker (`worker.py`) that ingests documents, runs research jobs, retries failures and recovers interrupted work.
  - `rag/` — embeddings, hybrid retrieval, reranking, grounded generation, evidence selection, citation checks, and the query that ties them together.
  - `research/` — projects, research runs, and saved reports.
- `backend/app/worker.py` — `python -m app.worker`, the worker without the HTTP API.
- `backend/alembic/` — migrations. The current head is `0013_background_jobs`.
- `backend/tests/` — unit and API tests. PostgreSQL and Docling tests are opt-in.
- `backend/scripts/` — manual checks that load the local reranker and Ollama model.
- `backend/data/` — local SQLite files and uploads. Only `.gitkeep` is committed.

## Frontend

- `src/app/` — router (lazy-loaded pages behind an error boundary) and the auth, project, and toast providers.
- `src/pages/` — route screens.
- `src/components/` — layout, landing page, and the project, document, research, and source UI.
- `src/services/` — typed `fetch` clients. They are the only place that builds API URLs.
- `src/hooks/` — project document loading and `useBackoffPolling`, which polls while documents are processing, backs off up to 30 s and stops after 15 minutes.
- `src/types/` — TypeScript copies of the API payloads.
- `src/test/` — Vitest setup and most component tests. A few auth tests sit next to the page or service they cover.

## Request flow

```text
React page
  → src/services
  → FastAPI route
  → service module
  → SQLAlchemy
  → SQLite, or PostgreSQL with pgvector and full-text search
```

Document upload stores the file, enqueues a job and returns `202`; the worker continues through `services/ingestion`. A research question continues through `services/rag`. LlamaIndex is used to standardize parsed documents and nodes. PostgreSQL remains the only stored vector and keyword index.

## Not in this tree

PPTX and other file types, URL ingestion, DOI lookup, stricter structured generation, LangGraph, and Ragas are not implemented.

## Deployment files

- `backend/Dockerfile` and `backend/docker-entrypoint.sh` — non-root API/worker image with CPU PyTorch; runs `alembic upgrade head` before starting.
- `frontend/Dockerfile` and `frontend/nginx.conf` — static build served by unprivileged nginx with security headers, proxying `/api`.
- `docker-compose.yml` — PostgreSQL + pgvector, Ollama, API, optional worker, and web.
- `.github/workflows/ci.yml` and `.github/dependabot.yml` — CI and dependency updates.
