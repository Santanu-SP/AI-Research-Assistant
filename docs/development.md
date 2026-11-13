# Developer Guide

## Prerequisites
- **Python**: 3.11 or newer
- **Node.js & npm**: Required for frontend development

## Clone and Setup Workflow
To get started with the project locally, clone the repository and navigate into the directory:

```bash
git clone <repository-url>
cd AI-Research-Assistant
```

## Backend Setup
The backend is built with FastAPI, SQLAlchemy, and Alembic.

1. **Create and activate a virtual environment:**
```bash
python3 -m venv .venv
source .venv/bin/activate  # On Windows use: .venv\Scripts\activate
```

2. **Install dependencies:**
```bash
python -m pip install -r backend/requirements-dev.txt
```

3. **Environment Configuration:**
Copy the example environment file:
```bash
cp .env.example .env
```
*Note on Safe Environment Variables*: The `.env.example` provides safe defaults for local development. Real `.env` files containing actual API secrets or production database credentials must **never** be committed to the repository. The `.gitignore` is configured to ignore `.env`.

4. **Database Migration:**
Run Alembic to apply the latest database schemas:
```bash
alembic upgrade head
```
*(Other useful Alembic commands used in the project: `alembic revision --autogenerate -m "message"` to create a new migration, and `alembic downgrade -1` to revert the last migration).*

5. **Running the FastAPI Server:**
```bash
uvicorn app.main:app --app-dir backend --reload
```

The backend loads the repository-root `.env` even when this command is launched from a different directory. Restart the backend after changing `.env`; settings are read when the process starts.

**`APP_ENVIRONMENT` defaults to `production`.** Production means secure cookies (an explicit `AUTH_COOKIE_SECURE=false` is refused), no Swagger/ReDoc, and no private-network CORS. `.env.example` sets `APP_ENVIRONMENT=development` for local work.

### Background jobs

Uploads and `POST /api/v1/research/jobs` write a row to `background_jobs` and return `202 Accepted`. By default the API process runs the worker in a thread (`WORKER_ENABLED=true`, `WORKER_THREADS=1`), so nothing extra needs to be started locally. To run the worker separately:

```bash
WORKER_ENABLED=false uvicorn app.main:app --app-dir backend   # API only
cd backend && python -m app.worker                            # worker only
```

Several workers can share one PostgreSQL database; jobs are claimed with `FOR UPDATE SKIP LOCKED`. Unexpected failures are retried with backoff up to `JOB_MAX_ATTEMPTS`; parse errors fail immediately. Every `MAINTENANCE_INTERVAL_SECONDS` the worker re-queues jobs that have been running longer than `JOB_STALE_AFTER_SECONDS` (for example after a crash), marks documents left in `processing` without a job as failed so they can be retried, and purges expired sessions and OAuth states. `INGESTION_MODE=inline` processes uploads inside the request instead; the test suite uses it.

Failed documents can be retried with `POST /api/v1/documents/{id}/retry`, or by uploading the same file again.

### Security defaults

- Unsafe requests (POST, PATCH, DELETE) must send an allowed `Origin`, or a `Referer` from an allowed origin; requests with neither get `403 origin_required`. Set `REQUIRE_ORIGIN_HEADER=false` only for trusted non-browser clients, and remember the session cookie is `SameSite=Lax`.
- JSON bodies over `MAX_JSON_BODY_BYTES` (1 MB) and uploads over `DOCUMENT_MAX_UPLOAD_BYTES` plus 1 MB are refused with `413` while streaming.
- Login, registration, Google sign-in, uploads and research queries are rate limited (`RATE_LIMIT_*`, `429` with `Retry-After`). The limiter is in memory per API process; behind a proxy that overwrites `X-Forwarded-For`, set `TRUST_FORWARDED_FOR=true`.
- Passwords must be at least 8 characters, use at least 4 different characters, and not be on the common-password list. Login does the same hashing work for unknown emails, so timing does not reveal registered addresses.
- At most `AUTH_MAX_SESSIONS_PER_USER` sessions are kept per user; `POST /api/v1/auth/logout-all` revokes all of them.
- Google sign-in only links to an existing account that has a verified email. Linking to an unverified password account removes that password and its sessions, so whoever registered the address first cannot keep access.
- Every error uses one shape: `{"error": {"code", "message", "details?"}}`. Responses carry `X-Request-ID`, which also appears in the logs (`LOG_JSON=true` for JSON lines).

### Health checks

- `GET /api/v1/health/live` (also `/health`) — the process is up.
- `GET /api/v1/health/ready` — `200` only when the database answers, the `vector` extension exists on PostgreSQL, and Ollama lists the configured model; otherwise `503` with per-check details.

Authentication uses random, database-backed session tokens in HTTP-only cookies. No static signing secret is needed. Sessions expire after `AUTH_SESSION_DAYS` (default 7). Set `AUTH_COOKIE_SECURE=true` when serving the API over HTTPS. For local development, use `localhost` for both the frontend and backend so the browser sends the session cookie. Existing document and research rows remain in the database after migration but have no owner; new accounts cannot see them.

## Google OAuth and local retrieval (PR 2)

Google sign-in is optional. Password registration and login work without Google credentials. To enable Google sign-in, add `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, and `GOOGLE_REDIRECT_URI` only to the root `.env`; the React app never receives the secret. The local callback URI is `http://localhost:8000/api/v1/auth/google/callback` and the authorized JavaScript origin is `http://localhost:3000`. Teammates should copy `.env.example` to `.env`; they must not copy another developer's private `.env`.

Retrieval requires PostgreSQL with the `vector` extension. SQLite remains supported for unit tests and non-retrieval PR 1 workflows only; it is deliberately not a vector-search substitute. Configure a PostgreSQL URL such as `DATABASE_URL=postgresql+psycopg://ara:ara@localhost:5432/ara`, create the extension as a superuser (`CREATE EXTENSION IF NOT EXISTS vector;`), then run `alembic upgrade head`.

With `EMBEDDING_ENABLED=true`, document indexing loads `Qwen/Qwen3-Embedding-0.6B` at the pinned `EMBEDDING_MODEL_REVISION` (the reranker uses `RERANKER_MODEL_REVISION`; remote model code is disabled unless `MODEL_TRUST_REMOTE_CODE=true`), creates normalized 1024-dimensional vectors in batches, and only marks documents indexed when vectors persist. Set `MODEL_DEVICE=auto` for CUDA/MPS/CPU detection, or use `mps`/`cpu` explicitly. Use `POST /api/v1/research/retrieve` with `{"query":"..."}` while authenticated to inspect user-scoped hybrid candidates. It performs pgvector cosine search plus PostgreSQL full-text search, then reciprocal-rank fusion and stable chunk-ID deduplication. It does not generate an answer.

## Grounded local RAG (PR 3)

The final research flow keeps embeddings in the existing Python service, loads `Qwen/Qwen3-Reranker-0.6B` once through SentenceTransformers, and sends only the selected evidence to the local Ollama model `qwen3.5:9b`. The FastAPI process never loads the 9B generation model directly.

Install and start Ollama, then verify the required model:

```bash
ollama pull qwen3.5:9b
ollama list
```

Run the real model smoke tests separately from the ordinary unit suite:

```bash
python backend/scripts/test_reranker.py
python backend/scripts/test_generation_model.py
```

The authenticated `POST /api/v1/research/query` endpoint accepts `{"query":"...","researchDepth":"standard"}`. It retrieves user-owned chunks from active (non-archived) projects, reranks them, applies the evidence-sufficiency gate, generates a grounded answer when appropriate, drops sentences that cite only unknown source IDs (an answer left with no valid citation becomes an insufficient-evidence result), and persists the completed report and source metadata. An insufficient-evidence answer is a successful, persisted result and deliberately skips Ollama.

`POST /api/v1/research/jobs` takes the same body, returns `202` with the research record straight away, and runs the query on the worker; the New Research page uses it and opens `/research/{id}/progress`.

Evidence is passed to the model inside `<evidence id="S1">…</evidence>` blocks with the grounding rules as the system prompt, and evidence text cannot close or open those tags, so instructions hidden in an uploaded document are treated as data. Ollama calls use a connect timeout (`GENERATION_CONNECT_TIMEOUT_SECONDS`) and retry connection errors and `502/503/504` up to `GENERATION_MAX_RETRIES` times.

## Projects and structured ingestion

Project APIs are available under `/api/v1/projects`. Project document uploads
use `/api/v1/projects/{project_id}/documents`; project research passes
`projectId` in the request. Both vector and keyword retrieval apply the
authenticated user and exact project inside SQL before top-K selection.

Docling is the default PDF/DOCX parser. LlamaIndex supplies Document and Node
contracts plus `DoclingNodeParser`; it does not create a vector store. The
configured Qwen tokenizer drives `HybridChunker` through
`DOCUMENT_CHUNK_MAX_TOKENS`. Set `DOCUMENT_INGESTION_BACKEND=legacy` only for
the explicitly logged pypdf PDF fallback.

Legacy null-project records remain available through compatibility endpoints.
A query without `projectId` searches all documents owned by that user, while a
query with `projectId` excludes null-project and other-project documents.

## Frontend Setup
The frontend is a React application built with TypeScript and Vite.

1. **Navigate to the frontend directory:**
```bash
cd frontend
```

2. **Install npm dependencies:**
```bash
npm install
```

3. **Environment Configuration:**
Copy the frontend environment template:
```bash
cp .env.example .env
```
Leave `VITE_API_BASE_URL` blank for ordinary local development. The app then uses the same hostname as the page with backend port `8000`—for example, `http://localhost:3000` calls `http://localhost:8000`, and `http://192.168.x.x:3000` calls `http://192.168.x.x:8000`.

4. **Running the Development Server:**
```bash
npm run dev
```

The Vite dev server listens on `127.0.0.1` only. For another device on the same private network, opt in explicitly: set `CORS_ALLOW_LOCAL_NETWORK=true` in `.env` (development only), start both servers on all interfaces, and open the frontend using the host computer's private IP:

```bash
uvicorn app.main:app --app-dir backend --host 0.0.0.0 --reload
cd frontend && VITE_DEV_HOST=0.0.0.0 npm run dev
```
 For Google sign-in, use `localhost` unless you have configured matching public HTTPS OAuth callback and frontend URLs in Google Cloud.

## Default Local URLs
- **Backend API Documentation (Swagger)**: http://127.0.0.1:8000/docs (outside production only)
- **Backend API Base**: http://127.0.0.1:8000/api/v1
- **Frontend Application**: http://localhost:3000

## Testing & Validation

**Running Backend Tests:**
From the root repository (with the virtual environment activated):
```bash
pytest
```

The PostgreSQL integration suite is destructive and must use a dedicated test
database whose name contains `test`:

```bash
export POSTGRES_TEST_DATABASE_URL='postgresql+psycopg://ara_test:ara_test@localhost:5432/ara_test'
pytest -m postgres backend/tests/test_postgres_retrieval_integration.py
```

Never point this variable at a shared Supabase or production database. Without
the variable, the test is intentionally reported as skipped.

The real Docling PDF test is also opt-in:

```bash
RUN_DOCLING_INTEGRATION_TESTS=1 pytest -m docling backend/tests/test_docling_pdf_integration.py
```

**Running Frontend Typecheck:**
From the `frontend/` directory:
```bash
npm run typecheck
```

**Running Frontend Lint:**
```bash
npm run lint
```

**Running Frontend Tests:**
```bash
npm test
```

**Running Frontend Production Build:**
To verify the production build locally (from the `frontend/` directory):
```bash
npm run build
```

**Dependency and secret checks** (also run in CI):
```bash
pip install pip-audit && pip-audit -r backend/requirements.txt
cd frontend && npm audit --omit=dev
gitleaks git . --redact
```
