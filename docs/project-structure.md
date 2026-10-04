# Project Structure Guide

## Current status

The repository contains a working local RAG application with authentication,
private projects, PDF/DOCX ingestion, PostgreSQL hybrid retrieval, Qwen models,
Ollama generation, citations, reports, and a React frontend.

## Backend

- `backend/app/api/`: authenticated FastAPI routes and dependencies.
- `backend/app/core/`: settings, error handling, and shared time helpers.
- `backend/app/db/`: SQLAlchemy engine, sessions, base classes, and database
  types.
- `backend/app/domain/`: stable enums and framework-neutral domain contracts.
- `backend/app/models/`: SQLAlchemy users, projects, documents, research, and
  report models.
- `backend/app/schemas/`: Pydantic request and response contracts.
- `backend/app/services/`: authentication, project/document lifecycle,
  Docling/LlamaIndex ingestion, embeddings, retrieval, reranking, evidence,
  generation, citations, and reports.
- `backend/alembic/`: migrations through `0012_canonical_document_metadata`.
- `backend/tests/`: unit/API tests plus opt-in Docling and PostgreSQL
  integration tests.
- `backend/scripts/`: manual local model smoke tests.
- `backend/data/`: ignored local SQLite files and uploads; only `.gitkeep` is
  versioned.

## Frontend

- `frontend/src/app/`: routing, authentication context, and application shell.
- `frontend/src/components/`: shared UI, research, source, document, and layout
  components.
- `frontend/src/pages/`: authentication, document, research, progress, report,
  and landing pages.
- `frontend/src/services/`: typed API clients.
- `frontend/src/types/`: backend-aligned TypeScript contracts.
- `frontend/src/data/`: deliberate static product content such as suggested
  research questions.

## Data flow

```text
FastAPI route
→ ownership-aware service
→ Docling and LlamaIndex ingestion or custom RAG orchestration
→ SQLAlchemy
→ PostgreSQL/pgvector/FTS
→ typed API response
→ React service and page
```

LlamaIndex is limited to document and node standardization. PostgreSQL remains
the only persisted vector and keyword retrieval store.

## Deferred areas

Multi-format expansion beyond PDF/DOCX, web and scholarly source ingestion,
advanced filters, strict structured generation, stronger citation validation,
LangGraph, Ragas, and background jobs are intentionally outside this branch.
