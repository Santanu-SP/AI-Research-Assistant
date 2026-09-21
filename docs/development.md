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

Authentication uses random, database-backed session tokens in HTTP-only cookies. No static signing secret is needed. Sessions expire after `AUTH_SESSION_DAYS` (default 7). Set `AUTH_COOKIE_SECURE=true` when serving the API over HTTPS. For local development, use `localhost` for both the frontend and backend so the browser sends the session cookie. Existing document and research rows remain in the database after migration but have no owner; new accounts cannot see them.

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
This sets `VITE_API_BASE_URL` to point to the local backend.

4. **Running the Development Server:**
```bash
npm run dev
```

## Default Local URLs
- **Backend API Documentation (Swagger)**: http://127.0.0.1:8000/docs
- **Backend API Base**: http://127.0.0.1:8000/api/v1
- **Frontend Application**: http://localhost:3000

## Testing & Validation

**Running Backend Tests:**
From the root repository (with the virtual environment activated):
```bash
pytest
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

**Running Frontend Production Build:**
To verify the production build locally (from the `frontend/` directory):
```bash
npm run build
```
