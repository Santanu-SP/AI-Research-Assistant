# Frontend

React 19 application for the research assistant. It talks to the FastAPI backend through cookie sessions. There is no mock API layer.

## Setup

From this directory:

```bash
npm install
cp .env.example .env
npm run dev
```

The dev server listens on http://localhost:3000 (127.0.0.1 only). To open it from another device, run `VITE_DEV_HOST=0.0.0.0 npm run dev` and set `CORS_ALLOW_LOCAL_NETWORK=true` for the backend.

Leave `VITE_API_BASE_URL` empty for local work. The client then calls port 8000 on the same hostname as the page, which keeps a private-network URL on one host. Set the variable only when the API lives somewhere else.

Start the API from the repository root with:

```bash
uvicorn app.main:app --app-dir backend --reload
```

## Scripts

```bash
npm test
npm run typecheck
npm run lint      # eslint with react-hooks rules; CI uses --max-warnings=0
npm run build
```

`docker build -t ara-web .` builds the nginx image (see `Dockerfile` and `nginx.conf`).

## Layout

```text
src/
  app/          router, auth, selected project, toasts
  components/   shared UI, landing page, and feature panels
  pages/        one screen per route
  services/     fetch wrappers for auth, projects, documents, research, reports
  hooks/        project document loading and polling with backoff
  types/        API response types
  test/         Vitest setup, fixtures, and component tests
```

Routes worth knowing:

- `/` landing page
- `/login` and `/register`
- `/projects` and `/projects/:projectId`
- `/research`, `/research/new`, `/research/:id`, `/research/:id/progress`
- `/documents`

Authenticated requests send the session cookie. The API base URL is resolved in `src/services/api.ts`; it may be absolute or a same-origin path such as `/api/v1` (the Docker image).

Every request has a timeout (30 s by default, 5 minutes for uploads and inline answers). Errors are read from the backend envelope `{ "error": { "code", "message", "details" } }`. Signed-in pages are code-split with `React.lazy` and wrapped in an error boundary that resets on navigation.

Uploads return `202 Accepted` while the server indexes the file. Lists poll with backoff (2 s doubling to 30 s) and stop after 15 minutes with a "Refresh now" link. Failed documents have a Retry action. New research starts a background run and opens its progress page.
