# AI Research Assistant

An evidence-first research workspace for ingesting multimodal documents and URLs, running hybrid vector + keyword retrieval on PostgreSQL (`pgvector`), and generating grounded reports with sentence-level citations across local Ollama models, a centralized multi-provider LLM router, or user-supplied (BYOK) API keys.

## Current capabilities

- **Authentication & Sessions**: Email/password registration and login, revocable HTTP-only cookie sessions with a sliding inactivity timeout (`AUTH_INACTIVITY_DAYS=3`, hard limit `AUTH_SESSION_DAYS=7`), `POST /auth/logout-all`, and optional popup Google OAuth with clock-skew tolerance, clean error redirects, and disabled-account protection.
- **Private Projects & Responsive Workspace UI**: User-owned research projects with CRUD and soft archiving; tabbed `Ask` and `Documents` views preserved across tab switches; sidebar research history grouped by date with live search (`Cmd/Ctrl+K`), rename, and delete; collapsible desktop icon rail; in-place retry for failed runs (`POST /research/{id}/retry`); 15s duplicate-submission guard; session-scoped SWR caching (`SessionDataCacheContext`) to prevent redundant reload skeletons across navigation; and light/dark/system themes.
- **Multimodal & URL Ingestion**:
  - **Files**: `.pdf`, `.docx`, `.pptx`, `.xlsx`, `.html`/`.htm`, audio (`.mp3`, `.wav`, `.m4a`, `.ogg`, `.flac`, `.webm`), video (`.mp4`, `.mov`, `.mkv`, `.webm`), and images (`.png`, `.jpg`, `.jpeg`, `.webp`, `.tiff`, `.tif`).
  - **URLs**: YouTube transcripts (`YouTubeIngestionAdapter`) and public web pages (`r.jina.ai` + BeautifulSoup SSRF-guarded fallback).
  - **Parsing & Deduplication**: Default Docling + LlamaIndex `Document` / `HybridChunker` normalization (preserving page ranges, sections, tables, and captions), explicit `pypdf` PDF-only fallback, SHA-256 duplicate checks scoped per user and project, and retry/replacement of failed uploads.
- **Hybrid Retrieval & Adaptive RAG Pipeline**:
  - **Embeddings**: Local `Qwen/Qwen3-Embedding-0.6B` (1,024-dim, offline-first cache + LRU query embedding cache) or Cloudflare Workers AI (`@cf/baai/bge-m3`).
  - **Retrieval & Reranking**: Single-round-trip PostgreSQL `pgvector` cosine similarity + GIN-indexed `tsvector` full-text search combined via Reciprocal Rank Fusion (`RRF`), ranked with `Qwen/Qwen3-Reranker-0.6B`, Jina Reranker, Cloudflare `@cf/baai/bge-reranker-base`, or fast lexical scoring.
  - **Adaptive Fast-Path & Grounding**: `Quick`, `Standard`, and `Deep` research depths (`ADAPTIVE_FAST_PATH_ENABLED`), direct synchronous fast-path for quick queries (`/research/query`), prompt-injection sanitization, evidence sufficiency checks, sentence-level citation validation, and persisted reports.
- **Multi-Provider LLM Router, BYOK & Fair-Share Quota**:
  - Supports local **Ollama** (`qwen3.5:9b` + dynamic detection of installed Ollama generation models), an 8-provider cloud catalog (**Gemini**, **OpenRouter**, **Cerebras**, **Mistral**, **Groq**, **OpenAI**, **Claude**, **Grok**) with circuit breakers, sticky failover, and shared keep-alive HTTP pooling, plus optional client-side AI helpers (Puter.js / WebLLM).
  - Encrypted per-user BYOK API keys (`API_KEY_ENCRYPTION_SECRET`), persisted per-provider model selections and local-fallback toggle, reasoning effort selector (`low`, `medium`, `high`), and atomic daily shared quota enforcement (`LLM_DAILY_REQUESTS_PER_PROVIDER`, exempting user BYOK keys and local Ollama).
- **Cloud Storage & Background Jobs**: Pluggable `local` or S3-compatible Cloudflare **R2** object storage with SigV4 presigned URLs (`/documents/{id}/signed-url`), plus `202 Accepted` background ingestion and `/research/jobs` backed by the PostgreSQL `background_jobs` table (`FOR UPDATE SKIP LOCKED`, stale-job crash recovery) or optional **Celery + Redis** (`QUEUE_BACKEND=celery`).
- **Observability & Production Hardening**: Execution telemetry, Ragas-style RAG evaluation helpers, `/telemetry/summary`, optional Langfuse reporting, `X-Request-ID` structured logs, secure cookies, `Origin`/`Referer` enforcement, CORS rules (including `PUT` and mixed `localhost`/`127.0.0.1` loopback support), security headers, streaming `413` body limits, rate limiting, and startup secret validation (`validate_production_startup()`).

The production retrieval path requires PostgreSQL with `pgvector` (Neon PostgreSQL or self-hosted). SQLite is kept for fast unit tests and non-retrieval local development.

## Repository layout

```text
backend/app/
  api/            HTTP routes, router registration, and request dependencies
  core/           settings, startup validation, errors, logging, middleware, rate limiting
  db/             SQLAlchemy engine, Neon/Supabase pool tuning, and session helpers
  domain/         enums and framework-neutral ingestion/scholarly contracts
  models/         ORM tables (users, projects, documents, research, jobs, api_keys, usage, telemetry)
  providers/      CentralizedLLMRouter and Gemini/OpenRouter/Cerebras/Mistral/OpenAI/Claude/Grok/Ollama adapters
  schemas/        Pydantic request and response models
  services/
    auth/         cookie sessions, sliding inactivity, password hashing, and Google OAuth
    documents/    upload records, local disk and Cloudflare R2 storage, presigned URLs
    ingestion/    Docling, pypdf fallback, Office/HTML, audio, video, vision, web, and YouTube parsers
    jobs/         PostgreSQL SKIP LOCKED queue, background worker, maintenance recovery, Celery option
    observability/ telemetry tracking, fair-share usage quota ledger, Ragas-style RAG evaluation
    rag/          embeddings, pgvector/FTS/RRF retrieval, reranking, evidence, generation, citations
    research/     projects, research runs, retry/duplicate guards, and persisted reports
  worker.py       standalone background worker entrypoint (`python -m app.worker`)
backend/alembic/  schema migrations (`0001_backend_foundation` through `0016_model_prefs_usage_quota`)
backend/scripts/  model verification utilities and `migrate_supabase_to_neon.py`
backend/tests/    API, RAG, auth, quota, evaluation, and PostgreSQL/Docling integration tests
frontend/src/
  app/            router (`resetKey` ErrorBoundary), Auth, Project, ResearchHistory, SessionDataCache, Toast contexts
  components/     landing, layout (`AppLayout`, sidebar rail), auth, documents, projects, research (`ModelControlBar`, `CitationPanel`, `RunRecovery`), sources
  hooks/          SWR document library (`useDocumentLibrary`), actions, backoff polling
  pages/          route screens (Landing, Login, Register, GoogleAuthComplete, NewResearch, Projects, ProjectWorkspace, ResearchProgress, ResearchReport, Settings)
  services/       typed API clients and optional client-side AI service
  types/          TypeScript API response contracts
docs/             setup, project structure, and handoff guides
```

## Architecture

```text
Authenticated user + owned project (or unscoped library)
  → File upload (.pdf/.docx/.pptx/.xlsx/.html/audio/video/image) or URL (web/YouTube)
  → SHA-256 project-scoped deduplication + local or Cloudflare R2 storage
  → 202 Accepted + job dispatch (PostgreSQL `background_jobs` or Celery/Redis)
  → Worker: Docling/LlamaIndex HybridChunker or multimodal/URL extractor
  → Local Qwen3-Embedding-0.6B or Cloudflare Workers AI `@cf/baai/bge-m3`
  → Neon / PostgreSQL (`pgvector` cosine + GIN `tsvector` FTS + Reciprocal Rank Fusion)
  → Adaptive Fast-Path: Lexical / Qwen3-Reranker-0.6B / Jina / Cloudflare BGE reranker
  → Evidence sufficiency + prompt-injection sanitization
  → Centralized LLM Router (8 cloud providers + BYOK + fair-share quota) or local Ollama
  → Sentence-level citation validation + persisted research report
```

PostgreSQL remains the single source of truth for vectors, full-text indexes, job state, user preferences, and reports; LlamaIndex provides document/node normalization without creating a second vector store.

## Local setup

See [docs/development.md](docs/development.md) for Neon PostgreSQL, Cloudflare R2, Ollama, Google OAuth, Celery/Redis, migration, and troubleshooting guides.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r backend/requirements-dev.txt
cp .env.example .env
alembic upgrade head
uvicorn app.main:app --app-dir backend --reload
```

Optional standalone worker (otherwise the in-process worker thread runs when `WORKER_ENABLED=true`):

```bash
PYTHONPATH=backend python -m app.worker
```

In another terminal for the frontend:

```bash
cd frontend
npm install
npm run dev
```

> **Google OAuth on localhost**: Open the app on the same loopback host (`localhost` or `127.0.0.1`) configured in `FRONTEND_URL` and `GOOGLE_REDIRECT_URI` in `.env` so `SameSite=Lax` session cookies returned by `/api/v1/auth/google/callback` stay aligned with API requests.

## Main API areas (`/api/v1`)

- `/auth`: `POST /register`, `POST /login`, `POST /logout`, `POST /logout-all`, `GET /me`, and Google OAuth (`/google/status`, `/google/start`, `/google/callback`).
- `/auth/api-keys`: per-user encrypted BYOK key CRUD (`GET ""`, `PUT /{provider}`, `DELETE /{provider}`), `GET /models-status` (server router + local Ollama models + user preferences), `GET /usage` (daily fair-share cap & per-model breakdown), `POST /local-fallback`, and `POST /provider-model`.
- `/projects`: private project creation, listing/search/archive filters, updates, and soft archiving.
- `/documents`: user-scoped upload (`POST`), URL ingestion (`POST /url`), list/filter (`GET`), metadata/delete, inline file streaming (`GET /{id}/file`), R2 presigned downloads (`GET /{id}/signed-url`), `POST /{id}/reembed`, and failed document retry (`POST /{id}/retry`).
- `/projects/{project_id}/documents`: exact project-scoped file upload, URL ingestion (`/url`), and document listing.
- `/research`: research CRUD, project filtering, progress polling (`/status`), persisted reports (`/report`), raw hybrid retrieval inspection (`POST /retrieve`), grounded synchronous fast queries (`POST /query`), background research jobs (`POST /jobs`), and in-place retry (`POST /{id}/retry`).
- `/jobs/{job_id}` and `/telemetry/summary`: background job status tracking and pipeline latency/cache/token telemetry.
- `/health`, `/health/live`, and `/health/ready`: liveness and dependency readiness checks (database, `pgvector`, and Ollama or LLM router availability).

Existing records with `project_id = NULL` remain supported. Project-scoped retrieval applies an exact `project_id` SQL filter and excludes null-project, foreign, and archived project documents.

## Database schema history (Alembic)

- `0001`–`0006`: core foundation, research runs, documents, progress stages, report sources/citations, and chunk/ingestion metadata.
- `0007`–`0009`: user accounts, sessions, ownership foreign keys, Google OAuth state table, `pgvector` HNSW index, and grounded citation evidence columns.
- `0010`–`0012`: private research projects (`ResearchProject`), project scoping, trigger-maintained `tsvector` + GIN FTS index, and canonical source/node provenance metadata.
- `0013`: persistent `background_jobs` table (`FOR UPDATE SKIP LOCKED`) and lease/heartbeat recovery columns.
- `0014`–`0015`: Neon/multimodal extensions, user BYOK key table, telemetry events, widened `file_type`/`source_type`/`content_level` enums and `CHECK` constraints.
- `0016_model_prefs_usage_quota`: persisted user provider/model preferences, `local_fallback` setting, and atomic daily quota ledger (`daily_usage_quotas`).

## Supported vs remaining deferred scope

### Implemented

- Files: PDF, DOCX, PPTX, XLSX, HTML/HTM, audio (`mp3`, `wav`, `m4a`, `ogg`, `flac`, `webm`), video (`mp4`, `mov`, `mkv`, `webm`), and images (`png`, `jpg`, `jpeg`, `webp`, `tiff`, `tif`).
- URLs: YouTube video transcripts and public web articles (SSRF-guarded).
- Cloud & local deployment stack: Neon PostgreSQL + `pgvector`, Cloudflare R2 object storage, optional Celery/Redis workers, Cloudflare Workers AI / Jina adapters, 8-provider LLM router + BYOK + Ollama, and Ragas-style quality metrics in `observability/evaluation.py`.

### Deferred

- Plain text/Markdown/CSV direct file upload types (`txt`, `md`, `csv`) and structured metadata retrieval filter UI.
- Live Crossref / OpenAlex scholarly API connectors and automated DOI resolution (schema fields exist cleanly for future wiring).
- Schema-constrained (strict Pydantic) structured generation and LangGraph multi-agent orchestration.
- Shared multi-process (Redis) HTTP rate limiter and full email-verification workflow.

## Pull request evolution

Every PR merged into `main` (plus the current stack) shaped the system as follows:

| PR(s) | Milestone & Key Additions |
|---|---|
| **#1, #3–#6** | Repo README update (#1), PRD backend starter (#3), core CRUD backend foundation (#4), initial React/Vite frontend (#5), and developer onboarding guide (#6). *(PR #2 closed on branch rename.)* |
| **#7–#16** | Research lifecycle/progress API (#7, #12), loading & UX states (#8, #11), animated canvas background (#9), real FastAPI documents/research/report/citation wiring & mock data removal (#10, #13–#16). |
| **#17–#19** | PDF upload validation, chunking, extraction pipeline, and document library UX (#17–#19). |
| **#20–#25** | Cookie-session auth & user ownership (#20), Google OAuth + Qwen3/pgvector/FTS/RRF hybrid retrieval (#21), popup OAuth & public landing page (#22), grounded local RAG via Ollama + citations (#23), landing spacing/palette fixes (#24–#25). |
| **#26–#30** | Local auth without Google OAuth (#26), directory-independent `.env` loading (#27), popup OAuth completion messaging (#28), LAN CORS & auto API hostname detection (#29), and TLS Supabase/PostgreSQL URL configuration (#30). |
| **#31–#32, #35** | Private `ResearchProject` scoping, Docling + LlamaIndex `HybridChunker`, canonical metadata, and `tsvector` GIN FTS (`0010`–`0012`, #31); full project Research Workspace UI (#32); backend service package reorganization into cohesive domain modules (#35). *(PRs #33–#34 closed without merge.)* |
| **#36** | Production security & reliability hardening: `background_jobs` queue (`0013`) with crash recovery, async `get_db`, Origin checks, streaming `413` limits, rate limiting, prompt-injection delimiters, citation dropping, `logout-all`, and CI `backend-postgres` / `security` jobs. |
| **#37–#39** | Design-token & Sage/Cream UI overhaul (#37), date-grouped sidebar research history with search/rename/delete and `/settings` (#38), and workspace-first document library embedded directly in Projects & New Research (#39). |
| **#40–#42** | Neon PostgreSQL + Cloudflare R2 + multimodal parsers + Celery/Redis option + centralized free-tier LLM router & evaluation helpers (`0014`–`0015`, #40); `cryptography`/`pillow` CVE upgrades & Gitleaks CI fix (#41); adaptive RAG fast-path, lexical reranking, query embedding LRU cache, pooled HTTP clients, sticky Gemini fallback, and synchronous quick queries dropping warm latency from ~40s to ~2.5s (#42). |
| **#43, #45** | Sliding 3-day inactivity / 7-day max sessions, 8 cloud LLM providers + dynamic Ollama probing, encrypted BYOK keys, persisted model/fallback preferences (`0016`), atomic fair-share daily quota enforcement, `ModelControlBar`, Settings usage breakdown (#43), and CI Alembic revision ID (`<= 32` chars) + Gitleaks cleanup (#45). |
| **#44** | In-place retry for failed runs (`POST /research/{id}/retry`), 15s duplicate-submission guard, collapsed desktop sidebar icon rail, and pointer/layout polish. |
| **#46** *(stack base)* | Fixed login on mixed `localhost`/`127.0.0.1` loopback hosts for `SameSite` cookies and added `PUT` to CORS allowed methods for BYOK API key updates. |
| **Latest PR (this branch)** | Google OAuth hardening (10s clock-skew leeway, SQLAlchemy rollback on callback errors, disabled-account rejection, explicit error messages, loopback-host `.env.example` note), React navigation/cache stability (`ErrorBoundary` `resetKey`, `SessionDataCacheContext` SWR caching, quiet document reloads, event-driven sidebar history updates, persistent `Ask`/`Documents` tabs, `ModelControlBar` effect stabilization, resilient session checks), and comprehensive `README.md` sync. |

## Validation

```bash
.venv/bin/pytest backend/tests -rs
cd frontend
npm test -- --run
npm run typecheck
npx tsc --noEmit -p tsconfig.test.json
npm run lint
npm run build
```

CI ([.github/workflows/ci.yml](.github/workflows/ci.yml)) runs:
1. `backend`: `pytest` unit/API suite under `APP_ENVIRONMENT=test`.
2. `backend-postgres`: PostgreSQL 16 + `pgvector` integration tests (`pytest -m postgres -v`) and `alembic upgrade head && alembic check`.
3. `frontend`: `eslint --max-warnings=0`, TypeScript app + test typechecks, Vitest suite, and Vite production build.
4. `security`: `pip-audit`, `npm audit --omit=dev`, and `gitleaks` secret scanning.

> **PostgreSQL test warning**: Integration tests require a dedicated disposable database whose name contains `test` configured via `POSTGRES_TEST_DATABASE_URL`. Never point it at shared Neon, Supabase, or production databases.

## Product principles

- Evidence comes before explanation.
- Missing metadata and citations are never invented.
- Project and user ownership is enforced in backend queries.
- Insufficient evidence produces an explicit bounded response.
- The assistant supports human research judgment; it does not replace it.

## License

This project is licensed under the terms in [LICENSE](LICENSE).
