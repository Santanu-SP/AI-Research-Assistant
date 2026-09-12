# Project Structure Guide

## Current Project Status
The project is currently in its foundational stage. The implemented features include:
- **Backend Foundation**: FastAPI application factory, environment-based settings, SQLAlchemy/Alembic setup, CORS configuration, and a health endpoint.
- **Research Management API**: Persistent CRUD operations for research records.
- **Document Management API**: Local document upload (PDF, DOCX, TXT) and metadata management.
- **React Frontend**: Setup with Vite, TypeScript, TailwindCSS, and basic routing.

*Note: The following features are intentionally future work and are **not yet implemented**:*
- Document content extraction, chunking, and indexing
- Research execution pipeline
- Evidence retrieval, reranking, and GenAI/RAG models
- Answers, synthesis, and citation generations
- Reports and evaluation metrics
- Authentication

## Repository Directories

### Backend
The backend follows a domain-driven structure located in the `backend/` directory:

- `backend/app/api/`: Contains FastAPI route definitions and endpoints (e.g., for research and documents).
- `backend/app/core/`: Application-wide settings, configuration, and dependencies.
- `backend/app/db/`: SQLAlchemy engine, session management, and the declarative base for models.
- `backend/app/domain/`: Shared domain logic, enums, and product states.
- `backend/app/models/`: SQLAlchemy ORM models representing persisted database tables.
- `backend/app/schemas/`: Pydantic models for API request validation and response serialization.
- `backend/app/services/`: Business logic layer connecting routes with models/database.
- `backend/tests/`: Backend test suite using pytest.

*(Additional folders like `backend/alembic/` exist for database migrations, and `backend/data/` for local SQLite storage and document uploads.)*

### Frontend
The frontend is located in the `frontend/` directory and follows a feature/component-based architecture:

- `frontend/src/app/`: Application-level routing or core shell components.
- `frontend/src/components/`: Reusable UI components used across different pages.
- `frontend/src/data/`: Local data constants or mock data.
- `frontend/src/pages/`: Top-level page components representing different views in the app.
- `frontend/src/services/`: API client functions to communicate with the backend.
- `frontend/src/types/`: TypeScript type definitions and interfaces.
