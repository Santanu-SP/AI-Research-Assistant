# AI Research Assistant

An evidence-first research workspace for finding, understanding, comparing, and citing academic work.

The project is currently in its foundation stage. The first implementation is a small backend service that gives later search, paper processing, retrieval, and citation features a clear place to grow.

## Product goal

AI Research Assistant is intended for students, researchers, and knowledge workers who need to:

- discover papers from approved scholarly sources
- verify paper metadata independently from generated text
- find legitimate open-access copies or upload PDFs they are allowed to use
- ask questions across one or more processed papers
- compare findings, methods, datasets, limitations, and disagreements
- create research reports with traceable citations
- receive `INSUFFICIENT_EVIDENCE` when the available sources do not support an answer

The core workflow is:

`Discover -> Verify -> Analyze -> Compare -> Synthesize -> Cite`

## MVP scope

Phase 1 covers authentication, private research projects, paper discovery through OpenAlex, DOI verification through Crossref, legal open-access lookup, PDF upload and processing, semantic retrieval, reranking, cited answers, comparison, synthesis, research history, evaluation, and basic report export.

The MVP will support up to 10 ready papers in a single question, comparison, or synthesis request. It will not bypass publisher paywalls or treat unrestricted web content as verified research evidence.

## Current starter

This repository currently contains:

- a FastAPI application factory
- a versioned health endpoint
- environment-based settings
- configurable CORS for the local frontend
- SQLAlchemy 2.x database and session infrastructure
- Alembic migration infrastructure
- persistent research CRUD with filtering, pagination, and soft archiving
- safe PDF upload, metadata extraction, normalization, and page-aware chunk storage
- account registration, login, revocable sessions, and private research/document records
- the main project, paper, and answer states from the PRD
- a small test suite for the initial API contract

Research execution, semantic retrieval, and model providers are not implemented yet. Document chunks intentionally do not contain embeddings until the retrieval phase.

## Local setup

Please see the full developer guide in [docs/development.md](docs/development.md) for prerequisite details, backend setup, and frontend configuration.

## Project structure

Please refer to [docs/project-structure.md](docs/project-structure.md) for a detailed overview of the current architecture and codebase layout.

## API

### Authentication

- `POST /api/v1/auth/register` creates an account.
- `POST /api/v1/auth/login` starts an HTTP-only cookie session.
- `GET /api/v1/auth/me` restores the current user.
- `POST /api/v1/auth/logout` revokes the current session.

Research and document endpoints require a session and return only the current user's records. Existing records created before authentication remain stored without an owner and are hidden from new accounts.

### Health check

`GET /api/v1/health`

Example response:

```json
{
  "status": "ok",
  "service": "ai-research-assistant-api",
  "environment": "development"
}
```

### Research management

- `POST /api/v1/research` creates a draft research record without starting an AI workflow.
- `GET /api/v1/research` lists research with search, domain, status, pagination, and optional archived-record filters.
- `GET /api/v1/research/{research_id}` retrieves an active research record.
- `PATCH /api/v1/research/{research_id}` updates supported metadata or its summary status.
- `DELETE /api/v1/research/{research_id}` soft-archives the record.

### Document management

- `POST /api/v1/documents` validates, stores, extracts, normalizes, and chunks one PDF upload.
- `GET /api/v1/documents` lists document metadata with search, status, type, and pagination filters.
- `GET /api/v1/documents/{document_id}` retrieves document metadata without exposing its storage path.
- `GET /api/v1/documents/{document_id}/file` opens an owned PDF in the browser.
- `DELETE /api/v1/documents/{document_id}` removes the stored file and metadata.

Uploaded files are stored under `DOCUMENT_UPLOAD_DIR` and are ignored by Git. The default maximum upload size is 25 MiB. Page-aware chunks and available PDF metadata are persisted; missing metadata remains null. Chunk size and overlap are controlled by `DOCUMENT_CHUNK_SIZE` and `DOCUMENT_CHUNK_OVERLAP`.

## Product principles

- Evidence comes before explanation.
- Papers, citations, and missing metadata must never be invented.
- Important factual claims should link back to stored evidence.
- Disagreement between sources should remain visible.
- Research gap suggestions are hypotheses, not facts.
- AI providers and retrieval components should remain replaceable.
- Evaluation scores must come from real test cases and calculations.
- The assistant supports human research judgment. It does not replace it.

## Planned delivery

1. Project and user foundations
2. OpenAlex discovery and Crossref metadata verification
3. PDF upload, extraction, chunking, and indexing
4. Evidence retrieval, reranking, answers, and citations
5. Comparison, synthesis, reports, and evaluation

## License

This project is licensed under the terms in [LICENSE](LICENSE).
