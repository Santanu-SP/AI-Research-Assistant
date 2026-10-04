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
  sufficiency checks, citation-ID allowlisting, and persisted reports.

The production retrieval path requires PostgreSQL with pgvector. SQLite is
kept for ordinary unit tests and non-retrieval development workflows.

## Architecture

```text
Authenticated user and optional owned project
  → PDF/DOCX validation and SHA-256 duplicate check
  → Docling
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

- `/api/v1/auth`: registration, login, logout, session restoration, and Google
  OAuth when configured.
- `/api/v1/projects`: private project creation, listing, updates, and archiving.
- `/api/v1/documents`: compatibility upload/list/read/delete operations across
  the authenticated user's documents.
- `/api/v1/projects/{project_id}/documents`: exact project-scoped PDF/DOCX
  upload and listing.
- `/api/v1/research`: research CRUD, project filters, progress, reports, hybrid
  retrieval inspection, and grounded query execution.

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
- strict structured generation and stronger citation validation
- LangGraph orchestration, Ragas evaluation, and background job infrastructure

## Validation

```bash
pytest backend/tests
cd frontend
npm test -- --run
npm run typecheck
npm run lint
npm run build
```

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
