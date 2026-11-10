# AI Research Assistant

An evidence-first workspace for searching uploaded research documents and
producing locally generated answers with traceable source excerpts.

## Current capabilities

- FastAPI backend and React/Vite frontend.
- Password authentication, optional Google OAuth, revocable cookie sessions,
  and user-owned data.
- Private research projects with CRUD, ownership checks, and soft archiving.
- PDF and DOCX validation, local storage, SHA-256 duplicate detection, Docling
  parsing, and LlamaIndex Document/Node normalization.
- Token-aware `HybridChunker` nodes with stable IDs, page ranges, sections,
  tables, captions, and canonical metadata.
- Qwen3 embeddings and reranking, PostgreSQL pgvector search, indexed full-text
  search, and Reciprocal Rank Fusion.
- Local grounded generation through `qwen3.5:9b` in Ollama, evidence
  sufficiency checks, sentence-level citation validation, and persisted reports.
- A PostgreSQL-backed job queue: uploads return `202 Accepted` and a worker
  parses and indexes them off the request path, with retries and recovery of
  jobs interrupted by a crash or restart.
- Production-safe defaults: secure cookies, Origin checks on unsafe requests,
  security headers, request size limits, rate limiting, and hidden API docs.

The production retrieval path requires PostgreSQL with pgvector. SQLite is
kept for ordinary unit tests and non-retrieval development workflows.

## Repository layout

```text
backend/app/
  api/            HTTP routes and request dependencies
  core/           settings, errors, logging, middleware, rate limiting
  db/             SQLAlchemy engine and sessions
  domain/         enums and parser-neutral contracts
  models/         tables
  schemas/        request and response models
  services/
    auth/         password sessions and Google sign-in
    documents/    upload records and local file storage
    ingestion/    Docling, the pypdf fallback, and chunking
    jobs/         database job queue and the background worker
    rag/          hybrid retrieval, reranking, and generation
    research/     projects, research runs, and reports
backend/alembic/  schema migrations
backend/tests/    API and service tests
frontend/src/
  app/            router and auth, project, and toast state
  components/     layout and feature UI
  hooks/          data loading and polling with backoff
  pages/          route screens
  services/       typed API clients
  types/          response shapes shared with the API
docs/             setup notes and design records
```

## Architecture

```text
Authenticated user and optional owned project
  → PDF/DOCX validation and SHA-256 duplicate check
  → 202 Accepted + background job (background_jobs table)
  → worker: Docling
  → LlamaIndex Document + DoclingNodeParser/HybridChunker
  → canonical document and node contracts
  → Qwen3 embeddings
  → PostgreSQL + pgvector + indexed FTS
  → Reciprocal Rank Fusion
  → Qwen3 reranker
  → evidence selection
  → Ollama qwen3.5:9b
  → citation mapping and persisted report
```

PostgreSQL remains the source of truth. LlamaIndex standardizes parsed
documents and nodes; it does not create another vector store.

## Local setup

See [docs/development.md](docs/development.md) for backend, database, Ollama,
frontend, migration, and testing instructions.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r backend/requirements-dev.txt
cp .env.example .env
alembic upgrade head
uvicorn app.main:app --app-dir backend --reload
```

In another terminal:

```bash
cd frontend
npm install
npm run dev
```

## Main API areas

- `/api/v1/auth`: registration, login, logout, logout from every device
  (`/auth/logout-all`), session restoration, and Google OAuth when configured.
- `/api/v1/projects`: private project creation, listing, updates, and archiving.
- `/api/v1/documents`: compatibility upload/list/read/delete operations across
  the authenticated user's documents, plus `POST /documents/{id}/retry` for
  failed documents.
- `/api/v1/projects/{project_id}/documents`: exact project-scoped PDF/DOCX
  upload and listing.
- `/api/v1/research`: research CRUD, project filters, progress, reports, hybrid
  retrieval inspection, grounded query execution (`/research/query`, in the
  request) and background research runs (`/research/jobs`, returns 202).
- `/api/v1/health/live` and `/api/v1/health/ready`: liveness, and readiness
  that checks the database, pgvector and the Ollama model.

Existing records with `project_id = NULL` remain supported. Project-scoped
retrieval uses an exact project filter and excludes null-project and other
project documents.

## Supported and deferred scope

Implemented file formats are PDF and DOCX. The pypdf path is an explicitly
configured PDF-only fallback; Docling is the default parser.

Deferred to later pull requests:

- PPTX, HTML, Markdown, CSV, and spreadsheet ingestion
- secure URL ingestion
- DOI normalization and Crossref/OpenAlex integrations
- advanced metadata retrieval filters
- strict structured generation
- LangGraph orchestration and Ragas evaluation
- a shared (Redis) rate limiter for multi-process deployments

## Validation

```bash
pytest backend/tests
cd frontend
npm test -- --run
npm run typecheck
npm run lint
npm run build
```

CI (`.github/workflows/ci.yml`) runs the backend suite, the PostgreSQL +
pgvector integration suite including migration downgrade, the frontend lint,
typecheck, tests and build, and `pip-audit`, `npm audit` and a secret scan.

The PostgreSQL integration test requires a dedicated disposable database named
with `test` through `POSTGRES_TEST_DATABASE_URL`. Never point it at shared
Supabase or production data.

## Product principles

- Evidence comes before explanation.
- Missing metadata and citations are never invented.
- Project and user ownership is enforced in backend queries.
- Insufficient evidence produces an explicit bounded response.
- The assistant supports human research judgment; it does not replace it.

## License

This project is licensed under the terms in [LICENSE](LICENSE).
