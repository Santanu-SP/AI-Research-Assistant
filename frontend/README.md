# Frontend

React 19 application for the research assistant. It talks to the FastAPI backend through cookie sessions. There is no mock API layer.

## Setup

From this directory:

```bash
npm install
cp .env.example .env
npm run dev
```

The dev server listens on http://localhost:3000.

Leave `VITE_API_BASE_URL` empty for local work. The client then calls port 8000 on the same hostname as the page, which keeps a private-network URL on one host. Set the variable only when the API lives somewhere else.

Start the API from the repository root with:

```bash
uvicorn app.main:app --app-dir backend --reload
```

## Scripts

```bash
npm test
npm run typecheck
npm run lint
npm run build
```

## Layout

```text
src/
  app/          router, auth, selected project, toasts
  components/   shared UI, landing page, and feature panels
  pages/        one screen per route
  services/     fetch wrappers for auth, projects, documents, research, reports
  hooks/        project document loading and polling
  types/        API response types
  test/         Vitest setup, fixtures, and component tests
```

Routes worth knowing:

- `/` landing page
- `/login` and `/register`
- `/projects` and `/projects/:projectId`
- `/research`, `/research/new`, `/research/:id`, `/research/:id/progress`
- `/documents`

Authenticated requests send the session cookie. The API base URL is resolved in `src/services/api.ts`.
