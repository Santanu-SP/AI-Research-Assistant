# AI Research Assistant

An evidence-first, collaborative research workspace for ingesting multimodal files and URLs, discovering curated scholarly and news sources, running hybrid vector + keyword retrieval on PostgreSQL (`pgvector`), and generating grounded reports and follow-up Q&A with sentence-level citations across local Ollama models, a centralized multi-provider LLM router, or user-supplied (BYOK) API keys.

## Current capabilities

- **Authentication & Sessions**:
  - Email/password registration and login with Argon2 hashing, timing-safe unknown-email parity, revocable database-backed HTTP-only cookie sessions with a sliding inactivity timeout (`AUTH_INACTIVITY_DAYS=3`, hard limit `AUTH_SESSION_DAYS=7`, `AUTH_MAX_SESSIONS_PER_USER=10`), and `POST /auth/logout-all`.
  - Optional popup Google OAuth (`GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_REDIRECT_URI`) with 10s clock-skew tolerance, clean error redirects, and disabled-account protection.
  - Adaptive cookie policies (`SameSite=Lax` on local HTTP vs. `SameSite=None; Secure` on cross-origin HTTPS deployments) plus an optional **Cloudflare Pages same-origin `/api/*` proxy** (`frontend/functions/api/[[path]].ts`) that keeps session cookies first-party so browsers blocking third-party cookies (Brave Shields, Safari ITP, Firefox Strict, Incognito) remain signed in across reloads and OAuth popups.
- **Real-Time Multi-User Collaboration & RBAC**:
  - Role-based access control (`owner`, `editor`, `viewer`) across both **projects** and standalone **research chats**.
  - Share via direct email invite (`POST /projects/{id}/members`, `POST /research/{id}/members`) or expiring, optionally capped shareable links (`POST .../invites` → `/join/{token}` preview and acceptance flow in `JoinInvitePage`), managed in `ShareDialog`.
  - Optimistic concurrency locking (`version` field on projects and research runs returning `409 version_conflict` on stale edits).
  - Authenticated WebSocket rooms (`/api/v1/ws/projects/{project_id}`, `/api/v1/ws/research/{research_id}`) managed by `RealtimeHub` (authenticating via a short-lived DB session closed immediately before the socket loop so idle sockets never hold PostgreSQL pool slots), multi-tab collapsed `PresenceBar` with live activity states (`viewing`, `asking`, `typing`, `uploading`, `editing`), and live sync for file uploads/progress, research status, follow-up turns, and collaborator changes.
- **Projects, Library & Responsive Workspace UI**:
  - Owned and shared research projects with live file/report counters (`file_count`, `report_count`), soft archive/restore (`POST /projects/{id}/restore`), permanent deletion (`DELETE /projects/{id}/permanent`, preserving files and research in the user's library), and state-preserved `Ask` / `Files` tabs (`ProjectWorkspace`).
  - Dedicated `/library` screen with search, media-kind filters (`documents`, `images`, `audio`, `video`, `links`), live per-file preparation stages & progress (`reading`, `ocr`, `embedding` 0–100%, `saving`), and usage badges showing where each file is referenced.
  - Per-research document scoping (`research_documents` join table + `LibraryPickerDialog`): standalone research starts with zero files attached until chosen or auto-discovered.
  - Date-grouped sidebar research history with coherent 2–5 word chat titles (`MAX_CHAT_TITLE_WORDS=5`, filler/chatter filtering, minor-word casing, optional LLM refinement via `chat_title_llm_enabled`, automatic legacy title backfill on startup, and full research questions shown in sidebar tooltips and report headers), keyboard shortcuts (`Cmd/Ctrl+K` search, `Cmd/Ctrl+Shift+O` new research, `Cmd/Ctrl+Shift+S` toggle sidebar), rename, and undoable soft-delete (`DELETE /research/{id}` + `POST /research/{id}/restore`).
  - Live run controls and recovery: **Pause** (`POST /research/{id}/pause` with cooperative mid-run worker cancellation and calm **Resume** state), in-place **Edit question** (`POST /research/{id}/edit-question` across active, paused, failed, and completed runs without duplicating history), persisted model failure diagnostics (`failure_provider`, `failure_model`, `failure_type` — `quota`, `auth`, `timeout`, `unavailable`, `other`) with in-place retry (`POST /research/{id}/retry`) and one-click **Switch model** recovery (`RunRecovery`), 15s duplicate-submission guard, session-scoped SWR caching (`SessionDataCacheContext`), light/dark/system themes, and System Status readiness checks in `/settings`.
- **Multimodal, URL & Zero-RAM Ingestion**:
  - **Files**: `.pdf`, `.docx`, `.pptx`, `.xlsx`, `.html`/`.htm`, audio (`.mp3`, `.wav`, `.m4a`, `.ogg`, `.flac`, `.webm`), video (`.mp4`, `.mov`, `.mkv`, `.webm`), and images (`.png`, `.jpg`, `.jpeg`, `.webp`, `.tiff`, `.tif`), with browser MIME alias normalization, Office archive ZIP-bomb/macro rejection, SHA-256 deduplication scoped per user (personal library) or per project (shared workspace), and retry/replacement of failed uploads.
  - **Dual Ingestion Backends**:
    - **Full Local Stack (`DOCUMENT_INGESTION_BACKEND=docling`)**: Default Docling + LlamaIndex `Document` / `HybridChunker` normalization (`DOCUMENT_CHUNK_MAX_TOKENS=512`), preserving page ranges, sections, tables, and captions, while skipping OCR on PDFs that already have a selectable text layer (`DOCLING_OCR_MODE=auto`).
    - **Zero-RAM Lite Cloud Stack (`DOCUMENT_INGESTION_BACKEND=legacy`)**: Designed for 512 MB+ free-tier containers (`backend/requirements-prod-lite.txt` without `torch`, `docling`, `llama-index`, or `sentence-transformers`). Extracts digital PDFs with `pypdf`, performs **selective Gemini Flash scanned-PDF OCR fallback** (`find_scanned_pdf_pages` + compact `slice_pdf_pages` batches), and parses `.docx` (heading- and table-aware `python-docx`), `.pptx` (`python-pptx`), `.xlsx` (`openpyxl`), and `.html` (BeautifulSoup) in low memory (plus internal `.txt` parsing in `LegacyPdfIngestionAdapter`).
  - **Audio, Video, Vision & URLs**: Groq Whisper (`whisper-large-v3-turbo`, 25 MB limit) with automatic Gemini Flash (`gemini-3.8-flash`) audio fallback (up to 15 MB); FFmpeg mono 16 kHz audio extraction + up to `VIDEO_MAX_FRAMES=3` scene-change keyframes analyzed via Gemini Vision (`inspect_image_for_vision` filters blank/small/solid banners); YouTube transcripts (`YouTubeIngestionAdapter`); and public web pages (`r.jina.ai` keyless Reader + BeautifulSoup SSRF-guarded fallback).
- **Controlled Discovery & Background Auto-Discovery**:
  - Keyless parallel discovery across **OpenAlex**, **Crossref**, **arXiv**, **Wikipedia**, and **reputable news RSS feeds** (Bing News + Google News RSS filtered to verified outlets such as Reuters, AP News, BBC, The Guardian, Al Jazeera, NYT, Washington Post, WSJ, FT, The Economist, Bloomberg, NPR, PBS, The Hindu, Indian Express, CFR, Chatham House, Foreign Affairs, Crisis Group, DW, France 24).
  - Conversational query distillation (`distill_search_query`), parallel querying across `all`, `scholarly`, and `web` scopes, DOI/title deduplication, trust-tier classification (`peer-reviewed`, `preprint`, `institutional`, `official-documentation`), library match annotation (`already_in_library`), concurrent media prefetch, and SSRF-safe ingestion ladder (Open-Access PDF full text → MediaWiki section extraction / public web article → verified curated abstract fallback).
  - Background auto-discovery (`autoDiscover: true` on `POST /research/jobs`): searches, interleaves diverse news/encyclopedia/scholarly sources (for `discoveryScope="all"`), imports, and attaches sources inside the worker so starting research never waits on network extraction. Inside projects, editors/owners can also toggle **Also find sources online** (`ProjectResearchPanel` + `projectDiscovery.ts`) to discover and add up to `PROJECT_DISCOVERY_SOURCE_LIMIT=6` new sources in memory-bounded batches (`PROJECT_DISCOVERY_BATCH_SIZE=2`) directly into the project's Files while reusing existing matches and answering across the full project.
- **Hybrid Retrieval, Adaptive RAG & Report Follow-ups**:
  - **Embeddings**: Local `Qwen/Qwen3-Embedding-0.6B` (1,024-dim, offline-first cache + 256-entry LRU query embedding cache) or **Cloudflare Workers AI** (`@cf/baai/bge-m3`, 1,024-dim, with automatic PostgreSQL full-text fallback if Cloudflare embeddings fail).
  - **Retrieval & Reranking**: Single-round-trip PostgreSQL `pgvector` HNSW cosine similarity + GIN-indexed `tsvector` OR-mode full-text search combined via Reciprocal Rank Fusion (`RRF_K=60`) with collaborator-aware SQL scoping; ranked with `Qwen/Qwen3-Reranker-0.6B`, **Cloudflare Workers AI** (`@cf/baai/bge-reranker-base`, falling back automatically to lexical scoring if quota is exhausted), Jina Reranker, or instant `lexical` scoring.
  - **Adaptive Fast-Path, Plain-English Synthesis, Multi-Section Reports & Citations**: `Quick` (`Low`), `Standard` (`Medium`), and `Deep` (`High`) research depths (`ADAPTIVE_FAST_PATH_ENABLED`, with depth-calibrated technical detail), direct synchronous queries (`POST /research/query`), background research jobs (`POST /research/jobs`), `<evidence>` / `<report_memory>` prompt-injection neutralization, evidence sufficiency checks, plain-English opening takeaways, `##`/`###` multi-section report splitting (`_split_report_sections`) into structured `ReportSection` items + executive `summary`, explicit contradiction-surfacing prompts (attributing competing claims or figures to each source), Markdown table generation & cell-level citation validation, same-`(document_id, page)` citation cluster deduplication, safe frontend Markdown rendering (`SafeMarkdown` tables, 2-level nested lists, `*italic*`, accessible **Competing accounts** and **Not covered in the sources** callouts, superscript `CitationChip` pills), and rich bibliographic citations (authors, publisher, year, DOI, source URL, BibTeX).
  - **Grounded Report Follow-ups (`POST /research/{id}/followups`)**: Persisted Q&A thread on completed reports (`report_followups`), combining bounded compact report memory (~<=1.4k chars of question, summary, and last 2 turns) with focused hybrid retrieval while preserving `[S#]` numbering, consuming **0.25x credit**, attributed per collaborator, and streamed via WebSockets (`followup.created`).
- **Multi-Provider LLM Router, BYOK & Fixed Dual-Window Credits**:
  - Supports local **Ollama** (`qwen3.5:9b` + dynamic detection of installed Ollama models) and an 8-provider cloud catalog (**Gemini**, **OpenRouter**, **Cerebras**, **Mistral**, **Groq**, **OpenAI**, **Claude**, **Grok**) with circuit breakers (`LLM_CIRCUIT_BREAKER_THRESHOLD=3`), sticky failover (including Gemini primary → fallback cooldown), depth-aware timeouts (`12s`/`18s`/`60s`), shared keep-alive HTTP pooling, and optional client-side AI helpers (Puter.js / WebLLM).
  - Encrypted per-user BYOK API keys (`API_KEY_ENCRYPTION_SECRET`, Fernet at rest with key-prefix auto-detection), persisted per-provider custom model selections (`UserModelPreference`), and `local_fallback` toggle.
  - **Fixed Dual-Window Per-Model Credits** (independent of user count): a **3-hour burst bucket** (`LLM_CREDITS_3H_PER_MODEL=20`) and a **2-day pool** (`LLM_CREDITS_2D_PER_MODEL=100`), metered in quarter-credit units (`4` units = 1 full run, `1` unit = 0.25x report follow-up) with atomic reservation, failover provider transfer, and automatic refund on failed or insufficient-evidence runs. User BYOK keys and Local Ollama are unlimited.
- **Cloud Storage, Background Jobs & Observability**:
  - Pluggable `local` or S3-compatible **Cloudflare R2 / Supabase Storage S3 API** (`STORAGE_BACKEND=r2` with configurable `R2_ENDPOINT_URL`, AWS SigV4 path-style requests, local caching, and presigned download URLs via `/documents/{id}/signed-url`).
  - `202 Accepted` background ingestion and `/research/jobs` backed by PostgreSQL `background_jobs` (`FOR UPDATE SKIP LOCKED`, dedicated `worker_threads=1` and `research_worker_threads=2` lanes so questions never wait behind slow uploads, lease heartbeats, and crash recovery) or optional **Celery + Redis** (`QUEUE_BACKEND=celery`).
  - Execution telemetry, Ragas-style RAG evaluation helpers (`observability/evaluation.py`), `/telemetry/summary`, optional Langfuse reporting, `X-Request-ID` structured logs, secure cookies, `Origin`/`Referer` enforcement, CORS rules (`PUT`, `CORS_ORIGIN_REGEX`, loopback support), security headers, streaming `413` body limits, rate limiting, and `validate_production_startup()`.

The production retrieval path requires PostgreSQL with `pgvector` (Neon PostgreSQL or self-hosted). SQLite is kept for fast unit tests and non-retrieval local development.

## Repository layout

```text
backend/app/
  api/
    dependencies.py, router.py, uploads.py
    routes/       api_keys, auth, collaboration, discovery, documents, health, jobs, project_documents, projects, research, ws
  core/           settings, startup validation, errors, logging, middleware, rate limiting, realtime_bus, time
  db/             SQLAlchemy engine, Neon/Supabase pool tuning, migration helpers, and session management
  domain/         enums and framework-neutral contracts (collaboration, documents, ingestion, reports, research, states)
  models/         ORM tables (users, projects, collaboration, documents, research, reports/followups, jobs, api_keys, usage, telemetry)
  providers/      CentralizedLLMRouter and Gemini/OpenRouter/Cerebras/Mistral/Groq/OpenAI/Claude/Grok/Ollama adapters
  schemas/        Pydantic request and response models
  services/
    auth/         cookie sessions, sliding inactivity, Argon2 hashing, Google OAuth, and encrypted BYOK keys
    collaboration/ RBAC access guards, email/link invites, and collaborator management
    discovery/    curated OpenAlex, Crossref, arXiv, Wikipedia, and reputable news RSS connectors + SSRF-safe ingestion
    documents/    upload records, local disk and R2/Supabase S3 storage, SigV4 presigned URLs
    ingestion/    Docling, legacy pypdf + Gemini Flash OCR fallback, python-docx/pptx/xlsx/HTML, audio, video, vision, web, YouTube
    jobs/         PostgreSQL SKIP LOCKED queue, dual-lane background worker, maintenance recovery, Celery option
    observability/ telemetry tracking, dual-window credit ledger, Ragas-style RAG evaluation
    rag/          embeddings, pgvector/FTS/RRF retrieval, reranking, evidence, generation, citations, follow-ups
    realtime/     thread-safe WebSocket RealtimeHub, room presence, and event broadcasting
    research/     projects, research runs, 2–5 word chat titles + backfill, pause/edit-question/retry guards, multi-section reports
  worker.py       standalone background worker entrypoint (`python -m app.worker`)
backend/alembic/  schema migrations (`0001_backend_foundation` through `0022_collaboration_realtime`)
backend/scripts/  model verification utilities and `migrate_supabase_to_neon.py`
backend/tests/    API, RAG, auth, credits, follow-ups, collaboration/WS, discovery, deploy-prep, and Postgres/Docling tests
backend/          `requirements.txt` (full local ML/Docling), `requirements-prod-lite.txt` (512 MB+ cloud), `requirements-dev.txt`
frontend/
  functions/api/[[path]].ts   Cloudflare Pages same-origin HTTP & WebSocket `/api/*` proxy
  src/
    app/          router (`resetKey` ErrorBoundary), Auth, Project, ResearchHistory, SessionDataCache, Toast contexts
    components/   auth, collaboration (`PresenceBar`, `ShareDialog`), common, documents (`SourceDiscoveryDialog`, `LibraryPickerDialog`),
                  landing, layout (`AppLayout`, `AppSidebar`, `SidebarRail`, `TopBar`), projects, research, settings, sources
    hooks/        `useDocumentLibrary`, `useDocumentActions`, `useBackoffPolling`, `useRealtimeRoom`, `useSourceDiscovery`
    lib/          defaultModel, ingestionProgress, modelCatalog, modelCredits, modelErrors, navigation, projectDiscovery, researchDocuments, shortcuts
    pages/        Landing, Login, Register, GoogleAuthComplete, Projects, ProjectWorkspace, JoinInvitePage,
                  NewResearch, ResearchProgress, ResearchReport, Library, Settings, NotFound
    services/     typed API clients and optional client-side AI service
    types/        TypeScript API response contracts
docs/             setup, project structure, and handoff guides
Dockerfile        lite production container image (Python 3.11-slim + FFmpeg + `requirements-prod-lite.txt`)
.env.example / .env.production.example   local development and $0/month cloud deployment templates
```

## Architecture

```text
Authenticated user / collaborator (Owner, Editor, Viewer)
  │
  ├─► File upload (.pdf/.docx/.pptx/.xlsx/.html/audio/video/image), URL (web/YouTube),
  │   or Controlled Discovery (OpenAlex / Crossref / arXiv / Wikipedia / Reputable News RSS)
  │     → SHA-256 user/project deduplication + local disk or Cloudflare R2 / Supabase S3 storage
  │     → 202 Accepted + background_jobs (PostgreSQL SKIP LOCKED or Celery/Redis)
  │     → Worker: Docling/LlamaIndex HybridChunker OR Zero-RAM legacy + Gemini Flash OCR fallback
  │     → Local Qwen3-Embedding-0.6B OR Cloudflare Workers AI `@cf/baai/bge-m3`
  │
  ├─► Research run (`POST /research/jobs` or `/research/query`) & Report follow-ups (`/followups`)
  │     → Optional background auto-discovery + source attachment (`0020`)
  │     → Neon / PostgreSQL (`pgvector` HNSW cosine + GIN `tsvector` FTS + RRF)
  │     → Adaptive Fast-Path: Lexical / Qwen3-Reranker-0.6B / Cloudflare BGE / Jina reranker
  │     → Evidence sufficiency + prompt-injection sanitization + contradiction prompts
  │     → Centralized LLM Router (8 cloud providers + BYOK + 3h/2d credits) or Local Ollama
  │     → Sentence-level [S#] citation validation + persisted report & follow-up Q&A (`0021`)
  │
  └─► Real-time Collaboration (`RealtimeHub` via `/api/v1/ws/projects|research/{id}`)
        → Live presence, document progress, research stage updates, and follow-up turns
```

PostgreSQL remains the single source of truth for vectors, full-text indexes, job state, collaboration membership, credits, user preferences, reports, and follow-ups; LlamaIndex (in full local mode) provides document/node normalization without creating a second vector store.

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

## Production cloud deployment (Lite / Free-Tier Stack)

The repository includes a ready-to-deploy low-RAM cloud setup built around [Dockerfile](Dockerfile), [backend/requirements-prod-lite.txt](backend/requirements-prod-lite.txt), [.env.production.example](.env.production.example), and `frontend/functions/api/[[path]].ts`:

- **Backend Container (`Dockerfile`)**: `python:3.11-slim` with FFmpeg, non-root `appuser`, `/api/v1/health` `HEALTHCHECK`, automatic `alembic upgrade head`, and `uvicorn --proxy-headers --forwarded-allow-ips='*'` serving `backend/requirements-prod-lite.txt` (excludes multi-GB PyTorch/Docling packages to run comfortably in 512 MB RAM).
- **Recommended `$0/month` Cloud Primitives** (see [.env.production.example](.env.production.example)):
  - **Database**: Neon PostgreSQL + `pgvector` (`DATABASE_URL` pooled for runtime, `DATABASE_URL_UNPOOLED` for Alembic DDL migrations).
  - **Ingestion & OCR**: `DOCUMENT_INGESTION_BACKEND=legacy` + `VISION_ENABLED=true` for zero-RAM `pypdf`/`python-docx`/`python-pptx`/`openpyxl` parsing and selective Gemini Flash scanned-PDF OCR fallback.
  - **Embeddings & Reranking**: Cloudflare Workers AI (`EMBEDDING_PROVIDER=cloudflare` with `@cf/baai/bge-m3`, `RERANKER_PROVIDER=cloudflare` with `@cf/baai/bge-reranker-base`, and `ADAPTIVE_FAST_PATH_ENABLED=false` for neural reranking on every query with automatic lexical fallback).
  - **Object Storage**: `STORAGE_BACKEND=r2` pointing at either Cloudflare R2 or Supabase Storage's S3-compatible endpoint (`R2_ENDPOINT_URL`, `R2_REGION`).
  - **Cloudflare Pages Same-Origin `/api` Proxy**: Deploy `frontend/` to Cloudflare Pages with `VITE_API_BASE_URL=/api/v1` and `BACKEND_ORIGIN=https://your-backend-host`, and set `GOOGLE_REDIRECT_URI=https://your-app.pages.dev/api/v1/auth/google/callback`. The Pages Function at `frontend/functions/api/[[path]].ts` forwards both `/api/*` HTTP requests (preserving `Set-Cookie`, OAuth `3xx` redirects, and `CF-Connecting-IP` → `X-Forwarded-For`) and WebSocket upgrades on the same origin, keeping authentication working even when browsers block cross-site cookies.

## Main API areas (`/api/v1`)

- `/auth`: `POST /register`, `POST /login`, `POST /logout`, `POST /logout-all`, `GET /me`, and Google OAuth (`/google/status`, `/google/start`, `/google/callback`).
- `/auth/api-keys`: per-user encrypted BYOK key CRUD (`GET ""`, `PUT /{provider}`, `DELETE /{provider}`), `GET /models-status` (server router + local Ollama models + user preferences + credits snapshot), `GET /usage` (dual-window 3h/2d per-model credits & usage breakdown), `POST /local-fallback`, and `POST /provider-model`.
- `/projects`: shared/private project creation, listing/search/archive filters (with `file_count` and `report_count`), updates (with optimistic `version`), soft archiving (`DELETE /{project_id}`), restore (`POST /{project_id}/restore`), and permanent deletion (`DELETE /{project_id}/permanent`).
- `/documents`: user-scoped upload (`POST`), URL ingestion (`POST /url`), list/filter (`GET` with `search`, `status`, `type`, and `kind`), metadata/delete, inline file streaming (`GET /{id}/file`), R2/S3 presigned downloads (`GET /{id}/signed-url`), `POST /{id}/reembed`, and failed document retry (`POST /{id}/retry`).
- `/projects/{project_id}/documents`: exact project-scoped file upload, URL ingestion (`/url`), and document listing/filtering.
- `/discovery`: `GET /status` (active scopes & providers), `POST /search` (rate-limited cross-provider search with library annotation), and `POST /import` (SSRF-guarded batch ingestion into personal library or project).
- `/research`: research CRUD, project filtering, `PATCH /{id}` (optimistic `version`), `DELETE /{id}` (archive), `POST /{id}/restore`, progress polling (`GET /{id}/status`), pause active runs (`POST /{id}/pause`), edit question & restart in place (`POST /{id}/edit-question`), persisted multi-section reports & follow-ups (`GET /{id}/report`), lightweight grounded report follow-ups (`POST /{id}/followups` at 0.25x credit), raw hybrid retrieval inspection (`POST /retrieve`), grounded synchronous queries (`POST /query`), background research jobs (`POST /jobs`), and in-place retry/resume (`POST /{id}/retry`). Supports scoped `documentIds`, `autoDiscover: true`, and `discoveryScope`.
- **Collaboration & Invites**:
  - `/projects/{project_id}/members` (`GET`, `POST` email invite, `PATCH /{member_user_id}`, `DELETE /{member_user_id}`) and `/projects/{project_id}/invites` (`POST`, `DELETE /{invite_id}`).
  - Matching collaboration endpoints under `/research/{research_id}/members` and `/research/{research_id}/invites`.
  - `/collaboration/invites/{token}` (`GET` preview) and `/collaboration/invites/{token}/accept` (`POST`).
- **WebSockets (`/api/v1/ws`)**: `WS /ws/projects/{project_id}` and `WS /ws/research/{research_id}` for room presence, activity indicators, and live research/document/follow-up/membership events.
- `/jobs/{job_id}` and `/telemetry/summary`: collaborator-aware background job status tracking and pipeline latency/cache/token telemetry.
- `/health`, `/health/live`, and `/health/ready`: liveness and dependency readiness checks (database, `pgvector`, and Ollama or LLM router availability).

Existing records with `project_id = NULL` remain supported. Project-scoped retrieval applies an exact `project_id` SQL filter and excludes null-project, foreign, and archived project documents while supporting collaborator-shared projects and shared research attachments.

## Database schema history (Alembic)

- `0001`–`0006`: core foundation, research runs, documents, progress stages, report sources/citations, and chunk/ingestion metadata.
- `0007`–`0009`: user accounts, sessions, ownership foreign keys, Google OAuth state table, `pgvector` HNSW index, and grounded citation evidence columns.
- `0010`–`0012`: private research projects (`ResearchProject`), project scoping, trigger-maintained `tsvector` + GIN FTS index, and canonical source/node provenance metadata.
- `0013`: persistent `background_jobs` table (`FOR UPDATE SKIP LOCKED`) and lease/heartbeat recovery columns.
- `0014`–`0015`: Neon/multimodal extensions, user BYOK key table, telemetry events, widened `file_type`/`source_type`/`content_level` enums and `CHECK` constraints.
- `0016_model_prefs_usage_quota`: persisted user provider/model preferences (`user_model_preferences`), `local_fallback_enabled` setting, atomic quota/credit ledger (`daily_quota_usage`), and daily usage rollups (`model_usage_daily`).
- `0017_research_documents`: per-research document scope join table and foreign key cascading.
- `0018_research_model_failure` & `0019_document_progress`: persisted model failure diagnostics (`failure_provider`, `failure_model`, `failure_type`) and per-file ingestion step/percentage tracking.
- `0020_research_discovery_scope`: persisted `research.discovery_scope` enabling asynchronous background auto-discovery on queued research jobs.
- `0021_report_followups`: `report_followups` table storing persisted grounded follow-up Q&A turns, citation numbers, ordering, and model metadata on composed reports.
- `0022_collaboration_realtime`: `version` columns for optimistic locking on `research_projects` and `research`, `user_id` attribution on `report_followups`, and `project_members`, `research_members`, and `collaboration_invites` tables.

## Supported vs remaining deferred scope

### Implemented

- Files: PDF (Docling or `pypdf` + Gemini Flash scanned-PDF OCR fallback), DOCX (Docling or zero-RAM `python-docx`), PPTX, XLSX, HTML/HTM, audio (`mp3`, `wav`, `m4a`, `ogg`, `flac`, `webm`), video (`mp4`, `mov`, `mkv`, `webm`), and images (`png`, `jpg`, `jpeg`, `webp`, `tiff`, `tif`). *(Note: `LegacyPdfIngestionAdapter` also parses `.txt` internally, while direct HTTP uploads validate against the extensions above.)*
- URLs & Discovery: YouTube video transcripts, public web articles (SSRF-guarded), and Controlled Discovery across OpenAlex, Crossref, arXiv, Wikipedia, and curated reputable news RSS outlets with automated DOI resolution, trust-tier badges, and Open-Access PDF / full-article / verified-abstract ingestion.
- Grounded Report Follow-ups, Real-Time Multi-User Collaboration (RBAC, email/link invites, WebSocket rooms & presence, optimistic locking), Fixed Dual-Window Per-Model Credits, and Ragas-style RAG evaluation metrics in `observability/evaluation.py`.
- Full local stack (Docling + Qwen3 + Ollama) and `$0/month` lite cloud stack (Docker lite + Neon PostgreSQL + Cloudflare Workers AI + R2/Supabase S3 + Cloudflare Pages same-origin `/api` proxy).

### Deferred

- Direct HTTP file uploads for plain text/Markdown/CSV (`.txt`, `.md`, `.csv`) and structured metadata retrieval filter UI.
- Schema-constrained (strict Pydantic) structured generation and LangGraph multi-agent orchestration.
- Multi-node Redis Pub/Sub fan-out for `RealtimeHub` and shared multi-process (Redis) HTTP rate limiter.
- Full email-verification and outbound SMTP invite-delivery workflow (currently email invites resolve registered accounts directly and return `/join/{token}` invite URLs).

## Pull request evolution

Every PR merged into `main` shaped the system as follows:

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
| **#40–#42** | Neon PostgreSQL + Cloudflare R2 + multimodal parsers + Celery/Redis option + centralized free-tier LLM router & evaluation helpers (`0014`–`0015`, #40); `cryptography`/`pillow` CVE upgrades & Gitleaks CI fix (#41); adaptive RAG fast-path, lexical reranking, query embedding LRU cache, pooled HTTP clients, sticky Gemini fallback, and synchronous quick queries (#42). |
| **#43, #45** | Sliding 3-day inactivity / 7-day max sessions, 8 cloud LLM providers + dynamic Ollama probing, encrypted BYOK keys, persisted model/fallback preferences (`0016`), atomic fair-share quota enforcement, `ModelControlBar`, Settings usage breakdown (#43), and CI Alembic revision ID (`<= 32` chars) + Gitleaks cleanup (#45). |
| **#44** | In-place retry for failed runs (`POST /research/{id}/retry`), 15s duplicate-submission guard, collapsed desktop sidebar icon rail, and pointer/layout polish. |
| **#46** | Fixed login on mixed `localhost`/`127.0.0.1` loopback hosts for `SameSite` cookies and added `PUT` to CORS allowed methods for BYOK API key updates. |
| **#47** | Google OAuth hardening (10s clock-skew leeway, SQLAlchemy rollback on callback errors, disabled-account rejection, explicit error messages, loopback-host `.env.example` note), React navigation/cache stability (`ErrorBoundary` `resetKey`, `SessionDataCacheContext` SWR caching, quiet document reloads, persistent `Ask`/`Documents` tabs), and `README.md` sync. |
| **#48** | Research worker concurrency: dedicated `research-worker` threads (`RESEARCH_WORKER_THREADS=2`) so research never waits behind large uploads, plus OCR skip when PDFs already contain valid digital text. |
| **#49** | Answer quality improvements: list and bold markdown formatting, hybrid passage retrieval boost, prompt grounding, and citation validator preserving grounded citations. |
| **#50** | Per-research document scoping via `research_documents` join table (`0017`), new research starting with zero documents, library picker modal (`LibraryPickerDialog`), and `POST /research/query` + `POST /research/jobs` document scoping. |
| **#51** | Multimodal ingestion fixes: browser MIME aliases (`.mkv`, `.flac`, `.m4a`), PPTX/YouTube/audio/video/vision ingestion pipeline fixes, and upload modal status synchronization. |
| **#52** | Route `/library` rename and dedicated Library view with filters, sidebar route-based active tab highlighting, light/dark theme switch moved to Settings, and project archive/restore/permanent delete. |
| **#54** | Controlled Discovery: keyless curated connectors (OpenAlex, Crossref, arXiv, Wikipedia), parallel search with DOI/title deduplication, SSRF-safe ingestion ladder (OA PDF → web/Wiki → abstract), provenance & coverage badges, opt-in auto-discovery RAG with rich bibliographic citations, and regression test suite. |
| **#55** | UX polish (PR #53 changes merged via #55): model failure diagnostics (`0018`) with "Switch model" recovery, per-file ingestion step & progress bar (`0019`), Library kind filters & usage tags, Settings Models & API keys panel + folded System status, undoable research delete (`POST /research/{id}/restore`), project file/report counts, and consistent `files` UX wording. |
| **#56** | Background auto-discovery (`0020`): moved `autoDiscover` search, import, and source attachment into `execute_research` inside the background job so starting discovery-backed research returns `202` immediately without HTTP timeouts. |
| **#57** | Fixed dual-window per-model credits (3-hour burst + 2-day pool independent of user count) with per-model percentages & renewal timers, persisted grounded report follow-ups (`0021`) using compact memory at `0.25x` credit cost, and discovery query distillation + concurrent source prefetch. |
| **#58** | Multi-user real-time collaboration (`0022`): project & research RBAC (`owner`/`editor`/`viewer`), email & shareable link invites (`/join/{token}`), optimistic concurrency locking (`version`), thread-safe WebSocket `RealtimeHub` (`/ws/projects/{id}`, `/ws/research/{id}`), `ShareDialog`, `PresenceBar`, and live sync for shared runs, uploads, and follow-ups. |
| **#59** | Short sidebar chat titles: deterministic + LLM-refined `<= 3`-word chat titles (`chat_title_llm_enabled`), automatic startup backfill for legacy unedited titles, and full research question display in sidebar tooltips and report headers. |
| **#60** | Production deploy prep: lite `Dockerfile` + `requirements-prod-lite.txt` (excluding heavy local ML dependencies), `.env.production.example` for `$0/month` cloud stack (Neon + Cloudflare Workers AI + Supabase S3/R2 + Gemini/Groq/OpenRouter), Gemini Flash scanned-PDF OCR fallback & zero-RAM `python-docx`/TXT parsing, and `SameSite=None; Secure` cross-origin production cookies. |
| **#61** | Reputable news discovery (curated Bing/Google News RSS connectors with diverse news/encyclopedia/scholarly interleaving), contradiction-surfacing grounding prompts, and PostgreSQL full-text fallback resilience when Cloudflare embeddings are unavailable. |
| **#62** | Cloudflare Pages same-origin `/api/*` proxy (`frontend/functions/api/[[path]].ts`) supporting HTTP & WebSocket upgrades and first-party cookies for Brave Shields, Safari ITP, and Incognito. |
| **#63** | Project online discovery: **"Also find sources online"** switch in project `Ask` panels (persisted per project via `projectDiscovery.ts`), queuing background discovery jobs (`PROJECT_DISCOVERY_SOURCE_LIMIT=6`) that batch-import new trusted sources into the project's Files without re-downloading duplicates and fall back to existing project files if no new matches are found. |

## Validation

```bash
.venv/bin/pytest backend/tests -rs
cd frontend
npm test
npm run typecheck
npx tsc --noEmit -p tsconfig.test.json
npm run lint
npm run build
```

CI ([.github/workflows/ci.yml](.github/workflows/ci.yml)) runs:
1. `backend`: `pytest` unit/API suite under `APP_ENVIRONMENT=test`.
2. `backend-postgres`: PostgreSQL 16 + `pgvector` integration tests (`pytest -m postgres -v`) and `alembic upgrade head && alembic check`.
3. `frontend`: `eslint src --max-warnings=0`, TypeScript app + test typechecks, Vitest suite, and Vite production build.
4. `security`: `pip-audit -r backend/requirements.txt`, `npm audit --omit=dev --audit-level=moderate`, and `gitleaks` secret scanning.

> **PostgreSQL test warning**: Integration tests require a dedicated disposable database whose name contains `test` configured via `POSTGRES_TEST_DATABASE_URL`. Never point it at shared Neon, Supabase, or production databases.

## Product principles

- Evidence comes before explanation.
- Missing metadata and citations are never invented.
- Project, collaborator, and user ownership is enforced in backend queries.
- Insufficient evidence produces an explicit bounded response.
- The assistant supports human research judgment; it does not replace it.

## License

This project is licensed under the terms in [LICENSE](LICENSE).
